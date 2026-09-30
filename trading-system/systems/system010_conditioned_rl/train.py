"""Walk-forward PPO inside the region: train only where R holds, trade only where R holds.

The operator, 2026-09-30: *"when training, we will only train when those criteria are met,
and when executing we will only execute when they are met."* The region is the oracle's
(`region.py`, the densest conditions holding the target share of the top-20% swings, widened
until the availability rule passes - >=70% of days tradeable, no gap over 40 days). Every
episode starts inside it; the policy may only open a position inside it.

Two exams, each with its own region and its own policy, nothing seen twice:

    exam 2024:  region + policy fitted on <= 2022, checkpoint chosen on 2023, read on 2024
    exam 2025:  region + policy fitted on <= 2023, checkpoint chosen on 2024, read on 2025

Four seeds per exam, the spread reported. Every reported number comes from the three-slot
book (`research/system10/tools/conditions.book_year`), never from the training environment.
The same book, with the region's naive entry and a fixed exit, is the baseline the policy
has to beat on the same years.

Compute: the tape lives on the GPU in float16 and the policy is a two-layer MLP; one fold
uses well under 1 GB, so this shares the card with 06's autoloop rather than braking it.
No 2026 bar is ever loaded.

Run from the repo root:
    PYTHONPATH="trading-system;trading-system/systems;backtester;live-trading" \
        python -m system010_conditioned_rl.train --coverage 0.9
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from . import region as R
from .env import BatchEnv, build_tape
from .policy import Policy

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "research/system10"
SEEDS = (77101, 77102, 91002, 51015)
EXAMS = ((2024, 2023), (2025, 2024))     # (test year, selection year)
HORIZON = 384
QUANTILE = 0.2


def _tools():
    sys.path.insert(0, str(OUT / "tools"))
    import conditions as C  # noqa: WPS433
    import availability as A  # noqa: WPS433
    return C, A


def fit_region(per: dict, last_train_year: int, coverage: float):
    _, A = _tools()
    X, zone, sid, n_best, floor = A.fold_inputs(per, last_train_year + 1)
    return R.fit(X, zone, sid, n_best, coverage=coverage,
                 fitted_on=range(2017, last_train_year + 1), quantile=QUANTILE, net_floor=floor)


@torch.no_grad()
def run_policy(policy: Policy, per: dict, inside: dict, year: int, mean, std, device) -> dict:
    """The policy stepped through one whole year, all symbols in parallel: wants-long per bar."""
    syms = [s for s in per if (per[s]["year"] == year).any()]
    cols = []
    for s in syms:
        sel = per[s]["year"] == year
        X = np.nan_to_num(np.clip((per[s]["X"][sel] - mean) / std, -5, 5), nan=0.0)
        cols.append((s, sel, X, np.log(np.maximum(per[s]["close"][sel], 1e-12)), inside[s][sel]))
    T = max(len(c[3]) for c in cols)
    S = len(cols)
    Xt = torch.zeros(T, S, cols[0][2].shape[1], device=device)
    lp = torch.zeros(T, S, device=device)
    ins = torch.zeros(T, S, dtype=torch.bool, device=device)
    live = torch.zeros(T, S, dtype=torch.bool, device=device)
    for j, (_, _, X, logp, inn) in enumerate(cols):
        n = len(logp)
        Xt[:n, j] = torch.tensor(X, dtype=torch.float32, device=device)
        lp[:n, j] = torch.tensor(logp, dtype=torch.float32, device=device)
        ins[:n, j] = torch.tensor(inn, device=device)
        live[:n, j] = True
    pos = torch.zeros(S, device=device)
    entry = torch.zeros(S, device=device)
    held = torch.zeros(S, device=device)
    out = torch.zeros(T, S, dtype=torch.bool, device=device)
    for t in range(T):
        inside_t = ins[t].float()
        unreal = torch.where(pos > 0, lp[t] - entry, torch.zeros_like(pos))
        obs = torch.cat([Xt[t], torch.stack([pos, unreal * 10.0, held / 96.0, inside_t], 1)], 1)
        mask = torch.stack([torch.ones(S, dtype=torch.bool, device=device), (pos > 0) | ins[t]], 1)
        a = policy.act(obs, mask).float() * live[t].float()
        entry = torch.where((a > 0) & (pos == 0), lp[t], entry)
        held = torch.where(a > 0, held + 1, torch.zeros_like(held))
        pos = a
        out[t] = a > 0
    wants = {s: np.zeros(len(per[s]["X"]), dtype=bool) for s in per}
    arr = out.cpu().numpy()
    for j, (s, sel, _, logp, _) in enumerate(cols):
        idx = np.flatnonzero(sel)
        wants[s][idx] = arr[: len(idx), j]
    return wants


def score(per, wants, year, band, risk) -> dict:
    C, _ = _tools()
    r = C.book_year(per, wants, year, band, risk, keep=wants)
    r.pop("daily", None)
    return r


def train_one(per, band, risk, reg, last_train_year, select_year, seed, device,
              updates: int, n_envs: int, steps: int, lam: float, log) -> dict:
    torch.manual_seed(seed)
    np.random.seed(seed)
    inside = {s: reg.holds(d["X"]) for s, d in per.items()}
    pieces = []
    for s, d in per.items():
        tr = d["year"] <= last_train_year
        if tr.sum() > HORIZON + 10:
            pieces.append({"X": d["X"][tr], "close": d["close"][tr], "inside": inside[s][tr]})
    pooled = np.concatenate([p["X"] for p in pieces])
    mean = np.nanmean(pooled, axis=0)
    std = np.nanstd(pooled, axis=0) + 1e-8
    del pooled
    tape = build_tape(pieces, mean, std, HORIZON, device)
    env = BatchEnv(tape, n_envs, lam, seed)
    policy = Policy(tape.obs_dim).to(device)
    opt = torch.optim.Adam(policy.parameters(), lr=3e-4)
    gamma, lam_gae, clip, epochs, mb = 0.995, 0.95, 0.2, 4, 16_384

    best = {"q": -1e9}
    t0 = time.time()
    for u in range(1, updates + 1):
        obs_b, mask_b, act_b, logp_b, val_b, rew_b, done_b = [], [], [], [], [], [], []
        with torch.no_grad():
            for _ in range(steps):
                obs, mask = env.observe()
                dist, v = policy(obs, mask)
                a = dist.sample()
                r, d = env.step(a)
                obs_b.append(obs); mask_b.append(mask); act_b.append(a)
                logp_b.append(dist.log_prob(a)); val_b.append(v); rew_b.append(r); done_b.append(d)
            _, v_last = policy(*env.observe())
        rew = torch.stack(rew_b); done = torch.stack(done_b).float(); val = torch.stack(val_b)
        adv = torch.zeros_like(rew)
        gae = torch.zeros(n_envs, device=device)
        for k in reversed(range(steps)):
            nxt = v_last if k == steps - 1 else val[k + 1]
            delta = rew[k] + gamma * nxt * (1 - done[k]) - val[k]
            gae = delta + gamma * lam_gae * (1 - done[k]) * gae
            adv[k] = gae
        ret = (adv + val).flatten()
        obs_f = torch.cat(obs_b); mask_f = torch.cat(mask_b); act_f = torch.cat(act_b)
        logp_f = torch.cat(logp_b); adv_f = adv.flatten()
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
        if u % 25 == 0 or u == updates:
            wants = run_policy(policy, per, inside, select_year, mean, std, device)
            s = score(per, wants, select_year, band, risk)
            long_share = float(act_f.float().mean())
            log(f"    seed {seed} update {u}/{updates} [{(time.time() - t0) / 60:.1f}m] "
                f"mean reward {float(rew.mean()):+.3f}bps long {long_share:.0%} | "
                f"{select_year}: {s['return']:+.1%} dd {s['max_dd']:.0%} Q {s['q']:+.3f} {s['trades']} trades")
            if s["q"] > best["q"]:
                best = {"q": s["q"], "update": u, "select": s,
                        "state": {k: v.detach().clone() for k, v in policy.state_dict().items()}}
    policy.load_state_dict(best["state"])
    return {"policy": policy, "mean": mean, "std": std, "inside": inside, "best": best}


def main() -> int:
    ap = argparse.ArgumentParser(description="S10-7/8: PPO inside the oracle's region")
    ap.add_argument("--coverage", type=float, default=0.9)
    ap.add_argument("--updates", type=int, default=150)
    ap.add_argument("--envs", type=int, default=4096)
    ap.add_argument("--steps", type=int, default=128)
    ap.add_argument("--lam", type=float, default=1.0)
    ap.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    C, _ = _tools()
    stamp = f"{datetime.now(timezone.utc):%Y-%m-%d}"
    tape_path = OUT / "rnd" / f"ppo_progress_{stamp}.jsonl"

    def log(msg: str) -> None:
        print(msg, flush=True)

    data = C.load(C.ENGINE)
    per, band, risk = data["per"], data["band"], data["risk"]
    results = {}
    for test_year, select_year in EXAMS:
        last = select_year - 1
        reg = fit_region(per, last, args.coverage)
        log(f"exam {test_year}: region fitted on <= {last} ({len(reg.leaves)} leaves, "
            f"{reg.train_bar_share:.0%} of training bars, {reg.train_swing_coverage:.0%} of best swings)")
        inside = {s: reg.holds(d["X"]) for s, d in per.items()}
        naive = {y: C.book_year(per, inside, y, band, risk) for y in (select_year, test_year)}
        for y in naive:
            naive[y].pop("daily", None)
        log(f"  baseline (enter anywhere in R, fixed exit): {select_year} {naive[select_year]['return']:+.1%}"
            f" dd {naive[select_year]['max_dd']:.0%} | {test_year} {naive[test_year]['return']:+.1%}"
            f" dd {naive[test_year]['max_dd']:.0%}")
        exam = {"region_rules": reg.rules(), "baseline": naive, "seeds": {}}
        for seed in args.seeds:
            fit = train_one(per, band, risk, reg, last, select_year, seed, device,
                            args.updates, args.envs, args.steps, args.lam, log)
            wants = run_policy(fit["policy"], per, fit["inside"], test_year, fit["mean"], fit["std"], device)
            test = score(per, wants, test_year, band, risk)
            row = {"exam": test_year, "seed": seed, "coverage": args.coverage, "lam": args.lam,
                   "chosen_update": fit["best"]["update"], "select": fit["best"]["select"],
                   "test": test, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            exam["seeds"][seed] = row
            with tape_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            log(f"  seed {seed}: chosen at update {fit['best']['update']} -> {test_year}: "
                f"{test['return']:+.1%} dd {test['max_dd']:.0%} Q {test['q']:+.3f} {test['trades']} trades")
            torch.save({"state": fit["policy"].state_dict(), "mean": fit["mean"], "std": fit["std"]},
                       OUT / f"_auto_policy_{test_year}_{seed}.pt")
        results[test_year] = exam
    tag = "-".join(str(s) for s in args.seeds)
    path = OUT / "rnd" / f"ppo_exams_{stamp}_cov{int(args.coverage * 100)}_{tag}.json"
    path.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    log(f"written {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
