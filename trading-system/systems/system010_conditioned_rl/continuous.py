"""The 24/7 trainer: one frozen filter, a policy that keeps learning, a 2026 reading every 5 h.

The operator, 2026-10-01: *"we train until January 2026 and use 2026 to do a forward testing
until today... train the model continuously 24 hours a day, 7 days a week... every 5 hours a
forward testing... register it in time... I need graphic evidence in the frontend."*

    1. THE FILTER, frozen once. The oracle's region fitted on 2017-2025 (top-20% swings,
       coverage 0.9, which passes the availability rule: >=97% of days tradeable, no pause
       over 3 days). Saved as `research/system10/region.pkl` and printed as rules in
       `region_rules.json`. Training episodes start only inside it; the policy may open a
       position only inside it, in training, in the forward test, and live. Same object.
    2. THE POLICY, never finished. PPO on episodes from 2017-2025, warm-started from its
       own last checkpoint after a restart, so hours of training accumulate.
    3. THE READING, every `--every-hours`. The current policy through the three-slot book
       on 2025 (in-sample, for reference) and on 2026-01-01 to the last closed bar
       (forward). One line per reading in `rnd/forward_log.jsonl`; the model card the
       dashboard draws is rewritten from that log.

**2026 is observed, never chosen on.** This departs from the laboratory's one-reading rule
on the operator's explicit instruction, and the price of that is contained here: no
reading changes what is trained, which checkpoint continues, or which is exported. The
curve is evidence of whether more training helps, not a selector - the moment a checkpoint
is *picked* for its 2026 number, 2026 stops being a forward test.

Brake: `research/system10/STOP_S10` stops the loop at the next reading.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from . import train as T
from .env import BatchEnv, build_tape
from .features import FEATURE_HASH
from .policy import Policy

OUT = T.OUT
LOG = OUT / "rnd" / "forward_log.jsonl"
CARD = OUT / "model_card.json"
STOP = OUT / "STOP_S10"
COVERAGE = 0.9
LAST_TRAIN_YEAR = 2025
FORWARD_YEAR = 2026


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def frozen_region(per: dict):
    path = OUT / "region.pkl"
    if path.is_file():
        return pickle.loads(path.read_bytes())
    reg = T.fit_region(per, LAST_TRAIN_YEAR, COVERAGE)
    path.write_bytes(pickle.dumps(reg))
    (OUT / "region_rules.json").write_text(json.dumps({
        "fitted_at": _now(), "fitted_on": "2017-08 to 2025-12-31", "coverage_target": COVERAGE,
        "quantile": T.QUANTILE, "feature_hash": FEATURE_HASH,
        "train_bar_share": round(reg.train_bar_share, 4),
        "train_swing_coverage": round(reg.train_swing_coverage, 4),
        "rules": reg.rules()}, indent=1), encoding="utf-8")
    return reg


def curve(per, wants, year, band, risk) -> tuple[dict, list]:
    C, _ = T._tools()
    r = C.book_year(per, wants, year, band, risk, keep=wants)
    daily = r.pop("daily")
    eq = list(np.round(np.cumprod(1 + np.asarray(daily)) * 100_000.0, 2))
    return r, eq


def write_card(lineage: str, state: dict, baseline: dict) -> None:
    rows = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()] if LOG.is_file() else []
    card = json.loads(CARD.read_text(encoding="utf-8")) if CARD.is_file() else {}
    card.update({
        "system": "system10", "family": "system10-conditioned-rl", "system_type": "ai-model",
        "status": "training (continuous)", "updated_at": _now(),
        "walk_forward": {"trained_through": LAST_TRAIN_YEAR, "forward_window": "2026-01-01 to today",
                         "note": "2026 is observed every reading, never used to choose a checkpoint"},
        "region": json.loads((OUT / "region_rules.json").read_text(encoding="utf-8")),
        "forward_baseline": baseline,
        "forward_history": [{k: r[k] for k in ("at", "lineage", "cycle", "train_hours", "updates",
                                                "env_steps", "in_sample_2025", "forward_2026")}
                            for r in rows],
    })
    card.setdefault("lineages", {})[lineage] = state
    CARD.write_text(json.dumps(card, indent=1, default=str), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 continuous trainer with a 2026 forward reading")
    ap.add_argument("--seed", type=int, default=77101)
    ap.add_argument("--every-hours", type=float, default=5.0)
    ap.add_argument("--envs", type=int, default=8192)
    ap.add_argument("--steps", type=int, default=128)
    ap.add_argument("--lam", type=float, default=1.0)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    lineage = f"seed-{args.seed}"
    ckpt = OUT / f"_auto_continuous_{lineage}.pt"
    C, _ = T._tools()

    print(f"[{_now()}] loading 2017 to today (2026 for the forward reading only)", flush=True)
    data = C.load(C.ENGINE, include_sealed=True)
    per, band, risk = data["per"], data["band"], data["risk"]
    reg = frozen_region(per)
    inside = {s: reg.holds(d["X"]) for s, d in per.items()}
    print(f"[{_now()}] frozen region: {len(reg.leaves)} leaves, "
          f"{reg.train_swing_coverage:.0%} of best swings, {reg.train_bar_share:.0%} of bars", flush=True)

    base26, _ = curve(per, inside, FORWARD_YEAR, band, risk)
    baseline = {"naive_region_2026": base26}

    pieces = []
    for s, d in per.items():
        tr = d["year"] <= LAST_TRAIN_YEAR
        if tr.sum() > T.HORIZON + 10:
            pieces.append({"X": d["X"][tr], "close": d["close"][tr], "inside": inside[s][tr]})
    pooled = np.concatenate([p["X"] for p in pieces])
    mean, std = np.nanmean(pooled, axis=0), np.nanstd(pooled, axis=0) + 1e-8
    del pooled
    tape = build_tape(pieces, mean, std, T.HORIZON, device)
    del pieces

    torch.manual_seed(args.seed)
    policy = Policy(tape.obs_dim).to(device)
    opt = torch.optim.Adam(policy.parameters(), lr=3e-4)
    state = {"updates": 0, "env_steps": 0, "train_seconds": 0.0, "cycle": 0}
    if ckpt.is_file():
        saved = torch.load(ckpt, map_location=device, weights_only=False)
        policy.load_state_dict(saved["policy"])
        opt.load_state_dict(saved["opt"])
        state = saved["state"]
        print(f"[{_now()}] resumed {lineage}: {state['updates']} updates, "
              f"{state['train_seconds'] / 3600:.1f} h trained", flush=True)
    env = BatchEnv(tape, args.envs, args.lam, args.seed + state["updates"])
    gamma, lam_gae, clip, epochs, mb = 0.995, 0.95, 0.2, 4, 16_384

    # A fresh lineage reads once before it has learned anything, so the chart starts from
    # the untrained policy rather than from the first five hours.
    budget = 0.0 if state["updates"] == 0 else args.every_hours * 3600
    while not STOP.exists():
        started = time.time()
        rewards = []
        while time.time() - started < budget and not STOP.exists():
            obs_b, mask_b, act_b, logp_b, val_b, rew_b, done_b = [], [], [], [], [], [], []
            with torch.no_grad():
                for _ in range(args.steps):
                    obs, mask = env.observe()
                    dist, v = policy(obs, mask)
                    a = dist.sample()
                    r, d = env.step(a)
                    obs_b.append(obs); mask_b.append(mask); act_b.append(a)
                    logp_b.append(dist.log_prob(a)); val_b.append(v); rew_b.append(r); done_b.append(d)
                _, v_last = policy(*env.observe())
            rew = torch.stack(rew_b); done = torch.stack(done_b).float(); val = torch.stack(val_b)
            adv = torch.zeros_like(rew)
            gae = torch.zeros(args.envs, device=device)
            for k in reversed(range(args.steps)):
                nxt = v_last if k == args.steps - 1 else val[k + 1]
                delta = rew[k] + gamma * nxt * (1 - done[k]) - val[k]
                gae = delta + gamma * lam_gae * (1 - done[k]) * gae
                adv[k] = gae
            ret = (adv + val).flatten()
            obs_f, mask_f, act_f = torch.cat(obs_b), torch.cat(mask_b), torch.cat(act_b)
            logp_f, adv_f = torch.cat(logp_b), adv.flatten()
            adv_f = (adv_f - adv_f.mean()) / (adv_f.std() + 1e-8)
            n = len(act_f)
            for _ in range(epochs):
                perm = torch.randperm(n, device=device)
                for i in range(0, n, mb):
                    j = perm[i:i + mb]
                    dist, v = policy(obs_f[j], mask_f[j])
                    ratio = torch.exp(dist.log_prob(act_f[j]) - logp_f[j])
                    pg = -torch.min(ratio * adv_f[j], ratio.clamp(1 - clip, 1 + clip) * adv_f[j]).mean()
                    loss = pg + 0.5 * (v - ret[j]).pow(2).mean() - 0.01 * dist.entropy().mean()
                    opt.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
                    opt.step()
            state["updates"] += 1
            state["env_steps"] += args.envs * args.steps
            rewards.append(float(rew.mean()))
        state["train_seconds"] += time.time() - started
        budget = args.every_hours * 3600

        # The reading. Observed, recorded, never used to choose anything.
        w25 = T.run_policy(policy, per, inside, LAST_TRAIN_YEAR, mean, std, device)
        w26 = T.run_policy(policy, per, inside, FORWARD_YEAR, mean, std, device)
        in25, _ = curve(per, w25, LAST_TRAIN_YEAR, band, risk)
        fwd, eq = curve(per, w26, FORWARD_YEAR, band, risk)
        row = {"at": _now(), "lineage": lineage, "cycle": state["cycle"],
               "train_hours": round(state["train_seconds"] / 3600, 2), "updates": state["updates"],
               "env_steps": state["env_steps"],
               "mean_reward_bps": round(float(np.mean(rewards)), 4) if rewards else None,
               "in_sample_2025": in25, "forward_2026": fwd, "forward_equity": eq[::3]}
        state["cycle"] += 1
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        torch.save({"policy": policy.state_dict(), "opt": opt.state_dict(), "state": state,
                    "mean": mean, "std": std, "feature_hash": FEATURE_HASH}, ckpt)
        write_card(lineage, {**state, "last_forward": fwd, "last_in_sample": in25}, baseline)
        print(f"[{_now()}] {lineage} cycle {row['cycle']} ({row['train_hours']:.1f} h, "
              f"{state['updates']} updates): 2025 {in25['return']:+.1%} dd {in25['max_dd']:.0%} | "
              f"2026 fwd {fwd['return']:+.1%} dd {fwd['max_dd']:.0%} Q {fwd['q']:+.3f} "
              f"{fwd['trades']} trades", flush=True)
    print(f"[{_now()}] STOP_S10 present - stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
