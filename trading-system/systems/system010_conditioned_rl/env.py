"""The environment the policy learns in: thousands of short episodes, all inside R, on the GPU.

**The simple version, on the operator's word** (2026-09-30: *"as simple as possible... I
don't want a complex trading system, because that did not work in any of the previous
cases"*). One symbol per episode, one decision per bar, two actions:

    0  be flat        1  be long

An episode starts on a bar where the region R holds, with the position flat, and runs a
fixed `horizon` bars (384 = four days). The policy may ENTER only while R holds - outside
it the "be long" action is masked away for a flat book - and may EXIT at any bar. At the
horizon the position is closed and charged. That is the whole game: *inside the zone where
the best trades live, learn which of them to take and when to leave.*

Reward per bar, in basis points so the learner sees numbers near one:

    position * log(close[t+1] / close[t])          what the bar paid
  - half_cost * |position change|                  0.15% each way, the backtester's toll
  - lambda * increase in the episode's drawdown    the operator's criterion, made local

Observation: the 44 frozen market columns at the bar (standardised on training years only,
clipped at 5), then the book: position, unrealised log return since entry, bars held / 96,
and the region bit. No window, no model of the book beyond that - four numbers.

**This is a fast approximation of the instrument, not the instrument.** It exists so that
millions of decisions fit on one GPU. It charges the same round trip and fills at the bar's
close. Every number a decision is taken on - validation, the exams, anything shown to the
operator - comes from the three-slot book in `research/system10/tools/conditions.py`, and
S10-12 replays the exported policy through the frozen backtester before anything trades.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

HALF_COST = 0.0015
BPS = 1e4
N_BOOK = 4          # position, unrealised, bars held, region bit


@dataclass
class Tape:
    """Every training bar of every symbol, concatenated, resident on the device."""

    x: torch.Tensor          # (n, 44) standardised features, float16
    logp: torch.Tensor       # (n,) log close
    inside: torch.Tensor     # (n,) bool, R holds
    starts: torch.Tensor     # (m,) legal episode starts: in R, and `horizon` bars left in-symbol
    horizon: int

    @property
    def obs_dim(self) -> int:
        return self.x.shape[1] + N_BOOK


def build_tape(pieces: list[dict], mean: np.ndarray, std: np.ndarray, horizon: int,
               device: str) -> Tape:
    """`pieces`: per symbol {"X", "close", "inside"} already cut to the training years."""
    xs, lps, ins, starts, off = [], [], [], [], 0
    for p in pieces:
        n = len(p["close"])
        if n <= horizon + 1:
            continue
        X = np.clip((p["X"] - mean) / std, -5, 5)
        ok = np.isfinite(X).all(axis=1) & np.isfinite(p["close"]) & (p["close"] > 0)
        X = np.nan_to_num(X, nan=0.0)
        inside = p["inside"] & ok
        legal = np.flatnonzero(inside[: n - horizon - 1])
        xs.append(X.astype(np.float16)); lps.append(np.log(np.where(ok, p["close"], 1.0)))
        ins.append(inside); starts.append(legal + off)
        off += n
    return Tape(x=torch.tensor(np.concatenate(xs), device=device),
                logp=torch.tensor(np.concatenate(lps), dtype=torch.float32, device=device),
                inside=torch.tensor(np.concatenate(ins), device=device),
                starts=torch.tensor(np.concatenate(starts), device=device),
                horizon=horizon)


class BatchEnv:
    """`n_envs` episodes stepped together; a finished episode restarts on a fresh R bar."""

    def __init__(self, tape: Tape, n_envs: int, lam: float, seed: int):
        self.tape, self.n, self.lam = tape, n_envs, lam
        self.gen = torch.Generator(device=tape.x.device).manual_seed(seed)
        dev = tape.x.device
        self.t = torch.zeros(n_envs, dtype=torch.long, device=dev)
        self.age = torch.zeros(n_envs, dtype=torch.long, device=dev)
        self.pos = torch.zeros(n_envs, device=dev)
        self.entry = torch.zeros(n_envs, device=dev)
        self.held = torch.zeros(n_envs, device=dev)
        self.eq = torch.zeros(n_envs, device=dev)
        self.peak = torch.zeros(n_envs, device=dev)
        self._restart(torch.ones(n_envs, dtype=torch.bool, device=dev))

    def _restart(self, which: torch.Tensor) -> None:
        k = int(which.sum())
        if not k:
            return
        pick = torch.randint(len(self.tape.starts), (k,), generator=self.gen, device=self.t.device)
        self.t[which] = self.tape.starts[pick]
        for buf in (self.age, self.pos, self.entry, self.held, self.eq, self.peak):
            buf[which] = 0

    def observe(self) -> tuple[torch.Tensor, torch.Tensor]:
        """Observation and the legal-action mask (True = allowed), both (n_envs, ...)."""
        t = self.t
        inside = self.tape.inside[t].float()
        unreal = torch.where(self.pos > 0, self.tape.logp[t] - self.entry, torch.zeros_like(self.pos))
        book = torch.stack([self.pos, unreal * 10.0, self.held / 96.0, inside], dim=1)
        obs = torch.cat([self.tape.x[t].float(), book], dim=1)
        can_long = (self.pos > 0) | (inside > 0)
        mask = torch.stack([torch.ones_like(can_long), can_long], dim=1)
        return obs, mask

    def step(self, action: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Apply target positions; return (reward in bps, done)."""
        t = self.t
        new = action.float()
        change = (new - self.pos).abs()
        self.entry = torch.where((new > 0) & (self.pos == 0), self.tape.logp[t], self.entry)
        bar = self.tape.logp[t + 1] - self.tape.logp[t]
        r = new * bar - HALF_COST * change
        self.held = torch.where(new > 0, self.held + 1, torch.zeros_like(self.held))
        self.pos = new
        self.t = t + 1
        self.age += 1
        done = self.age >= self.tape.horizon
        # The horizon closes the position and charges the exit.
        r = r - HALF_COST * (done & (self.pos > 0)).float()
        self.eq = self.eq + r
        dd_before = self.peak - (self.eq - r)
        self.peak = torch.maximum(self.peak, self.eq)
        dd_after = self.peak - self.eq
        reward = (r - self.lam * torch.clamp(dd_after - dd_before, min=0.0)) * BPS
        self._restart(done)
        return reward, done
