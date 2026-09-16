"""A96 adoption attempt: the full cycle, with the rules fixed before the numbers exist.

Operator, 2026-09-07: "finish all the tests, and above all let us see how it works in
2026 too, and whether we meet all the requirements or get close to them every year. If
it turns out to be a winner then we replace the best result data, and from there we
decide where to continue. Close this cycle completely so no doubts are left."

This is that closure. It runs ONLY if the reference features have already won BOTH
walk-forward exams, and everything it will decide is written here first.

--------------------------------------------------------------------------------------
GATE 1 - already spent by the time this runs.
    exam 1  train <= 2024, examine 2025   reference alone must beat  -6.54%
    exam 2  train <= 2023, examine 2024   reference alone must beat +22.36%
    Two of two, or this script refuses to start. The arm that counts is REFERENCE
    ALONE, because it is the only one that isolates the new information; the
    reference+recency arm is a separate series and cannot buy this attempt.

GATE 2 - the sealed year, read ONCE, after everything else is on the record.
    ADOPT only if sealed 2026 BEATS the champion's +25.71%.
    Not "approaches", not "is respectable given the drawdown" - beats. A candidate
    that reads +20% is a candidate that lost, and it will be recorded as one. This
    project has three sealed readings that would have been adopted under a softer
    rule and every one of them was worse than what it would have replaced.

WHAT IS PRINTED EITHER WAY, because the operator asked for the requirements year by
year rather than a verdict alone: every research year 2018-2025, the sealed 2026
reading, worst drawdown, months won, and the mandate scorecard - minimum +30% per
calendar year, every year positive.

ORDER IS STRUCTURAL, NOT DISCIPLINE. The research table is computed and printed, then
the mandate scorecard, and only then is the sealed window opened. Nothing after the
sealed reading can change what was chosen before it, because the choice is already on
disk by then.

If GATE 2 passes, best.json is replaced - with the previous champion preserved under a
superseded_* key, the way every prior adoption in this file has been - and the daily
reference-refresh requirement is written into the artifact, because a champion that
depends on a feed nobody refreshes is a champion that quietly goes blind.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a96_adopt.py
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
SCRATCH = ROOT / "_a96_champion"
CHAMPION_2026 = 0.2571143689499318          # what the incumbent scored on the sealed year
EXAM1 = ROOT / "rnd" / "a96_reference_2026-09-07.json"
EXAM2 = ROOT / "rnd" / "a96b_reference_exam2_2026-09-07.json"


def _gate1() -> dict:
    """Both exams, reference-ALONE arm, or we do not run."""
    if not (EXAM1.is_file() and EXAM2.is_file()):
        sys.exit("gate 1: both exam files must exist before an adoption attempt")
    e1 = json.loads(EXAM1.read_text(encoding="utf-8"))
    e2 = json.loads(EXAM2.read_text(encoding="utf-8"))
    a1 = e1["arms"]["wf_ref"]["return"]
    a2 = e2["arms"]["wf23_ref"]["return"]
    c1, c2 = e1["control"]["return"], e2["control"]["return"]
    print(f"GATE 1  exam 1 (2025): reference {a1:+.2%} vs control {c1:+.2%}  "
          f"-> {'WIN' if a1 > c1 else 'LOSS'}")
    print(f"GATE 1  exam 2 (2024): reference {a2:+.2%} vs control {c2:+.2%}  "
          f"-> {'WIN' if a2 > c2 else 'LOSS'}", flush=True)
    if not (a1 > c1 and a2 > c2):
        sys.exit("gate 1 NOT cleared (needs 2 of 2 on the reference-alone arm) - "
                 "no adoption attempt, no sealed reading")
    return {"exam1": {"arm": a1, "control": c1}, "exam2": {"arm": a2, "control": c2}}


def main() -> int:
    from system006_oracle_net_15m import autoloop, infer, launch, moneymodel, train, universe
    from system006_oracle_net_15m import meta as metalabel
    from system006_oracle_net_15m.dataset import Dataset

    t0 = time.time()
    gate1 = _gate1()

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, band, risk = dict(best["config"]), dict(best["band"]), dict(best["risk"])
    enter, exit_, hold = float(band["enter"]), float(band["exit_"]), int(band["min_hold"])
    symbols = universe.load()
    SCRATCH.mkdir(parents=True, exist_ok=True)

    # Trained on EVERYTHING through 2025 - no train_until. The walk-forward split was
    # the instrument that judged the recipe; the shipped model uses the whole record,
    # which is also the operator's "maximum recent data" instinct, honoured where it
    # belongs: at adoption, never at selection.
    if not (SCRATCH / "oracle_net.pt").exists():
        print("\ntraining the candidate on ALL research years through 2025 ...", flush=True)
        train.train(data_root=DATA, symbols=symbols, threshold=cfg["threshold"],
                    window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"],
                    dropout=cfg["dropout"], out_dir=str(SCRATCH), seed=91002,
                    uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                    enter=enter, exit_=exit_, min_hold=hold,
                    channels=tuple(cfg.get("channels") or (192, 192, 192)),
                    reference_features=True)
        print(f"trained in {(time.time() - t0) / 60:.1f} min", flush=True)

    sig = str(SCRATCH / "signals.npz")
    if not Path(sig).exists():
        infer.export(data_root=DATA, symbols=symbols, model_dir=str(SCRATCH), out_path=sig,
                     trend_span=int(cfg.get("trend_span", autoloop.TREND_SPAN)))
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})
    if not (SCRATCH / "meta.npz").exists():
        cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
        verdicts, _doc = metalabel.build_verdicts(cand)
        metalabel.write_meta(verdicts, str(SCRATCH / "meta.npz"))
    brain = {"enter": enter, "exit_": exit_, "min_hold": hold,
             "meta_signals": str(SCRATCH / "meta.npz"), **risk}
    if float(risk.get("money_model") or 0) > 0:
        if not (SCRATCH / "moneymodel.npz").exists():
            overlay = moneymodel.build_sizing(
                sig, DATA, enter=enter, exit_=exit_, min_hold=hold,
                stop_loss=float(risk.get("stop_loss") or 0.0),
                trail_stop=float(risk.get("trail_stop") or 0.0), research=rbars)
            moneymodel.write_sizing(overlay, str(SCRATCH / "moneymodel.npz"))
        brain["size_signals"] = str(SCRATCH / "moneymodel.npz")

    # ---- the research table, printed BEFORE the sealed window is touched -----------
    py = launch.per_year(rbars, rstamps, autoloop.RESEARCH_YEARS, sig, brain_kwargs=brain)
    cons = autoloop._consistency(py)
    rets = {int(y): (py[y] or {}).get("return_pct") for y in py
            if (py[y] or {}).get("return_pct") is not None}
    champ = best.get("annual_returns") or {}

    print("\n" + "=" * 74)
    print("RESEARCH YEARS 2018-2025  (training and selection live in here)")
    print("=" * 74)
    for y in sorted(rets):
        c = champ.get(str(y))
        ctxt = f"   champion {c:+9.2%}" if isinstance(c, (int, float)) else ""
        print(f"  {y}  {rets[y]:+10.2%}   maxDD {(py[y] or {}).get('max_drawdown', 0):5.1%}   "
              f"trades {(py[y] or {}).get('trades'):>4}{ctxt}")
    worst_dd = max(((py[y] or {}).get("max_drawdown") or 0.0) for y in py)
    print(f"\n  worst year {cons['min_year']:+.2%}   CAGR {cons['cagr']:+.2%}   "
          f"worst drawdown {worst_dd:.1%}   all years positive: {cons['all_positive']}")

    # ---- the mandate scorecard, also before the seal -------------------------------
    over30 = sum(1 for v in rets.values() if v >= 0.30)
    positive = sum(1 for v in rets.values() if v > 0)
    print("\nMANDATE (research years)")
    print(f"  years at or above +30%: {over30}/{len(rets)}")
    print(f"  years positive:         {positive}/{len(rets)}")

    # ---- GATE 2: the sealed window, opened once ------------------------------------
    print("\n" + "=" * 74)
    print("SEALED 2026 - opened once, whatever it says")
    print("=" * 74, flush=True)
    fwd = launch.forward(dataset, sig, brain_kwargs=brain)
    got = float(fwd["return_pct"])
    print(f"  candidate  {got:+.2%}   maxDD {fwd['max_drawdown']:.2%}   "
          f"trades {fwd['trades']}   exposure {(fwd.get('average_exposure') or 0):.2%}")
    print(f"  champion   {CHAMPION_2026:+.2%}   maxDD 22.13%   90 trades")
    adopt = got > CHAMPION_2026
    print(f"\n  GATE 2 (must BEAT the champion on the sealed year): "
          f"{'PASS - adopting' if adopt else 'FAIL - not adopted'}")

    row = {
        "id": "A96-adoption", "at": datetime.now(timezone.utc).isoformat(),
        "candidate": "192x3 + 8 reference-market columns (VIX, NASDAQ, dollar, oil, 10y, curve), "
                     "trained on all research years through 2025, champion band+risk",
        "earned_by": f"gate 1, two walk-forward exams: {gate1}",
        "research": {str(y): rets[y] for y in sorted(rets)},
        "worst_drawdown": worst_dd, "consistency": cons,
        "mandate": {"years_over_30pct": over30, "years_positive": positive,
                    "of": len(rets)},
        "sealed_2026": {k: fwd.get(k) for k in
                        ("return_pct", "max_drawdown", "trades", "average_exposure",
                         "status", "stop_reason")},
        "champion_2026": CHAMPION_2026,
        "adopted": bool(adopt),
        "minutes": round((time.time() - t0) / 60, 1),
    }
    with (ROOT / "rnd" / "sealed_readouts.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    if adopt:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        shutil.copy(ROOT / "best.json", ROOT / f"best_superseded_{stamp}.json")
        new = dict(best)
        new[f"superseded_{stamp}"] = {k: best.get(k) for k in
                                      ("config", "annual_returns", "forward_2026",
                                       "consistency", "score")}
        new["config"] = {**cfg, "reference_features": True}
        new["annual_returns"] = {str(y): rets[y] for y in sorted(rets)}
        new["consistency"] = cons
        new["forward_2026"] = {k: fwd.get(k) for k in
                               ("return_pct", "max_drawdown", "trades",
                                "average_exposure", "status", "stop_reason")}
        new["at"] = datetime.now(timezone.utc).isoformat()
        new["adoption"] = {
            "id": "A96", "what": "8 reference-market columns from FRED",
            "why": "won both walk-forward exams and beat the champion on the sealed year",
            "operational_requirement": (
                "REQUIRES a daily refresh of research/system06/external/"
                "reference_markets.json. If that job dies the features freeze and the "
                "book trades on a stale picture of the world. reference.staleness_days() "
                "is the alarm."),
        }
        (ROOT / "best.json").write_text(json.dumps(new, indent=1), encoding="utf-8")
        print(f"\nbest.json REPLACED; previous champion kept at best_superseded_{stamp}.json")
    else:
        print("\nbest.json untouched. The candidate is recorded in sealed_readouts.jsonl "
              "with the number that refused it.")
    print(f"\ntotal {(time.time() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
