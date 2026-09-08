"""A125: was the instrument broken, or was it read at the wrong DISTANCE?

Two sealed readings were spent today and both lost. Three now, counting A103. Every
candidate this project's out-of-sample instrument has ever approved has then failed on
2026 - nought for three - and that is a far more serious fact than any lever.

    A103  deep-field net   walk-forward +0.2019 vs +0.1643   sealed -18.04% vs +25.71%
    A120  lean champion    held-out     +0.1769 vs +0.1572   sealed -11.65% vs +25.71%
    A124  min_hold 32      7 of 8 boundaries, median +0.0834 sealed +22.38% vs +25.71%

But before concluding that the method cannot find a winner, there is one structural
difference between the boundaries and the sealed year that nobody has controlled for,
and it is visible in data already on disk.

    a net trained <= 2022 was examined on 2023, 2024 and 2025   - one, two, three years out
    a net trained <= 2023 was examined on 2024 and 2025         - one and two years out
    a net trained <= 2024 was examined on 2025                  - one year out
    the CHAMPION trained <= 2025 and was examined on 2026       - EIGHT MONTHS out

The boundary verdict - "hold longer" - was computed by pooling every unseen year of every
net, so it is dominated by years two and three past the cutoff. The sealed year is not
even one full year past. If the market drifts away from what a net learned, the right
amount of caution should grow with that distance, and a verdict pooled over distant years
would then be exactly wrong when applied at close range.

There is a second fact pointing the same way, already in the record and never assembled:
on SEEN years the champion's 16 bars wins on every single net measured - _wf22_single
+0.2587, _wf23_single +0.2323, _wf192x3 +0.2830, _wf23_ens5 +0.2543, _wf_ref +0.2725, all
beating their own 32-bar arms. Sixteen wins on seen years; longer wins on distant unseen
years. 2026 behaved like a SEEN year. The question is whether "close to the cutoff" is
what makes a year behave that way.

------------------------------------------------------------------------------------
THE TEST, AND IT COSTS NO COMPUTE AT ALL
------------------------------------------------------------------------------------
Every per-year return needed is already stored in rnd/a122_*.json and rnd/a123_*.json.
Re-group them by DISTANCE - the exam year minus the net's cutoff - instead of by the
"seen / unseen" binary that hid this, and read off the ratio of each hold against 16.

  REGISTERED PREDICTION   at distance +1 the champion's 16 bars wins or ties, and the
                          advantage of a longer hold appears only at +2 and +3.
                          -> then the instrument was misread rather than broken: it was
                             applied at a distance it had never been validated at, and
                             the sealed result at +1 is exactly what it should have
                             predicted.
  THE ALTERNATIVE         the advantage is flat across distances, so distance explains
                          nothing and the instrument genuinely does not transfer to the
                          sealed year. Then the honest move is to stop buying candidates
                          with it and to say so.

Either answer is worth having, and neither costs a sealed reading. Nothing is adopted
here under any outcome; min_hold is already closed by its own pre-registered rule.

ADDENDUM, added after the run and marked as such because the text above is the
pre-registration and must not be edited into agreement with its own result.

The registered prediction was WRONG: longer holds beat 16 at +1 year too (1.02x, 1.10x,
1.05x, 1.05x), so distance explains nothing. But the first version of this file then
printed "the instrument does not transfer - stop buying candidates with it", and that
conclusion was drawn off medians alone, which is the same mistake in a different suit.

Looking at the SPREAD instead: at +1 year the 32-bar ratio runs 0.76x to 1.52x across
seven net-years, median 1.02x, winning 71% of them. The sealed draw was 0.97x - inside
that range, below two of the seven. A 2% median edge with that spread cannot be settled
by one year in either direction. The instrument is not refuted; the reading was bought at
odds nobody had computed, and eight "boundaries" were treated as eight verdicts when at
the distance that matters they are seven noisy year-observations.

The protocol change that follows is in the printed verdict and is the durable part of
this file: do not spend a sealed reading on an edge whose year-to-year spread straddles
1.0.

Run from repo root:
    PYTHONPATH=trading-system python research/system06/tools/a125_distance_from_cutoff.py
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
RND = ROOT / "rnd"
BASE_HOLD = 16
# What the sealed reading actually produced, so the draw can be placed inside the
# distribution the boundaries describe instead of compared to its median alone.
# A124-sealed: +22.38% against the control's +25.71% -> 1.2238 / 1.2571.
SEALED_HOLD = 32
SEALED_RATIO = 1.2238 / 1.2571
CUTOFFS = {"_wf22_single": 2022, "_wf22_ens5": 2022,
           "_wf23_single": 2023, "_wf23_ens5": 2023, "_wf23_ref": 2023,
           "_wf192x3": 2024, "_wf_recency_hl2": 2024, "_wf_ref": 2024}


def _latest(pattern: str) -> dict | None:
    files = sorted(RND.glob(pattern))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def collect() -> dict[str, dict[int, dict[str, float]]]:
    """{net: {hold: {year: return}}} from every study that stored per-year returns."""
    out: dict[str, dict[int, dict[str, float]]] = defaultdict(dict)
    a122 = _latest("a122_boundary_*.json")
    if a122:
        for net, rows in (a122.get("results") or {}).items():
            for hold, r in rows.items():
                if r.get("returns"):
                    out[net][int(hold)] = r["returns"]
    a123 = _latest("a123_hold_replication_*.json")
    if a123:
        for net, rows in (a123.get("fresh") or {}).items():
            for hold, r in rows.items():
                if r.get("returns"):
                    out[net][int(hold)] = r["returns"]
    return out


def main() -> int:
    data = collect()
    if not data:
        sys.exit("no stored per-year returns found - A122/A123 json missing")

    # distance -> hold -> [ratio against the 16-bar arm of the SAME net and year]
    by_distance: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    coverage: dict[int, set] = defaultdict(set)
    for net, holds in data.items():
        cutoff = CUTOFFS.get(net)
        base = holds.get(BASE_HOLD)
        if cutoff is None or not base:
            continue
        for hold, rets in holds.items():
            if hold == BASE_HOLD:
                continue
            for year, r in rets.items():
                d = int(year) - cutoff
                if d <= 0:
                    continue                      # a year the net trained on
                b = base.get(year)
                if b is None or (1.0 + b) <= 0:
                    continue
                by_distance[d][hold].append((1.0 + r) / (1.0 + b))
                coverage[d].add(net)

    holds = sorted({h for d in by_distance.values() for h in d})
    print("=" * 96)
    print(f"RETURN RATIO AGAINST THE {BASE_HOLD}-BAR ARM, grouped by YEARS PAST THE "
          f"NET'S CUTOFF")
    print("=" * 96)
    print(f"{'distance':>9} {'nets':>5} " + " ".join(f"{h:>12}" for h in holds))
    rows = {}
    for d in sorted(by_distance):
        cells, med = [], {}
        for h in holds:
            vals = by_distance[d].get(h) or []
            if vals:
                m = statistics.median(vals)
                med[h] = m
                cells.append(f"{m:>11.2f}x")
            else:
                cells.append("           -")
        rows[d] = med
        print(f"{d:>9} {len(coverage[d]):>5} " + " ".join(cells))
    print(f"  (median over every net-year at that distance; >1 means the longer hold "
          f"beat {BASE_HOLD})")

    # ---- the adjudication -----------------------------------------------------------
    longs = [h for h in holds if h > BASE_HOLD]
    near = rows.get(1, {})
    far = {h: statistics.median(
        [v for d in rows if d >= 2 and (v := rows[d].get(h)) is not None] or [float("nan")])
        for h in longs}
    print("\n" + "-" * 96)
    print(f"{'hold':>6} {'at +1 year':>12} {'at +2 and beyond':>18} {'verdict':>10}")
    near_wins, far_wins = 0, 0
    for h in longs:
        n, f = near.get(h), far.get(h)
        if n is not None and n > 1.0:
            near_wins += 1
        if f == f and f is not None and f > 1.0:      # f == f rejects NaN
            far_wins += 1
        tag = ""
        if n is not None and f == f and f is not None:
            tag = "grows" if f > n else "shrinks"
        print(f"{h:>6} {(f'{n:.2f}x' if n is not None else '-'):>12} "
              f"{(f'{f:.2f}x' if f == f and f is not None else '-'):>18} {tag:>10}")

    confirmed = near_wins == 0 and far_wins >= 1
    print(f"\nlonger holds beating {BASE_HOLD} at +1 year:      {near_wins} of {len(longs)}")
    print(f"longer holds beating {BASE_HOLD} at +2 and beyond: {far_wins} of {len(longs)}")

    # ---- POWER, which the first version of this file forgot to look at ---------------
    # A median is not a verdict. If the per-year ratios at the matched distance are
    # spread from 0.76x to 1.52x, then a median of 1.02x means the lever wins about
    # seven years in ten and loses three, and ONE sealed year cannot distinguish that
    # from nothing. The first run of this file printed "the instrument does not
    # transfer" off the medians alone, which mistook an underpowered measurement for a
    # refuted one - the same error as reading a coin that came up tails twice.
    spread = {}
    for h in longs:
        vals = sorted(by_distance.get(1, {}).get(h) or [])
        if len(vals) >= 4:
            q = statistics.quantiles(vals, n=4)
            spread[h] = {"n": len(vals), "min": vals[0], "q1": q[0],
                         "median": statistics.median(vals), "q3": q[2], "max": vals[-1],
                         "share_above_1": sum(1 for v in vals if v > 1.0) / len(vals)}
    print(f"\nper-year spread at +1 year - the range ONE sealed reading is drawn from:")
    print(f"{'hold':>6} {'n':>3} {'min':>7} {'q1':>7} {'median':>8} {'q3':>7} "
          f"{'max':>7} {'years won':>10}   sealed draw")
    for h in longs:
        s = spread.get(h)
        if not s:
            continue
        mark = ""
        if SEALED_RATIO is not None and h == SEALED_HOLD:
            below = sum(1 for v in by_distance[1][h] if v < SEALED_RATIO)
            mark = (f"   {SEALED_RATIO:.2f}x -> below {below}/{s['n']}, "
                    f"{'INSIDE' if s['min'] <= SEALED_RATIO <= s['max'] else 'OUTSIDE'} "
                    f"the range")
        print(f"{h:>6} {s['n']:>3} {s['min']:>7.2f} {s['q1']:>7.2f} {s['median']:>8.2f} "
              f"{s['q3']:>7.2f} {s['max']:>7.2f} {s['share_above_1']:>9.0%}{mark}")

    s = spread.get(SEALED_HOLD)
    inside = bool(s and SEALED_RATIO is not None and s["min"] <= SEALED_RATIO <= s["max"])
    if confirmed:
        verdict = (f"DISTANCE EXPLAINS IT - no longer hold beats {BASE_HOLD} one year "
                   f"past the cutoff, and the advantage appears only further out.")
    elif inside:
        verdict = (
            f"UNDERPOWERED, NOT REFUTED - at the matched distance the {SEALED_HOLD}-bar "
            f"ratio runs {s['min']:.2f}x to {s['max']:.2f}x with a median of "
            f"{s['median']:.2f}x, winning {s['share_above_1']:.0%} of years. The sealed "
            f"draw of {SEALED_RATIO:.2f}x sits INSIDE that range. A median edge of "
            f"{(s['median'] - 1) * 100:.0f}% cannot be decided by one year, so the "
            f"reading neither confirms nor refutes the lever - it was bought at odds we "
            f"never computed. The instrument is not broken; it was read as though eight "
            f"boundaries were eight independent verdicts when at the distance that "
            f"matters they are {s['n']} noisy year-observations.")
    elif near_wins and far_wins:
        verdict = (f"THE SEALED YEAR IS OUTSIDE THE RANGE - the {SEALED_HOLD}-bar ratio "
                   f"never fell as low on any boundary as it did on 2026. That is a "
                   f"genuine failure to transfer rather than a bad draw.")
    else:
        verdict = ("MIXED - the distances disagree with each other; report the table and "
                   "claim nothing from it.")
    print(f"\nVERDICT: {verdict}")
    print("\nNothing is adopted here. min_hold closed this morning under its own "
          "pre-registered rule and stays closed. What this changes is the PROTOCOL: a "
          "sealed reading should not be spent on an edge whose year-to-year spread "
          "straddles 1.0, because the reading cannot settle it either way.")

    out = RND / f"a125_distance_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A125", "at": datetime.now(timezone.utc).isoformat(),
        "sealed_read": False, "base_hold": BASE_HOLD,
        "cutoffs": CUTOFFS,
        "median_ratio_by_distance": {str(d): {str(h): v for h, v in rows[d].items()}
                                     for d in sorted(rows)},
        "nets_per_distance": {str(d): sorted(coverage[d]) for d in sorted(coverage)},
        "near_wins": near_wins, "far_wins": far_wins, "spread_at_plus_one": spread, "sealed_ratio": SEALED_RATIO, "sealed_hold": SEALED_HOLD, "sealed_inside_range": inside,
        "distance_explains_it": confirmed, "verdict": verdict,
        "note": "pure re-analysis of returns already stored by A122 and A123; no "
                "backtest was run and 2026 was not read.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
