"""The position manager: reinforcement learning that only decides when to leave a trade.

The operator, 2026-10-09: *"two models - one that sends the buy signals and another that is
dedicated to managing the position"*, and before that: *"teach it to notice when the market
has turned against it while it has a trade open"*.

The full-trader PPO (rl.py) learned for 56 hours without beating the rules: deciding where
to enter, how much, and when to leave, from one reward, is a large problem. Here the entries
are given - the search's best release opens the trades, walk-forward as always - and the
policy answers one question every 4 hours for each open trade: hold, or close.

    episode   one trade, from a real entry of the signal model (years 2020-2024)
    state     the full market picture at that bar + the trade: unrealised return, time
              held, distance below the trade's best close, its worst dip so far
    actions   0 hold, 1 close
    reward    the trade's 4 h log return while held - 0.15% to close; at the end, minus
              LAMBDA x the trade's maximum drawdown. 06's 16.3% stop and the 768-bar cap
              close it regardless, as they do in the book.
    data      trains on 2020-2023 entries; 2024 is the validation year, 2025 out of sample,
              2026 the forward. (Release 1 trained on 2020-2024 and memorised it: +6.8 per
              trade in training, then 2025 -17.4% against the release's own exit +0.1%.)
    selection every release is booked on 2024 against the release's own exit; the best
              weights so far are kept, and after PATIENCE releases without a better 2024
              the trainer goes back to them at half the step. 2025 and 2026 choose nothing.

Releases every RELEASE_EVERY_S by the clock (research/system10/releases_mgr/); the
evaluator runs each through the same book as the release it manages, against that
release's own exit, on 2025 and 2026.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from . import search as S
from .rl import clean

OUT = S.OUT
MGR_DIR = OUT / "releases_mgr"
CKPT = OUT / "_auto_mgr_checkpoint.pt"
STEP = 16
MAX_STEPS = 48            # 768 bars, the release's own cap
HALF_COST = 0.0015
STOP = 0.163
LAMBDA = 0.5
ENTRY_YEARS = (2020, 2021, 2022, 2023, 2024)   # computed once, cached
TRAIN_YEARS = (2020, 2021, 2022, 2023)
VAL_YEAR = 2024
PATIENCE = 3
RELEASE_EVERY_S = 2 * 3600
N_TRADE = 6               # regime, breadth, unrealised, held, below best, worst dip


class Net(nn.Module):
    def __init__(self, obs_dim: int, hidden: int = 256):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(obs_dim, hidden), nn.Tanh(),
                                  nn.Linear(hidden, hidden), nn.Tanh())
        self.pi = nn.Linear(hidden, 2)
        self.v = nn.Linear(hidden, 1)
        nn.init.zeros_(self.pi.weight)
        nn.init.zeros_(self.pi.bias)

    def forward(self, obs):
        h = self.body(obs)
        return torch.distributions.Categorical(logits=self.pi(h)), self.v(h).squeeze(-1)


def signal_cfg() -> dict:
    """The entries' source: the confirmed champion, else the newest release."""
    champ = S.champion(S.ledger())
    if champ:
        return champ["cfg"]
    return S.releases()[-1]["cfg"]


def entries(world: S.World, cfg: dict, years, device: str) -> dict:
    """Bars where the signal model opens a trade, walk-forward per year, cached on disk."""
    cache = OUT / f"_auto_mgr_entries_{S.cfg_id(cfg)}_{min(years)}_{max(years)}.npz"
    if cache.is_file():
        z = np.load(cache)
        return {s: z[s] for s in z.files}
    g, regime = S.gate(world, cfg)
    out = {s: np.zeros(len(d["X"]), dtype=bool) for s, d in world.per.items()}
    for N in years:
        _, masks, _ = S.signals(world, cfg, N, g, regime, device)
        for s, d in world.per.items():
            out[s] |= masks[s] & (d["year"] == N)
        print(f"[{S._now()}] manager: entries for {N} ready", flush=True)
    np.savez_compressed(cache, **out)
    return out


def trade_state(logp: np.ndarray | torch.Tensor, i0, i):
    """Unrealised, held (in decisions), below best, worst dip - from the decision points
    i0, i0+16, ..., i (the same in training and in the book)."""
    pts = logp[i0:i + 1:STEP]
    run = np.maximum.accumulate(pts)
    return (float(pts[-1] - pts[0]), (i - i0) / STEP / MAX_STEPS,
            float(run[-1] - pts[-1]), float((run - pts).max()))


