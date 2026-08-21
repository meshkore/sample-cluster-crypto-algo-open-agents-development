"""Export the net's per-bar hold signal, for every symbol, to one table.

The `system05` pattern: the model runs once, here, over each symbol's whole
series, and writes one bit per bar per symbol. The brain then holds no torch and
no feature code — it looks a (symbol, timestamp) pair up in a table. No lookahead
survives: the signal at bar `i` reads features from bars `<= i`, the model was
fitted only on pre-lock data, and the brain still fills at the next open.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from . import universe
from .channels import load_table  # re-exported: the pure-numpy signal-table reader
from .dataset import Dataset
from .features import Standardizer, build_matrix, combined_store, finite_rows, research_store
from .model import ModelConfig, OracleNet

__all__ = ["export", "validation_signals", "load_table"]


def _epoch_ns(timestamps: np.ndarray) -> np.ndarray:
    return timestamps.astype("datetime64[ns]").astype("int64")


def _causal_uptrend(close: np.ndarray, span: int) -> np.ndarray:
    """1 where price is above its own trailing mean — a causal regime bit per bar.

    Uses only bars `<= i` (a trailing simple mean over `span`), so it never peeks.
    In a broad crash every correlated coin drops below its trend at once, which is
    exactly when the brain should empty the book — the mandate's real defence.
    """
    n = len(close)
    if n == 0:
        return np.zeros(0, dtype=np.int8)
    csum = np.concatenate([[0.0], np.cumsum(close)])
    idx = np.arange(n)
    lo = np.maximum(0, idx - span + 1)
    count = idx - lo + 1
    trailing_mean = (csum[idx + 1] - csum[lo]) / count
    up = (close > trailing_mean).astype(np.int8)
    up[:span // 2] = 0  # not enough history to call a regime yet — treat as risk-off
    return up


def _causal_volratio(close: np.ndarray, short_span: int = 96, long_span: int = 2880) -> np.ndarray:
    """Per-bar realized-volatility RATIO: recent vol / typical vol, causal.

    Idea from the volatility-targeting literature (managed-vol): size DOWN when the
    market is turbulent, UP when calm, to hold roughly constant risk. Here we publish
    the ratio short-vol/long-vol (both trailing std of log returns, bars <= i only);
    the brain turns it into an exposure multiplier. >1 = turbulent (de-risk), <1 =
    calm. Bear-market crashes spike realized vol, so this is the mandate's ally.
    """
    n = len(close)
    if n < 3:
        return np.ones(n, dtype=np.float16)
    r = np.zeros(n)
    r[1:] = np.diff(np.log(np.maximum(close, 1e-12)))

    def roll_std(x: np.ndarray, span: int) -> np.ndarray:
        c1 = np.concatenate([[0.0], np.cumsum(x)])
        c2 = np.concatenate([[0.0], np.cumsum(x * x)])
        idx = np.arange(n)
        lo = np.maximum(0, idx - span + 1)
        cnt = (idx - lo + 1).astype(float)
        s1 = c1[idx + 1] - c1[lo]
        s2 = c2[idx + 1] - c2[lo]
        var = np.maximum(0.0, s2 / cnt - (s1 / cnt) ** 2)
        return np.sqrt(var)

    sv = roll_std(r, short_span)
    lv = roll_std(r, long_span)
    ratio = np.ones(n)
    good = lv > 1e-9
    ratio[good] = sv[good] / lv[good]
    ratio[:long_span] = 1.0  # warmup: not enough history to judge the regime — neutral
    return ratio.astype(np.float16)


def _causal_momentum(close: np.ndarray, span: int = 2880) -> np.ndarray:
    """Per-bar trailing return over `span` bars — the raw relative-strength signal for
    cross-sectional ranking (idea xsec-momentum, arXiv:2512.08124). Causal: uses only
    bars <= i. The brain compares this ACROSS symbols at a tick to prefer the coins
    strongest relative to the basket. Warmup (< span) reads as 0 (neutral)."""
    n = len(close)
    if n == 0:
        return np.zeros(0, dtype=np.float16)
    mom = np.zeros(n)
    if n > span:
        prev = close[:-span]
        mom[span:] = np.where(prev > 0, close[span:] / prev - 1.0, 0.0)
    return mom.astype(np.float16)


def _signals_for(bars, nets, scaler, window, device, symbol=None, store=None,
                 trend_span: int = 480, batch: int = 8192):
    """Return `(epoch_ns, probability, uptrend, volratio, momentum)` per bar — the brain
    gates on prob + trend, can size by volratio, and rank cross-sectionally by momentum.

    `nets` is one net or a list of nets; a list is a bagged ENSEMBLE — their sigmoid
    probabilities are averaged bar by bar, which lowers variance and improves
    out-of-sample generalisation (idea ensemble-bagging)."""
    if not isinstance(nets, (list, tuple)):
        nets = [nets]
    matrix, timestamps = build_matrix(bars, store=store, symbol=symbol)
    standardized = scaler.transform(matrix)
    finite = finite_rows(matrix)
    if len(finite) == 0:
        return (np.array([], dtype="int64"), np.array([], dtype=np.float16),
                np.array([], dtype=np.int8), np.array([], dtype=np.float16),
                np.array([], dtype=np.float16))
    ends = np.arange(int(finite[0]) + window - 1, len(matrix), dtype=np.int64)
    close = np.array([b.close for b in bars], dtype=float)
    uptrend = _causal_uptrend(close, trend_span)[ends]
    volratio = _causal_volratio(close)[ends]
    momentum = _causal_momentum(close)[ends]
    Xz = torch.tensor(standardized, dtype=torch.float32, device=device)
    offsets = torch.arange(-window + 1, 1, device=device)
    out = []
    with torch.no_grad():
        for start in range(0, len(ends), batch):
            idx = torch.tensor(ends[start:start + batch], device=device)
            xw = Xz[idx[:, None] + offsets[None, :]]
            with torch.autocast(device_type="cuda", enabled=device == "cuda"):
                acc = None
                for net in nets:
                    s = torch.sigmoid(net(xw)).float()
                    acc = s if acc is None else acc + s
                probs = acc / len(nets)  # bagged average across the ensemble
            out.append(probs.cpu().numpy())
    prob = np.concatenate(out).astype(np.float16) if out else np.array([], dtype=np.float16)
    return _epoch_ns(timestamps[ends]), prob, uptrend, volratio, momentum


def export(
    data_root: str = "backtester/data",
    symbols: list[str] | None = None,
    interval: str = "15m",
    model_dir: str = "research/system06",
    out_path: str | None = None,
    trend_span: int = 480,
) -> dict:
    """Compute signals over research+forward for every symbol, into one .npz."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    md = Path(model_dir)
    cfg = json.loads((md / "config.json").read_text())
    symbols = symbols or cfg.get("symbols") or universe.load()
    window = int(cfg["model"]["window"])

    config = ModelConfig.from_dict(cfg["model"])
    scaler = Standardizer.from_dict(json.loads((md / "standardizer.json").read_text()))
    # Load every ensemble member (oracle_net.pt + oracle_net_1.pt ...). One file =
    # a 1-net ensemble = the pre-ensemble behaviour, so old models still work.
    net_paths = sorted(md.glob("oracle_net*.pt")) or [md / "oracle_net.pt"]
    nets = []
    for p in net_paths:
        n = OracleNet(config).to(device)
        n.load_state_dict(torch.load(p, map_location=device))
        n.eval()
        nets.append(n)

    dataset = Dataset(data_root, symbols=symbols, interval=interval)
    combined = dataset.combined()
    store = combined_store(data_root)  # cached forward panels
    payload: dict[str, np.ndarray] = {}
    total_held = total = 0
    for symbol in symbols:
        bars = combined.get(symbol)
        if not bars:
            continue
        ns, prob, uptrend, volratio, momentum = _signals_for(bars, nets, scaler, window, device,
                                                            symbol=symbol, store=store, trend_span=trend_span)
        payload[f"{symbol}__epoch_ns"] = ns
        payload[f"{symbol}__prob"] = prob
        payload[f"{symbol}__trend"] = uptrend
        payload[f"{symbol}__vol"] = volratio
        payload[f"{symbol}__mom"] = momentum
        total += len(prob); total_held += int((prob.astype(np.float32) > 0.5).sum())
    out = Path(out_path) if out_path else md / "signals.npz"
    np.savez(out, **payload)
    print(f"signals for {len(symbols)} symbols, {total:,} bars, "
          f"{total_held:,} p>0.5 ({total_held / max(total, 1):.1%}) -> {out}")
    return {"symbols": len(symbols), "bars": total, "held": total_held, "path": str(out)}


