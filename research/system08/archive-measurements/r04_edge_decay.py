"""R04: is EVERY edge decaying, or only the ones I happened to look at?

R02 and R03 killed absorption. Reading around them, four independent series pointed the
same way - published carry Sharpe 6.45 -> 4.06 -> negative; our own turnover payoff 2.97x
(2018) -> 0.82x (2024); order flow at 15m already zero; and R01 showing the cross-section
did NOT change. I turned that into a claim: crypto edges are not shifting regime, they are
decaying uniformly, so signals should be selected by the SLOPE of their payoff rather than
its mean.

That claim is currently four anecdotes and a story, which is exactly the standard I refuse
from everyone else. So this tests it on signals I did not choose for the purpose - the
plainest, most canonical things anyone would compute from a price series - and it is
built to be able to refute me.

WHAT IS REGISTERED, BEFORE THE NUMBERS EXIST

  The claim predicts that MOST canonical signals have a negative payoff slope over
  2017-2025. It is not a claim about any one signal; it is a claim about the population.

  KILL: if fewer than 60% of the signals show a negative slope, "uniform decay" is false
  and I withdraw it. A mix of signs would mean signals are being repriced in both
  directions, which is a different and much less interesting world - it would just mean
  payoffs move around.

  SECOND KILL, and the one I expect to be harder: a negative slope is only interesting if
  the EARLY payoff was positive. A signal that has always been worthless and drifts from
  -1 bps to -3 bps has a negative slope and no decay - nothing was competed away because
  there was nothing there. So the headline is restricted to signals whose first three
  years paid something.

  A THIRD OUTCOME would refute me most usefully: slopes negative but driven ENTIRELY by
  2017-2018. Crypto in 2017 was a different market by any measure, and "everything paid in
  2017" is not the same claim as "edges are being competed away". The per-year table is
  printed in full so this is visible rather than buried in a regression.

WHAT THIS IS NOT. It is not a backtest and nothing here is tradeable. Payoff is measured
as mean(sign(signal) * forward return) in basis points, gross. No costs, no sizing, no
portfolio. That is deliberate: the question is about the DIRECTION of a trend in gross
predictive value, and adding a cost model would only subtract a constant from every year
and change no slope.

2026 is not touched.

Run from the repo root:
    PYTHONPATH=trading-system python research/system08/tools/r04_edge_decay.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OUT = Path("research/system08/rnd")

BARS_DAY = 96
HORIZON = BARS_DAY          # judge every signal on the next 24 hours
WARMUP = 2880               # 30 days
MIN_YEAR_OBS = 2000
NEG_SLOPE_KILL = 0.60


def roll_mean(a: np.ndarray, w: int) -> np.ndarray:
    n = a.size
    out = np.full(n, np.nan)
    if n < w:
        return out
    c = np.concatenate(([0.0], np.cumsum(np.nan_to_num(a))))
    out[w - 1:] = (c[w:] - c[:-w]) / w
    return out


def roll_std(a: np.ndarray, w: int) -> np.ndarray:
    """Shifted by a[0] before squaring - without that, mean(x^2)-mean(x)^2 cancels
    catastrophically on a price series near 40,000 and returns noise for zero."""
    n = a.size
    out = np.full(n, np.nan)
    if n < w:
        return out
    d = np.nan_to_num(a - a[0])
    m = roll_mean(d, w)
    m2 = roll_mean(d * d, w)
    out = np.sqrt(np.maximum(m2 - m * m, 0.0))
    return out


def signals(close: np.ndarray, ret: np.ndarray, funding: np.ndarray,
            vol: np.ndarray) -> dict[str, np.ndarray]:
    """The plainest things anyone would compute. Chosen BEFORE looking at any payoff,
    and chosen to be canonical rather than promising - a hand-picked set would make the
    population claim vacuous."""
    sig: dict[str, np.ndarray] = {}
    n = close.size
    lg = np.log(np.maximum(close, 1e-12))
    for name, h in (("mom_1d", 96), ("mom_3d", 288), ("mom_7d", 672),
                    ("mom_30d", 2880)):
        s = np.full(n, np.nan)
        s[h:] = lg[h:] - lg[:-h]
        sig[name] = s
    s = np.full(n, np.nan)
    s[4:] = -(lg[4:] - lg[:-4])
    sig["reversal_1h"] = s                      # short-horizon mean reversion
    s = np.full(n, np.nan)
    s[BARS_DAY:] = -(lg[BARS_DAY:] - lg[:-BARS_DAY])
    sig["reversal_1d"] = s
    sd = roll_std(ret, 672)
    with np.errstate(invalid="ignore", divide="ignore"):
        sig["mom_7d_volscaled"] = np.where(sd > 0, sig["mom_7d"] / sd, np.nan)
        # Distance from the 30-day mean, in standard deviations: the plainest breakout /
        # stretch measure there is.
        m = roll_mean(lg, 2880)
        sdl = roll_std(lg, 2880)
        sig["stretch_30d"] = np.where(sdl > 0, (lg - m) / sdl, np.nan)
        # Carry: when funding is positive, longs pay shorts, so the carry signal is SHORT.
        sig["carry_funding"] = -funding
        # Volume shock: is today's turnover unusual for this symbol?
        vm = roll_mean(vol, 2880)
        sig["volume_shock"] = np.where(vm > 0, vol / vm - 1.0, np.nan)
    return sig


def main() -> int:
    import quantlab_catalog as cat

    symbols = cat.load_universe()
    print(f"loading {len(symbols)} symbols at 15m (research era only) ...", flush=True)
    research = cat.research(symbols)

    # payoff[signal][year] -> list of daily means, one per (symbol, day)
    daily: dict[str, dict[int, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))

    for sym in symbols:
        bars = research.get(sym) or []
        if len(bars) < WARMUP + HORIZON + 5000:
            continue
        close = np.array([float(b.close) for b in bars])
        vol = np.array([float(b.volume or 0.0) for b in bars])
        fund = np.array([(float(b.funding_rate)
                          if getattr(b, "funding_rate", None) is not None else np.nan)
                         for b in bars])
        lg = np.log(np.maximum(close, 1e-12))
        ret = np.full(close.size, np.nan)
        ret[1:] = lg[1:] - lg[:-1]
        fwd = np.full(close.size, np.nan)
        fwd[:-HORIZON] = lg[HORIZON:] - lg[:-HORIZON]

        sig = signals(close, ret, fund, vol)
        years = np.array([b.timestamp.year for b in bars])
        days = [b.timestamp.strftime("%Y-%m-%d") for b in bars]

        for name, s in sig.items():
            ok = np.isfinite(s) & np.isfinite(fwd)
            ok[:WARMUP] = False
            idx = np.flatnonzero(ok)
            if idx.size == 0:
                continue
            pay = np.sign(s[idx]) * fwd[idx]
            for j, i in enumerate(idx):
                daily[name][int(years[i])][days[i]].append(float(pay[j]))
        print(f"  {sym:<12} done", flush=True)

    print("\n" + "=" * 92)
    print("GROSS PAYOFF PER YEAR, bps per observation.  mean(sign(signal) * next-24h "
          "return)")
    print("=" * 92)
    years_all = sorted({y for v in daily.values() for y in v})
    hdr = f"{'signal':<20}" + "".join(f"{y:>7}" for y in years_all) + f"{'slope':>9}{'t':>7}"
    print(hdr)

    results = {}
    for name in sorted(daily):
        row, xs, ys = [], [], []
        for y in years_all:
            dd = daily[name].get(y) or {}
            n_obs = sum(len(v) for v in dd.values())
            if n_obs < MIN_YEAR_OBS:
                row.append(None)
                continue
            # Average within the day first: two symbols on one afternoon are not two
            # independent draws in a market that is one risk factor sampled fourteen
            # times.
            dm = np.array([np.mean(v) for v in dd.values()])
            m = float(np.mean(dm)) * 10_000.0
            row.append(m)
            xs.append(y)
            ys.append(m)
        if len(xs) < 5:
            continue
        x = np.array(xs, dtype=float)
        yv = np.array(ys)
        x0 = x - x.mean()
        slope = float((x0 * (yv - yv.mean())).sum() / (x0 * x0).sum())
        resid = yv - (yv.mean() + slope * x0)
        se = float(np.sqrt((resid ** 2).sum() / max(1, len(x) - 2) / (x0 * x0).sum()))
        t = slope / se if se > 0 else float("nan")
        early = [v for v in row[:3] if v is not None]
        results[name] = {"per_year": {str(y): v for y, v in zip(years_all, row)},
                         "slope_bps_per_year": slope, "t": t,
                         "early_mean": float(np.mean(early)) if early else float("nan"),
                         "mean": float(yv.mean())}
        cells = "".join(f"{v:>7.1f}" if v is not None else f"{'-':>7}" for v in row)
        print(f"{name:<20}{cells}{slope:>9.2f}{t:>7.2f}")

    # ---- adjudication against what was registered above --------------------------------
    #
    # MIRRORS ARE NOT EVIDENCE. `reversal_1d` is defined as -mom_1d, so its payoff is the
    # exact negative of mom_1d's and its slope is forced to the opposite sign. Counting
    # both inflates the population and GUARANTEES at least one positive slope no matter
    # what the market did. I built the signal list before looking at any payoff, which is
    # the right instinct, and still put a redundant pair in it. Excluded from the count;
    # left in the table because seeing the mirror is informative.
    MIRRORS = {"reversal_1d"}
    slopes = {k: v["slope_bps_per_year"] for k, v in results.items()
              if k not in MIRRORS}
    neg = [k for k, s in slopes.items() if s < 0]
    frac = len(neg) / len(slopes) if slopes else 0.0

    paid_early = {k: v for k, v in results.items()
                  if v["early_mean"] > 0 and k not in MIRRORS}
    neg_paid = [k for k, v in paid_early.items() if v["slope_bps_per_year"] < 0]
    frac_paid = len(neg_paid) / len(paid_early) if paid_early else float("nan")

    # Third outcome: is the slope only 2017-2018? Refit dropping them.
    print("\n" + "=" * 92)
    print("IS IT JUST THE EARLY YEARS?  slope refitted from 2019 onward")
    print("=" * 92)
    late = {}
    for name, v in results.items():
        if name in MIRRORS:
            continue
        xs = [(int(y), val) for y, val in v["per_year"].items()
              if val is not None and int(y) >= 2019]
        if len(xs) < 4:
            continue
        x = np.array([a for a, _ in xs], dtype=float)
        yv = np.array([b for _, b in xs])
        x0 = x - x.mean()
        s = float((x0 * (yv - yv.mean())).sum() / (x0 * x0).sum())
        late[name] = s
        print(f"  {name:<20} full {slopes[name]:>8.2f}   from-2019 {s:>8.2f}")
    late_neg = sum(1 for s in late.values() if s < 0)
    frac_late = late_neg / len(late) if late else float("nan")

    print("\n" + "=" * 92)
    print(f"  signals measured                         {len(slopes)}")
    print(f"  negative slope                           {len(neg)}/{len(slopes)} "
          f"({frac:.0%})   [kill line {NEG_SLOPE_KILL:.0%}]")
    print(f"  negative slope AMONG those that paid early  {len(neg_paid)}/"
          f"{len(paid_early)} ({frac_paid:.0%})")
    print(f"  still negative excluding 2017-2018        {late_neg}/{len(late)} "
          f"({frac_late:.0%})")

    if frac < NEG_SLOPE_KILL:
        verdict = (
            f"REFUTED. Only {frac:.0%} of canonical signals decay, under the {NEG_SLOPE_KILL:.0%} "
            f"line I registered. 'Every edge is being competed away' is not what the data "
            f"says - payoffs move in both directions, which is a duller and more ordinary "
            f"world. I withdraw the claim.")
    elif frac_late < NEG_SLOPE_KILL:
        verdict = (
            f"REFUTED IN ITS INTERESTING FORM. {frac:.0%} of signals decay across the full "
            f"record but only {frac_late:.0%} do from 2019 onward, so the trend is carried "
            f"by 2017-2018. 'Crypto in 2017 was a different market' is a much weaker claim "
            f"than 'edges are being competed away', and it is the one that survives.")
    else:
        verdict = (
            f"SURVIVES. {frac:.0%} of canonical signals decay ({frac_paid:.0%} of those "
            f"that paid early), and {frac_late:.0%} still decay with 2017-2018 excluded, so "
            f"it is not a story about one manic era. Selecting on the SLOPE rather than the "
            f"mean is therefore worth building - but note this measures GROSS predictive "
            f"value and nothing here clears 30 bps by itself.")

    print("\nVERDICT:", verdict)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"r04_edge_decay_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps({
        "id": "R04", "at": datetime.now(timezone.utc).isoformat(),
        "horizon_bars": HORIZON, "signals": results,
        "slope_from_2019": late,
        "fraction_negative": frac, "fraction_negative_paid_early": frac_paid,
        "fraction_negative_from_2019": frac_late,
        "kill_line": NEG_SLOPE_KILL, "verdict": verdict,
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
