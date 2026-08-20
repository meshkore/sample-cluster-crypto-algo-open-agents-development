"""Train ONE symbol-agnostic oracle-net on the whole liquid universe, on the GPU.

The single-symbol version proved the pipeline; this trains the same causal TCN on
every symbol at once, which is the point of the exercise — a net that has seen a
swing set up on fourteen different coins has learned the swing, not BTC's price
history. Nothing about the model changes: the features are stationary, so pooling
symbols is just more examples of the same thing.

    universe (research, < 2026)  ->  pooled.build_pooled  ->  Xz [ΣN, F], y [ΣN]
    windows never cross a symbol boundary; val is each symbol's own recent slice
    standardise on the pooled TRAIN rows only, train with mixed precision
    report pooled accuracy and the mean per-symbol return of following the net
    export {weights, standardiser, config, model_card} for infer.py / the brain

The pooled table is a few hundred MB, so it lives on the GPU whole and every batch
is a gather — no streaming needed at this universe size.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torch import nn

from . import universe
from .features import Standardizer
from .model import ModelConfig, OracleNet
from .positions import positions_from_prob
from .pooled import Pooled, build_pooled


def _uniqueness_weights(labels: np.ndarray, bounds: dict[str, tuple[int, int]]) -> np.ndarray:
    """Per-bar sample weights = 1 / (length of the contiguous label-run the bar is in),
    normalised to mean 1. Our per-bar-state adaptation of Lopez de Prado's sample
    uniqueness: our labels are hold/flat STATES (not triple-barrier events), so the
    redundancy is a swing's DURATION — a 500-bar hold-run is ~500 near-identical
    examples of one swing. Down-weighting by run length makes each oracle swing
    contribute roughly equal weight, so the net stops over-fitting long trends —
    the generalization gap the sealed 2026 readout exposed. Computed per symbol block
    (via bounds) so runs never merge across a symbol boundary."""
    w = np.ones(len(labels), dtype=np.float32)
    for lo, hi in bounds.values():
        seg = labels[lo:hi]
        if len(seg) == 0:
            continue
        change = np.flatnonzero(np.diff(seg) != 0) + 1
        starts = np.concatenate([[0], change])
        ends = np.concatenate([change, [len(seg)]])
        for s, e in zip(starts.tolist(), ends.tolist()):
            w[lo + s:lo + e] = 1.0 / max(e - s, 1)
    mean = float(w.mean())
    if mean > 0:
        w /= mean
    return w


def _follow_return(close: np.ndarray, position: np.ndarray, local_ends: np.ndarray) -> float:
    log_ret = np.zeros(len(close))
    log_ret[1:] = np.diff(np.log(close))
    held = np.zeros(len(close))
    held[local_ends] = position
    return float(np.exp(np.sum(log_ret[1:] * held[:-1])) - 1.0)


# The anti-churn band is applied to the model's PROBABILITIES after training, so
# it costs no GPU to try many. We sweep this grid on validation for every trained
# net and keep the band that maximises net-of-toll edge — one train explores the
# whole knob that actually governs the toll, instead of one random draw per train.
BAND_ENTERS = (0.55, 0.65, 0.75, 0.85)
BAND_EXITS = (0.15, 0.25, 0.35)
BAND_HOLDS = (16, 48, 96, 192, 288, 384)


def train(
    data_root: str = "backtester/data",
    symbols: list[str] | None = None,
    interval: str = "15m",
    threshold: float = 0.01,
    window: int = 64,
    val_fraction: float = 0.2,
    epochs: int = 12,
    batch_size: int = 8192,
    lr: float = 1e-3,
    dropout: float = 0.1,
    enter: float | None = None,
    exit_: float | None = None,
    min_hold: int | None = None,
    out_dir: str = "research/system06",
    seed: int = 42,
    on_progress=None,
    uniqueness_weighting: float = 0.0,   # 0 = off; >0 = weight loss by swing uniqueness
    ensemble: int = 1,                   # number of seed-varied nets to bag (1 = single net)
    embargo: int = 0,                    # purged-CV embargo (bars) at the train/val split
) -> dict:
    def _emit(**ev):
        if on_progress:
            try:
                on_progress(ev)
            except Exception:  # noqa: BLE001 -- telemetry must never break training
                pass

    torch.manual_seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    symbols = symbols or universe.load()

    _emit(stage="building", msg=f"building pooled dataset · {len(symbols)} symbols · {interval} candles")
    pooled: Pooled = build_pooled(symbols, data_root, interval, threshold, window, val_fraction, embargo=embargo)
    print(f"universe {len(pooled.symbols)} symbols | pooled bars {len(pooled.Xz):,} | "
          f"features {pooled.n_features} | window {window}")
    print(f"windows train {len(pooled.train_ends):,} val {len(pooled.val_ends):,}")

    Xz = torch.tensor(pooled.Xz, dtype=torch.float32, device=device)
    y = torch.tensor(pooled.labels, dtype=torch.float32, device=device)
    offsets = torch.arange(-window + 1, 1, device=device)

    def gather(end_idx: torch.Tensor) -> torch.Tensor:
        return Xz[end_idx[:, None] + offsets[None, :]]

    config = ModelConfig(n_features=pooled.n_features, window=window, dropout=dropout)
    pos = float(pooled.labels[pooled.train_ends].mean())
    pos_weight = torch.tensor([(1 - pos) / max(pos, 1e-6)], device=device)
    # Sample-uniqueness weighting (off by default): weight each sample by 1/run-length
    # so each oracle swing counts equally — an anti-overfitting lever, A/B-tested by
    # the loop. reduction='none' so we can apply per-sample weights in the batch.
    uniq_w = None
    if uniqueness_weighting:
        uniq_w = torch.tensor(_uniqueness_weights(pooled.labels, pooled.bounds),
                              dtype=torch.float32, device=device)
    loss_fn = nn.BCEWithLogitsLoss(
        pos_weight=pos_weight, reduction=("none" if uniq_w is not None else "mean"))

    train_ends_t = torch.tensor(pooled.train_ends, device=device)
    n_ensemble = max(1, int(ensemble))
    param_count = int(sum(p.numel() for p in OracleNet(config).parameters()))
    n_train = len(pooled.train_ends)
    batches_per_epoch = max(1, (n_train + batch_size - 1) // batch_size)
    # The facts of what this training is chewing through — emitted once so the
    # monitor can show the shape of the data, not just a clock.
    dataset_facts = {
        "symbols": len(pooled.symbols), "pooled_bars": int(len(pooled.Xz)),
        "features": int(pooled.n_features), "window": int(window),
        "train_windows": int(n_train), "val_windows": int(len(pooled.val_ends)),
        "batch_size": int(batch_size), "batches_per_epoch": int(batches_per_epoch),
        "epochs": int(epochs), "params": param_count, "device": device,
        "oracle_time_in_market": float(pooled.labels[pooled.train_ends].mean()),
        "interval": interval, "ensemble": n_ensemble,
    }
    _emit(stage="training", epoch=0, epochs=epochs, batch=0, batches=batches_per_epoch,
          loss=None, loss_curve=[], dataset=dataset_facts, member=1, ensemble=n_ensemble,
          msg=f"training {n_ensemble} net(s) on {n_train:,} windows across {len(pooled.symbols)} coins")

    # Bagged ensemble: train n_ensemble seed-varied nets; their probabilities are
    # averaged (in _evaluate and infer.export) to cut variance and generalise better.
    nets: list[OracleNet] = []
    loss_curves: list[list[float]] = []
    for member in range(n_ensemble):
        torch.manual_seed(seed + member)
        net = OracleNet(config).to(device)
        optimizer = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
        scaler_amp = torch.cuda.amp.GradScaler(enabled=device == "cuda")
        generator = torch.Generator(device=device).manual_seed(seed + member)
        loss_curve: list[float] = []
        for epoch in range(epochs):
            net.train()
            perm = torch.randperm(len(train_ends_t), generator=generator, device=device)
            total = 0.0
            seen = 0
            for bi, start in enumerate(range(0, len(perm), batch_size)):
                batch = train_ends_t[perm[start:start + batch_size]]
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast(device_type="cuda", enabled=device == "cuda"):
                    raw = loss_fn(net(gather(batch)), y[batch])
                    if uniq_w is not None:
                        wb = uniq_w[batch]
                        loss = (raw * wb).sum() / wb.sum()
                    else:
                        loss = raw
                scaler_amp.scale(loss).backward()
                scaler_amp.step(optimizer)
                scaler_amp.update()
                total += float(loss) * len(batch)
                seen += len(batch)
                # Per-batch telemetry: the consumer throttles disk writes, so calling
                # every batch is cheap and gives the screen maximum movement.
                _emit(stage="training", epoch=epoch + 1, epochs=epochs, batch=bi + 1,
                      batches=batches_per_epoch, loss=total / max(seen, 1),
                      loss_curve=loss_curve + [total / max(seen, 1)], dataset=dataset_facts,
                      samples_done=seen, samples_total=n_train,
                      member=member + 1, ensemble=n_ensemble)
            loss_curve.append(total / len(pooled.train_ends))
            print(f"  [net {member + 1}/{n_ensemble}] epoch {epoch + 1:2d}/{epochs}  loss {loss_curve[-1]:.4f}", flush=True)
            _emit(stage="training", epoch=epoch + 1, epochs=epochs, batch=batches_per_epoch,
                  batches=batches_per_epoch, loss=loss_curve[-1], loss_curve=loss_curve[:],
                  dataset=dataset_facts, epoch_done=True, member=member + 1, ensemble=n_ensemble)
        nets.append(net)
        loss_curves.append(loss_curve)

    loss_curve = loss_curves[0]  # first member's curve is representative for the card

    # If a band is pinned by the caller, evaluate only it; otherwise sweep the grid on
    # the ENSEMBLE-averaged validation probabilities and keep the toll-optimal band.
    _emit(stage="evaluating", epochs=epochs, loss_curve=loss_curve[:], dataset=dataset_facts,
          msg="scoring validation + sweeping anti-churn bands")
    fixed = None if enter is None or exit_ is None or min_hold is None else (enter, exit_, min_hold)
    metrics = _evaluate(nets, gather, y, pooled, device, batch_size, fixed)
    enter, exit_, min_hold = metrics["enter"], metrics["exit"], metrics["min_hold"]
    print(f"\nval accuracy         {metrics['accuracy']:.1%}")
    print(f"val mean net return  {metrics['net_return']:+.2%}  (after toll, per-symbol)")
    print(f"val mean gross       {metrics['gross_return']:+.2%}  (before toll)")
    print(f"val mean buy & hold  {metrics['buy_hold']:+.2%}")
    print(f"val avg trades/sym    {metrics['avg_trades']:.0f}  (best band: enter {enter} exit {exit_} min_hold {min_hold})")
    print(f"symbols net > B&H     {metrics['symbols_beating_bh']}/{len(pooled.symbols)}")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for i, member_net in enumerate(nets):  # member 0 = oracle_net.pt (backward compatible)
        torch.save(member_net.state_dict(), out / ("oracle_net.pt" if i == 0 else f"oracle_net_{i}.pt"))
    (out / "standardizer.json").write_text(json.dumps(pooled.scaler.to_dict()))
    (out / "config.json").write_text(json.dumps({
        "symbols": pooled.symbols, "interval": interval, "threshold": threshold,
        "model": config.to_dict(), "val_metrics": metrics,
        "hysteresis": {"enter": enter, "exit": exit_, "min_hold": min_hold},
    }, indent=2))

    card = {
        "family": "system06-oracle-net",
        "system_type": "ai-model",
        "status": "trained",
        "architecture": "Causal TCN (dilated 1-D convolutions)",
        "universe_size": len(pooled.symbols),
        "symbols": pooled.symbols,
        "interval": interval, "threshold": threshold,
        "features": config.n_features, "window": window,
        "parameters": param_count, "ensemble": n_ensemble,
        "epochs": epochs, "final_loss": loss_curve[-1] if loss_curve else None,
        "loss_curve": loss_curve,
        "enter": enter, "exit": exit_, "min_hold": min_hold,
        "val_accuracy": metrics["accuracy"],
        "val_net_return": metrics["net_return"],
        "val_gross_return": metrics["gross_return"],
        "val_buy_hold": metrics["buy_hold"],
        "val_avg_trades": metrics["avg_trades"],
        "symbols_beating_bh": metrics["symbols_beating_bh"],
        "oracle_time_in_market": pos,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / "model_card.json").write_text(json.dumps(card, indent=2))
    print(f"\nexported to {out}/  ({len(pooled.symbols)} symbols, {param_count:,} params)")
    return metrics


def _band_metrics(per_symbol, enter, exit_, min_hold, round_trip=0.003) -> dict:
    """Score one anti-churn band across all symbols' precomputed val probabilities."""
    gross, nets, bhs, trades, beating = [], [], [], [], 0
    for sym_prob, close, local, bh in per_symbol:
        pos = positions_from_prob(sym_prob, enter, exit_, min_hold)
        gross_ret = _follow_return(close, pos, local)
        entries = int(pos[0]) + int(np.sum((pos[1:] == 1) & (pos[:-1] == 0)))
        net_ret = gross_ret - entries * round_trip
        gross.append(gross_ret); nets.append(net_ret); bhs.append(bh); trades.append(entries)
        beating += int(net_ret > bh)
    return {
        "enter": enter, "exit": exit_, "min_hold": min_hold,
        "net_return": float(np.mean(nets)) if nets else 0.0,       # after toll — the score
        "gross_return": float(np.mean(gross)) if gross else 0.0,   # before toll, for context
        "buy_hold": float(np.mean(bhs)) if bhs else 0.0,
        "avg_trades": float(np.mean(trades)) if trades else 0.0,
        "symbols_beating_bh": beating,
    }