def validation_signals(
    data_root: str,
    symbols: list[str],
    model_dir: str,
    interval: str = "15m",
    trend_span: int = 2880,
    from_ts: str = "2024-07-01T00:00:00+00:00",
) -> dict[str, dict]:
    """Per-symbol (epoch_ns, prob, trend, close) over the PRE-2026 validation window.

    Computed from the research history only (never 2026), causal, sliced to the
    trade window. This feeds the fast numpy portfolio sim that selects the risk
    layer — orders of magnitude cheaper than a tick-by-tick backtest, and it never
    touches the sealed forward.
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    md = Path(model_dir)
    cfg = json.loads((md / "config.json").read_text())
    window = int(cfg["model"]["window"])
    config = ModelConfig.from_dict(cfg["model"])
    scaler = Standardizer.from_dict(json.loads((md / "standardizer.json").read_text()))
    net = OracleNet(config).to(device)
    net.load_state_dict(torch.load(md / "oracle_net.pt", map_location=device))
    net.eval()

    dataset = Dataset(data_root, symbols=symbols, interval=interval)
    research = dataset.research()
    rstore = research_store(data_root)  # cached research panels; same store training used
    from_ns = int(np.datetime64(from_ts.replace("Z", "").split("+")[0], "ns").astype("int64"))

    out: dict[str, dict] = {}
    for symbol in symbols:
        bars = research.get(symbol)
        if not bars:
            continue
        ns, prob, trend, _vol, _mom = _signals_for(bars, net, scaler, window, device,
                                                   symbol=symbol, store=rstore, trend_span=trend_span)
        if len(ns) == 0:
            continue
        close_by_ns = {int(np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64")): b.close
                       for b in bars}
        close = np.array([close_by_ns.get(int(x), np.nan) for x in ns], dtype=float)
        mask = ns >= from_ns
        if not mask.any():
            continue
        out[symbol] = {"ns": ns[mask], "prob": prob[mask].astype(float),
                       "trend": trend[mask].astype(np.int8), "close": close[mask]}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--model-dir", default="research/system06")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    symbols = [s for s in args.symbols.split(",") if s] if args.symbols else None
    export(args.data_root, symbols, args.interval, args.model_dir, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
