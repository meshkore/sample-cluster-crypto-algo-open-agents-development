"""P50: the deep-field net against the champion, judged the way the method now demands.

The net in _w192d6 is the champion's exact recipe - same 14 symbols, same seed 91002,
same 50 epochs, same 3% labels, same 96-bar window - with ONE change: six blocks
instead of three, so its receptive field (127 bars) finally covers the window it is
fed. The champion sees 15 of its 96 bars (A103, measured by gradient probe).

Its validation already said something the champion's never did: the raw signal is
net-PROFITABLE (+315.6% mean per symbol after the toll, against the champion's
-31.3%), on lower accuracy (63.3% vs 66.2%) - the A108 diagnosis in action: accuracy
was never the number.

This runs the book-level comparison, paired to the recipe used for the 256 attempt:
the champion's OWN band and risk layer verbatim from best.json, only the net and the
overlays derived from its signals are swapped. Then the verdict comes from the
held-out method, not from the all-years score:

    FIT     2018-2023   what we may look at freely
    HOLDOUT 2024-2025   confirmation, read once per candidate
    2026    NOT OPENED HERE. A sealed reading is a separate deliberate act that
            only a held-out win can justify.

Both halves are scored with the study's own mandate_score so the number is
comparable with the threshold search's anchor (fit +0.2805, holdout +0.1621).

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a103_paired.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
NEW = ROOT / "_w192d6"
FIT_YEARS = (2018, 2019, 2020, 2021, 2022, 2023)
HOLDOUT_YEARS = (2024, 2025)


def _mandate_score():
    spec = importlib.util.spec_from_file_location(
        "nopt", ROOT / "tools" / "numerical_optimization.py")
    nopt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nopt)
    return nopt.mandate_score, nopt.monthly_returns


def main() -> int:
    from quantlab_system06 import autoloop, infer, launch, moneymodel, universe
    from quantlab_system06 import meta as metalabel
    from quantlab_system06.dataset import Dataset

    t0 = time.time()
    mandate_score, monthly_returns = _mandate_score()
    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, band, risk = dict(best["config"]), dict(best["band"]), dict(best["risk"])
    enter, exit_, hold = float(band["enter"]), float(band["exit_"]), int(band["min_hold"])
    symbols = universe.load()

    sig = str(NEW / "signals.npz")
    if not Path(sig).exists():
        print("exporting signals for the deep-field net ...", flush=True)
        infer.export(data_root=DATA, symbols=symbols, model_dir=str(NEW), out_path=sig,
                     trend_span=int(cfg.get("trend_span", autoloop.TREND_SPAN)))

    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})

    if not (NEW / "meta.npz").exists():
        print("building the meta overlay from the new net's own signals ...", flush=True)
        cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
        verdicts, _doc = metalabel.build_verdicts(cand)
        metalabel.write_meta(verdicts, str(NEW / "meta.npz"))
    brain = {"enter": enter, "exit_": exit_, "min_hold": hold,
             "meta_signals": str(NEW / "meta.npz"), **risk}
    if float(risk.get("money_model") or 0) > 0:
        if not (NEW / "moneymodel.npz").exists():
            print("building the sizing overlay ...", flush=True)
            overlay = moneymodel.build_sizing(sig, DATA, enter=enter, exit_=exit_,
                                              min_hold=hold,
                                              stop_loss=float(risk.get("stop_loss") or 0.0),
                                              trail_stop=float(risk.get("trail_stop") or 0.0),
                                              research=rbars)
            moneymodel.write_sizing(overlay, str(NEW / "moneymodel.npz"))
        brain["size_signals"] = str(NEW / "moneymodel.npz")

    print("running the research-years book (champion band+risk, deep net) ...", flush=True)
    py = launch.per_year(rbars, rstamps, autoloop.RESEARCH_YEARS, sig,
                         brain_kwargs=brain, keep_equity=True)

    def half(years):
        rows = {y: py[y] for y in py if int(y) in years and py.get(y)}
        if not rows:
            return None
        cons = autoloop._consistency(rows)
        rets = {y: rows[y].get("return_pct") for y in rows}
        dd = max((rows[y].get("max_drawdown") or 0.0) for y in rows)
        months = [m for y in sorted(rows) for m in monthly_returns(rows[y].get("equity"))]
        return {"score": mandate_score(rets, cons, dd, months),
                "house_score": float(cons["score"]), "returns": rets,
                "worst_drawdown": dd,
                "months_won": (sum(1 for m in months if m > 0) / len(months))
                              if months else None}

    fit, hold_ = half(FIT_YEARS), half(HOLDOUT_YEARS)
    print("\nYEAR BY YEAR (deep-field net under the champion's exact book)")
    for y in sorted(py):
        r = py[y] or {}
        if r.get("return_pct") is None:
            continue
        tag = "FIT" if int(y) in FIT_YEARS else "HELD-OUT"
        print(f"  {y}  {r['return_pct']:+9.2%}   maxDD {r.get('max_drawdown', 0):5.1%}   "
              f"trades {r.get('trades'):>4}   {tag}")

    # The anchor is the same book with the champion net - trial 2 of the study,
    # measured by the same instrument on the same years.
    ANCHOR = {"fit": 0.2805, "holdout": 0.1643}
    print(f"\nmandate_score  FIT      {fit['score']:+.4f}   (champion net {ANCHOR['fit']:+.4f})")
    print(f"mandate_score  HELD-OUT {hold_['score']:+.4f}   (champion net {ANCHOR['holdout']:+.4f})")
    print(f"months won FIT {fit['months_won']:.1%} | held-out DD {hold_['worst_drawdown']:.1%}")
    wins = hold_["score"] > ANCHOR["holdout"]
    print(f"\nwins the held-out half: {wins}")
    print("sealed 2026: NOT read here." + (" A held-out win earns ONE deliberate reading."
                                           if wins else " No held-out win, no reading."))

    out = ROOT / "rnd" / f"a103_paired_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "P50", "at": datetime.now(timezone.utc).isoformat(),
        "minutes": round((time.time() - t0) / 60, 1),
        "returns": {str(y): (py[y] or {}).get("return_pct") for y in sorted(py)},
        "fit": fit, "holdout": hold_, "anchor": ANCHOR,
        "wins_holdout": bool(wins),
        "band_and_risk": "champion's verbatim (best.json); only the net and its overlays swapped",
        "note": "sealed 2026 deliberately not read in this run",
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}   ({(time.time() - t0) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
