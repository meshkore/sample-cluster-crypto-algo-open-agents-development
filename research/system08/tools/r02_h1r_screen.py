"""R02: a coarse, cheap screen of H1-R. It can KILL the hypothesis. It cannot confirm it.

H1-R, as the external reviewers corrected it, is about the IMPACT RESIDUAL:

    R_t = I_t - E[I_t | state_t]

Large aggressive flow that moves price LESS than that flow normally moves it has been
absorbed by something. The claim is that the absorption is informative - that a passive
participant large enough to absorb a 90th-percentile flow is telling you something the
flow alone does not.

Their pre-registered test is a 5-minute formation window and a 60-minute horizon, which
needs `aggTrades` we have not downloaded (415 MB per month per symbol). This is not that
test and cannot pass for it. What it is: the same shape at 15 minutes, over nine years,
from data already on disk - because our 15m candles carry `taker_buy_volume`, so

    signed_flow = 2 * taker_buy_volume - volume

is available from 2017 without a single byte downloaded. The reviewers were explicit that
15m is a diagnostic and "may not rescue H1-R if the pre-registered 5m test fails". The
asymmetry is the point and it runs the other way too: a coarse screen that finds NOTHING
across nine years and fourteen symbols is a reason not to spend a week and 30 GB on the
fine one. Cheap first, and let the cheap thing only be able to give bad news.

WHAT IS PRE-REGISTERED, BEFORE THE NUMBERS EXIST

  The quantity that decides this is NOT "do absorbed-flow bars predict returns". Flow
  alone predicts returns - Anastasopoulos et al. (JFM 2026) find order flow has a
  PERMANENT same-direction effect, and we verified that paper is real. A bucket selected
  on high flow will therefore look predictive whether or not the residual carries
  anything. The decisive quantity is the DIFFERENCE:

      C - B    where B = high flow, any residual      (the continuation baseline)
                     C = high flow AND low residual   (absorption)

  If the residual is inert, C - B is zero and every apparent edge in C belongs to B.

  Direction is deliberately NOT predicted. Two readings of absorption are equally
  standard and they disagree: informed passive accumulation implies CONTINUATION, a large
  passive seller implies REVERSAL. Predicting a direction I do not hold would be theatre.
  The test is two-sided.

  KILL CRITERION, registered now: if |C - B| at the 60-minute horizon is under 5 bps, the
  hypothesis is dead at this resolution and we do not download aggTrades for it. The
  round trip costs 30 bps. An effect that cannot pay a sixth of its own toll does not
  become tradeable by being measured more finely - it becomes a smaller number measured
  more precisely.

  EVENT COUNT IS REPORTED BEFORE ANY RESULT. This is my addition to the reviewers' plan:
  their power discipline sits at stage 8, and stage 2 is where we decide to continue or
  stop. A mean return computed on 40 clustered events is not evidence either way, and I
  would rather know that before I read it than after.

2026 IS NOT TOUCHED. `cat.research()` stops at the lock. The reviewers also flagged 2026
as contaminated for this hypothesis - they shaped it, so it cannot be its own clean test -
which is a second reason, not a substitute for the first.

Run from the repo root:
    PYTHONPATH=trading-system python research/system08/tools/r02_h1r_screen.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OUT = Path("research/system08/rnd")

WINDOW = 2880          # 30 days of 15m bars: the trailing window for every causal stat
FLOW_P = 0.90          # "large flow" = top decile of |signed flow| in its own month
RESID_P = 0.20         # "absorbed"   = bottom quintile of directional residual
CLUSTER_BARS = 4       # adjacent qualifying bars are ONE event, not four
HORIZONS = (1, 2, 4, 8, 16)          # bars -> 15, 30, 60, 120, 240 minutes
DECIDING_H = 4                        # 60 minutes, the reviewers' horizon
KILL_BPS = 5.0
COST_BPS = 30.0


def shift1(a: np.ndarray) -> np.ndarray:
    """Everything computed from a trailing window must be usable only on the NEXT bar.

    Without this the beta used to explain bar t is fitted on a window that contains bar
    t, so the residual is partly the model explaining the very observation it is being
    scored on - the residual shrinks for mechanical reasons and 'absorption' becomes an
    artefact of the fit.
    """
    out = np.full(a.size, np.nan)
    out[1:] = a[:-1]
    return out


def roll_mean(a: np.ndarray, w: int) -> np.ndarray:
    """Trailing mean, NaN until the window is full. NaNs propagate rather than being
    silently treated as zero."""
    n = a.size
    out = np.full(n, np.nan)
    if n < w:
        return out
    c = np.concatenate(([0.0], np.nancumsum(a)))
    valid = np.concatenate(([0.0], np.cumsum(~np.isnan(a))))
    s = c[w:] - c[:-w]
    k = valid[w:] - valid[:-w]
    with np.errstate(invalid="ignore", divide="ignore"):
        out[w - 1:] = np.where(k == w, s / w, np.nan)
    return out


def roll_pct(a: np.ndarray, w: int) -> np.ndarray:
    """Where the current value sits in its own trailing window, midrank, in [0,1]."""
    n = a.size
    out = np.full(n, np.nan)
    if n < w:
        return out
    view = np.lib.stride_tricks.sliding_window_view(a, w)
    cur = a[w - 1:, None]
    with np.errstate(invalid="ignore"):
        below = np.nansum(view < cur, axis=1)
        equal = np.nansum(view == cur, axis=1)
    out[w - 1:] = (below + 0.5 * equal) / w
    return out


def per_symbol(bars) -> list[dict] | None:
    """Every bar of one symbol, reduced to the handful of numbers the test needs."""
    n = len(bars)
    if n < WINDOW + max(HORIZONS) + 10:
        return None
    close = np.array([float(b.close) for b in bars])
    vol = np.array([float(b.volume or 0.0) for b in bars])
    tbv = np.array([(float(b.taker_buy_volume)
                     if getattr(b, "taker_buy_volume", None) is not None else np.nan)
                    for b in bars])
    if np.isnan(tbv).all():
        return None

    with np.errstate(invalid="ignore", divide="ignore"):
        # Signed aggressive flow, scaled by the symbol's own recent turnover so that one
        # coin's 2021 is comparable to another coin's 2019. An unscaled base-volume flow
        # would rank BTC's quiet bars above an altcoin's violent ones forever.
        signed = 2.0 * tbv - vol
        scale = roll_mean(vol, WINDOW)
        f = np.where(scale > 0, signed / scale, np.nan)
        ret = np.full(n, np.nan)
        ret[1:] = np.log(close[1:] / close[:-1])

    # E[I | f] from a STRICTLY PAST rolling regression through the origin. Through the
    # origin because zero net aggression should imply zero expected impact; an intercept
    # here would just absorb drift and call it price impact.
    num = roll_mean(ret * f, WINDOW)
    den = roll_mean(f * f, WINDOW)
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = np.where(den > 0, num / den, np.nan)
    beta = shift1(beta)
    expected = beta * f
    resid = ret - expected
    sgn = np.sign(f)
    resid_dir = resid * sgn          # "less than expected IN THE DIRECTION OF THE FLOW"

    pct_flow = roll_pct(np.abs(f), WINDOW)
    pct_resid = roll_pct(resid_dir, WINDOW)

    fwd = {}
    for h in HORIZONS:
        y = np.full(n, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            y[:-h] = np.log(close[h:] / close[:-h])
        fwd[h] = y * sgn             # signed by the flow, so >0 always means CONTINUATION

    rows = []
    for i in range(WINDOW, n - max(HORIZONS)):
        if not np.isfinite(pct_flow[i]) or not np.isfinite(pct_resid[i]):
            continue
        if sgn[i] == 0:
            continue
        rec = {"i": i, "day": bars[i].timestamp.strftime("%Y-%m-%d"),
               "year": bars[i].timestamp.year,
               "pf": float(pct_flow[i]), "pr": float(pct_resid[i])}
        ok = True
        for h in HORIZONS:
            v = fwd[h][i]
            if not np.isfinite(v):
                ok = False
                break
            rec[f"y{h}"] = float(v)
        if ok:
            rows.append(rec)
    return rows


def cluster(rows: list[dict]) -> list[dict]:
    """Adjacent qualifying bars are one event.

    A 90th-percentile flow rarely arrives alone; without this a single episode
    contributes four or five near-identical observations and every standard error is
    computed as if they were independent draws.
    """
    out, last = [], -10**9
    for r in rows:
        if r["i"] - last > CLUSTER_BARS:
            out.append(r)
        last = r["i"]
    return out


def day_clustered(rows: list[dict], key: str) -> tuple[float, float, int]:
    """Mean, and a standard error clustered on the CALENDAR DAY across all symbols.

    Crypto is one risk factor sampled fourteen times: two symbols on the same afternoon
    are not two independent observations. Clustering on the day is the cheapest honest
    correction; the alternative of treating 40,000 bar-level rows as independent would
    manufacture a t-stat out of cross-sectional correlation.
    """
    if not rows:
        return float("nan"), float("nan"), 0
    by_day = defaultdict(list)
    for r in rows:
        by_day[r["day"]].append(r[key])
    daily = np.array([np.mean(v) for v in by_day.values()])
    m = float(np.mean(daily))
    se = float(np.std(daily, ddof=1) / np.sqrt(daily.size)) if daily.size > 1 else float("nan")
    return m, se, daily.size


def bps(x: float) -> float:
    return x * 10_000.0


def main() -> int:
    import quantlab_catalog as cat

    symbols = cat.load_universe()
    print(f"loading {len(symbols)} symbols at 15m (research era only, 2026 untouched) ...",
          flush=True)
    research = cat.research(symbols)

    everything: list[dict] = []
    used = []
    for sym in symbols:
        bars = research.get(sym) or []
        rows = per_symbol(bars)
        if not rows:
            print(f"  {sym:<12} skipped (no taker_buy_volume or too short)")
            continue
        for r in rows:
            r["sym"] = sym
        everything.extend(rows)
        used.append(sym)
        print(f"  {sym:<12} {len(rows):>8,} usable bars", flush=True)

    if not everything:
        sys.exit("no usable bars - is taker_buy_volume present in the 15m candles?")

    # ---- the three populations ------------------------------------------------------
    A = everything
    B = [r for r in A if r["pf"] >= FLOW_P]                       # continuation baseline
    C_raw = [r for r in B if r["pr"] <= RESID_P]                  # absorption

    by_sym = defaultdict(list)
    for r in C_raw:
        by_sym[r["sym"]].append(r)
    C = []
    for sym in sorted(by_sym):
        C.extend(cluster(sorted(by_sym[sym], key=lambda r: r["i"])))

    B_by_sym = defaultdict(list)
    for r in B:
        B_by_sym[r["sym"]].append(r)
    B_cl = []
    for sym in sorted(B_by_sym):
        B_cl.extend(cluster(sorted(B_by_sym[sym], key=lambda r: r["i"])))

    # ---- COUNT FIRST, before a single return is printed -------------------------------
    print("\n" + "=" * 84)
    print("HOW MUCH EVIDENCE IS THERE - read this before any return below")
    print("=" * 84)
    print(f"  symbols used                         {len(used)}")
    print(f"  bars scored                          {len(A):,}")
    print(f"  B  high flow (>= p{FLOW_P * 100:.0f})           "
          f"{len(B):,} bars -> {len(B_cl):,} clustered events")
    print(f"  C  + absorbed (resid <= p{RESID_P * 100:.0f})     "
          f"{len(C_raw):,} bars -> {len(C):,} clustered events")
    print(f"  distinct days in C                   "
          f"{len({r['day'] for r in C}):,}")
    print(f"  years spanned                        "
          f"{min(r['year'] for r in C)}-{max(r['year'] for r in C)}")

    # ---- the comparison that decides ---------------------------------------------------
    print("\n" + "=" * 84)
    print("FORWARD RETURN, SIGNED BY THE FLOW  (>0 = continuation, <0 = reversal)")
    print("all figures in basis points; a round trip costs "
          f"{COST_BPS:.0f} bps")
    print("=" * 84)
    print(f"{'horizon':>9} {'A all bars':>12} {'B high flow':>13} {'C absorbed':>13} "
          f"{'C - B':>10} {'se(C)':>9} {'t(C-B)':>8}")

    table = {}
    for h in HORIZONS:
        k = f"y{h}"
        ma, _, _ = day_clustered(A, k)
        mb, seb, _ = day_clustered(B_cl, k)
        mc, sec, nd = day_clustered(C, k)
        diff = mc - mb
        # Independent-ish SE for the difference; B and C overlap, so this UNDERSTATES
        # the correlation between them and therefore OVERSTATES the t. Stated because a
        # generous t that still fails is a stronger kill than a strict one.
        se_d = float(np.sqrt(sec ** 2 + seb ** 2)) if np.isfinite(sec) and np.isfinite(seb) else float("nan")
        t = diff / se_d if se_d and np.isfinite(se_d) and se_d > 0 else float("nan")
        table[h] = {"A": bps(ma), "B": bps(mb), "C": bps(mc), "diff": bps(diff),
                    "se_C": bps(sec), "t": t, "days": nd}
        print(f"{h * 15:>7}m {bps(ma):>12.2f} {bps(mb):>13.2f} {bps(mc):>13.2f} "
              f"{bps(diff):>10.2f} {bps(sec):>9.2f} {t:>8.2f}")

    # ---- the 2D surface the reviewers asked for ----------------------------------------
    print("\n" + "=" * 84)
    print(f"FLOW DECILE x RESIDUAL QUINTILE, forward {DECIDING_H * 15}m in bps "
          f"(cell count underneath)")
    print("=" * 84)
    grid = defaultdict(list)
    for r in A:
        fd = min(9, int(r["pf"] * 10))
        rq = min(4, int(r["pr"] * 5))
        grid[(fd, rq)].append(r[f"y{DECIDING_H}"])
    print(f"{'flow dec':>9}" + "".join(f"{'R q' + str(q + 1):>11}" for q in range(5)))
    for fd in range(9, -1, -1):
        cells = []
        for rq in range(5):
            v = grid.get((fd, rq)) or []
            cells.append(f"{bps(float(np.mean(v))):>11.1f}" if len(v) >= 30 else f"{'-':>11}")
        print(f"{fd + 1:>9}" + "".join(cells))

    # ---- adjudication against the criterion registered above ----------------------------
    dec = table[DECIDING_H]
    verdict_bps = abs(dec["diff"])
    if verdict_bps < KILL_BPS:
        verdict = (
            f"DEAD AT THIS RESOLUTION. The residual adds {dec['diff']:+.2f} bps to what "
            f"flow alone already gives at {DECIDING_H * 15}m, against a {KILL_BPS:.0f} bp "
            f"kill line and a {COST_BPS:.0f} bp round trip. Every apparent edge in the "
            f"absorbed bucket belongs to the flow, not to the absorption. Do NOT spend a "
            f"week and 30 GB downloading aggTrades to measure this more finely.")
    elif abs(dec["t"]) < 2.0:
        verdict = (
            f"NOT SETTLED. C - B is {dec['diff']:+.2f} bps at {DECIDING_H * 15}m, which "
            f"clears the {KILL_BPS:.0f} bp line, but t = {dec['t']:.2f} on "
            f"{dec['days']:,} clustered days - and that t is already generous, because "
            f"the difference's standard error ignores that B contains C. Survives the "
            f"screen; is not evidence.")
    else:
        verdict = (
            f"SURVIVES THE SCREEN. C - B = {dec['diff']:+.2f} bps at {DECIDING_H * 15}m, "
            f"t = {dec['t']:.2f}. This does NOT confirm H1-R - the pre-registered test is "
            f"5-minute formation and this is 15 - but it is the first thing that would "
            f"justify downloading aggTrades. Direction: "
            f"{'continuation' if dec['diff'] > 0 else 'reversal'}.")

    print("\n" + "=" * 84)
    print("VERDICT:", verdict)
    print("=" * 84)
    print("This screen can kill H1-R. It cannot confirm it: the pre-registered formation "
          "window is 5\nminutes and this is 15, and the reviewers were explicit that a "
          "15m diagnostic may not rescue\nthe hypothesis if the 5m test fails.")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"r02_h1r_screen_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps({
        "id": "R02", "at": datetime.now(timezone.utc).isoformat(),
        "window_bars": WINDOW, "flow_percentile": FLOW_P,
        "residual_percentile": RESID_P, "cluster_bars": CLUSTER_BARS,
        "symbols": used, "bars_scored": len(A),
        "events_B": len(B_cl), "events_C": len(C),
        "days_in_C": len({r["day"] for r in C}),
        "by_horizon_bps": table, "kill_line_bps": KILL_BPS,
        "deciding_horizon_min": DECIDING_H * 15, "verdict": verdict,
        "note": "15m formation from taker_buy_volume; the reviewers' pre-registered "
                "test is 5m from aggTrades. This screen can only kill.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
