"""A77: why is a backtest over the TRAINING data not almost perfect?

    PYTHONPATH=trading-system python research/system06/tools/fit_diagnosis.py

The operator's intuition, 2026-09-03, and it is the right question to ask. A model with
enough capacity and enough passes should be able to memorise its own training labels.
Ours reaches ~66% validation accuracy, and the ceiling measurement says that even
inside the research years - the ones it trained on - the book captures 0.03%-5.9% of
what perfect foresight would earn.

There are two very different worlds that look identical from the outside, and one
measurement separates them:

  TRAIN accuracy >> VAL accuracy   ->  it memorises but does not generalise. The cure
                                       is regularisation, more data, less capacity.
  TRAIN accuracy ~= VAL accuracy   ->  it cannot even fit what it has already seen.
                                       That is UNDERFITTING, and the cure is the
                                       opposite: more capacity, more data, longer
                                       training. P34/P35 already pointed here, and P37
                                       died on an 8GB card before finding the ceiling.

Measured on the shipping net, on the same pooled windows train.py builds, with the
same split - so the numbers are comparable to the ones printed during training rather
than to a re-derived quantity.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"


def main() -> int:
    sys.path.insert(0, "trading-system")
    import argparse

    import torch

    # Why a device switch exists at all: two jobs on one 8GB card do not share it,
    # they spill past its memory and collapse (P37 lost an epoch-per-30-minutes to
    # exactly that). So when a training owns the GPU, this runs on the CPU instead of
    # waiting - accuracy on a fair sample of 120k windows carries a standard error
    # near 0.15%, far below any effect worth arguing about.
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=None, help="cuda / cpu (default: cuda if free)")
    ap.add_argument("--cap", type=int, default=400_000, help="max windows per split")
    args = ap.parse_args()

    from system006_oracle_net_15m import universe
    from system006_oracle_net_15m.model import ModelConfig, OracleNet
    from system006_oracle_net_15m.pooled import build_pooled

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg = best["config"]
    window = int(cfg["window"])
    symbols = universe.load()

    # The SAME pooled panel train.py builds, with the same split - so these numbers sit
    # beside the ones printed during training instead of beside a re-derived quantity.
    panel = build_pooled(symbols, data_root=DATA, interval="15m",
                         threshold=float(cfg["threshold"]), window=window,
                         embargo=int(cfg.get("embargo", 0)))
    X, y = panel.Xz, panel.labels
    train_ends, val_ends = panel.train_ends, panel.val_ends
    print(f"pooled windows: {len(train_ends) + len(val_ends):,} "
          f"({len(train_ends):,} train / {len(val_ends):,} val)")

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}   sample cap: {args.cap:,} windows per split")
    # The architecture comes from the champion's OWN config.json, never from a guess:
    # a mismatched width would fail to load, and a mismatched dilation would load and
    # quietly measure a different model.
    model_cfg = ModelConfig.from_dict(
        json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["model"])
    net = OracleNet(model_cfg)
    net.load_state_dict(torch.load(ROOT / "oracle_net.pt", map_location=device))
    net.to(device).eval()
    print(f"net: channels {list(model_cfg.channels)}, window {model_cfg.window}, "
          f"{sum(p.numel() for p in net.parameters()):,} params")

    # Fail loudly on a layout mismatch rather than reshaping until something runs:
    # a silent reshape would measure a different model and report it as this one.
    if X.shape[1] != model_cfg.n_features:
        raise SystemExit(f"panel has {X.shape[1]} features, the shipping net expects "
                         f"{model_cfg.n_features} - the feature set moved under the model")
    Xt = torch.tensor(X, dtype=torch.float32, device=device)
    yt = torch.tensor(y, dtype=torch.float32, device=device)

    def evaluate(ends_arr, tag, cap=None):
        cap = cap or args.cap
        idx = np.asarray(ends_arr)
        if len(idx) > cap:                       # a fair sample beats an OOM
            idx = idx[np.linspace(0, len(idx) - 1, cap).astype(int)]
        probs, labels = [], []
        with torch.no_grad():
            for start in range(0, len(idx), 8192):
                chunk = torch.tensor(idx[start:start + 8192], dtype=torch.long,
                                     device=device)
                # OracleNet.forward expects [batch, window, features] and does its own
                # transpose to conv1d's layout - transposing here as well fed it a
                # window-as-channels tensor and it refused, correctly.
                w = torch.stack([Xt[e - window + 1:e + 1] for e in chunk.tolist()])
                probs.append(torch.sigmoid(net(w)).squeeze(-1).cpu().numpy())
                labels.append(yt[chunk].cpu().numpy())
        p = np.concatenate(probs)
        l = np.concatenate(labels)
        acc = float(((p > 0.5) == (l > 0.5)).mean())
        # The band the book actually trades on: how often is a high-conviction call right?
        hi = p >= float(best["band"]["enter"])
        prec = float((l[hi] > 0.5).mean()) if hi.any() else float("nan")
        print(f"{tag:>6}: accuracy {acc:.1%}   base rate {l.mean():.1%}   "
              f"p>={best['band']['enter']:.2f} on {hi.mean():.1%} of bars, "
              f"right {prec:.1%} of the time")
        return {"accuracy": acc, "base_rate": float(l.mean()),
                "high_conviction_share": float(hi.mean()), "high_conviction_precision": prec,
                "n": int(len(p))}

    tr = evaluate(train_ends, "TRAIN")
    va = evaluate(val_ends, "VAL")
    gap = tr["accuracy"] - va["accuracy"]

    print("\n" + "=" * 78)
    print(f"generalisation gap: {gap:+.1%}")
    if gap < 0.03:
        print("VERDICT: UNDERFITTING. The net cannot fit even the data it has already")
        print("seen, so nothing it fails to catch is explained by 'the future is hard'.")
        print("The cure is more capacity / more data / longer training - not more caution.")
    elif gap > 0.15:
        print("VERDICT: MEMORISING. It fits the past far better than the future, so the")
        print("cure is regularisation and more data, and capacity is NOT the lever.")
    else:
        print("VERDICT: mixed - a real but modest gap. Capacity and data both plausible.")
    print("=" * 78)

    out = ROOT / "rnd" / f"fit_diagnosis_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                               "channels": list(model_cfg.channels), "train": tr, "val": va,
                               "gap": gap}, indent=1), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
