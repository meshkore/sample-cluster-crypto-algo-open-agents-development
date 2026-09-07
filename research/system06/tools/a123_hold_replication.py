"""A123: does a LONGER minimum hold beat the champion's on every boundary we own?

A122 refuted my own explanation and left a better one standing.

WHAT WAS REFUTED. I said min_hold was leverage on the net's MEMORY - that removing it
paid on years the net trained on and cost on years it did not. A122 put the same calendar
year on both sides of three training cutoffs and the gap vanished: 2024 pays 0.86x when
the net had seen it and 0.81x when it had not; 2023 pays 1.09x seen and 0.91x unseen.
Both inside the noise I had pre-registered as the threshold. The step A121 measured was
the YEAR COMPOSITION of its two blocks, not the net's memory - "unseen" and "recent" had
been the same thing in every measurement until three cutoffs pulled them apart.

WHAT STANDS. The payoff for trading fast is a property of the CALENDAR, and it collapsed:

    2018 2.97x   2019 1.94x   2020 1.58x   2021 4.17x
    2022 1.12x   2023 1.00x   2024 0.82x   2025 1.08x   2026 0.70x  (sealed)

Fast rotation was enormously profitable through 2021 and has paid nothing since. The
champion's 16-bar hold was chosen against a record that is four-fifths pre-2022, and
every study since has re-confirmed it on the same record.

AND THE CONSEQUENCE REPLICATED, three for three, on the only years those nets never saw:

    _wf22_single (<=2022)   champion 16: +0.0885   best long: 64 at +0.1707
    _wf23_single (<=2023)   champion 16: +0.1064   best long: 32 at +0.2077
    _wf192x3     (<=2024)   champion 16: -0.0429   best long: 128 at +0.0066

A fourth agrees: A121's `_wf23_ref` scored +0.0059 at 48 bars against -0.1417 at 16. And
the sealed year - the one year no net has ever seen and the only real out-of-sample
reading this project owns - agrees too: at 1 bar it returned 0.70x the champion.

So four walk-forward boundaries and the sealed year all say the same thing, and the
champion's own in-sample record says the opposite. That is the correct shape for a
finding: the record disagrees precisely where the record is untrustworthy.

------------------------------------------------------------------------------------
WHAT THIS FILE ADDS, AND THE RULE, BOTH BEFORE THE NUMBERS
------------------------------------------------------------------------------------
Four more independent boundaries, chosen to be as UNLIKE each other as this project can
supply - two ensembles, a recency-weighted net and a reference-feature net, across three
different cutoffs. Every one of them lost its own exam, which is exactly why they belong
here: if a threshold behaves the same way on nets that are good and nets that are bad,
the behaviour is a property of the market and not of any net.

  REPLICATES   a longer hold (32, 48 or 64) beats the champion's 16 on the unseen years
               of at least 6 of the 7 boundaries now measured.
  THE SETTING  whichever of 32 / 48 / 64 wins on the most boundaries. Not the best
               average - an average over seven differently-scaled nets is a number with
               no units. A vote is honest; a mean is not.

If it replicates, that setting earns ONE sealed reading, and this project will have paid
for it with seven out-of-sample boundaries rather than the two its rule demands. If it
does not, min_hold is closed and the champion keeps its 16 bars.

2026 is not read here.

Run from repo root:
    PYTHONPATH=trading-system python research/system06/tools/a123_hold_replication.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")

# net dir -> last year its weights ever saw. Deliberately heterogeneous.
NETS: dict[str, int] = {
    "_wf22_ens5": 2022,          # 5-seed ensemble, lost A113
    "_wf23_ens5": 2023,          # 5-seed ensemble, lost A112
    "_wf_recency_hl2": 2024,     # recency half-life 2y, lost A110b
    "_wf_ref": 2024,             # +8 reference-market columns, lost A96b
}
ALL_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
CHAMPION_MIN_HOLD = 16
HOLDS = (16, 32, 48, 64)
LONGS = (32, 48, 64)

# Everything already measured, so the vote is counted over all of it in one place.
# From rnd/a122_boundary_*.json and rnd/a121_amplification_*.json.
PRIOR: dict[str, dict] = {
    "_wf22_single": {"cutoff": 2022, "champion": 0.0885,
                     "long": {32: 0.1362, 64: 0.1707, 128: 0.0429}},
    "_wf23_single": {"cutoff": 2023, "champion": 0.1064,
                     "long": {32: 0.2077, 64: 0.1963, 128: 0.1248}},
    "_wf192x3": {"cutoff": 2024, "champion": -0.0429,
                 "long": {32: -0.0333, 64: -0.0358, 128: 0.0066}},
    "_wf23_ref": {"cutoff": 2023, "champion": -0.1417,
                  "long": {24: -0.0097, 48: 0.0059}},
}
MIN_REPLICATIONS = 6
# A setting can only be voted on where it was actually run. 48 bars exists on `_wf23_ref`
# and the four new nets but never on the three A122 boundaries, so a threshold of 6 would
# disqualify it for a gap in coverage rather than for losing - which is how a study
# quietly picks its own winner.
MIN_MEASURED = 5


def _nopt():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nets", nargs="*")
    args = ap.parse_args()

    nets = {n: c for n, c in NETS.items() if not args.nets or n in args.nets}
    for name in nets:
        if not (ROOT / name / "signals.npz").exists():
            sys.exit(f"{name}/signals.npz missing")

    nopt = _nopt()
    first = next(iter(nets))
    ev = nopt.Evaluator(tuple(y for y in ALL_YEARS if y <= nets[first]),
                        tuple(y for y in ALL_YEARS if y > nets[first]),
                        with_enter=False, net_dir=ROOT / first)
    anchor = nopt._champion_point_full(ev.risk, ev.band, list(nopt.SPACE))

    print(f"A123 - {len(HOLDS)} holds x {len(nets)} NEW boundaries "
          f"(+{len(PRIOR)} already measured), 2026 NOT read\n", flush=True)

    fresh: dict[str, dict] = {}
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
            point = dict(anchor)
            point["min_hold"] = int(hold)
            t0 = time.time()
            try:
                r = ev.score(point)
            except Exception as exc:  # noqa: BLE001
                print(f"  min_hold {hold:>4}  FAILED: {exc}", flush=True)
                continue
            rows[hold] = r
            print(f"  min_hold {hold:>4}  seen {r['fit']:+.4f}  "
                  f"UNSEEN {r['holdout']:+.4f}  trades {r['trades']:>5}  "
                  f"({time.time() - t0:.0f}s)", flush=True)
        fresh[net] = {"cutoff": cutoff, "unseen": list(unseen), "rows": rows}

    # ---- the vote, over everything measured -----------------------------------------
    table: dict[str, dict] = {}
    for net, blk in PRIOR.items():
        table[net] = {"cutoff": blk["cutoff"], "champion": blk["champion"],
                      "long": dict(blk["long"]), "source": "A121/A122"}
    for net, blk in fresh.items():
        if CHAMPION_MIN_HOLD not in blk["rows"]:
            continue
        table[net] = {
            "cutoff": blk["cutoff"],
            "champion": blk["rows"][CHAMPION_MIN_HOLD]["holdout"],
            "long": {h: blk["rows"][h]["holdout"] for h in LONGS if h in blk["rows"]},
            "source": "A123"}

    print("\n" + "=" * 100)
    print("UNSEEN-YEAR SCORE: the champion's 16 bars against longer holds, every "
          "boundary we own")
    print("=" * 100)
    print(f"{'net':<18} {'<=':>5} {'16 (champ)':>11} " +
          " ".join(f"{h:>10}" for h in LONGS) + "   beats 16?")
    wins_by_hold = {h: 0 for h in LONGS}
    replications = 0
    for net, row in sorted(table.items(), key=lambda kv: kv[1]["cutoff"]):
        cells = []
        any_win = False
        for h in LONGS:
            v = row["long"].get(h)
            if v is None:
                cells.append("         -")
                continue
            cells.append(f"{v:>+10.4f}")
            if v > row["champion"]:
                wins_by_hold[h] += 1
                any_win = True
        replications += 1 if any_win else 0
        print(f"{net:<18} {row['cutoff']:>5} {row['champion']:>+11.4f} " +
              " ".join(cells) + ("   YES" if any_win else "   no"))

    print(f"\nboundaries where SOME longer hold beats 16: {replications} of {len(table)}"
          f"  (rule asks for {MIN_REPLICATIONS})")
    print("votes per setting: " + "  ".join(
        f"{h}: {wins_by_hold[h]}/{sum(1 for r in table.values() if h in r['long'])}"
        for h in LONGS))
    replicates = replications >= MIN_REPLICATIONS
    eligible = {h: wins_by_hold[h] for h in LONGS
                if sum(1 for r in table.values() if h in r["long"]) >= MIN_MEASURED}
    setting = max(eligible, key=lambda h: eligible[h]) if eligible else None
    print(f"\nREPLICATES: {replicates}")
    print("THE SETTING: " + (str(setting) if setting else
                             f"none - no hold was run on {MIN_MEASURED}+ boundaries"))
    if replicates and setting:
        print(f"\n-> min_hold {setting} has earned ONE sealed reading, paid for with "
              f"{replications} out-of-sample boundaries against the rule's two.")
    else:
        print("\n-> min_hold is closed. The champion keeps its 16 bars and the record "
              "keeps the reason.")

    out = ROOT / "rnd" / f"a123_hold_replication_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A123", "at": datetime.now(timezone.utc).isoformat(),
        "sealed_read": False, "champion_min_hold": CHAMPION_MIN_HOLD,
        "holds": list(HOLDS), "longs": list(LONGS),
        "min_replications": MIN_REPLICATIONS,
        "boundaries": table, "replications": replications,
        "votes_by_hold": wins_by_hold,
        "replicates": replicates, "setting": setting,
        "fresh": {n: {str(h): {k: r[k] for k in (
            "fit", "holdout", "fit_min_year", "holdout_min_year", "trades", "returns")}
            for h, r in b["rows"].items()} for n, b in fresh.items()},
        "note": "the four new nets all LOST their own exams, on purpose: a threshold "
                "that behaves the same way on good and bad nets is describing the "
                "market, not the net.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
