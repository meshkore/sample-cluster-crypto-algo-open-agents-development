"""What changed in the crypto cross-section in 2026? The only question left.

WHY THIS AND NOT ANOTHER PARAMETER

Every code-side explanation for the sealed year has been measured and eliminated: costs
(2026 sits between 2023 and 2025), the BTC hedge (every scale from 0 to 2 still gives eight
positive research years), funding, volatility targeting, seasoning, liquidity, and the
selection process itself - walk-forward gives six of six held-out years positive with
NEGATIVE optimism. The loop has since run 215 more parameter experiments without improving
on the same configuration. Turning knobs is finished.

So the question is about the market, and this measures the four things that would have to
change for a residual momentum book to stop working, year by year, with 2026 as just another
column rather than the answer we are looking for.

  DISPERSION. How far apart the cross-section's returns are. A book that buys winners and
  sells losers needs them to be distinguishable; if every coin moves together there is
  nothing to rank.

  RESIDUAL SHARE. What fraction of a name's variance survives after the market factor is
  removed. This is the raw material the whole design is built on. If it collapsed, the
  residual stopped being idiosyncratic and became noise, and the signal is ranking noise.

  SIGNAL AUTOCORRELATION. Whether past residual momentum still predicts future residual
  momentum at our horizon. This is the edge itself, measured directly rather than through
  the book's P&L - the information coefficient between the formation-window score and the
  return actually realised over the following holding period.

  CROWDING PROXY. Whether the cross-section's own correlation structure tightened. A trade
  that many people are running shows up as names moving together more than their
  fundamentals warrant.

The point of doing all four per year is that 2026 has to be compared against eight years we
KNOW the book worked in, including two it barely worked in. A number that is unusual in 2026
and also unusual in 2020 explains nothing. Only a number that separates 2026 from every
research year is a candidate.

Nothing here reads a configuration or optimises anything. It measures the market.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from quantlab_system08 import residual as R                 # noqa: E402

WINDOW = 35          # the beta window of the configuration under study
LOOKBACK = 18        # its formation window
HOLD = 14            # its holding period
MIN_NAMES = 6        # a "cross-section" with fewer names is not one


def load(universe: str = "universe_wide.json") -> dict:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    syms = [str(s) for s in meta["symbols"]]
    bars = cat.candles(syms, include_sealed=True)
    return {s: b for s, b in bars.items() if b}


def compounded(series: dict[str, float], days: list[str], i: int, n: int) -> float | None:
    """Compounded return over n days ending at index i. None if the window is incomplete."""
    if i - n < 0:
        return None
    acc = 1.0
    for d in days[i - n:i]:
        v = series.get(d)
        if v is None:
            return None
        acc *= (1.0 + v)
    return acc - 1.0


def main(universe: str = "universe_wide.json") -> int:
    bars = load(universe)
    rets = {s: R.simple_returns(R.daily_closes(b)) for s, b in bars.items()}
    rets = {s: v for s, v in rets.items() if v}
    print(f"{universe}: {len(rets)} names\n")

    factors = R.market_ex_self(sorted(rets))
    loads = R.residuals(rets, factors=factors, window=WINDOW)
    eps = R.residual_series(rets, loads, factors=factors)

    all_days = sorted({d for v in rets.values() for d in v})
    by_year_days = defaultdict(list)
    for d in all_days:
        by_year_days[d[:4]].append(d)

    # --- dispersion and residual share, per year.
    disp, share, corr = {}, {}, {}
    for year, days in sorted(by_year_days.items()):
        if len(days) < 30:
            continue
        spreads, shares = [], []
        for d in days:
            row = [rets[s][d] for s in rets if d in rets[s]]
            if len(row) >= MIN_NAMES:
                spreads.append(float(np.std(row, ddof=1)))
        for s, per_day in eps.items():
            e = [per_day[d] for d in days if d in per_day]
            r = [rets[s][d] for d in days if d in rets.get(s, {})]
            if len(e) >= 30 and len(r) >= 30:
                sd_r = float(np.std(r, ddof=1))
                if sd_r > 0:
                    shares.append(float(np.std(e, ddof=1)) / sd_r)
        # Average pairwise correlation of daily returns: the crowding proxy.
        names = [s for s in rets if sum(1 for d in days if d in rets[s]) >= 30]
        mat = []
        for s in names:
            mat.append([rets[s].get(d, np.nan) for d in days])
        arr = np.array(mat, dtype=float)
        ok = ~np.isnan(arr).any(axis=1)
        cm = np.corrcoef(arr[ok]) if ok.sum() >= MIN_NAMES else None
        if cm is not None and cm.ndim == 2:
            iu = np.triu_indices_from(cm, k=1)
            corr[year] = float(np.nanmean(cm[iu]))
        disp[year] = float(np.mean(spreads)) if spreads else float("nan")
        share[year] = float(np.mean(shares)) if shares else float("nan")

    # --- information coefficient: does the formation score predict the held period?
    ic = defaultdict(list)
    for s, per_day in eps.items():
        days = sorted(per_day)
        idx = {d: i for i, d in enumerate(days)}
        for d in days:
            i = idx[d]
            if i + HOLD >= len(days):
                continue
            past = compounded(per_day, days, i, LOOKBACK)
            fut = compounded(per_day, days, i + HOLD, HOLD)
            if past is None or fut is None:
                continue
            ic[d[:4]].append((past, fut))

    print(f"{'year':<6}{'dispersion':>12}{'resid share':>13}{'avg corr':>10}"
          f"{'IC':>8}{'n':>8}")
    for year in sorted(disp):
        pairs = ic.get(year, [])
        if len(pairs) >= 50:
            a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
            c = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
        else:
            c = float("nan")
        print(f"{year:<6}{disp[year]:>12.4f}{share.get(year, float('nan')):>13.3f}"
              f"{corr.get(year, float('nan')):>10.3f}{c:>8.3f}{len(pairs):>8}")

    print("\nREADING THIS TABLE. A number is only a candidate explanation if it separates")
    print("2026 from EVERY research year - including 2020 and 2022, which the book survived.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
