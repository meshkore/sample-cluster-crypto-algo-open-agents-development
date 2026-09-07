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
from .features import FEATURE_COLUMNS, Standardizer, build_matrix, combined_store, finite_rows, research_store
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


def _causal_hurst(close: np.ndarray, window: int = 2880,
                  lags: tuple[int, ...] = (8, 16, 32, 64, 128),
                  min_window: int = 384) -> np.ndarray:
    """Per-bar generalized Hurst exponent H (fractal market regime), fully causal.

    Idea `hurst-ghe` (Mandelbrot; Di Matteo generalized Hurst). The q=1 structure
    function of log-price grows with the lag as E[|logP(t)-logP(t-tau)|] ~ tau^H, so
    H is the slope of log(mean|tau-lag move|) versus log(tau). H>0.5 = persistent /
    trending (trend-following works), H=0.5 = random walk, H<0.5 = anti-persistent /
    choppy (trend-following whipsaws — the bear-chop of 2018/2022). A Fractal module
    leans the book in only where H says the tape is genuinely persistent.

    Vectorized and causal: for each lag the trailing mean of |Δlogp| is an O(n) cumsum
    over a `window` look-back using bars <= i only; H per bar is the OLS slope across
    lags. The warm-up region (< min_window bars) is neutral 0.5 — an honest 'unknown'
    that the module treats as no signal, so early bars never fabricate a regime call."""
    n = len(close)
    if n < min_window + max(lags):
        return np.full(n, 0.5, dtype=np.float16)
    logp = np.log(np.maximum(close, 1e-12))
    idx = np.arange(n)
    lo = np.maximum(0, idx - window + 1)
    cnt = (idx - lo + 1).astype(float)
    feats = []  # log(trailing mean |tau-lag log move|) per lag, per bar
    for tau in lags:
        d = np.zeros(n)
        d[tau:] = np.abs(logp[tau:] - logp[:-tau])
        c = np.concatenate([[0.0], np.cumsum(d)])
        mean = (c[idx + 1] - c[lo]) / cnt
        feats.append(np.log(np.maximum(mean, 1e-12)))
    y = np.vstack(feats)                     # (n_lags, n)
    x = np.log(np.asarray(lags, dtype=float))
    xc = x - x.mean()
    denom = float(np.sum(xc * xc)) or 1.0
    slope = (xc[:, None] * (y - y.mean(axis=0)[None, :])).sum(axis=0) / denom
    slope[:min_window] = 0.5                  # warm-up: honest 'unknown'
    return np.clip(slope, 0.0, 1.0).astype(np.float16)


def _causal_feargreed(close: np.ndarray, span: int = 2880,
                      ext_gain: float = 3.0, vol_gain: float = 0.8) -> np.ndarray:
    """Per-bar behavioural fear/greed index in [0,1], fully causal (idea `fear-greed-behavioral`).

    A crowd-emotion proxy from price alone (Kahneman-Tversky prospect theory;
    De Bondt-Thaler overreaction): the market is GREEDY when price is extended above
    its own trend in calm conditions, and FEARFUL when it is below trend amid turbulence.
    Two causal components combine through a logistic squash:

      - extension:  close / trailing_mean(close, span) - 1   (same O(n) cumsum the trend
                    bit uses) — far above trend = greed.
      - turbulence: the recent/typical realized-vol ratio — high vol = fear.

        fg = sigmoid( ext_gain * extension - vol_gain * (volratio - 1) )

    0.5 = neutral, >~0.7 greedy (extended + calm), <~0.3 fearful (below trend + turbulent).
    The Sentiment module reads this to TRIM into greed extremes (protect the rolling
    one-year cohorts that would otherwise buy a top) and gently PRESS fear extremes — but
    only on names that already pass the trend/breadth gates, so 'fear' means a pullback
    inside an uptrend, never catching a falling knife in a confirmed bear."""
    n = len(close)
    if n == 0:
        return np.zeros(0, dtype=np.float16)
    idx = np.arange(n)
    lo = np.maximum(0, idx - span + 1)
    csum = np.concatenate([[0.0], np.cumsum(close)])
    trailing_mean = (csum[idx + 1] - csum[lo]) / (idx - lo + 1)
    ext = np.where(trailing_mean > 0, close / np.maximum(trailing_mean, 1e-12) - 1.0, 0.0)
    volratio = _causal_volratio(close).astype(float)
    z = ext_gain * ext - vol_gain * (volratio - 1.0)
    fg = 0.5 * (1.0 + np.tanh(z))
    return np.clip(fg, 0.0, 1.0).astype(np.float16)