def _evaluate(nets, gather, y, pooled: Pooled, device, batch_size, fixed=None) -> dict:
    """Val probabilities computed once; then the best anti-churn band net of toll.

    `nets` is one net or a bagged ensemble; ensemble members' sigmoid probabilities
    are averaged before band selection, exactly as infer.export does at inference.

    The band is applied to the model's probabilities, so sweeping the whole grid
    costs no GPU — one trained net explores the entire knob that governs the toll.
    Everything here is the held-out validation slice; 2026 is never touched. Band
    selection on the same val it scores adds a mild optimistic bias — the sealed
    2026 readout stays the true out-of-sample check.
    """
    if not isinstance(nets, (list, tuple)):
        nets = [nets]
    for net in nets:
        net.eval()
    val_ends = pooled.val_ends
    val_ends_t = torch.tensor(val_ends, device=device)
    probs = []
    with torch.no_grad():
        for start in range(0, len(val_ends_t), batch_size):
            batch = val_ends_t[start:start + batch_size]
            xw = gather(batch)
            with torch.autocast(device_type="cuda", enabled=device == "cuda"):
                acc = None
                for net in nets:
                    s = torch.sigmoid(net(xw)).float()
                    acc = s if acc is None else acc + s
                p = acc / len(nets)
            probs.append(p.cpu().numpy())
    prob = np.concatenate(probs) if probs else np.array([])
    truth = y[val_ends].cpu().numpy().astype(np.int8)
    accuracy = float(((prob > 0.5).astype(np.int8) == truth).mean()) if len(truth) else 0.0

    # Precompute each symbol's val probabilities, close, indices and buy&hold ONCE
    # so the band grid is a pure-numpy loop over cached arrays.
    prob_by_global = dict(zip(val_ends.tolist(), prob.tolist()))
    per_symbol = []
    for symbol, sym_val in pooled.val_ends_by_symbol.items():
        offset = pooled.bounds[symbol][0]
        local = sym_val - offset
        sym_prob = np.array([prob_by_global[g] for g in sym_val.tolist()], dtype=float)
        close = pooled.close[symbol]
        lo, hi = int(local[0]), int(local[-1])
        bh = float(close[hi] / close[lo] - 1.0)
        per_symbol.append((sym_prob, close, local, bh))

    if fixed is not None:
        best = _band_metrics(per_symbol, *fixed)
    else:
        best = None
        for e in BAND_ENTERS:
            for x in BAND_EXITS:
                if x >= e:
                    continue
                for h in BAND_HOLDS:
                    m = _band_metrics(per_symbol, e, x, h)
                    if best is None or (m["net_return"] - m["buy_hold"]) > (best["net_return"] - best["buy_hold"]):
                        best = m
    best["accuracy"] = accuracy
    best["val_windows"] = int(len(val_ends))
    return best


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=None, help="comma list; default = the saved universe")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--window", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--out-dir", default="research/system06")
    args = parser.parse_args(argv)
    symbols = [s for s in args.symbols.split(",") if s] if args.symbols else None
    train(
        data_root=args.data_root, symbols=symbols, interval=args.interval,
        threshold=args.threshold, window=args.window, val_fraction=args.val_fraction,
        epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, out_dir=args.out_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
