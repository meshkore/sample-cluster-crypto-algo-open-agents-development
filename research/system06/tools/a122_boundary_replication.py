"""A122: the same year, seen by one net and unseen by another. Memorisation or decay?

A121 confirmed its registered prediction on one net. On `_wf23_ref` (trained <= 2023),
removing the minimum hold pays 1.88x median on the years that net trained on and 0.85x
on the two it never saw - and its 2024 ratio is 0.70x, the same number the champion net
produced for 2026, the only year IT never saw. The held-out score went from -0.1417 to
-0.4033. The signature reproduced across two independent nets.

But one confound survives that test, and it is the whole reason for this file. In every
measurement so far, "unseen" and "recent" are the same thing. A net trained to 2023 has
2024-2025 unseen AND last; the champion has 2026 unseen AND last. So "the lever stops
paying because the net never saw the year" and "the lever stops paying because the market
got harder lately" both fit every number on the table.

Three nets break the tie, because they put the SAME CALENDAR YEAR on both sides:

    _wf22_single   trained <= 2022    2023, 2024, 2025 unseen
    _wf23_single   trained <= 2023    2023 SEEN, 2024 and 2025 unseen
    _wf192x3       trained <= 2024    2023 and 2024 SEEN, 2025 unseen

2023 is unseen for one net and seen for two. 2024 is unseen for two and seen for one.
2025 is unseen for all three, so it says nothing and is reported anyway. If the ratio for
a given year depends on whether THAT NET saw it, rather than on which year it is, then
decay is dead and memorisation is the mechanism - proven within the calendar year, with
the market held fixed.

------------------------------------------------------------------------------------
REGISTERED BEFORE THE RUN
------------------------------------------------------------------------------------
  MEMORISATION CONFIRMED   for at least 2 of {2023, 2024}, the min_hold=1 ratio is
                           materially lower (>= 0.25x) on the nets that never saw the
                           year than on the nets that did.
  DECAY                    the ratio for a year is about the same whatever the net's
                           cutoff. Then A121's result is about recency, not memory, and
                           the sealed loss needs a different explanation.

AND THE FORWARD QUESTION, which is the one that could still pay. On unseen years A121's
curve ran BACKWARDS: min_hold 48 scored +0.0059 and min_hold 24 scored -0.0097 against
the champion setting's -0.1417, while min_hold 1 scored -0.4033. That is not a smaller
effect, it is an INVERTED one - on years the net has not memorised, holding LONGER was
better. Every study this project has run said the opposite, and every one of them scored
on years the net had trained on.

  LONGER EARNS A TEST   on all three nets, the unseen-year score at min_hold >= 32 beats
                        the unseen-year score at the champion's 16.

Nothing is adopted here under any outcome. A sealed reading was spent and lost hours ago;
the next one has to be bought with a result that replicates across independent
boundaries, which is precisely what this file is for. 2026 is not read.

Run from repo root:
    PYTHONPATH=trading-system python research/system06/tools/a122_boundary_replication.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")

# net dir -> the last year its weights ever saw
NETS: dict[str, int] = {
    "_wf22_single": 2022,
    "_wf23_single": 2023,
    "_wf192x3": 2024,
}
ALL_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
SHARED = (2023, 2024)        # the years that are seen by some nets and unseen by others
CHAMPION_MIN_HOLD = 16
HOLDS = (1, 8, 16, 32, 64, 128)
LONG = 32                    # "longer than the champion" starts here
STEP_MARGIN = 0.25           # how much lower the unseen ratio must be to count

# No ARMS table here on purpose: this study's arms ARE `HOLDS`, one lever at six
# settings across three nets, and inventing a parallel names table would give the report
# a second source of truth to drift from.


def _nopt():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ratio(arm: dict, base: dict, year: str) -> float | None:
    """Growth multiple of the arm against the baseline for one year (ratio of 1+r)."""
    a, b = arm.get(year), base.get(year)
    if a is None or b is None or (1.0 + b) <= 0:
        return None
    return (1.0 + a) / (1.0 + b)


def point_for(nopt, anchor: dict, hold: int) -> dict:
    p = dict(anchor)
    p["min_hold"] = int(hold)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nets", nargs="*", help="restrict to these net directories")
    args = ap.parse_args()

    nets = {n: c for n, c in NETS.items() if not args.nets or n in args.nets}
    for name in nets:
        if not (ROOT / name / "signals.npz").exists():
            sys.exit(f"{name}/signals.npz missing - A122 needs all three boundaries")

    nopt = _nopt()
    # One Evaluator, one load of the bars. The net is swapped between runs by pointing
    # its signal and overlay paths at another directory, which is exactly what net_dir
    # does at construction - done here in a loop so eight years of candles are not read
    # from disk three times for no reason.
    first = next(iter(nets))
    ev = nopt.Evaluator(tuple(y for y in ALL_YEARS if y <= nets[first]),
                        tuple(y for y in ALL_YEARS if y > nets[first]),
                        with_enter=False, net_dir=ROOT / first)
    anchor = nopt._champion_point_full(ev.risk, ev.band, list(nopt.SPACE))
    if int(anchor["min_hold"]) != CHAMPION_MIN_HOLD:
        print(f"note: the champion's min_hold is {anchor['min_hold']}, not "
              f"{CHAMPION_MIN_HOLD}; the baseline arm follows the champion")

    print(f"A122 - {len(HOLDS)} holds x {len(nets)} boundaries, 2026 NOT read\n", flush=True)

    out: dict[str, dict] = {}
    for net, cutoff in nets.items():
        seen = tuple(y for y in ALL_YEARS if y <= cutoff)
        unseen = tuple(y for y in ALL_YEARS if y > cutoff)
        ev.net_dir = ROOT / net
        ev.signals = str(ROOT / net / "signals.npz")
        ev.meta_path = ROOT / net / "meta.npz"
        ev.money_path = ROOT / net / "moneymodel.npz"
        ev.fit_years, ev.holdout_years = seen, unseen
        ev.years = tuple(sorted(set(seen) | set(unseen)))
        print(f"--- {net}: trained <= {cutoff}; unseen {unseen} ---", flush=True)
        rows = {}
        for hold in HOLDS:
            t0 = time.time()
            try:
                r = ev.score(point_for(nopt, anchor, hold))
            except Exception as exc:  # noqa: BLE001
                print(f"  min_hold {hold:>4}  FAILED: {exc}", flush=True)
                continue
            rows[hold] = r
            print(f"  min_hold {hold:>4}  seen {r['fit']:+.4f}  UNSEEN {r['holdout']:+.4f}"
                  f"  trades {r['trades']:>5}  ({time.time() - t0:.0f}s)", flush=True)
        out[net] = {"cutoff": cutoff, "seen": list(seen), "unseen": list(unseen),
                    "rows": rows}

    # ---- the cross-net contrast -----------------------------------------------------
    print("\n" + "=" * 96)
    print("THE SAME YEAR, SEEN AND UNSEEN: min_hold=1 return ratio against that net's "
          "own baseline")
    print("=" * 96)
    print(f"{'net':<16} {'cutoff':>7} " + " ".join(f"{y:>13}" for y in ALL_YEARS))
    by_year: dict[int, dict[str, list[float]]] = {y: {"seen": [], "unseen": []}
                                                  for y in ALL_YEARS}
    for net, blk in out.items():
        rows = blk["rows"]
        if 1 not in rows or CHAMPION_MIN_HOLD not in rows:
            continue
        base = rows[CHAMPION_MIN_HOLD]["returns"]
        cells = []
        for y in ALL_YEARS:
            v = ratio(rows[1]["returns"], base, str(y))
            tag = "s" if y <= blk["cutoff"] else "U"
            cells.append(f"{v:>11.2f}{tag}" if v is not None else "            -")
            if v is not None:
                by_year[y]["seen" if y <= blk["cutoff"] else "unseen"].append(v)
        print(f"{net:<16} {blk['cutoff']:>7} " + " ".join(cells))
    print("  s = the net trained on that year   U = it never saw it")

    print(f"\n{'year':>6} {'ratio when SEEN':>18} {'ratio when UNSEEN':>19} {'gap':>8}")
    gaps = {}
    for y in ALL_YEARS:
        s, u = by_year[y]["seen"], by_year[y]["unseen"]
        ms = statistics.mean(s) if s else None
        mu = statistics.mean(u) if u else None
        gap = (ms - mu) if (ms is not None and mu is not None) else None
        gaps[y] = gap
        print(f"{y:>6} {(f'{ms:.2f}x (n={len(s)})' if ms else '-'):>18} "
              f"{(f'{mu:.2f}x (n={len(u)})' if mu else '-'):>19} "
              f"{(f'{gap:+.2f}' if gap is not None else '-'):>8}")

    decided = [y for y in SHARED if gaps.get(y) is not None]
    confirms = [y for y in decided if gaps[y] >= STEP_MARGIN]
    memorisation = len(confirms) >= 2
    print(f"\nyears with the year held fixed and only the net's memory changing: "
          f"{decided or 'none'}")
    print(f"of those, {len(confirms)} show the lever paying at least {STEP_MARGIN:.2f}x "
          f"more when the net had seen the year: {confirms or 'none'}")
    print(f"MEMORISATION CONFIRMED ACROSS BOUNDARIES: {memorisation}")

    # ---- the forward question -------------------------------------------------------
    print("\n" + "-" * 96)
    print("does holding LONGER than the champion help on years the net never saw?")
    longer_ok, detail = True, {}
    for net, blk in out.items():
        rows = blk["rows"]
        if CHAMPION_MIN_HOLD not in rows:
            longer_ok = False
            continue
        champ_u = rows[CHAMPION_MIN_HOLD]["holdout"]
        best_long = max(((h, rows[h]["holdout"]) for h in rows if h >= LONG),
                        key=lambda kv: kv[1], default=(None, None))
        wins = best_long[1] is not None and best_long[1] > champ_u
        longer_ok = longer_ok and wins
        detail[net] = {"champion_unseen": champ_u, "best_long_hold": best_long[0],
                       "best_long_unseen": best_long[1], "wins": wins}
        print(f"  {net:<16} champion({CHAMPION_MIN_HOLD}) {champ_u:+.4f}   "
              f"best >= {LONG}: {best_long[0]} at {best_long[1]:+.4f}   "
              f"{'WINS' if wins else 'loses'}")
    print(f"LONGER EARNS A TEST (all three boundaries): {longer_ok}")
    print("\nNothing is adopted here whatever this says. A sealed reading was spent and "
          "lost today; the next one is bought by replication, not by a good table.")

    path = ROOT / "rnd" / f"a122_boundary_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps({
        "id": "A122", "at": datetime.now(timezone.utc).isoformat(),
        "sealed_read": False, "nets": {n: b["cutoff"] for n, b in out.items()},
        "holds": list(HOLDS), "shared_years": list(SHARED),
        "step_margin": STEP_MARGIN, "long_from": LONG,
        "ratio_by_year": {str(y): {k: v for k, v in by_year[y].items()}
                          for y in ALL_YEARS},
        "gaps": {str(y): gaps[y] for y in ALL_YEARS},
        "memorisation_confirmed": memorisation,
        "longer_earns_a_test": longer_ok, "longer_detail": detail,
        "results": {n: {str(h): {k: r[k] for k in (
            "fit", "holdout", "fit_min_year", "holdout_min_year", "trades", "returns")}
            for h, r in b["rows"].items()} for n, b in out.items()},
        "note": "`fit`/`holdout` mean SEEN-BY-THAT-NET and UNSEEN-BY-THAT-NET. The point "
                "of three cutoffs is that 2023 and 2024 appear on both sides, so the "
                "calendar year is held fixed while only the net's memory changes.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
