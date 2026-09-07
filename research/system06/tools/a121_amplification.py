"""A121: is min_hold an edge, or an amplifier of a net that has memorised the year?

THE SEALED READING FAILED, and it failed in a way that explains itself.

`lean_all` - the champion with the minimum hold removed and three dead levers deleted -
was better on all six fitted years, better on both held-out years, with a monotone
response over eight settings of the lever and seven points of less drawdown. It earned
its reading under a rule written before the numbers. Then 2026 came back at -11.65%
against the control's +25.71%, re-run through the same code path to the decimal. A
thirty-seven point loss.

So the instrument is wrong, and the shape of the error is visible in the record. Here is
the lean arm's return ratio against the champion, year by year:

    2018  3.16x   2019  1.94x   2020  1.30x   2021  5.17x
    2022  1.22x   2023  1.19x   2024  1.10x   2025  1.05x   2026  0.70x

Excluding the 2021 moonshot that is monotone: the older the year, the more removing the
hold pays, until the sealed year where it costs. That is not what an edge looks like.
It is what LEVERAGE ON SIGNAL QUALITY looks like - a lever that makes the book more
reactive, so it multiplies the net's accuracy in both directions.

And the champion net trained on 2018-2025. EVERY year in which the lever paid is a year
the net had seen; the one year it never saw is the one where the lever lost. The
"held-out" half of this and every previous threshold study is held out from the
THRESHOLDS and not from the NET, which is fine for a lever that gates and useless for a
lever that amplifies.

------------------------------------------------------------------------------------
THE DISCRIMINATING TEST, and it costs no sealed reading
------------------------------------------------------------------------------------
Two explanations fit that column equally well from where we stand:

  MEMORISATION  the lever amplifies the net, and the net is accurate on years it
                trained on. Nothing about the market changed.
  DECAY         the market genuinely got harder over time, so reactivity paid in 2018
                and does not pay now. Nothing about the net is involved.

They separate cleanly on a different net. `_wf23_ref` trained only up to 2023, so for
IT, 2024 and 2025 are unseen - exactly what 2026 is for the champion. Run the same curve
on it:

  if MEMORISATION, the ratio collapses at the 2023/2024 boundary as a STEP, and
    min_hold=1 should HURT 2024 and 2025 on this net the way it hurt 2026 on the other;
  if DECAY, the ratio declines smoothly through 2024-2025 with no step, and min_hold=1
    still improves the held-out half.

Registered before running: I expect MEMORISATION, because the step in the champion's own
column falls exactly at its own training boundary (2025 -> 2026) rather than anywhere a
market regime changed.

WHY IT MATTERS BEYOND ONE LEVER. If this holds, then no threshold study in this project
- v1, v2, v3, A115, A119, A120 - has ever measured a reactivity lever honestly, because
all of them scored candidates on years their net had trained on. v4 is already built on
the right footing (net <= 2023, thresholds 2018-2023, 2024-2025 unseen by both) and this
would make that design mandatory rather than incidental.

Run from repo root:
    PYTHONPATH=trading-system python research/system06/tools/a121_amplification.py
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
NET = ROOT / "_wf23_ref"          # trained <= 2023; 2024 and 2025 are unseen BY THE NET
SEEN = (2018, 2019, 2020, 2021, 2022, 2023)
UNSEEN = (2024, 2025)

_LEAN3 = {"trail_stop": 0.0, "breadth_gate": 0.0, "fng_min": 0.0}
ARMS: dict[str, tuple[str, dict]] = {
    "baseline": ("this net under the champion's thresholds", {}),
    "min_hold_1": ("min_hold -> 1 bar", {"min_hold": 1}),
    "min_hold_2": ("min_hold -> 2 bars", {"min_hold": 2}),
    "min_hold_4": ("min_hold -> 4 bars", {"min_hold": 4}),
    "min_hold_8": ("min_hold -> 8 bars", {"min_hold": 8}),
    "min_hold_12": ("min_hold -> 12 bars", {"min_hold": 12}),
    "min_hold_24": ("min_hold -> 24 bars", {"min_hold": 24}),
    "min_hold_48": ("min_hold -> 48 bars", {"min_hold": 48}),
    "lean_all": ("the arm that lost the sealed year", {**_LEAN3, "min_hold": 1}),
}

# The champion net's own column, for the side-by-side. Measured in A120 (2018-2025) and
# in A120-sealed (2026); copied here so the comparison prints in one place.
CHAMPION_NET_RATIOS = {2018: 3.157, 2019: 1.942, 2020: 1.302, 2021: 5.166,
                       2022: 1.222, 2023: 1.190, 2024: 1.100, 2025: 1.048,
                       2026: 0.703}


def _nopt():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ratio(arm: dict, base: dict, year: str) -> float | None:
    """Growth multiple of the arm against the baseline for one year.

    Ratio of (1+r), not of r: a year that goes +8.7% -> +32.8% has multiplied the
    account by 1.22, and differencing the percentages would call that +24 points and
    make a bad year look like a good one's equal.
    """
    a, b = arm.get(year), base.get(year)
    if a is None or b is None or (1.0 + b) <= 0:
        return None
    return (1.0 + a) / (1.0 + b)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()

    if not (NET / "signals.npz").exists():
        sys.exit(f"{NET}/signals.npz missing - this study needs the A96b net")

    nopt = _nopt()
    ev = nopt.Evaluator(SEEN, UNSEEN, with_enter=False, net_dir=NET)
    anchor = nopt._champion_point_full(ev.risk, ev.band, list(nopt.SPACE))

    arms = ARMS if not args.only else \
        {n: v for n, v in ARMS.items() if n == "baseline" or n in args.only}
    print(f"A121 - {len(arms)} arms on {NET.name}\n"
          f"  this net trained <= 2023, so {UNSEEN} are unseen BY THE NET - the same\n"
          f"  relationship 2026 has to the champion. 2026 is not read here at all.\n",
          flush=True)

    results: dict[str, dict] = {}
    for name, (what, off) in arms.items():
        point = dict(anchor)
        for k, v in off.items():
            point[k] = int(v) if nopt.SPACE[k][0] == "i" else float(v)
        t0 = time.time()
        try:
            r = ev.score(point)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:<14} FAILED: {exc}", flush=True)
            continue
        results[name] = r
        print(f"  {name:<14} seen {r['fit']:+.4f}  UNSEEN {r['holdout']:+.4f}  "
              f"worst seen yr {(r['fit_min_year'] or 0):+7.2%}  "
              f"trades {r['trades']:>5}  ({time.time() - t0:.0f}s)", flush=True)

    if "baseline" not in results:
        print("\nno baseline - nothing to compare against")
        return 1
    base = results["baseline"]["returns"]

    years = [str(y) for y in (*SEEN, *UNSEEN)]
    print("\nreturn ratio against this net's own baseline (>1 = removing the hold paid):")
    print(f"{'arm':<14} " + " ".join(f"{y:>8}" for y in years) +
          f" | {'seen':>7} {'UNSEEN':>7}  step")
    summary = {}
    for name in arms:
        if name not in results or name == "baseline":
            continue
        rr = results[name]["returns"]
        cells, seen_r, unseen_r = [], [], []
        for y in years:
            v = ratio(rr, base, y)
            cells.append(f"{v:>8.2f}" if v is not None else "       -")
            if v is not None:
                (seen_r if int(y) in SEEN else unseen_r).append(v)
        ms = statistics.median(seen_r) if seen_r else None
        mu = statistics.median(unseen_r) if unseen_r else None
        step = (mu / ms) if (ms and mu) else None
        summary[name] = {"median_seen": ms, "median_unseen": mu, "step": step,
                         "per_year": {y: ratio(rr, base, y) for y in years}}
        tail = (f" | {ms:>7.2f} {mu:>7.2f}  {step:.2f}x" if (ms and mu) else "")
        print(f"{name:<14} " + " ".join(cells) + tail)

    print("\nthe champion net's own column, for comparison (A120 + the sealed reading):")
    print("  " + "  ".join(f"{y}:{v:.2f}x" for y, v in
                           sorted(CHAMPION_NET_RATIOS.items())))
    print("  that net trained through 2025; the only year it never saw is 2026, and it "
          "is the only year below 1.")

    # ---- adjudication ---------------------------------------------------------------
    mh1 = summary.get("min_hold_1")
    print("\n" + "-" * 96)
    if mh1 and mh1["step"] is not None:
        hurts_unseen = (mh1["median_unseen"] or 0) < 1.0
        holdout_worse = results["min_hold_1"]["holdout"] <= results["baseline"]["holdout"]
        if hurts_unseen and holdout_worse:
            verdict = ("MEMORISATION - the lever pays on years this net trained on and "
                       "COSTS on the two it never saw, exactly as it cost 2026 on the "
                       "champion net. min_hold is leverage on the net's accuracy, not "
                       "an edge, and no study that scores a reactivity lever on a net's "
                       "own training years can measure one.")
        elif not hurts_unseen and not holdout_worse:
            verdict = ("DECAY - the lever still pays on years this net never saw, so "
                       "the champion's 2026 loss is not explained by memorisation and "
                       "something specific to 2026 has to be. A121 does not settle it.")
        else:
            verdict = ("MIXED - the two signatures disagree with each other; report the "
                       "numbers and claim nothing.")
        print(f"median ratio: seen {mh1['median_seen']:.2f}x  unseen "
              f"{mh1['median_unseen']:.2f}x  (step {mh1['step']:.2f}x)")
        print(f"held-out score: min_hold_1 {results['min_hold_1']['holdout']:+.4f} vs "
              f"baseline {results['baseline']['holdout']:+.4f}")
        print(f"\nVERDICT: {verdict}")
    else:
        verdict = "INCOMPLETE - min_hold_1 did not produce a comparable record"
        print(verdict)

    out = ROOT / "rnd" / f"a121_amplification_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A121", "at": datetime.now(timezone.utc).isoformat(),
        "net": NET.name, "seen_by_net": list(SEEN), "unseen_by_net": list(UNSEEN),
        "sealed_read": False,
        "champion_net_ratios": CHAMPION_NET_RATIOS,
        "ratios": summary,
        "results": {n: {k: r[k] for k in (
            "fit", "holdout", "fit_min_year", "holdout_min_year", "fit_worst_drawdown",
            "trades", "returns")} for n, r in results.items()},
        "verdict": verdict,
        "note": "`fit`/`holdout` here mean SEEN-BY-THE-NET and UNSEEN-BY-THE-NET, which "
                "is the distinction A120 lacked: its held-out years were held out from "
                "the thresholds only.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
