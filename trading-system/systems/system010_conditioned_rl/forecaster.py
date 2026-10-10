"""The signal forecaster, trained continuously on the GPU: the strength behind every trade.

The operator, 2026-10-10: *"I understand we are training continuously ... if we were really
doing that, the GPU should be at the top all the time."* The evidence of the same day says
where training pays: the release's next-day forecast, used as the signal's STRENGTH to size
each entry, halved the drawdown at the same return. So the GPU's 24/7 job is to make that
forecast better - not an RL policy that lost to the rule eight releases in a row.

What it does, forever:
    variant k   an MLP (width and depth drawn from ARCHS, seed k) on the full picture
                (World.full(): 64 columns) predicting the next-day return (96 bars), Huber
                loss, AdamW, a few epochs over up to ROWS rows
    folds       walk-forward: the model for year N trains only on bars whose 96-bar window
                ends by N-1 - years 2021..2026 (the 2026 fold trains on <= 2025 and is the
                only one that may be applied to 2026)
    saved       _auto_forecaster/<variant>_<N>.pt, plus registry.jsonl with each fold's
                out-of-sample rank correlation (IC) on year N (N <= 2025)
    ensemble    `predict(world, N)` averages every variant that has fold N - the search's
                `forecast: ensemble` option reads it, so the forecast improves as variants
                accumulate. Nothing reads 2026 to choose: the 2026 fold has no IC here.
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

DIR = S.OUT / "_auto_forecaster"
REGISTRY = S.OUT / "rnd" / "forecaster_registry.jsonl"
FOLDS = (2021, 2022, 2023, 2024, 2025, 2026)
K = 96
ROWS = 6_000_000          # effectively every row (~3.5 M)
EPOCHS = 30               # 2026-10-10: at 6 a fold took 3 s and the GPU idled
BATCH = 8192
ARCHS = ((512, 3), (1024, 3), (1024, 4), (2048, 3), (256, 2))


class MLP(nn.Module):
    def __init__(self, d_in: int, width: int, depth: int):
        super().__init__()
        layers, d = [], d_in
        for _ in range(depth):
            layers += [nn.Linear(d, width), nn.GELU(), nn.Dropout(0.1)]
            d = width
        layers.append(nn.Linear(d, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x).squeeze(-1)


def _rows(world: S.World, last: int) -> tuple[np.ndarray, np.ndarray]:
    feats, tgt = world.full(), world.fwd(K)
    xs, ys = [], []
    for s, d in world.per.items():
        t = tgt[s]
        ok = world.valid[s] & (d["year"] <= last) & (t["end_year"] <= last) & np.isfinite(t["fwd"])
        idx = np.flatnonzero(ok)
        if len(idx):
            xs.append(feats[s][idx]); ys.append(np.clip(t["fwd"][idx], -0.3, 0.3))
    return np.concatenate(xs), np.concatenate(ys).astype(np.float32)


def _ic(world: S.World, model: MLP, year: int, device: str) -> float | None:
    """Out-of-sample rank correlation of the forecast with the realised next day, year N."""
    feats, tgt = world.full(), world.fwd(K)
    p, y = [], []
    for s, d in world.per.items():
        t = tgt[s]
        ok = world.valid[s] & (d["year"] == year) & np.isfinite(t["fwd"])
        idx = np.flatnonzero(ok)
        if len(idx):
            p.append(_score(model, feats[s][idx], device)); y.append(t["fwd"][idx])
    if not p:
        return None
    p, y = np.concatenate(p), np.concatenate(y)
    rk = lambda a: np.argsort(np.argsort(a)).astype(np.float64)  # noqa: E731
    return round(float(np.corrcoef(rk(p), rk(y))[0, 1]), 4)


@torch.no_grad()
def _score(model: MLP, x: np.ndarray, device: str) -> np.ndarray:
    model.eval()
    out = []
    for i in range(0, len(x), 262_144):
        out.append(model(torch.tensor(x[i:i + 262_144], device=device)).float().cpu().numpy())
    return np.concatenate(out) / 100.0


def train_fold(world: S.World, variant: int, year: int, device: str) -> dict:
    width, depth = ARCHS[variant % len(ARCHS)]
    rng = np.random.default_rng(1000 + variant)
    torch.manual_seed(1000 + variant)
    X, Y = _rows(world, year - 1)
    pick = rng.choice(len(X), min(ROWS, len(X)), replace=False)
    x = torch.tensor(X[pick], device=device)
    y = torch.tensor(Y[pick] * 100.0, device=device)
    del X, Y
    model = MLP(x.shape[1], width, depth).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    steps = EPOCHS * (len(x) // BATCH)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=1e-3, total_steps=max(steps, 1))
    loss_fn = nn.HuberLoss(delta=2.0)
    t0 = time.time()
    model.train()
    for _ in range(EPOCHS):
        perm = torch.randperm(len(x), device=device)
        for i in range(0, len(x) - BATCH + 1, BATCH):
            j = perm[i:i + BATCH]
            loss = loss_fn(model(x[j]), y[j])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
    DIR.mkdir(parents=True, exist_ok=True)
    torch.save({"state": model.state_dict(), "width": width, "depth": depth, "d_in": x.shape[1]},
               DIR / f"v{variant:04d}_{year}.pt")
    row = {"at": S._now(), "variant": variant, "fold": year, "width": width, "depth": depth,
           "rows": len(x), "minutes": round((time.time() - t0) / 60, 2),
           "ic": _ic(world, model, year, device) if year <= 2025 else None}
    with REGISTRY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def complete_variants(year: int) -> list[Path]:
    return sorted(DIR.glob(f"v*_{year}.pt")) if DIR.is_dir() else []


def predict(world: S.World, year: int, device: str, upto: int | None = None) -> dict | None:
    """The ensemble forecast for every bar of every symbol, from the fold-`year` models (each
    trained on data ending by year-1). Applied to year `year` only. None if no model yet.
    `upto` caps the number of variants, so a release can be re-read with the same ensemble."""
    paths = complete_variants(year)
    if upto is not None:
        paths = [p for p in paths if int(p.stem[1:5]) < upto]
    if not paths:
        return None
    feats = world.full()
    out = {s: np.zeros(len(d["X"]), dtype=np.float32) for s, d in world.per.items()}
    for p in paths:
        saved = torch.load(p, map_location=device, weights_only=False)
        m = MLP(saved["d_in"], saved["width"], saved["depth"]).to(device)
        m.load_state_dict(saved["state"])
        for s, d in world.per.items():
            sel = d["year"] == year
            if sel.any():
                out[s][sel] += _score(m, feats[s][sel], device) / len(paths)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 signal forecaster, trained continuously (GPU)")
    ap.add_argument("--hours", type=float, default=24.0)
    args = ap.parse_args()
    device = "cuda"
    started = time.time()
    print(f"[{S._now()}] forecaster: loading research bars (<= 2025)", flush=True)
    world = S.World()
    world.full()
    done = {(r["variant"], r["fold"]) for r in S.ledger_rows(REGISTRY)}
    variant = max((v for v, _ in done), default=-1)
    while time.time() - started < args.hours * 3600 and not S.STOP.exists():
        if all((variant, f) in done for f in FOLDS) or variant < 0:
            variant += 1
        for f in FOLDS:
            if (variant, f) in done or S.STOP.exists():
                continue
            row = train_fold(world, variant, f, device)
            done.add((variant, f))
            print(f"[{S._now()}] forecaster: variant {variant} {row['width']}x{row['depth']} fold {f} "
                  f"IC {row['ic']} [{row['minutes']} min]", flush=True)
        n = len(complete_variants(2025))
        if all((variant, f) in done for f in FOLDS):
            ics = [r["ic"] for r in S.ledger_rows(REGISTRY) if r["variant"] == variant and r["ic"] is not None]
            S.add_event("model", f"forecaster variant {variant} done: mean out-of-sample IC "
                                 f"{np.mean(ics):+.3f} (2021-2025); ensemble now {n} variants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
