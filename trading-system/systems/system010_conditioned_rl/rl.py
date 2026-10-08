"""Real reinforcement learning, trained for days: PPO deciding every 4 hours inside the conditions.

The operator, 2026-10-06: *"reinforcement learning lives, works, learns by itself - it should
spend hours doing tests and educating its weights"*. The condition search is not that: it
fits small supervised models from scratch in seconds. This is the learner that accumulates.

    decision      every 16 bars (4 h). The first RL run here decided every 15 minutes and
                  learned only that trading costs money (churn, then silence); at 4 h a
                  typical move is several times the 0.30% toll, so the signal is not drowned.
    actions       0 flat, 1 half position, 2 full position (long only, spot)
    state         the full market picture (World.full(): the coin's 44 columns, 1h/4h/1d/1w
                  views of it and of BTC, the lagged macro panel), the regime bit, breadth,
                  and the book: position, unrealised return, time held, episode drawdown
    conditions    a position may be OPENED or ENLARGED only where the condition search's
                  current champion gate holds; outside it the policy may only hold or cut.
                  Episodes start inside the gate. Same rule in training and in evaluation.
    reward        position x the 4 h log return - 0.15% per unit traded, in percent; at the
                  episode's end, minus LAMBDA x the episode's maximum drawdown. (v1 charged
                  every increase of drawdown as it happened, at 0.5: that bills every dip
                  that later recovers, so always-long scored -59% an episode against +2.8%
                  without it, and the policy learned to stay flat. Measured 2026-10-06.)
    data          2017-08 to 2025-12-31 only. Each episode samples one of the 16 phases of
                  the 4 h grid, so the 8 years read as 16 slightly different histories.

Weights accumulate across restarts (checkpoint + optimizer state). Every RELEASE_EVERY_S the
current policy is published under research/system10/releases_rl/ - by the clock, never by
its results - and the release evaluator reads it on 2025 (in-sample) and 2026 (forward).
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
RL_DIR = OUT / "releases_rl"
CKPT = OUT / "_auto_rl_checkpoint.pt"
STEP = 16                 # bars per decision (4 h)
EPISODE = 180             # decisions per episode (30 days)
HALF_COST = 0.0015
LAMBDA = 0.1              # per unit of the episode's max drawdown, charged once at its end
REWARD_VERSION = 2        # a checkpoint trained on another reward is not resumed
RELEASE_EVERY_S = 2 * 3600
CONTROL = OUT / "rl_control.json"   # written by the 8-hourly review; read live, no restart
ENT_COEF = 0.01


def control(opt) -> dict:
    """Apply the review's settings (entropy, learning rate, drawdown price) if any."""
    global ENT_COEF, LAMBDA
    if not CONTROL.is_file():
        return {}
    try:
        c = json.loads(CONTROL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    ENT_COEF = float(c.get("ent_coef", ENT_COEF))
    LAMBDA = float(c.get("lambda", LAMBDA))
    for g in opt.param_groups:
        g["lr"] = float(c.get("lr", g["lr"]))
    return c
ACTIONS = torch.tensor([0.0, 0.5, 1.0])
N_BOOK = 6                # regime, breadth, position, unrealised, held, episode drawdown


class Net(nn.Module):
    def __init__(self, obs_dim: int, hidden: int = 256):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(obs_dim, hidden), nn.Tanh(),
                                  nn.Linear(hidden, hidden), nn.Tanh())
        self.pi = nn.Linear(hidden, 3)
        self.v = nn.Linear(hidden, 1)
        nn.init.zeros_(self.pi.weight)
        nn.init.zeros_(self.pi.bias)

    def forward(self, obs, mask):
        h = self.body(obs)
        logits = self.pi(h).masked_fill(~mask, -1e9)
        return torch.distributions.Categorical(logits=logits), self.v(h).squeeze(-1)


def clean(x: np.ndarray) -> np.ndarray:
    """Standardized features, finite and inside +-10 (NaN reads as the mean)."""
    return np.clip(np.nan_to_num(x, nan=0.0, posinf=10.0, neginf=-10.0), -10.0, 10.0)


def legal(gate_t: torch.Tensor, cur: torch.Tensor) -> torch.Tensor:
    """Open or enlarge only inside the conditions; outside, hold or cut."""
    a = torch.arange(3, device=cur.device)[None, :]
    return gate_t[:, None] | (a <= cur[:, None])


