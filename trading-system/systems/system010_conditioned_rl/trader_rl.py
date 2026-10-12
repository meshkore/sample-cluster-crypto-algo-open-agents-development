"""RL v5 - the pure decision engine: long, nothing, or short. Nothing else.

The operator, 2026-10-10: *"remove from the equation the rules of a trading algorithm ... a
reinforcement learning engine has to have a lot of data to play with and rules as simple as
possible: decide when to buy, when to sell, when to go short and when to close. Evaluate the
percentages it gets ... like a sinusoid: near zero do nothing, at +1 buy, at -1 sell."* A
second, classical model may later decide how many positions, which assets and how big.

The formulation follows Zhang, Zohren & Roberts, "Deep Reinforcement Learning for Trading"
(J. Financial Data Science, 2020), where discrete long/flat/short agents beat classic
time-series momentum across 50 futures, with the ingredients that made training work there:

    actions    0 short, 1 nothing, 2 long - one asset per episode, position -1 / 0 / +1
    reward     position x the next 4 h return - 0.15% x |change of position|, DIVIDED by
               the asset's recent volatility (their volatility scaling) so every coin and
               every year teaches with the same weight; results are reported in raw %
    state      only the market: the asset's returns over 4 h, 12 h, 1 d, 3 d, 1 w, 3 w
               scaled by its volatility, three MACD-style trend signals, its volatility
               regime, the same returns of BTC, and the position held - no coin identity,
               no forecast of ours, no trading rules
    decisions  daily (v1 decided every 4 h and paid ~80% a year in costs); training
               reads each coin from 6 daily phases and charges turnover double
    network    one MLP shared by all 14 coins; PPO, thousands of parallel episodes of 30
               days drawn from random coins and dates
    score      the "sinusoid": P(long) - P(short) in [-1, 1]; near 0 means do nothing
    honesty    trains 2018-2023; every release is validated on 2024 against buy-and-hold
               and a 1-month trend follower; the evaluator reads 2025 and 2026. Shorts are
               simulated at the same 0.15% cost; perpetual funding is not charged yet.
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

OUT = S.OUT
REL_DIR = OUT / "releases_trader"
CKPT = OUT / "_auto_trader_checkpoint.pt"
STEP_NS = 24 * 3600 * 10**9              # v2: one decision a day (v1: 4 h)
PHASE_NS = 4 * 3600 * 10**9              # training sees the daily bar from 6 starting hours
COST_PENALTY = 2.0                       # training charges turnover double; results are raw
HALF_COST = 0.0015
EPISODE = 120                            # days
TRAIN_LAST = 2023
VAL_YEAR = 2024
LAGS = (1, 3, 5, 10, 21, 63)             # days: 1 d, 3 d, 1 w, 2 w, 1 m, 3 m
RELEASE_EVERY_S = 2 * 3600
PATIENCE = 4
DESIGN = "trader-v2"
# v2 (2026-10-12): v1 decided every 4 h and flipped ~270 times per coin per year; at 0.3% a
# round trip the costs alone were ~80% a year, and 18 releases (39 h) lost on the median coin
# (2025 -47% vs hold -37%; 2026 -47% vs hold -13%). Zhang, Zohren & Roberts decide daily.


# ------------------------------------------------------------------ data: 4 h closes only

def load(include_sealed: bool = False, phases: int = 1) -> dict:
    """Every coin's daily closes (the last 15-minute close of each day). With phases > 1,
    the same coin again with the day starting 4, 8, ... hours later - more histories to
    learn from, each one causal; keys are "SYM" for phase 0 and "SYM@k" for the others."""
    from quantlab_catalog.candles import candles, research
    symbols = json.loads((S.OUT.parents[1] / "research/system06/universe.json").read_text())["symbols"]
    bars = candles(symbols, include_sealed=True) if include_sealed else research(symbols)
    out = {}
    for s in symbols:
        series = bars.get(s) or []
        if len(series) < 2000:
            continue
        ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in series])
        close = np.array([b.close for b in series], dtype=float)
        for k in range(phases):
            bucket = (ns + k * PHASE_NS) // STEP_NS
            last = np.r_[bucket[1:] != bucket[:-1], True]
            out[s if k == 0 else f"{s}@{k}"] = {"ns": ns[last], "close": close[last]}
    return out


def ema(x: np.ndarray, span: int) -> np.ndarray:
    a = 2.0 / (span + 1)
    out = np.empty_like(x)
    acc = x[0]
    for i, v in enumerate(x):
        acc = a * v + (1 - a) * acc
        out[i] = acc
    return out


def features(close: np.ndarray, btc: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """Causal features per 4 h bar, and the volatility each reward is divided by."""
    lp = np.log(np.maximum(close, 1e-12))
    r1 = np.diff(lp, prepend=lp[0])
    vol = np.sqrt(ema(r1 ** 2, 21)) + 1e-4                      # ~1-month EWMA volatility
    cols = []
    for k in LAGS:
        r = np.zeros_like(lp)
        r[k:] = lp[k:] - lp[:-k]
        cols.append(np.clip(r / (vol * np.sqrt(k)), -5, 5))
    for fast, slow in ((8, 24), (16, 48), (32, 96)):             # the paper's MACD pairs
        m = (ema(close, fast) - ema(close, slow)) / (close * vol * 10 + 1e-12)
        cols.append(np.clip(m, -5, 5))
    cols.append(np.clip(np.log(vol / (np.sqrt(ema(r1 ** 2, 252)) + 1e-4)), -3, 3))  # vol regime
    if btc is not None:
        bl = np.log(np.maximum(btc, 1e-12))
        bv = np.sqrt(ema(np.diff(bl, prepend=bl[0]) ** 2, 21)) + 1e-4
        for k in (1, 5, 21):
            r = np.zeros_like(bl)
            r[k:] = bl[k:] - bl[:-k]
            cols.append(np.clip(r / (bv * np.sqrt(k)), -5, 5))
    return np.stack(cols, axis=1).astype(np.float32), vol.astype(np.float32)


class Tape:
    """All coins' 4 h features concatenated on the device; episodes stay inside one coin."""

    def __init__(self, data: dict, first_year: int, last_year: int, device: str, warm: int = 126):
        btc = data["BTCUSDT"]
        xs, rets, vols, years, starts, ranges, off = [], [], [], [], [], {}, 0
        for s, d in data.items():
            ph = s.split("@")[1] if "@" in s else None
            b = data[f"BTCUSDT@{ph}"] if ph else btc       # BTC on the same daily phase
            i = np.clip(np.searchsorted(b["ns"], d["ns"], side="right") - 1, 0, None)
            f, vol = features(d["close"], b["close"][i])
            lp = np.log(np.maximum(d["close"], 1e-12))
            nxt = np.zeros_like(lp)
            nxt[:-1] = lp[1:] - lp[:-1]
            yr = d["ns"].astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970
            keep = np.arange(len(lp)) >= warm
            idx = np.flatnonzero(keep & (yr >= first_year) & (yr <= last_year))
            if len(idx) < EPISODE + 2:
                continue
            xs.append(f[idx]); rets.append(np.clip(nxt[idx], -0.5, 0.5).astype(np.float32))
            vols.append(vol[idx]); years.append(yr[idx])
            n = len(idx)
            ranges[s] = (off, off + n)
            starts.append(np.arange(off, off + n - EPISODE - 1))
            off += n
        t = lambda a, **k: torch.tensor(np.concatenate(a), device=device, **k)  # noqa: E731
        self.x, self.ret, self.vol = t(xs), t(rets), t(vols)
        self.year = np.concatenate(years)
        self.starts = t(starts)
        self.ranges = ranges
        self.obs_dim = self.x.shape[1] + 1


