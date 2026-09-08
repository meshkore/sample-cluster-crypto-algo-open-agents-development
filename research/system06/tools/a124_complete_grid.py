"""A124: fill the five empty cells, so the VOTE decides the setting and not the dict order.

A123 replicated: on 7 of 8 walk-forward boundaries, some hold longer than the champion's
16 bars scores better on the years that net never saw. That is the finding, it is paid
for with seven out-of-sample boundaries against the rule's two, and it stands.

The setting it named does not. 32 and 64 both won 6 of the 7 boundaries where they were
measured, their median margins over 16 are identical to three decimals, and the tool
returned 32 because `max` returns the first maximum and 32 comes first in the tuple. That
is not a result, it is an ordering. And 48 was never run on three of the boundaries at
all, so its 4-of-5 could be a coverage gap rather than a loss - which is precisely how a
study quietly picks its own winner.

The grid has five holes. Filling them costs five backtests:

    _wf22_single   48        _wf23_single   48        _wf192x3   48
    _wf23_ref      32, 64

Then every setting has been measured on all eight boundaries and the vote means what it
claims to mean.

WHAT THE SHAPE ALREADY SUGGESTS, and it is better news than a winner would be. Across the
four boundaries where all of 32, 48 and 64 were run, the best setting was 64, 32, 48 and
48 - scattered. This is a PLATEAU, not a peak: anything between 32 and 64 beats 16 nearly
everywhere, and no single value is special. A plateau is the robust case. A peak would
have meant the number was fitted.

------------------------------------------------------------------------------------
THE TIE-BREAK, REGISTERED BEFORE THE FIVE NUMBERS EXIST
------------------------------------------------------------------------------------
  1. most boundaries beaten, out of eight;
  2. if tied, the higher MEDIAN margin over 16 across the eight - median and not mean,
     because one net dominating an average is the exact failure a vote exists to avoid;
  3. if still tied, the setting CLOSEST TO 16, because the smaller change is the one the
     record supports with the least extrapolation.

The winner earns the sealed reading A123 already bought. If the completed grid drops the
replication below 6 of 8, nothing is read and min_hold closes.

THE DISSENTER stays in the count. `_wf_recency_hl2` is the one boundary where 16 wins and
every longer hold loses badly (-0.2703 at 32). It would be easy to note that this net
already failed its own exam by thirty points and set it aside; that is exactly the
post-hoc exclusion this project has been burned by, so it votes like the rest.

2026 is not read here.

Run from repo root:
    PYTHONPATH=trading-system python research/system06/tools/a124_complete_grid.py
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

ALL_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
CHAMPION_MIN_HOLD = 16
LONGS = (32, 48, 64)
MIN_REPLICATIONS = 6

# net -> (cutoff, unseen score at 16, {hold: unseen score}) from A121/A122/A123.
MEASURED: dict[str, dict] = {
    "_wf22_single":    {"cutoff": 2022, "champion": 0.0885, "long": {32: 0.1362, 64: 0.1707}},
    "_wf22_ens5":      {"cutoff": 2022, "champion": -0.1130, "long": {32: -0.0337, 48: -0.0792, 64: -0.0221}},
    "_wf23_single":    {"cutoff": 2023, "champion": 0.1064, "long": {32: 0.2077, 64: 0.1963}},
    "_wf23_ref":       {"cutoff": 2023, "champion": -0.1417, "long": {48: 0.0059}},
    "_wf23_ens5":      {"cutoff": 2023, "champion": 0.1395, "long": {32: 0.2271, 48: 0.2088, 64: 0.2184}},
    "_wf192x3":        {"cutoff": 2024, "champion": -0.0429, "long": {32: -0.0333, 64: -0.0358}},
    "_wf_recency_hl2": {"cutoff": 2024, "champion": 0.0417, "long": {32: -0.2703, 48: -0.0973, 64: -0.1486}},
    "_wf_ref":         {"cutoff": 2024, "champion": 0.0398, "long": {32: 0.2013, 48: 0.2059, 64: 0.0881}},
}


def missing_cells() -> list[tuple[str, int]]:
    return [(net, h) for net, blk in MEASURED.items() for h in LONGS
            if h not in blk["long"]]


def _nopt():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def decide(grid: dict[str, dict]) -> tuple[int | None, dict]:
    """The registered tie-break: votes, then median margin, then closest to 16."""
    stats = {}
    for h in LONGS:
        margins = [blk["long"][h] - blk["champion"] for blk in grid.values()
                   if h in blk["long"]]
        stats[h] = {"n": len(margins),
                    "wins": sum(1 for m in margins if m > 0),
                    "median_margin": statistics.median(margins) if margins else None}
    best = sorted(LONGS, key=lambda h: (-stats[h]["wins"],
                                        -(stats[h]["median_margin"] or -9),
                                        abs(h - CHAMPION_MIN_HOLD)))
    return (best[0] if stats[best[0]]["wins"] else None), stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-run", action="store_true",
                    help="adjudicate on what is already in MEASURED")
    args = ap.parse_args()

    holes = missing_cells()
    print(f"A124 - {len(holes)} empty cells to fill: "
          + ", ".join(f"{n}@{h}" for n, h in holes) + "\n", flush=True)

    if not args.skip_run and holes:
        nopt = _nopt()
        first = holes[0][0]
        ev = nopt.Evaluator(
            tuple(y for y in ALL_YEARS if y <= MEASURED[first]["cutoff"]),
            tuple(y for y in ALL_YEARS if y > MEASURED[first]["cutoff"]),
            with_enter=False, net_dir=ROOT / first)
        anchor = nopt._champion_point_full(ev.risk, ev.band, list(nopt.SPACE))
        for net, hold in holes:
            cutoff = MEASURED[net]["cutoff"]
            seen = tuple(y for y in ALL_YEARS if y <= cutoff)
            unseen = tuple(y for y in ALL_YEARS if y > cutoff)
            ev.net_dir = ROOT / net
            ev.signals = str(ROOT / net / "signals.npz")
            ev.meta_path = ROOT / net / "meta.npz"
            ev.money_path = ROOT / net / "moneymodel.npz"
            ev.fit_years, ev.holdout_years = seen, unseen
            ev.years = tuple(sorted(set(seen) | set(unseen)))
            point = dict(anchor)
            point["min_hold"] = int(hold)
            t0 = time.time()
            try:
                r = ev.score(point)
            except Exception as exc:  # noqa: BLE001
                print(f"  {net}@{hold}  FAILED: {exc}", flush=True)
                continue
            MEASURED[net]["long"][hold] = r["holdout"]
            print(f"  {net:<18} min_hold {hold:>3}  UNSEEN {r['holdout']:+.4f}  "
                  f"seen {r['fit']:+.4f}  trades {r['trades']:>5}  "
                  f"({time.time() - t0:.0f}s)", flush=True)

    # ---- the complete grid ----------------------------------------------------------
    print("\n" + "=" * 92)
    print("UNSEEN-YEAR SCORE on every boundary, complete grid")
    print("=" * 92)
    print(f"{'net':<18} {'<=':>5} {'16 (champ)':>11} " +
          " ".join(f"{h:>10}" for h in LONGS) + "   best")
    replications = 0
    for net, blk in sorted(MEASURED.items(), key=lambda kv: (kv[1]["cutoff"], kv[0])):
        cells, wins = [], []
        for h in LONGS:
            v = blk["long"].get(h)
            cells.append(f"{v:>+10.4f}" if v is not None else "         -")
            if v is not None and v > blk["champion"]:
                wins.append(h)
        if wins:
            replications += 1
        best = max((h for h in LONGS if h in blk["long"]),
                   key=lambda h: blk["long"][h], default=None)
        print(f"{net:<18} {blk['cutoff']:>5} {blk['champion']:>+11.4f} " +
              " ".join(cells) + f"   {best if wins else '16'}")

    setting, stats = decide(MEASURED)
    print(f"\nboundaries where some longer hold beats 16: {replications} of "
          f"{len(MEASURED)}  (rule asks for {MIN_REPLICATIONS})")
    print(f"\n{'hold':>6} {'measured':>9} {'wins':>6} {'median margin over 16':>23}")
    for h in LONGS:
        s = stats[h]
        margin = f"{s['median_margin']:+.4f}" if s["median_margin"] is not None else "-"
        print(f"{h:>6} {s['n']:>9} {s['wins']:>6} {margin:>23}")
    replicates = replications >= MIN_REPLICATIONS
    print(f"\nREPLICATES: {replicates}")
    print(f"THE SETTING: {setting}")
    if replicates and setting:
        print(f"\n-> min_hold {setting} takes the sealed reading, decided by "
              f"{stats[setting]['wins']}/{stats[setting]['n']} boundaries and a median "
              f"margin of {stats[setting]['median_margin']:+.4f}.")
    else:
        print("\n-> min_hold closes; the champion keeps its 16 bars.")

    out = ROOT / "rnd" / f"a124_complete_grid_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A124", "at": datetime.now(timezone.utc).isoformat(),
        "sealed_read": False, "champion_min_hold": CHAMPION_MIN_HOLD,
        "grid": MEASURED, "stats": stats, "replications": replications,
        "replicates": replicates, "setting": setting,
        "tie_break": "votes, then median margin, then closest to 16 - registered before "
                     "the five filled cells existed",
        "note": "_wf_recency_hl2 is the single dissenter and votes like the rest; "
                "excluding it after seeing it is the post-hoc move this project has "
                "been burned by.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
