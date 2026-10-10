"""RL v4 - the portfolio sizer: reinforcement learning that decides HOW MUCH, not what is true.

The operator, 2026-10-10: *"it is hard to believe we have reached the ceiling of reinforcement
learning ... either keep spending compute until better results appear, or change the way the
model works - the rules, the conditions on which it iterates."*

Why the three earlier RL designs failed (full trader 56 h; position manager, 5 releases):
they had to learn to PREDICT the market and to DECIDE at once, from scratch, seeing which
coin it was - and they memorised the training years. This design removes each cause:

    prediction   is an INPUT, not a job: the signal model's walk-forward forecast for the
                 year (fit on earlier years only), its entry gate and its exit bit. The
                 policy only learns how much to hold given them.
    decision     every 4 h, a target weight per coin: 0 to 30% of equity in 7 levels (gross
                 capped at 100%). Reward = the portfolio's log return - 0.15% per unit
                 turned over - LAMBDA x the part of each new drawdown step beyond DD_FREE.
                 The book is judged on exactly this: profit for the account, small drawdown.
    warm start   it first imitates the rule that already works (stake by signal strength,
                 the 2026-10-10 probe: drawdown halved at the same return); PPO then has to
                 IMPROVE on a good policy instead of rediscovering it.
    no identity  one small network scores every coin from the same features (no coin id),
                 so it cannot learn "SOL in March 2021"; random coin dropout per episode.
    honesty      trains on 2020-2023, every release is validated on 2024 against the rule
                 in the same simulator; the evaluator reads 2025 and 2026. Nothing chooses
                 on 2025 or 2026.
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
SIZER_DIR = OUT / "releases_sizer"
CKPT = OUT / "_auto_sizer_checkpoint.pt"
STEP = 16                         # 4 h
LEVELS = torch.tensor([0.0, 0.025, 0.05, 0.1, 0.15, 0.2, 0.3])   # v2: fine enough for the falling-regime stakes
HALF_COST = 0.0015
LAMBDA = 2.0
DD_FREE = 0.10
EPISODE = 180                     # 30 days
TRAIN_YEARS = (2020, 2021, 2022, 2023)
VAL_YEAR = 2024
PANEL_YEARS = (2020, 2021, 2022, 2023, 2024)
BC_UPDATES = 400
RELEASE_EVERY_S = 2 * 3600
PATIENCE = 3
N_COIN = 9                        # per-coin features
N_GLOBAL = 3                      # drawdown, gross exposure, regime
DESIGN = "sizer-v2"


# ------------------------------------------------------------------ the panel: one row per 4 h

def signal_cfg() -> dict:
    champ = S.champion(S.ledger())
    return champ["cfg"] if champ else S.releases()[-1]["cfg"]


def build_panel(world: S.World, cfg: dict, years, device: str) -> dict:
    """Every coin on BTC's 4-hour grid for `years`: closes, the signal model's walk-forward
    forecast / entry gate / exit bit for that year, volatility and the regime."""
    g, regime = S.gate(world, cfg)
    btc = world.per["BTCUSDT"]
    sel = np.isin(btc["year"], years)
    grid_idx = np.flatnonzero(sel)[::STEP]
    grid = btc["ns"][grid_idx]
    syms = list(world.per)
    T, N = len(grid), len(syms)
    close = np.full((T, N), np.nan, dtype=np.float64)
    pred = np.zeros((T, N), dtype=np.float32)
    gate = np.zeros((T, N), dtype=bool)
    keep = np.zeros((T, N), dtype=bool)
    year = btc["year"][grid_idx]
    vol, ref = world.vol96()
    volr = np.zeros((T, N), dtype=np.float32)
    up = world.regime_up(cfg["regime_ma"])["BTCUSDT"][grid_idx].astype(np.float32) * 2 - 1
    per_year = {}
    for N_ in years:
        _, masks, kp = S.signals(world, cfg, N_, g, regime, device)
        st = S.strength(world, cfg, N_, g, regime, device)
        per_year[N_] = (masks, kp, st)
    for j, s in enumerate(syms):
        d = world.per[s]
        i = np.searchsorted(d["ns"], grid, side="right") - 1
        ok = (i >= 0)
        i = np.clip(i, 0, None)
        fresh = ok & (grid - d["ns"][i] <= np.int64(3600 * 10**9))
        close[:, j] = np.where(fresh, d["close"][i], np.nan)
        volr[:, j] = np.log(np.clip(vol[s][i] / ref, 0.1, 10.0))
        for N_, (masks, kp, st) in per_year.items():
            yr = fresh & (year == N_)
            gate[yr, j] = masks[s][i[yr]]
            keep[yr, j] = kp[s][i[yr]] if kp is not None else True
            if st is not None:
                pred[yr, j] = st[s][i[yr]]
    # carry prices over short gaps; coins not yet listed stay NaN = not tradable
    for j in range(N):
        c = close[:, j]
        ok = np.isfinite(c)
        if ok.any():
            k = np.where(ok, np.arange(T), 0)
            np.maximum.accumulate(k, out=k)
            filled = c[k]
            filled[: np.argmax(ok)] = np.nan
            close[:, j] = filled
    live = np.isfinite(close)
    lp = np.log(np.where(live, close, 1.0))

    def ret(k):
        r = np.zeros_like(lp)
        r[k:] = lp[k:] - lp[:-k]
        return np.clip(r, -0.5, 0.5).astype(np.float32)

    t = lambda a, **k: torch.tensor(a, device=device, **k)  # noqa: E731
    return {"syms": syms, "year": year, "grid": grid, "slots": int(cfg.get("slots", 3)),
            "size_down": float(cfg.get("size_down", 1.0)), "dd_scale": cfg.get("dd_scale"),
            "lp": t(lp, dtype=torch.float32), "live": t(live), "pred": t(pred), "gate": t(gate),
            "keep": t(keep), "volr": t(volr), "r1": t(ret(1)), "r6": t(ret(6)), "r42": t(ret(42)),
            "regime": t(up)}


def baseline_weights(P: dict, env: "Env") -> torch.Tensor:
    """The rule the sizer starts from - the release's book, on the 4 h grid (sizer-v2: v1
    left out the slot cap, the falling-regime stake and the drawdown cut, and read 2024
    -5.1% / DD 43% where the book reads +42% / DD 11%):
      enter where the gate opens and the forecast clears +0.3%, hold while it stays above
      -0.3%; stake = 1/slots x clip(forecast / 1%, 0.25, 1) x size_down when BTC is below
      its average x max(0.25, 1 - drawdown / dd_scale); at most `slots` coins, the
      strongest forecasts first."""
    t, cur = env.t, env.w
    pred, gate, keep = P["pred"][t], P["gate"][t], P["keep"][t]
    want = (gate & (pred > 0.003)) | ((cur > 0) & keep & (pred > -0.003))
    w = torch.where(want, torch.clamp(pred / 0.01, 0.25, 1.0) / P["slots"], torch.zeros_like(pred))
    w = w * torch.where(P["regime"][t] > 0, 1.0, P["size_down"])[:, None]
    if P["dd_scale"]:
        dd = env.peak - env.eq
        w = w * torch.clamp(1.0 - dd / P["dd_scale"], min=0.25)[:, None]
    k = min(P["slots"], w.shape[1])
    top = torch.topk(w, k, dim=1).values[:, -1:]
    return torch.where((w >= top) & (w > 0), w, torch.zeros_like(w))


def to_level(w: torch.Tensor) -> torch.Tensor:
    """The nearest allowed level; a positive weight never rounds to flat."""
    lv = (w[..., None] - LEVELS.to(w.device)).abs().argmin(-1)
    return torch.where((w > 0) & (lv == 0), torch.ones_like(lv), lv)


# ------------------------------------------------------------------ the network

class Net(nn.Module):
    """Per-coin scorer shared by every coin (no identity), plus a pooled value head."""

    def __init__(self, hidden: int = 128):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(N_COIN + N_GLOBAL, hidden), nn.Tanh(),
                                 nn.Linear(hidden, hidden), nn.Tanh())
        self.pi = nn.Linear(hidden, len(LEVELS))
        self.v = nn.Sequential(nn.Linear(hidden, hidden), nn.Tanh(), nn.Linear(hidden, 1))

    def forward(self, coin, glob, mask):
        # coin [B, N, F], glob [B, G], mask [B, N]
        x = torch.cat([coin, glob[:, None, :].expand(-1, coin.shape[1], -1)], dim=-1)
        h = self.enc(x)
        logits = self.pi(h)
        m = mask[..., None].float()
        pooled = (h * m).sum(1) / m.sum(1).clamp(min=1.0)
        return logits, self.v(pooled).squeeze(-1)


def dist_of(logits, mask):
    """Inactive coins are forced to level 0 so their log-prob is constant."""
    forced = torch.full_like(logits, -1e4)
    forced[..., 0] = 0.0
    return torch.distributions.Categorical(logits=torch.where(mask[..., None], logits, forced))


# ------------------------------------------------------------------ the environment

class Env:
    def __init__(self, P: dict, years, n: int, seed: int, train: bool = True):
        self.P, self.n, self.train = P, n, train
        dev = P["lp"].device
        T = P["lp"].shape[0]
        ok = np.isin(P["year"], years)
        idx = np.flatnonzero(ok[: T - 2])
        if train:   # the whole episode, and the bar after it, inside the training years
            idx = idx[idx < T - EPISODE - 2]
            idx = idx[np.isin(P["year"][idx + EPISODE + 1], years)]
        self.starts = torch.tensor(idx if train else idx[:1], device=dev)
        self.gen = torch.Generator(device=dev).manual_seed(seed)
        N = P["lp"].shape[1]
        self.w = torch.zeros(n, N, device=dev)
        self.t = torch.zeros(n, dtype=torch.long, device=dev)
        self.age = torch.zeros(n, dtype=torch.long, device=dev)
        self.eq = torch.zeros(n, device=dev)
        self.peak = torch.zeros(n, device=dev)
        self.drop = torch.ones(n, N, dtype=torch.bool, device=dev)
        self.reset(torch.ones(n, dtype=torch.bool, device=dev))

    def reset(self, which):
        k = int(which.sum())
        if not k:
            return
        pick = torch.randint(len(self.starts), (k,), generator=self.gen, device=self.t.device)
        self.t[which] = self.starts[pick]
        self.age[which] = 0
        self.w[which] = 0.0
        self.eq[which] = 0.0
        self.peak[which] = 0.0
        if self.train:   # coin dropout: each episode sees a random ~80% of the universe
            self.drop[which] = torch.rand(k, self.w.shape[1], generator=self.gen, device=self.t.device) < 0.8

    def mask(self):
        return self.P["live"][self.t] & self.drop

    def observe(self):
        P, t = self.P, self.t
        coin = torch.stack([torch.clamp(P["pred"][t] * 100, -5, 5), P["gate"][t].float(), P["keep"][t].float(),
                            P["volr"][t], P["r1"][t] * 20, P["r6"][t] * 10, P["r42"][t] * 4,
                            self.w * 5, (P["pred"][t] > 0.003).float()], dim=-1)
        glob = torch.stack([(self.peak - self.eq) * 10, self.w.sum(1), P["regime"][t]], dim=-1)
        return coin, glob, self.mask()

    def step(self, level):
        P, t = self.P, self.t
        m = self.mask()
        w_new = LEVELS.to(level.device)[level] * m.float()
        gross = w_new.sum(1, keepdim=True)
        w_new = torch.where(gross > 1.0, w_new / gross, w_new)
        turn = (w_new - self.w).abs().sum(1)
        r = P["lp"][t + 1] - P["lp"][t]
        r = torch.where(P["live"][t + 1] & m, r, torch.zeros_like(r))
        port = torch.log1p(torch.clamp((w_new * torch.expm1(r)).sum(1), min=-0.99)) - HALF_COST * turn
        dd_before = self.peak - self.eq
        self.eq = self.eq + port
        self.peak = torch.maximum(self.peak, self.eq)
        dd_after = self.peak - self.eq
        pain = torch.clamp(dd_after - torch.maximum(dd_before, torch.full_like(dd_before, DD_FREE)), min=0)
        reward = (port - LAMBDA * pain) * 100
        # weights drift with prices until the next decision
        grown = w_new * torch.exp(r)
        self.w = grown / torch.clamp(1.0 + (grown - w_new).sum(1, keepdim=True), min=1e-3)
        self.t = t + 1
        self.age += 1
        done = self.age >= EPISODE
        if self.train:
            self.reset(done)
        return reward, done, port, turn


@torch.no_grad()
def run_year(P: dict, net: Net | None, year: int) -> dict:
    """The whole year as one deterministic episode: the policy (argmax) or, with net=None,
    the rule it started from. Return, max drawdown, turnover - in the same simulator."""
    env = Env(P, (year,), 1, 0, train=False)
    T = int((torch.tensor(P["year"]) == year).sum())
    eqs = [0.0]
    turn = 0.0
    for _ in range(T - 2):
        coin, glob, m = env.observe()
        if net is None:
            lv = to_level(baseline_weights(P, env))
        else:
            logits, _ = net(coin, glob, m)
            lv = dist_of(logits, m).probs.argmax(-1)
        _, _, port, tr = env.step(lv)
        eqs.append(eqs[-1] + float(port[0]))
        turn += float(tr[0])
    e = np.exp(np.array(eqs))
    dd = float((1 - e / np.maximum.accumulate(e)).max())
    ret = float(e[-1] - 1)
    return {"return": round(ret, 4), "max_dd": round(dd, 4), "q": round(np.sign(ret) * ret ** 2 / max(dd, 0.02), 4),
            "turnover": round(turn, 1)}


# ------------------------------------------------------------------ training

def main() -> int:
    ap = argparse.ArgumentParser(description="S10 RL v4: portfolio sizer (PPO with a warm start)")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--envs", type=int, default=2048)
    ap.add_argument("--steps", type=int, default=64)
    ap.add_argument("--release-every", type=float, default=RELEASE_EVERY_S)
    args = ap.parse_args()
    device = "cuda"
    SIZER_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[{S._now()}] sizer: loading research bars (<= 2025)", flush=True)
    world = S.World()
    cfg = signal_cfg()
    print(f"[{S._now()}] sizer: building the 4 h panel for {S.cfg_label(cfg)}", flush=True)
    P = build_panel(world, cfg, PANEL_YEARS, device)
    base_val = run_year(P, None, VAL_YEAR)
    print(f"[{S._now()}] sizer: {VAL_YEAR} rule in this simulator {base_val}", flush=True)
    net = Net().to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=3e-4, weight_decay=1e-4)
    state = {"updates": 0, "decisions": 0, "train_seconds": 0.0, "bc_done": False,
             "best_q": None, "best_release": None, "stale": 0, "best_net": None}
    if CKPT.is_file():
        saved = torch.load(CKPT, map_location=device, weights_only=False)
        if saved.get("design") == DESIGN and saved.get("cfg_id") == S.cfg_id(cfg):
            net.load_state_dict(saved["net"]); opt.load_state_dict(saved["opt"]); state = saved["state"]
            print(f"[{S._now()}] sizer: resumed - {state['updates']} updates", flush=True)

    def save():
        torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "state": state,
                    "design": DESIGN, "cfg_id": S.cfg_id(cfg)}, CKPT)

    env = Env(P, TRAIN_YEARS, args.envs, 20261010 + state["updates"])
    if not state["bc_done"]:
        # warm start: imitate the rule on states the rule itself visits
        for u in range(BC_UPDATES):
            coin, glob, m = env.observe()
            target = to_level(baseline_weights(P, env))
            logits, _ = net(coin, glob, m)
            loss = (nn.functional.cross_entropy(logits.reshape(-1, len(LEVELS)), target.reshape(-1), reduction="none")
                    * m.reshape(-1).float()).sum() / m.sum().clamp(min=1)
            opt.zero_grad(); loss.backward(); opt.step()
            with torch.no_grad():
                env.step(target)
            if u % 100 == 0:
                print(f"[{S._now()}] sizer: imitation {u}/{BC_UPDATES} loss {float(loss):.3f}", flush=True)
        state["bc_done"] = True
        bc_val = run_year(P, net, VAL_YEAR)
        print(f"[{S._now()}] sizer: after imitation {VAL_YEAR} {bc_val} (rule {base_val})", flush=True)
        save()
    gamma, lam, clip, epochs, mb = 0.99, 0.95, 0.2, 4, 8192
    started = last_release = time.time()
    window = []
    while time.time() - started < args.hours * 3600 and not S.STOP.exists():
        t0 = time.time()
        buf = {k: [] for k in ("c", "g", "m", "a", "lp", "v", "r", "d")}
        with torch.no_grad():
            for _ in range(args.steps):
                coin, glob, m = env.observe()
                logits, v = net(coin, glob, m)
                dist = dist_of(logits, m)
                a = dist.sample()
                r, d, _, _ = env.step(a)
                for k, x in zip(buf, (coin, glob, m, a, dist.log_prob(a).sum(-1), v, r, d)):
                    buf[k].append(x)
            _, v_last = net(*env.observe())
        rew = torch.stack(buf["r"]); done = torch.stack(buf["d"]).float(); val = torch.stack(buf["v"])
        adv = torch.zeros_like(rew); gae = torch.zeros(args.envs, device=device)
        for k in reversed(range(args.steps)):
            nxt = v_last if k == args.steps - 1 else val[k + 1]
            delta = rew[k] + gamma * nxt * (1 - done[k]) - val[k]
            gae = delta + gamma * lam * (1 - done[k]) * gae
            adv[k] = gae
        ret = (adv + val).flatten()
        C, G, M, A = (torch.cat(buf[k]) for k in ("c", "g", "m", "a"))
        LP, ADV = torch.cat(buf["lp"]), adv.flatten()
        ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
        for _ in range(epochs):
            perm = torch.randperm(len(A), device=device)
            for i in range(0, len(A), mb):
                j = perm[i:i + mb]
                logits, v = net(C[j], G[j], M[j])
                dist = dist_of(logits, M[j])
                ratio = torch.exp((dist.log_prob(A[j]).sum(-1) - LP[j]).clamp(-20, 20))
                pg = -torch.min(ratio * ADV[j], ratio.clamp(1 - clip, 1 + clip) * ADV[j]).mean()
                ent = (dist.entropy() * M[j].float()).sum(-1).mean()
                loss = pg + 0.5 * (v - ret[j]).pow(2).mean() - 0.003 * ent
                if not torch.isfinite(loss):
                    continue
                opt.zero_grad(); loss.backward()
                if not torch.isfinite(nn.utils.clip_grad_norm_(net.parameters(), 0.5)):
                    opt.zero_grad(); continue
                opt.step()
        state["updates"] += 1
        state["decisions"] += args.envs * args.steps
        state["train_seconds"] += time.time() - t0
        window.append(float(rew.mean()))
        if state["updates"] % 50 == 0:
            print(f"[{S._now()}] sizer: update {state['updates']} ({state['train_seconds'] / 3600:.2f} h) "
                  f"reward {np.mean(window[-50:]):+.4f}", flush=True)
            save()
        if time.time() - last_release >= args.release_every:
            n = len(list(SIZER_DIR.glob("sizer_release_*.json"))) + 1
            val_ = run_year(P, net, VAL_YEAR)
            better = state["best_q"] is None or val_["q"] > state["best_q"]
            if better:
                state.update(best_q=val_["q"], best_release=n, stale=0,
                             best_net={k: v.detach().clone() for k, v in net.state_dict().items()})
            else:
                state["stale"] += 1
                if state["stale"] >= PATIENCE and state["best_net"] is not None:
                    net.load_state_dict(state["best_net"])
                    for grp in opt.param_groups:
                        grp["lr"] *= 0.5
                    state["stale"] = 0
            meta = {"n": n, "at": S._now(), "design": DESIGN, "train_hours": round(state["train_seconds"] / 3600, 2),
                    "updates": state["updates"], "decisions": state["decisions"],
                    "reward": round(float(np.mean(window[-200:])), 4), "signal_cfg": cfg,
                    "signal_label": S.cfg_label(cfg),
                    "validation": {"year": VAL_YEAR, "sizer": val_, "rule": base_val, "best_so_far": better}}
            torch.save({"net": net.state_dict(), "meta": meta}, SIZER_DIR / f"sizer_release_{n:04d}.pt")
            (SIZER_DIR / f"sizer_release_{n:04d}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            S.add_event("release", f"RL sizer release {n}: {VAL_YEAR} {val_['return']:+.1%} DD {val_['max_dd']:.0%} "
                                   f"vs rule {base_val['return']:+.1%} DD {base_val['max_dd']:.0%}")
            print(f"[{S._now()}] sizer: SIZER RELEASE {n} - {VAL_YEAR} {val_} vs rule {base_val} "
                  f"{'BEST' if better else 'stale ' + str(state['stale'])}", flush=True)
            last_release = time.time()
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