class Net(nn.Module):
    def __init__(self, obs_dim: int, hidden: int = 128):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(obs_dim, hidden), nn.Tanh(), nn.Linear(hidden, hidden), nn.Tanh())
        self.pi = nn.Linear(hidden, 3)
        self.v = nn.Linear(hidden, 1)
        nn.init.zeros_(self.pi.weight)
        nn.init.zeros_(self.pi.bias)

    def forward(self, obs):
        h = self.body(obs)
        return torch.distributions.Categorical(logits=self.pi(h)), self.v(h).squeeze(-1)


class Env:
    def __init__(self, tape: Tape, n: int, seed: int):
        self.tape, self.n = tape, n
        dev = tape.x.device
        self.gen = torch.Generator(device=dev).manual_seed(seed)
        self.t = torch.zeros(n, dtype=torch.long, device=dev)
        self.age = torch.zeros(n, dtype=torch.long, device=dev)
        self.pos = torch.zeros(n, device=dev)
        self.reset(torch.ones(n, dtype=torch.bool, device=dev))

    def reset(self, which):
        k = int(which.sum())
        if k:
            pick = torch.randint(len(self.tape.starts), (k,), generator=self.gen, device=self.t.device)
            self.t[which] = self.tape.starts[pick]
            self.age[which] = 0
            self.pos[which] = 0.0

    def observe(self):
        return torch.cat([self.tape.x[self.t], self.pos[:, None]], dim=1)

    def step(self, a):
        new = a.float() - 1.0                                    # -1 / 0 / +1
        r = self.tape.ret[self.t]
        pnl = new * r - HALF_COST * (new - self.pos).abs()
        train_pnl = new * r - COST_PENALTY * HALF_COST * (new - self.pos).abs()
        reward = train_pnl / self.tape.vol[self.t] * 0.1         # volatility-scaled, ~unit size
        self.pos = new
        self.t = self.t + 1
        self.age += 1
        done = self.age >= EPISODE
        self.reset(done)
        return reward, done, pnl