class Tape:
    def __init__(self, world: S.World, cfg: dict, ent: dict, years, device: str):
        feats = world.full()
        up = world.regime_up(cfg["regime_ma"])
        xs, lps, rg, br, starts, off = [], [], [], [], [], 0
        need = (MAX_STEPS + 1) * STEP + 1
        for s, d in world.per.items():
            n = len(d["X"])
            close = d["close"]
            ok = np.isfinite(close) & (close > 0)
            xs.append(clean(feats[s]).astype(np.float16))
            lps.append(np.log(np.where(ok, close, np.nan)))
            rg.append(up[s].astype(np.float32) * 2 - 1)
            br.append(d["breadth"].astype(np.float32) * 2 - 1)
            sel = ent[s] & np.isin(d["year"], years) & world.valid[s]
            idx = np.flatnonzero(sel)
            starts.append(idx[idx < n - need] + off)
            off += n
        lp = np.concatenate(lps)
        # carry the last price over gaps so a missing bar never reads as a move
        bad = ~np.isfinite(lp)
        if bad.any():
            pos = np.where(~bad, np.arange(len(lp)), 0)
            np.maximum.accumulate(pos, out=pos)
            lp = lp[pos]
        t = lambda a, **k: torch.tensor(a, device=device, **k)  # noqa: E731
        self.x = t(np.concatenate(xs))
        self.logp = t(lp, dtype=torch.float32)
        self.regime = t(np.concatenate(rg))
        self.breadth = t(np.concatenate(br))
        self.starts = t(np.concatenate(starts))
        self.obs_dim = self.x.shape[1] + N_TRADE


class Env:
    def __init__(self, tape: Tape, n: int, seed: int):
        self.tape, self.n = tape, n
        dev = tape.x.device
        self.gen = torch.Generator(device=dev).manual_seed(seed)
        z = lambda dt=torch.float32: torch.zeros(n, dtype=dt, device=dev)  # noqa: E731
        self.t0, self.t, self.age = z(torch.long), z(torch.long), z(torch.long)
        self.best, self.mdd = z(), z()
        self.reset(torch.ones(n, dtype=torch.bool, device=dev))

    def reset(self, which):
        k = int(which.sum())
        if not k:
            return
        lp = self.tape.logp
        pick = torch.randint(len(self.tape.starts), (k,), generator=self.gen, device=self.t.device)
        t0 = self.tape.starts[pick]
        self.t0[which] = t0
        self.t[which] = t0 + STEP          # the first decision comes 4 h after the entry
        self.age[which] = 1
        self.best[which] = torch.maximum(lp[t0], lp[t0 + STEP])
        self.mdd[which] = torch.clamp(self.best[which] - lp[t0 + STEP], min=0)

    def observe(self):
        tp, t = self.tape, self.t
        lp = tp.logp[t]
        trade = torch.stack([tp.regime[t], tp.breadth[t], (lp - tp.logp[self.t0]) * 10,
                             self.age.float() / MAX_STEPS, (self.best - lp) * 10, self.mdd * 10], dim=1)
        return torch.cat([tp.x[t].float(), trade], dim=1)

    def step(self, a):
        tp, t = self.tape, self.t
        close = a == 1
        ret = tp.logp[t + STEP] - tp.logp[t]
        reward = torch.where(close, torch.full_like(ret, -HALF_COST), ret)
        held = ~close
        self.t = torch.where(held, t + STEP, t)
        lp = tp.logp[self.t]
        self.best = torch.where(held, torch.maximum(self.best, lp), self.best)
        self.mdd = torch.where(held, torch.maximum(self.mdd, self.best - lp), self.mdd)
        self.age = self.age + held.long()
        forced = held & ((self.age >= MAX_STEPS) | (lp - tp.logp[self.t0] <= np.log(1 - STOP)))
        reward = reward - HALF_COST * forced.float()
        done = close | forced
        reward = (reward - LAMBDA * self.mdd * done.float()) * 100
        self.reset(done)
        return reward, done, held.float()