class Tape:
    """Every symbol's bars up to `last_year`, concatenated on the device."""

    def __init__(self, world: S.World, gate: dict, regime: dict, last_year: int, device: str):
        feats = world.full()
        xs, lps, gs, rg, br, starts, off = [], [], [], [], [], [], 0
        need = EPISODE * STEP + 1
        for s, d in world.per.items():
            sel = d["year"] <= last_year
            n = int(sel.sum())
            if n <= need + STEP:
                continue
            close = d["close"][sel]
            ok = np.isfinite(close) & (close > 0)
            # bars outside `valid` carry NaN features; an episode can walk into them
            xs.append(clean(feats[s][sel]).astype(np.float16))
            lps.append(np.log(np.where(ok, close, 1.0)))
            gs.append(gate[s][sel] & world.valid[s][sel])
            rg.append(regime[s][sel].astype(np.float32) * 2 - 1)
            br.append(d["breadth"][sel].astype(np.float32) * 2 - 1)
            legal_start = np.flatnonzero(gs[-1][: n - need - STEP])
            starts.append(legal_start + off)
            off += n
        t = lambda a, **k: torch.tensor(np.concatenate(a), device=device, **k)  # noqa: E731
        self.x = t(xs)
        self.logp = t(lps, dtype=torch.float32)
        self.gate = t(gs)
        self.regime = t(rg)
        self.breadth = t(br)
        self.starts = t(starts)
        self.obs_dim = self.x.shape[1] + N_BOOK


class Env:
    def __init__(self, tape: Tape, n: int, seed: int):
        self.tape, self.n = tape, n
        dev = tape.x.device
        self.gen = torch.Generator(device=dev).manual_seed(seed)
        z = lambda dt=torch.float32: torch.zeros(n, dtype=dt, device=dev)  # noqa: E731
        self.t, self.age = z(torch.long), z(torch.long)
        self.cur = z(torch.long)
        self.entry, self.held, self.eq, self.peak, self.mdd = z(), z(), z(), z(), z()
        self.reset(torch.ones(n, dtype=torch.bool, device=dev))

    def reset(self, which):
        k = int(which.sum())
        if not k:
            return
        pick = torch.randint(len(self.tape.starts), (k,), generator=self.gen, device=self.t.device)
        phase = torch.randint(STEP, (k,), generator=self.gen, device=self.t.device)
        self.t[which] = self.tape.starts[pick] + phase
        for b in (self.age, self.cur):
            b[which] = 0
        for b in (self.entry, self.held, self.eq, self.peak, self.mdd):
            b[which] = 0.0

    def observe(self):
        tp, t = self.tape, self.t
        pos = ACTIONS.to(t.device)[self.cur]
        unreal = torch.where(pos > 0, tp.logp[t] - self.entry, torch.zeros_like(pos))
        book = torch.stack([tp.regime[t], tp.breadth[t], pos, unreal * 10,
                            self.held / 30.0, (self.peak - self.eq) * 10], dim=1)
        return torch.cat([tp.x[t].float(), book], dim=1), legal(tp.gate[t], self.cur)

    def step(self, a):
        tp, t = self.tape, self.t
        acts = ACTIONS.to(t.device)
        old, new = acts[self.cur], acts[a]
        self.entry = torch.where((new > 0) & (old == 0), tp.logp[t], self.entry)
        ret = tp.logp[t + STEP] - tp.logp[t]
        r = new * ret - HALF_COST * (new - old).abs()
        self.held = torch.where(new > 0, self.held + 1, torch.zeros_like(self.held))
        self.cur = a
        self.t = t + STEP
        self.age += 1
        done = self.age >= EPISODE
        r = r - HALF_COST * new * done.float()
        self.eq = self.eq + r
        self.peak = torch.maximum(self.peak, self.eq)
        self.mdd = torch.maximum(self.mdd, self.peak - self.eq)
        reward = (r - LAMBDA * self.mdd * done.float()) * 100
        self.reset(done)
        return reward, done, new