@torch.no_grad()
def run(tape: Tape, policy) -> dict:
    """Every coin through the whole tape, deterministic. `policy(obs) -> action`, or one of
    the baselines 'hold' / 'trend'. Raw % results, per trade and per coin."""
    per_coin, trades, longs, shorts = {}, [], 0, 0
    for s, (a, b) in tape.ranges.items():
        pos, tr_ret, eq = 0.0, 0.0, 0.0
        x, r = tape.x[a:b], tape.ret[a:b]
        for i in range(b - a - 1):
            if policy == "hold":
                new = 1.0
            elif policy == "trend":
                new = float(np.sign(float(x[i, 4])))             # sign of the 1-month return
            else:
                new = float(policy(torch.cat([x[i], torch.tensor([pos], device=x.device)])[None])) - 1.0
            if new != pos:
                if pos != 0.0:
                    trades.append(tr_ret - HALF_COST)
                    longs += pos > 0; shorts += pos < 0
                tr_ret = -HALF_COST if new != 0 else 0.0
                eq -= HALF_COST * abs(new - pos)
            step = new * float(r[i])
            eq += step
            tr_ret += step
            pos = new
        if pos != 0.0:
            trades.append(tr_ret - HALF_COST)
        per_coin[s] = round(float(np.expm1(eq)), 4)
    t = np.array(trades) if trades else np.zeros(0)
    rets = np.array(list(per_coin.values()))
    return {"mean_coin_return": round(float(rets.mean()), 4), "median_coin_return": round(float(np.median(rets)), 4),
            "coins_positive": int((rets > 0).sum()), "coins": len(rets), "trades": len(t),
            "win_rate": round(float((t > 0).mean()), 4) if len(t) else None,
            "mean_trade": round(float(t.mean()), 5) if len(t) else None,
            "long_trades": int(longs), "short_trades": int(shorts), "per_coin": per_coin}