def _causal_sweep(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray,
                  span: int = 96, trigger: float = 0.25, refractory: int = 192,
                  vol_gain: float = 1.0, range_gain: float = 1.5,
                  base: float = 0.5) -> np.ndarray:
    """Per-bar market-maker liquidation-hunt (two-sided stop sweep) score in [0,1), causal.

    Idea `liquidation-hunt` (operator, 2026-08-25). A market maker clearing both sides of
    the book prints a distinctive bar: a long upper wick AND a long lower wick around a
    small body, on heavy volume and an unusually wide range — stops above and below were
    run, and price often reverses afterwards. Unlike `capitulation.py` (a one-sided
    lower-wick bear-bottom detector) this looks for the TWO-SIDED cleanup, which can occur
    in any regime — the point of the idea, since our trend model is blind in flat markets.

    Three coincident, bar-close-knowable conditions multiply into the score:

      - two-sided wicks: `2*min(upper, lower)/range` — high only when BOTH wicks are long,
      - a volume spike: trailing-window z-score of volume (bars <= i only),
      - range expansion: this bar's range against its trailing typical range.

    The operator also noted that a sweep is more meaningful when one has not happened for
    a while ("time since the last cleanup"). That is the refractory term: the raw score is
    scaled from `base` up to 1.0 as the gap since the previous triggering bar approaches
    `refractory`. It reads only bars STRICTLY BEFORE i, so it stays causal.

    Warm-up and degenerate bars score 0 (no signal), never a fabricated one."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)
    n = close.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.float16)
    opens = np.concatenate([[close[0]], close[:-1]])   # prior close proxies this bar's open
    rng = high - low
    body_hi = np.maximum(opens, close)
    body_lo = np.minimum(opens, close)
    upper = np.maximum(0.0, high - body_hi)
    lower = np.maximum(0.0, body_lo - low)
    two_sided = np.where(rng > 0, 2.0 * np.minimum(upper, lower) / (rng + 1e-12), 0.0)

    idx = np.arange(n)
    lo_i = np.maximum(0, idx - span + 1)
    cnt = (idx - lo_i + 1).astype(float)

    def _trailing(x):
        c1 = np.concatenate([[0.0], np.cumsum(x)])
        c2 = np.concatenate([[0.0], np.cumsum(x * x)])
        s1 = c1[idx + 1] - c1[lo_i]
        s2 = c2[idx + 1] - c2[lo_i]
        mean = s1 / cnt
        var = np.maximum(0.0, s2 / cnt - mean * mean)
        return mean, np.sqrt(var)

    v_mean, v_std = _trailing(volume)
    vol_z = (volume - v_mean) / (v_std + 1e-12)
    r_mean, _ = _trailing(rng)
    range_excess = np.maximum(0.0, rng / (r_mean + 1e-12) - 1.0)

    raw = (np.clip(two_sided, 0.0, 1.0)
           * np.tanh(vol_gain * np.maximum(0.0, vol_z))
           * np.tanh(range_gain * range_excess))
    raw[:span] = 0.0   # warm-up: no trailing baseline yet

    # Refractory: bars since the previous TRIGGERING bar, using only bars < i.
    fired = raw > trigger
    last = np.where(fired, idx, -1)
    prev = np.concatenate([[-1], np.maximum.accumulate(last)[:-1]])   # strictly before i
    gap = idx - prev
    recency = np.clip(gap / float(max(1, refractory)), 0.0, 1.0)
    score = raw * (base + (1.0 - base) * recency)
    return np.clip(score, 0.0, 1.0).astype(np.float16)


def _signals_for(bars, nets, scaler, window, device, symbol=None, store=None, market=None,
                 reference=None,
                 trend_span: int = 480, batch: int = 8192):
    """Return `(epoch_ns, probability, uptrend, volratio, momentum, hurst)` per bar — the
    brain gates on prob + trend, can size by volratio, rank cross-sectionally by momentum,
    and gate entries by the fractal-regime Hurst exponent.

    `nets` is one net or a list of nets; a list is a bagged ENSEMBLE — their sigmoid
    probabilities are averaged bar by bar, which lowers variance and improves
    out-of-sample generalisation (idea ensemble-bagging)."""
    if not isinstance(nets, (list, tuple)):
        nets = [nets]
    matrix, timestamps = build_matrix(bars, store=store, symbol=symbol, market=market,
                                      reference=reference)
    standardized = scaler.transform(matrix)
    finite = finite_rows(matrix)
    if len(finite) == 0:
        return (np.array([], dtype="int64"), np.array([], dtype=np.float16),
                np.array([], dtype=np.int8), np.array([], dtype=np.float16),
                np.array([], dtype=np.float16), np.array([], dtype=np.float16),
                np.array([], dtype=np.float16), np.array([], dtype=np.float16))
    ends = np.arange(int(finite[0]) + window - 1, len(matrix), dtype=np.int64)
    close = np.array([b.close for b in bars], dtype=float)
    uptrend = _causal_uptrend(close, trend_span)[ends]
    volratio = _causal_volratio(close)[ends]
    momentum = _causal_momentum(close)[ends]
    hurst = _causal_hurst(close)[ends]
    feargreed = _causal_feargreed(close)[ends]
    sweep = _causal_sweep(np.array([b.high for b in bars], dtype=float),
                          np.array([b.low for b in bars], dtype=float), close,
                          np.array([b.volume for b in bars], dtype=float))[ends]
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
    return _epoch_ns(timestamps[ends]), prob, uptrend, volratio, momentum, hurst, feargreed, sweep


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
    # A59: the standardizer is the authority on the layout the net expects. If it
    # carries the market columns, build ONE table over the whole universe here so
    # export matches training exactly - a flag could drift, the artifact cannot.
    # A59/A96: the standardizer is the authority on the layout the net expects, so the
    # width of its mean vector - not a flag anyone has to remember to pass - decides
    # which optional blocks are rebuilt here. A flag can drift between training and
    # inference; the artifact travels with the weights and cannot.
    from .market import MARKET_FEATURE_COLUMNS
    from .reference import REFERENCE_FEATURE_COLUMNS
    extra = len(scaler.mean) - len(FEATURE_COLUMNS)
    want_market = extra in (len(MARKET_FEATURE_COLUMNS),
                            len(MARKET_FEATURE_COLUMNS) + len(REFERENCE_FEATURE_COLUMNS))
    want_reference = extra in (len(REFERENCE_FEATURE_COLUMNS),
                               len(MARKET_FEATURE_COLUMNS) + len(REFERENCE_FEATURE_COLUMNS))
    if extra and not (want_market or want_reference):
        raise ValueError(
            f"the model expects {len(scaler.mean)} features, which matches no known "
            f"layout - refusing to feed it a matrix it was not trained on")
    market = None
    if want_market:
        from .market import MarketTable
        market = MarketTable(combined)
    reference = None
    if want_reference:
        from .reference import ReferenceTable
        reference = ReferenceTable()
    payload: dict[str, np.ndarray] = {}
    total_held = total = 0
    for symbol in symbols:
        bars = combined.get(symbol)
        if not bars:
            continue
        ns, prob, uptrend, volratio, momentum, hurst, feargreed, sweep = _signals_for(bars, nets, scaler, window, device,
                                                            symbol=symbol, store=store, market=market,
                                                            reference=reference, trend_span=trend_span)
        payload[f"{symbol}__epoch_ns"] = ns
        payload[f"{symbol}__prob"] = prob
        payload[f"{symbol}__trend"] = uptrend
        payload[f"{symbol}__vol"] = volratio
        payload[f"{symbol}__mom"] = momentum
        payload[f"{symbol}__hurst"] = hurst
        payload[f"{symbol}__feargreed"] = feargreed
        payload[f"{symbol}__sweep"] = sweep
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
        ns, prob, trend, _vol, _mom, _hurst, _fg, _sw = _signals_for(bars, net, scaler, window, device,
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