@torch.no_grad()
def positions(world: S.World, net: Net, gate: dict, regime: dict, year: int, device: str) -> dict:
    """The policy stepped through one whole year, every symbol at once, deciding every 4 h and
    holding in between. Greedy (argmax): a release is judged as it would trade."""
    feats = world.full()
    syms = [s for s in world.per if (world.per[s]["year"] == year).any()]
    idx = {s: np.flatnonzero(world.per[s]["year"] == year) for s in syms}
    T = max(len(v) for v in idx.values())
    out = {s: np.zeros(len(world.per[s]["X"]), dtype=np.float32) for s in world.per}
    acts = ACTIONS.to(device)
    cur = torch.zeros(len(syms), dtype=torch.long, device=device)
    entry = torch.zeros(len(syms), device=device)
    held = torch.zeros(len(syms), device=device)
    eq = torch.zeros(len(syms), device=device)
    peak = torch.zeros(len(syms), device=device)
    logp = {s: np.log(np.maximum(world.per[s]["close"][idx[s]], 1e-12)) for s in syms}
    last_lp = torch.zeros(len(syms), device=device)
    for t0 in range(0, T, STEP):
        rows, lp_now, g_now, rg, br, live = [], [], [], [], [], []
        for s in syms:
            i = idx[s][min(t0, len(idx[s]) - 1)]
            d = world.per[s]
            rows.append(clean(feats[s][i])); lp_now.append(logp[s][min(t0, len(idx[s]) - 1)])
            g_now.append(bool(gate[s][i] and world.valid[s][i]))
            rg.append(float(regime[s][i]) * 2 - 1); br.append(float(d["breadth"][i]) * 2 - 1)
            live.append(t0 < len(idx[s]))
        lpt = torch.tensor(lp_now, dtype=torch.float32, device=device)
        pos = acts[cur]
        # mark the book to this decision before reading it
        eq = eq + pos * (lpt - last_lp) * (last_lp != 0).float()
        peak = torch.maximum(peak, eq)
        unreal = torch.where(pos > 0, lpt - entry, torch.zeros_like(pos))
        book = torch.stack([torch.tensor(rg, device=device), torch.tensor(br, device=device), pos,
                            unreal * 10, held / 30.0, (peak - eq) * 10], dim=1)
        obs = torch.cat([torch.tensor(np.stack(rows), dtype=torch.float32, device=device), book], dim=1)
        dist, _ = net(obs, legal(torch.tensor(g_now, device=device), cur))
        a = dist.probs.argmax(dim=-1)
        a = torch.where(torch.tensor(live, device=device), a, torch.zeros_like(a))
        new = acts[a]
        entry = torch.where((new > 0) & (pos == 0), lpt, entry)
        held = torch.where(new > 0, held + 1, torch.zeros_like(held))
        cur, last_lp = a, lpt
        newc = new.cpu().numpy()
        for j, s in enumerate(syms):
            seg = idx[s][t0:t0 + STEP]
            out[s][seg] = newc[j]
    return out