def greedy(net: Net):
    def act(obs):
        dist, _ = net(obs)
        return dist.probs.argmax(-1)[0]
    return act


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 RL v5: pure long/flat/short decision engine (PPO)")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--envs", type=int, default=8192)
    ap.add_argument("--steps", type=int, default=64)
    ap.add_argument("--release-every", type=float, default=RELEASE_EVERY_S)
    args = ap.parse_args()
    device = "cuda"
    REL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[{S._now()}] trader: loading daily closes, 6 phases (<= 2025)", flush=True)
    data = load(False, phases=6)
    train = Tape(data, 2018, TRAIN_LAST, device)
    val = Tape({k: v for k, v in data.items() if "@" not in k}, VAL_YEAR, VAL_YEAR, device)
    base = {"hold": run(val, "hold"), "trend": run(val, "trend")}
    for k, v in base.items():
        print(f"[{S._now()}] trader: {VAL_YEAR} {k}: mean coin {v['mean_coin_return']:+.1%} "
              f"win {v['win_rate']} trades {v['trades']}", flush=True)
    net = Net(train.obs_dim).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=3e-4, weight_decay=1e-4)
    state = {"updates": 0, "decisions": 0, "train_seconds": 0.0, "best": None, "best_release": None,
             "stale": 0, "best_net": None}
    if CKPT.is_file():
        saved = torch.load(CKPT, map_location=device, weights_only=False)
        if saved.get("design") == DESIGN and saved.get("obs_dim") == train.obs_dim:
            net.load_state_dict(saved["net"]); opt.load_state_dict(saved["opt"]); state = saved["state"]
            print(f"[{S._now()}] trader: resumed - {state['updates']} updates", flush=True)

    def save():
        torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "state": state,
                    "design": DESIGN, "obs_dim": train.obs_dim}, CKPT)

    env = Env(train, args.envs, 20261010 + state["updates"])
    gamma, lam, clip, epochs, mb = 0.99, 0.95, 0.2, 4, 16384
    started = last_release = time.time()
    window = []
    print(f"[{S._now()}] trader: training on {len(train.ranges)} coins 2018-{TRAIN_LAST}, "
          f"{len(train.starts):,} episode starts", flush=True)
    while time.time() - started < args.hours * 3600 and not S.STOP.exists():
        t0 = time.time()
        buf = {k: [] for k in ("o", "a", "lp", "v", "r", "d", "p")}
        with torch.no_grad():
            for _ in range(args.steps):
                o = env.observe()
                dist, v = net(o)
                a = dist.sample()
                r, d, pnl = env.step(a)
                for k, x in zip(buf, (o, a, dist.log_prob(a), v, r, d, (a != 1).float())):
                    buf[k].append(x)
            _, v_last = net(env.observe())
        rew = torch.stack(buf["r"]); done = torch.stack(buf["d"]).float(); val_ = torch.stack(buf["v"])
        adv = torch.zeros_like(rew); gae = torch.zeros(args.envs, device=device)
        for k in reversed(range(args.steps)):
            nxt = v_last if k == args.steps - 1 else val_[k + 1]
            delta = rew[k] + gamma * nxt * (1 - done[k]) - val_[k]
            gae = delta + gamma * lam * (1 - done[k]) * gae
            adv[k] = gae
        ret = (adv + val_).flatten()
        O, A, LP = torch.cat(buf["o"]), torch.cat(buf["a"]), torch.cat(buf["lp"])
        ADV = adv.flatten()
        ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
        for _ in range(epochs):
            perm = torch.randperm(len(A), device=device)
            for i in range(0, len(A), mb):
                j = perm[i:i + mb]
                dist, v = net(O[j])
                ratio = torch.exp((dist.log_prob(A[j]) - LP[j]).clamp(-20, 20))
                pg = -torch.min(ratio * ADV[j], ratio.clamp(1 - clip, 1 + clip) * ADV[j]).mean()
                loss = pg + 0.5 * (v - ret[j]).pow(2).mean() - 0.01 * dist.entropy().mean()
                if not torch.isfinite(loss):
                    continue
                opt.zero_grad(); loss.backward()
                if not torch.isfinite(nn.utils.clip_grad_norm_(net.parameters(), 0.5)):
                    opt.zero_grad(); continue
                opt.step()
        state["updates"] += 1
        state["decisions"] += args.envs * args.steps
        state["train_seconds"] += time.time() - t0
        window.append((float(rew.mean()), float(torch.stack(buf["p"]).mean())))
        if state["updates"] % 50 == 0:
            w = window[-50:]
            print(f"[{S._now()}] trader: update {state['updates']} ({state['train_seconds'] / 3600:.2f} h) "
                  f"reward {np.mean([x[0] for x in w]):+.4f} in market {np.mean([x[1] for x in w]):.0%}", flush=True)
            save()
        if time.time() - last_release >= args.release_every:
            n = len(list(REL_DIR.glob("trader_release_*.json"))) + 1
            net.eval()
            res = run(val, greedy(net))
            net.train()
            # Median coin, not the mean: releases 1-4 read a +126% "mean coin" in 2025 that was
            # one coin (ZEC +2,320%); the median was -50% and 1-3 of 14 coins were positive.
            key = res["median_coin_return"]
            better = state["best"] is None or key > state["best"]
            if better:
                state.update(best=key, best_release=n, stale=0,
                             best_net={k: v.detach().clone() for k, v in net.state_dict().items()})
            else:
                state["stale"] += 1
                if state["stale"] >= PATIENCE and state["best_net"] is not None:
                    net.load_state_dict(state["best_net"])
                    for g in opt.param_groups:
                        g["lr"] *= 0.5
                    state["stale"] = 0
            meta = {"n": n, "at": S._now(), "design": DESIGN, "train_hours": round(state["train_seconds"] / 3600, 2),
                    "updates": state["updates"], "decisions": state["decisions"], "obs_dim": train.obs_dim,
                    "validation": {"year": VAL_YEAR, "agent": {k: v for k, v in res.items() if k != "per_coin"},
                                   "hold": {k: v for k, v in base["hold"].items() if k != "per_coin"},
                                   "trend": {k: v for k, v in base["trend"].items() if k != "per_coin"},
                                   "best_so_far": better}}
            torch.save({"net": net.state_dict(), "meta": meta}, REL_DIR / f"trader_release_{n:04d}.pt")
            (REL_DIR / f"trader_release_{n:04d}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            S.add_event("release", f"RL trader release {n}: {VAL_YEAR} median coin {key:+.1%} "
                                   f"({res['coins_positive']}/{res['coins']} coins up), win "
                                   f"{res['win_rate']}, {res['long_trades']} long / {res['short_trades']} short "
                                   f"(hold {base['hold']['median_coin_return']:+.1%}, trend {base['trend']['median_coin_return']:+.1%})")
            print(f"[{S._now()}] trader: TRADER RELEASE {n} - {VAL_YEAR} median coin {key:+.1%} win {res['win_rate']} "
                  f"trades {res['trades']} ({res['long_trades']} L / {res['short_trades']} S) "
                  f"{'BEST' if better else 'stale ' + str(state['stale'])}", flush=True)
            last_release = time.time()
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
