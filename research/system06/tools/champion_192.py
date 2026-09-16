"""The width-192 champion attempt: one build, one research table, ONE sealed readout.

    PYTHONPATH=trading-system python research/system06/tools/champion_192.py

Why this configuration and this seed, committed here BEFORE anything is measured:

P35 trained the champion recipe at four widths on four seeds. At 192 channels every
seed improved and the median research score was +0.4611 against a promotion bar of
+0.1001, with worst drawdown FALLING from 28.8% to 20.6%. The four scores were
77101 +0.6008, 91001 +0.4983, 91002 +0.4238, 77102 +0.3857.

The seed shipped is **91002**, the lower-middle of the four - not 77101, the best.
This project has already been burned twice by selection optimism: a headline built on
the luckiest draw does not reproduce, and the gap between the two was the single
largest source of disappointment in the ledger. Taking the seed at or below the median
means the sealed year is read on a draw that is, by construction, not the flattering
one. That rule is written here, in the file that performs the measurement, so it
cannot be revised after seeing the answer.

The order below is also structural, not a matter of discipline: the research table is
printed and compared to the bar FIRST, and the sealed 2026 window is opened once, at
the end, whatever it says. 2026 is never an input to any choice made here.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
SCRATCH = ROOT / "_w192"
SEED = 91002
CHANNELS = (192, 192, 192)
EXPECTED_RESEARCH_SCORE = 0.4238      # this seed's P35 score - the reproduction check
BAR = 0.1001                          # the promotion bar in force


def main() -> int:
    from system006_oracle_net_15m import autoloop, infer, launch, moneymodel, train, universe
    from system006_oracle_net_15m import meta as metalabel
    from system006_oracle_net_15m.dataset import Dataset

    t0 = time.time()
    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, band, risk = dict(best["config"]), dict(best["band"]), dict(best["risk"])
    enter, exit_, hold = float(band["enter"]), float(band["exit_"]), int(band["min_hold"])
    symbols = universe.load()
    SCRATCH.mkdir(parents=True, exist_ok=True)

    print(f"champion attempt: channels={CHANNELS} seed={SEED} on {len(symbols)} symbols",
          flush=True)

    def on_progress(ev):
        if ev.get("stage") == "training" and ev.get("epoch"):
            print(f"  epoch {ev['epoch']}/{ev.get('epochs')}  loss {ev.get('loss')}",
                  flush=True)

    train.train(data_root=DATA, symbols=symbols, threshold=cfg["threshold"],
                window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"],
                dropout=cfg["dropout"], out_dir=str(SCRATCH), seed=SEED,
                uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                ensemble=int(cfg.get("ensemble", 1)), embargo=int(cfg.get("embargo", 0)),
                enter=enter, exit_=exit_, min_hold=hold, channels=CHANNELS,
                on_progress=on_progress)
    print(f"trained in {(time.time() - t0) / 60:.1f} min", flush=True)

    sig = str(SCRATCH / "signals.npz")
    infer.export(data_root=DATA, symbols=symbols, model_dir=str(SCRATCH), out_path=sig,
                 trend_span=int(cfg.get("trend_span", autoloop.TREND_SPAN)))

    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})

    cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
    verdicts, _doc = metalabel.build_verdicts(cand)
    metalabel.write_meta(verdicts, str(SCRATCH / "meta.npz"))
    brain = {"enter": enter, "exit_": exit_, "min_hold": hold,
             "meta_signals": str(SCRATCH / "meta.npz"), **risk}
    if float(risk.get("money_model") or 0) > 0:
        overlay = moneymodel.build_sizing(sig, DATA, enter=enter, exit_=exit_,
                                          min_hold=hold,
                                          stop_loss=float(risk.get("stop_loss") or 0.0),
                                          trail_stop=float(risk.get("trail_stop") or 0.0),
                                          research=rbars)
        moneymodel.write_sizing(overlay, str(SCRATCH / "moneymodel.npz"))
        brain["size_signals"] = str(SCRATCH / "moneymodel.npz")

    # ---- research table: the whole basis of the decision ---------------------------
    py = launch.per_year(rbars, rstamps, autoloop.RESEARCH_YEARS, sig, brain_kwargs=brain)
    cons = autoloop._consistency(py)
    print("\nRESEARCH YEARS (train + selection live in here; limited merit by design)")
    for y in sorted(py):
        r = py[y] or {}
        if r.get("return_pct") is None:
            continue
        print(f"  {y}  {r['return_pct']:+8.2%}   maxDD {r.get('max_drawdown', 0):.1%}   "
              f"trades {r.get('trades')}")
    print(f"\nscore {cons['score']:+.4f}  (bar {BAR:+.4f}, P35 measured {EXPECTED_RESEARCH_SCORE:+.4f} "
          f"for this seed)  worst year {cons['min_year']:+.2%}  CAGR {cons['cagr']:+.2%}  "
          f"all years positive: {cons['all_positive']}")
    reproduced = abs(cons["score"] - EXPECTED_RESEARCH_SCORE) < 0.05
    print(f"reproduction of the P35 measurement: {'MATCH' if reproduced else 'MISMATCH'}")
    clears = cons["score"] > BAR

    # ---- the single sealed readout -------------------------------------------------
    # Opened once, after the decision basis above is on the record, and never used to
    # choose anything. A configuration that failed the bar is still read: hiding the
    # forward number of a rejected build is how a project learns to fool itself.
    fwd = launch.forward(dataset, sig, brain_kwargs=brain)
    print("\n" + "=" * 78)
    print(f"SEALED 2026 - the only year never trained or selected on")
    print("=" * 78)
    print(f"  return {fwd['return_pct']:+.2%}   maxDD {fwd['max_drawdown']:.2%}   "
          f"trades {fwd['trades']}   exposure {fwd['average_exposure']:.2%}")
    print(f"  incumbent on record: {best['forward_2026']['return_pct']:+.2%} "
          f"at {best['forward_2026']['max_drawdown']:.2%} drawdown, "
          f"{best['forward_2026']['trades']} trades")
    print(f"\nclears the research bar: {clears}   total {(time.time() - t0) / 60:.1f} min")

    out = ROOT / "rnd" / f"champion_192_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(), "seed": SEED,
        "channels": list(CHANNELS), "selection_rule": "lower-middle of the four P35 seeds",
        "research": {str(y): (py[y] or {}).get("return_pct") for y in sorted(py)},
        "consistency": cons, "bar": BAR, "clears_bar": clears,
        "expected_research_score": EXPECTED_RESEARCH_SCORE, "reproduced": reproduced,
        "sealed_2026": {k: fwd.get(k) for k in
                        ("return_pct", "max_drawdown", "trades", "average_exposure",
                         "status", "stop_reason")},
        "incumbent_2026": best.get("forward_2026"),
    }, indent=1), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
