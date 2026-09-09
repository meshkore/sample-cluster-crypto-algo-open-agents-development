"""R01: did the BTC factor lose its grip on altcoins, and when?

The question this settles, and it is the one both agents on the Wall are arguing about
without evidence: our systems stopped working somewhere around 2024-2025. Two
explanations fit equally well from where we stand.

    INSTITUTIONALISATION   the market changed. Spot BTC ETFs launched 2024-01 and by
                           2025 were up to 30% of global BTC volume. Published work
                           (LSE, Jan 2021 - Sep 2025, 18 altcoins) reports a pronounced
                           post-ETF decline in BTC-altcoin correlation - "independent
                           inflows", BTC becoming a standalone asset class.

    OVERFITTING            nothing changed. We fitted 2018-2024 and the fit expired,
                           as fits do.

They are worth separating because they imply opposite responses. If the market changed,
the answer is a regime reader. If we overfitted, the answer is discipline, and a regime
reader would be one more thing to overfit.

WHY THIS PARTICULAR MEASUREMENT. It touches no strategy. Rolling BTC-altcoin
correlation and the dispersion of altcoin returns after the BTC factor is removed are
properties of the CROSS-SECTION, computed from prices alone. No threshold, no entry, no
position. A test that cannot be passed by a strategy also cannot be flattered by one -
which matters here because I already believe one of the two answers, and that is exactly
when my own measurement is worth least.

    beta_i  = cov(r_i, r_btc) / var(r_btc)          rolling, causal
    resid_i = r_i - beta_i * r_btc
    R2_i    = 1 - var(resid_i) / var(r_i)           how much of the alt BTC explains

PREDICTIONS, REGISTERED BEFORE THE NUMBERS EXIST

  If institutionalisation: mean R2 across altcoins falls from 2024 onward and residual
  dispersion rises. The fall should be visible in the cross-section itself, on a
  calendar boundary near 2024-01, and should not be a smooth continuation of a trend
  that was already running through 2021-2023.

  If overfitting: R2 and residual dispersion are roughly flat, or drift without a break,
  and whatever happened to our systems happened only to our systems.

A THIRD OUTCOME IS POSSIBLE and would be the most useful of all: the decline is real but
began BEFORE the ETFs, which would refute the mechanism while confirming the break, and
send us looking for a different cause.

Run from repo root:
    PYTHONPATH=trading-system python research/system08/tools/r01_factor_decay.py
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OUT = Path("research/system08/rnd")
FACTOR = "BTCUSDT"
# Daily returns from 15m closes. Daily rather than 15m on purpose: the question is about
# the CROSS-SECTION of asset returns, not about microstructure, and a 15m correlation is
# dominated by non-synchronous trading and microstructure noise that would answer a
# different question convincingly and the wrong one.
BARS_PER_DAY = 96
WINDOW = 60          # trading days in the rolling beta - about a quarter
MIN_DAYS = 200       # an altcoin needs this much history in a year to be scored there


def daily_closes(bars) -> dict[str, float]:
    """Last close of each UTC day. Keyed by date so symbols align on the calendar."""
    out: dict[str, float] = {}
    for b in bars:
        out[b.timestamp.strftime("%Y-%m-%d")] = float(b.close)
    return out


def main() -> int:
    import quantlab_catalog as cat

    symbols = cat.load_universe()
    if FACTOR not in symbols:
        symbols = [FACTOR] + list(symbols)
    print(f"loading {len(symbols)} symbols ...", flush=True)
    research = cat.research(symbols)
    forward = cat.forward(symbols)

    # 2026 is included deliberately and is READ-ONLY here. This measurement has no
    # parameters, selects nothing and cannot be tuned, so looking at the cross-section
    # of 2026 prices does not spend anything - there is nothing here for a sealed year
    # to be spent ON. It is stated rather than assumed.
    closes: dict[str, dict[str, float]] = {}
    for sym in symbols:
        merged = daily_closes(research.get(sym) or [])
        merged.update(daily_closes(forward.get(sym) or []))
        if len(merged) > MIN_DAYS:
            closes[sym] = merged
    print(f"  {len(closes)} symbols with usable daily history", flush=True)

    all_days = sorted({d for s in closes.values() for d in s})
    btc = closes.get(FACTOR)
    if not btc:
        sys.exit("no BTCUSDT in the catalogue - the factor is the measurement")

    # returns aligned on the calendar
    rets: dict[str, dict[str, float]] = {}
    for sym, series in closes.items():
        days = sorted(series)
        r = {}
        for prev, day in zip(days, days[1:]):
            p0, p1 = series[prev], series[day]
            if p0 > 0 and p1 > 0:
                r[day] = np.log(p1 / p0)
        rets[sym] = r

    per_year: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: {"r2": [], "beta": [], "resid_vol": [], "raw_vol": []})

    for sym, r in rets.items():
        if sym == FACTOR:
            continue
        days = [d for d in all_days if d in r and d in rets[FACTOR]]
        if len(days) < WINDOW + MIN_DAYS // 2:
            continue
        a = np.array([r[d] for d in days])
        f = np.array([rets[FACTOR][d] for d in days])
        for i in range(WINDOW, len(days)):
            wa, wf = a[i - WINDOW:i], f[i - WINDOW:i]      # strictly past, causal
            var_f = float(np.var(wf))
            if var_f <= 0:
                continue
            beta = float(np.cov(wa, wf, bias=True)[0, 1]) / var_f
            resid = wa - beta * wf
            var_a = float(np.var(wa))
            if var_a <= 0:
                continue
            year = int(days[i][:4])
            per_year[year]["r2"].append(max(0.0, 1.0 - float(np.var(resid)) / var_a))
            per_year[year]["beta"].append(beta)
            per_year[year]["resid_vol"].append(float(np.std(resid)))
            per_year[year]["raw_vol"].append(float(np.std(wa)))

    print("\n" + "=" * 82)
    print("HOW MUCH OF AN ALTCOIN'S RETURN THE BTC FACTOR EXPLAINS, BY YEAR")
    print(f"rolling {WINDOW}-day causal beta, {len(rets) - 1} altcoins, daily returns")
    print("=" * 82)
    print(f"{'year':>6} {'median R2':>11} {'mean R2':>9} {'median beta':>12} "
          f"{'resid vol':>11} {'resid/raw':>10} {'obs':>8}")
    rows = {}
    for year in sorted(per_year):
        v = per_year[year]
        if len(v["r2"]) < 100:
            continue
        med = statistics.median(v["r2"])
        share = statistics.median(
            [rv / (raw + 1e-12) for rv, raw in zip(v["resid_vol"], v["raw_vol"])])
        rows[year] = {
            "median_r2": med, "mean_r2": statistics.mean(v["r2"]),
            "median_beta": statistics.median(v["beta"]),
            "median_resid_vol": statistics.median(v["resid_vol"]),
            "resid_share_of_vol": share, "observations": len(v["r2"]),
        }
        mark = "  <- spot BTC ETFs launch" if year == 2024 else ""
        print(f"{year:>6} {med:>11.3f} {statistics.mean(v['r2']):>9.3f} "
              f"{statistics.median(v['beta']):>12.3f} "
              f"{statistics.median(v['resid_vol']):>11.4f} {share:>10.3f} "
              f"{len(v['r2']):>8,}{mark}")

    # ---- adjudication, against the predictions registered in the docstring ----------
    years = sorted(rows)
    pre = [rows[y]["median_r2"] for y in years if y <= 2023]
    post = [rows[y]["median_r2"] for y in years if y >= 2024]
    verdict = "INCONCLUSIVE - not enough years on one side"
    if pre and post:
        drop = statistics.mean(pre) - statistics.mean(post)
        # Was the pre-period already trending down, or is 2024 a break? Compare the
        # step at the boundary against the movement WITHIN the pre-period, which is the
        # only way to tell a break from the continuation of a slide.
        pre_span = (max(pre) - min(pre)) if len(pre) > 1 else 0.0
        print(f"\nmedian R2  2020-2023: {statistics.mean(pre):.3f}   "
              f"2024-2026: {statistics.mean(post):.3f}   fall: {drop:+.3f}")
        print(f"spread WITHIN 2020-2023: {pre_span:.3f}  (a fall smaller than this is "
              f"not a break, it is the same wobble)")
        if drop > pre_span and drop > 0.05:
            verdict = ("STRUCTURAL BREAK AT 2024 - the BTC factor explains materially "
                       "less of the altcoin cross-section from the ETF launch onward, "
                       "and the step is larger than anything the pre-period did on its "
                       "own. This is a property of the market, not of our strategies.")
        elif drop > 0.05:
            verdict = ("DECLINE WITHOUT A CLEAN BREAK - the factor is weakening but the "
                       "2024 step is no larger than the pre-period's own movement. "
                       "Consistent with a slide that began earlier; the ETF mechanism "
                       "is not established by this.")
        else:
            verdict = ("NO CROSS-SECTIONAL CHANGE - the BTC factor explains about as "
                       "much as it always did. Whatever happened to our systems "
                       "happened to OUR SYSTEMS. Prefer the overfitting explanation "
                       "and do not build a regime reader on this evidence.")
    print(f"\nVERDICT: {verdict}")
    print("\nThis measurement has no parameters to tune and selects nothing. It cannot "
          "be passed by a strategy,\nand it cannot be flattered by one.")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"r01_factor_decay_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps({
        "id": "R01", "at": datetime.now(timezone.utc).isoformat(),
        "factor": FACTOR, "window_days": WINDOW,
        "altcoins": len(rets) - 1, "by_year": rows, "verdict": verdict,
        "note": "daily returns from 15m closes; rolling causal beta; 2026 included as a "
                "read-only cross-sectional observation - there are no parameters here "
                "for a sealed year to be spent on.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
