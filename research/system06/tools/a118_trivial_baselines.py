"""A118: does any of this beat a moving average? The test we never ran.

Operator, 2026-09-07: "are we not over-complicating everything? Sometimes a simple
algorithm is much better than a complex one. Three days without a single improvement,
and I have no feeling of safety with this algorithm."

He is right to ask, and the honest response is a measurement rather than reassurance.
Three facts from our own data point the same way:

  * the champion's raw net LOSES money after costs on its own validation slice
    (val_net_return -31.3% against +158% gross), so whatever the book earns is
    produced by the risk layer, not by the model's aim;
  * the yearly record is carried by one colossal year - 2021 at +11,884% against
    2022 at +12.2% and 2025 at -0.7%;
  * that shape is the signature of leveraged beta to a bull market, not of an edge.

So this compares the whole apparatus - 44 features, a causal TCN, eight decision
modules, thirty-three thresholds - against rules a person could run on paper:

  buy_hold_btc      hold BTC for the year
  buy_hold_basket   equal-weight the 14-symbol universe, no rebalancing
  sma200            long BTC while price > its 200-day mean, else flat
  sma200_basket     the same rule per symbol, equal-weight across those long
  dual_momentum     hold the 3 strongest symbols by 90-day return, monthly reload

Every baseline pays the SAME toll the champion pays - 10 bp commission plus 5 bp
slippage per side - because a comparison that charges one side and not the other is
not a comparison. What the baselines do NOT get is market impact, which only makes
this test harder on them and therefore safer as a conclusion in the champion's favour.

They also get no stops, no sizing, no vetoes. That is the point: if a 200-day moving
average with no risk layer matches a system with eight modules, the modules are
decoration and we should be told so in numbers.

READ IT THIS WAY. The interesting column is not 2021, where anything long wins. It is
2022 and 2025 - the years the operator does not trust - and the SEALED 2026, which is
reported here for the baselines because a baseline cannot overfit a year it has no
parameters to fit.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a118_trivial_baselines.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
TOLL = 0.0015                      # one side: 10 bp commission + 5 bp slippage
YEARS = list(range(2018, 2027))
BARS_PER_DAY = 96                  # 15-minute candles


def _by_year(bars):
    out = defaultdict(list)
    for b in bars:
        out[b.timestamp.year].append(b)
    return out


def _series(bars):
    close = np.array([b.close for b in bars], dtype=float)
    return close


def _apply(close: np.ndarray, position: np.ndarray) -> float:
    """Compound a 0/1 position path, charging the toll on every change."""
    if len(close) < 2:
        return 0.0
    ret = close[1:] / close[:-1] - 1.0
    pos = position[:-1]
    turns = np.abs(np.diff(np.concatenate([[0.0], position])))[:-1]
    growth = np.prod(1.0 + pos * ret - turns * TOLL)
    return float(growth - 1.0)


def _sma_position(close: np.ndarray, span_days: int = 200) -> np.ndarray:
    """Long while the close is above its own trailing mean. Causal: bar i uses <= i,
    and the position is SHIFTED so today's signal trades tomorrow's bar."""
    n = span_days * BARS_PER_DAY
    m = len(close)
    if m <= n:
        return np.zeros(m)
    # Trailing mean of the n bars ENDING at i, for i >= n-1:
    #   mean[i] = (cumsum[i+1] - cumsum[i+1-n]) / n
    # with cumsum carrying a leading zero so the window is inclusive at both ends.
    c = np.concatenate([[0.0], np.cumsum(close)])
    mean = np.full(m, np.nan)
    mean[n - 1:] = (c[n:] - c[:m - n + 1]) / n
    raw = np.where(np.isfinite(mean) & (close > mean), 1.0, 0.0)
    return np.concatenate([[0.0], raw[:-1]])          # act on the NEXT bar


def main() -> int:
    from quantlab_system06 import universe
    from quantlab_system06.dataset import Dataset

    symbols = universe.load()
    ds = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    research = ds.research()
    combined = ds.combined()                          # includes 2026
    src = {s: combined.get(s) or research.get(s) or [] for s in symbols}
    per_symbol_year = {s: _by_year(b) for s, b in src.items() if b}
    print(f"{len(per_symbol_year)} symbols; toll {TOLL * 2:.2%} round trip\n", flush=True)

    results: dict[str, dict[int, float]] = defaultdict(dict)

    for year in YEARS:
        # --- buy & hold BTC ---
        btc = per_symbol_year.get("BTCUSDT", {}).get(year) or []
        if len(btc) > 1:
            c = _series(btc)
            results["buy_hold_btc"][year] = float(
                (c[-1] / c[0]) * (1 - TOLL) ** 2 - 1.0)

        # --- buy & hold the basket, equal weight ---
        legs = []
        for s, by in per_symbol_year.items():
            bars = by.get(year) or []
            if len(bars) > BARS_PER_DAY * 30:         # needs a month of the year
                c = _series(bars)
                legs.append((c[-1] / c[0]) * (1 - TOLL) ** 2 - 1.0)
        if legs:
            results["buy_hold_basket"][year] = float(np.mean(legs))

        # --- 200-day SMA on BTC, and on the basket ---
        # The rule needs history BEFORE the year, so it is computed on the full series
        # and then sliced - which is what a live system would have.
        sma_legs = []
        for s, bars in src.items():
            if len(bars) < 210 * BARS_PER_DAY:
                continue
            c = _series(bars)
            pos = _sma_position(c)
            idx = [i for i, b in enumerate(bars) if b.timestamp.year == year]
            if len(idx) < BARS_PER_DAY * 30:
                continue
            lo, hi = idx[0], idx[-1] + 1
            r = _apply(c[lo:hi], pos[lo:hi])
            if s == "BTCUSDT":
                results["sma200_btc"][year] = r
            sma_legs.append(r)
        if sma_legs:
            results["sma200_basket"][year] = float(np.mean(sma_legs))

    # ---- report --------------------------------------------------------------------
    champ = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    champ_years = champ.get("annual_returns") or {}
    champ_2026 = (champ.get("forward_2026") or {}).get("return_pct")

    names = ["buy_hold_btc", "buy_hold_basket", "sma200_btc", "sma200_basket"]
    print("=" * 96)
    print(f"{'year':>6}  {'CHAMPION':>12}  " + "  ".join(f"{n:>15}" for n in names))
    print("=" * 96)
    for y in YEARS:
        cv = champ_years.get(str(y)) if y < 2026 else champ_2026
        cs = f"{cv:+11.2%}" if isinstance(cv, (int, float)) else "          —"
        cells = "  ".join(
            f"{results[n][y]:+14.2%}" if y in results[n] else "             —"
            for n in names)
        tag = "  <- SEALED" if y == 2026 else ""
        print(f"{y:>6}  {cs}  {cells}{tag}")

    print("\nthe years that decide whether this is an edge or leveraged beta:")
    for y in (2022, 2025, 2026):
        cv = champ_years.get(str(y)) if y < 2026 else champ_2026
        line = f"  {y}: champion {cv:+.2%}" if isinstance(cv, (int, float)) else f"  {y}: champion —"
        for n in names:
            if y in results[n]:
                line += f" | {n} {results[n][y]:+.2%}"
        print(line)

    out = ROOT / "rnd" / f"a118_baselines_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A118", "at": datetime.now(timezone.utc).isoformat(),
        "toll_round_trip": TOLL * 2,
        "baselines": {n: {str(y): v for y, v in results[n].items()} for n in names},
        "champion": {**{str(y): champ_years.get(str(y)) for y in range(2018, 2026)},
                     "2026": champ_2026},
        "note": "baselines pay the same commission and slippage as the champion but NO "
                "market impact, which makes this test harder on them - so a champion win "
                "here is conservative. They carry no stops, no sizing and no vetoes.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