def champion_gate(world: S.World) -> tuple[dict, dict, dict]:
    champ = S.champion(S.ledger())
    cfg = champ["cfg"] if champ else {"regime_ma": None, "b_up": 0.0, "b_down": 0.0}
    g, regime = S.gate(world, cfg)
    return g, regime, cfg


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 PPO trainer, 24/7, releases by the clock")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--envs", type=int, default=4096)
    ap.add_argument("--steps", type=int, default=64)
    ap.add_argument("--seed", type=int, default=20261006)
    ap.add_argument("--release-every", type=float, default=RELEASE_EVERY_S)
    ap.add_argument("--out", default=str(RL_DIR))
    args = ap.parse_args()
    device = "cuda"
    started = time.time()
    rl_dir = Path(args.out)
    rl_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{S._now()}] rl: loading research bars (<= 2025)", flush=True)
    world = S.World()
    gate, regime, cfg = champion_gate(world)
    tape = Tape(world, gate, regime, 2025, device)
    net = Net(tape.obs_dim).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=2e-4)
    state = {"updates": 0, "decisions": 0, "train_seconds": 0.0, "releases": 0}
    if CKPT.is_file():
        saved = torch.load(CKPT, map_location=device, weights_only=False)
        if saved.get("obs_dim") == tape.obs_dim and saved.get("reward_version") == REWARD_VERSION:
            net.load_state_dict(saved["net"]); opt.load_state_dict(saved["opt"]); state = saved["state"]
            print(f"[{S._now()}] rl: resumed - {state['updates']} updates, "
                  f"{state['train_seconds'] / 3600:.1f} h of training", flush=True)
    env = Env(tape, args.envs, args.seed + state["updates"])
    ctl = control(opt)
    if ctl:
        print(f"[{S._now()}] rl: control {ctl}", flush=True)
    gamma, lam, clip, epochs, mb = 0.99, 0.95, 0.2, 4, 16_384
    last_release = time.time()
    window = []
    started = time.time()  # the budget counts training, not the bar load
    print(f"[{S._now()}] rl: training inside {S.cfg_label(cfg)} - {len(tape.starts):,} legal starts", flush=True)
    while time.time() - started < args.hours * 3600 and not S.STOP.exists():
        t0 = time.time()
        buf = {k: [] for k in ("o", "m", "a", "lp", "v", "r", "d", "pos")}
        with torch.no_grad():
            for _ in range(args.steps):
                o, m = env.observe()
                dist, v = net(o, m)
                a = dist.sample()
                r, d, pos = env.step(a)
                for k, x in zip(buf, (o, m, a, dist.log_prob(a), v, r, d, pos)):
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
        o_f, m_f, a_f = torch.cat(buf["o"]), torch.cat(buf["m"]), torch.cat(buf["a"])
        lp_f, adv_f = torch.cat(buf["lp"]), adv.flatten()
        adv_f = (adv_f - adv_f.mean()) / (adv_f.std() + 1e-8)
        for _ in range(epochs):
            perm = torch.randperm(len(a_f), device=device)
            for i in range(0, len(a_f), mb):
                j = perm[i:i + mb]
                dist, v = net(o_f[j], m_f[j])
                # an unclamped log-ratio overflows exp() to inf, and inf x 0 in the backward
                # pass turned the weights to NaN mid-update (2026-10-06, twice)
                ratio = torch.exp((dist.log_prob(a_f[j]) - lp_f[j]).clamp(-20.0, 20.0))
                pg = -torch.min(ratio * adv_f[j], ratio.clamp(1 - clip, 1 + clip) * adv_f[j]).mean()
                loss = pg + 0.5 * (v - ret[j]).pow(2).mean() - ENT_COEF * dist.entropy().mean()
                if not torch.isfinite(loss):
                    state["skipped"] = state.get("skipped", 0) + 1
                    continue
                opt.zero_grad(); loss.backward()
                gn = nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                if not torch.isfinite(gn):
                    state["skipped"] = state.get("skipped", 0) + 1
                    opt.zero_grad()
                    continue
                opt.step()
        state["updates"] += 1
        state["decisions"] += args.envs * args.steps
        state["train_seconds"] += time.time() - t0
        window.append({"reward": float(rew.mean()), "in_market": float(torch.stack(buf["pos"]).mean())})
        if state["updates"] % 50 == 0:
            new = control(opt)
            if new != ctl:
                ctl = new
                print(f"[{S._now()}] rl: control {ctl}", flush=True)
            w = window[-50:]
            print(f"[{S._now()}] rl: update {state['updates']} ({state['train_seconds'] / 3600:.2f} h) "
                  f"reward {np.mean([x['reward'] for x in w]):+.3f} in market "
                  f"{np.mean([x['in_market'] for x in w]):.0%} skipped {state.get('skipped', 0)}", flush=True)
            torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "state": state,
                        "obs_dim": tape.obs_dim, "reward_version": REWARD_VERSION}, CKPT)
        if time.time() - last_release >= args.release_every:
            state["releases"] += 1
            n = len(list(rl_dir.glob("rl_release_*.json"))) + 1
            w = window[-200:]
            meta = {"n": n, "at": S._now(), "train_hours": round(state["train_seconds"] / 3600, 2),
                    "updates": state["updates"], "decisions": state["decisions"],
                    "mean_reward": round(float(np.mean([x["reward"] for x in w])), 4),
                    "in_market": round(float(np.mean([x["in_market"] for x in w])), 4),
                    "conditions": cfg, "conditions_label": S.cfg_label(cfg), "obs_dim": tape.obs_dim,
                    "reward_version": REWARD_VERSION}
            torch.save({"net": net.state_dict(), "meta": meta}, rl_dir / f"rl_release_{n:04d}.pt")
            (rl_dir / f"rl_release_{n:04d}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            S.add_event("release", f"RL release {n}: {meta['train_hours']} h trained, "
                                   f"{meta['decisions'] / 1e6:.0f} M decisions, in market {meta['in_market']:.0%}")
            print(f"[{S._now()}] rl: RL RELEASE {n}", flush=True)
            last_release = time.time()
    torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "state": state, "obs_dim": tape.obs_dim, "reward_version": REWARD_VERSION}, CKPT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