def make_manager(net: Net, world: S.World, cfg: dict, device: str):
    """The callable the book asks every 4 h: True closes the position. Greedy."""
    feats = world.full()
    up = world.regime_up(cfg["regime_ma"])
    logp = {}
    for s, d in world.per.items():
        lp = np.log(np.where(np.isfinite(d["close"]) & (d["close"] > 0), d["close"], np.nan))
        pos = np.where(np.isfinite(lp), np.arange(len(lp)), 0)
        np.maximum.accumulate(pos, out=pos)
        logp[s] = lp[pos]

    @torch.no_grad()
    def decide(sym: str, i: int, i0: int) -> bool:
        if i < 0 or i0 < 0 or i <= i0:
            return False
        un, held, below, dip = trade_state(logp[sym], i0, i)
        d = world.per[sym]
        obs = np.concatenate([clean(feats[sym][i]),
                              [float(up[sym][i]) * 2 - 1, float(d["breadth"][i]) * 2 - 1,
                               un * 10, held, below * 10, dip * 10]]).astype(np.float32)
        dist, _ = net(torch.tensor(obs[None], device=device))
        return bool(dist.probs[0, 1] > 0.5)

    return decide


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 position manager (PPO), 24/7, releases by the clock")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--envs", type=int, default=16384)
    ap.add_argument("--steps", type=int, default=32)
    ap.add_argument("--seed", type=int, default=20261009)
    ap.add_argument("--release-every", type=float, default=RELEASE_EVERY_S)
    ap.add_argument("--out", default=str(MGR_DIR))
    args = ap.parse_args()
    device = "cuda"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"[{S._now()}] manager: loading research bars (<= 2025)", flush=True)
    world = S.World()
    cfg = signal_cfg()
    ent = entries(world, cfg, ENTRY_YEARS, device)
    tape = Tape(world, cfg, ent, TRAIN_YEARS, device)
    g, regime = S.gate(world, cfg)
    _, vmasks, vkeep = S.signals(world, cfg, VAL_YEAR, g, regime, device)
    size, mm = S.sizing(world, cfg), S.mm_kwargs(cfg)
    keys = ("return", "max_dd", "q", "trades", "win_rate")
    own = world.book(vmasks, VAL_YEAR, cfg["horizon"], size, vkeep, S.EXIT_MIN_HOLD, **mm)
    own = {k: own.get(k) for k in keys}
    print(f"[{S._now()}] manager: {VAL_YEAR} own exit {own}", flush=True)

    def validate() -> dict:
        net.eval()
        r = world.book(vmasks, VAL_YEAR, cfg["horizon"], size, None, 0,
                       manager=make_manager(net, world, cfg, device), **mm)
        net.train()
        return {k: r.get(k) for k in keys}

    net = Net(tape.obs_dim).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-4, weight_decay=1e-3)
    state = {"updates": 0, "decisions": 0, "train_seconds": 0.0, "skipped": 0,
             "best_q": None, "best_release": None, "stale": 0, "best_net": None}
    if CKPT.is_file():
        saved = torch.load(CKPT, map_location=device, weights_only=False)
        if (saved.get("obs_dim") == tape.obs_dim and saved.get("cfg_id") == S.cfg_id(cfg)
                and saved.get("train_years") == list(TRAIN_YEARS)):
            net.load_state_dict(saved["net"]); opt.load_state_dict(saved["opt"]); state = saved["state"]
            print(f"[{S._now()}] manager: resumed - {state['updates']} updates", flush=True)
    env = Env(tape, args.envs, args.seed + state["updates"])
    gamma, lam, clip, epochs, mb = 0.99, 0.95, 0.2, 4, 16_384
    started = last_release = time.time()
    window = []
    print(f"[{S._now()}] manager: managing trades of {S.cfg_label(cfg)} - "
          f"{len(tape.starts):,} entries 2020-2024", flush=True)

    def save():
        torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "state": state,
                    "obs_dim": tape.obs_dim, "cfg_id": S.cfg_id(cfg),
                    "train_years": list(TRAIN_YEARS)}, CKPT)

    while time.time() - started < args.hours * 3600 and not S.STOP.exists():
        t0 = time.time()
        buf = {k: [] for k in ("o", "a", "lp", "v", "r", "d", "h")}
        with torch.no_grad():
            for _ in range(args.steps):
                o = env.observe()
                dist, v = net(o)
                a = dist.sample()
                r, d, h = env.step(a)
                for k, x in zip(buf, (o, a, dist.log_prob(a), v, r, d, h)):
                    buf[k].append(x)
            _, v_last = net(env.observe())
        rew = torch.stack(buf["r"]); done = torch.stack(buf["d"]).float(); val = torch.stack(buf["v"])
        adv = torch.zeros_like(rew); gae = torch.zeros(args.envs, device=device)
        for k in reversed(range(args.steps)):
            nxt = v_last if k == args.steps - 1 else val[k + 1]
            delta = rew[k] + gamma * nxt * (1 - done[k]) - val[k]
            gae = delta + gamma * lam * (1 - done[k]) * gae
            adv[k] = gae
        ret = (adv + val).flatten()
        o_f, a_f, lp_f = torch.cat(buf["o"]), torch.cat(buf["a"]), torch.cat(buf["lp"])
        adv_f = adv.flatten()
        adv_f = (adv_f - adv_f.mean()) / (adv_f.std() + 1e-8)
        for _ in range(epochs):
            perm = torch.randperm(len(a_f), device=device)
            for i in range(0, len(a_f), mb):
                j = perm[i:i + mb]
                dist, v = net(o_f[j])
                ratio = torch.exp((dist.log_prob(a_f[j]) - lp_f[j]).clamp(-20.0, 20.0))
                pg = -torch.min(ratio * adv_f[j], ratio.clamp(1 - clip, 1 + clip) * adv_f[j]).mean()
                loss = pg + 0.5 * (v - ret[j]).pow(2).mean() - 0.01 * dist.entropy().mean()
                if not torch.isfinite(loss):
                    state["skipped"] += 1
                    continue
                opt.zero_grad(); loss.backward()
                if not torch.isfinite(nn.utils.clip_grad_norm_(net.parameters(), 0.5)):
                    state["skipped"] += 1
                    opt.zero_grad()
                    continue
                opt.step()
        state["updates"] += 1
        state["decisions"] += args.envs * args.steps
        state["train_seconds"] += time.time() - t0
        trades = float(done.sum())
        window.append({"reward": float(rew.sum() / max(trades, 1.0)), "hold": float(torch.stack(buf["h"]).mean())})
        if state["updates"] % 50 == 0:
            w = window[-50:]
            print(f"[{S._now()}] manager: update {state['updates']} ({state['train_seconds'] / 3600:.2f} h) "
                  f"reward per trade {np.mean([x['reward'] for x in w]):+.3f} hold "
                  f"{np.mean([x['hold'] for x in w]):.0%} skipped {state['skipped']}", flush=True)
            save()
        if time.time() - last_release >= args.release_every:
            n = len(list(out.glob("mgr_release_*.json"))) + 1
            w = window[-200:]
            val = validate()
            better = state["best_q"] is None or val["q"] > state["best_q"]
            if better:
                state.update(best_q=val["q"], best_release=n, stale=0,
                             best_net={k: v.detach().clone() for k, v in net.state_dict().items()})
            else:
                state["stale"] += 1
                if state["stale"] >= PATIENCE and state["best_net"] is not None:
                    net.load_state_dict(state["best_net"])
                    for grp in opt.param_groups:
                        grp["lr"] *= 0.5
                    state["stale"] = 0
                    S.add_event("method", f"position manager: {PATIENCE} releases without a better "
                                          f"{VAL_YEAR} - back to release {state['best_release']}'s "
                                          f"weights, step halved")
            print(f"[{S._now()}] manager: {VAL_YEAR} validation {val} (own exit q {own['q']}) "
                  f"{'BEST' if better else 'stale ' + str(state['stale'])}", flush=True)
            meta = {"n": n, "at": S._now(), "train_hours": round(state["train_seconds"] / 3600, 2),
                    "updates": state["updates"], "decisions": state["decisions"],
                    "reward_per_trade": round(float(np.mean([x["reward"] for x in w])), 4),
                    "hold_share": round(float(np.mean([x["hold"] for x in w])), 4),
                    "signal_cfg": cfg, "signal_label": S.cfg_label(cfg), "obs_dim": tape.obs_dim,
                    "train_years": list(TRAIN_YEARS),
                    "validation": {"year": VAL_YEAR, "manager": val, "own_exit": own,
                                   "best_so_far": better}}
            torch.save({"net": net.state_dict(), "meta": meta}, out / f"mgr_release_{n:04d}.pt")
            (out / f"mgr_release_{n:04d}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            S.add_event("release", f"position manager release {n}: {meta['train_hours']} h trained, "
                                   f"holds {meta['hold_share']:.0%} of decisions")
            print(f"[{S._now()}] manager: MANAGER RELEASE {n}", flush=True)
            last_release = time.time()
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
