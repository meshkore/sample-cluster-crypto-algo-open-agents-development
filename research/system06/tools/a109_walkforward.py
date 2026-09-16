"""A109: the honest instrument for net-level changes - walk-forward, at last.

Why this exists, written before its numbers:

  Three candidates have now beaten the champion on research measures and lost the
  sealed year: P47 (+10.25% vs +25.71%), A83 (+20.39%), and today A103, which was
  the first ever to win the held-out half (+0.2019 vs +0.1643) and then read
  SEALED 2026 at -18.04% against the champion's +25.71%.

  The autopsy is specific. The fit/holdout split is honest for the THRESHOLD
  search - thresholds do not train on bars. It is NOT honest for a NET: the deep
  net's training slice ran to ~mid-2024, so most of the "held-out" 2024 was inside
  its own training data, and its FIT-year returns (+302%..+9148% at 3-10% DD) were
  memorisation wearing a crown. The one year the net had genuinely never seen,
  2025, showed +3.72% vs -1.49% - a small true signal buried under a large false
  one. The project mandate of 2026-08-29 already named the correct instrument:
  train on years <= X, evaluate ONLY on year X+1. train(train_until=...) has
  carried that capability all along.

So: train BOTH architectures - the champion's 192x3 (sees 15 bars) and the
deep-field 192x6 (sees 127) - with train_until=2024, everything else the
champion's recipe verbatim, and judge each book on 2025 ALONE, a year neither
net, nor its overlays, nor the band, has ever touched. 2026 is not read here;
no more sealed readings for this family until a walk-forward win earns one.

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a109_walkforward.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
TRAIN_UNTIL = 2024          # net sees <= 2024; the exam is 2025 only
ARMS = {
    "wf192x3": (192, 192, 192),                      # control: the shipping reach, 15 bars
    "wf192x6": (192, 192, 192, 192, 192, 192),       # treatment: sees the window, 127 bars
}


def main() -> int:
    from system006_oracle_net_15m import autoloop, infer, launch, moneymodel, train, universe
    from system006_oracle_net_15m import meta as metalabel
    from system006_oracle_net_15m.dataset import Dataset

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, band, risk = dict(best["config"]), dict(best["band"]), dict(best["risk"])
    enter, exit_, hold = float(band["enter"]), float(band["exit_"]), int(band["min_hold"])
    symbols = universe.load()
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})

    results = {}
    for name, channels in ARMS.items():
        scratch = ROOT / f"_{name}"
        scratch.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        print(f"\n=== {name}: channels {list(channels)}, train_until={TRAIN_UNTIL} ===",
              flush=True)
        if not (scratch / "oracle_net.pt").exists():
            train.train(data_root=DATA, symbols=symbols, threshold=cfg["threshold"],
                        window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"],
                        dropout=cfg["dropout"], out_dir=str(scratch), seed=91002,
                        uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                        enter=enter, exit_=exit_, min_hold=hold, channels=channels,
                        train_until=TRAIN_UNTIL)
            print(f"{name} trained in {(time.time() - t0) / 60:.1f} min", flush=True)

        sig = str(scratch / "signals.npz")
        if not Path(sig).exists():
            infer.export(data_root=DATA, symbols=symbols, model_dir=str(scratch),
                         out_path=sig,
                         trend_span=int(cfg.get("trend_span", autoloop.TREND_SPAN)))
        if not (scratch / "meta.npz").exists():
            cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
            verdicts, _doc = metalabel.build_verdicts(cand)
            metalabel.write_meta(verdicts, str(scratch / "meta.npz"))
        brain = {"enter": enter, "exit_": exit_, "min_hold": hold,
                 "meta_signals": str(scratch / "meta.npz"), **risk}
        if float(risk.get("money_model") or 0) > 0:
            if not (scratch / "moneymodel.npz").exists():
                overlay = moneymodel.build_sizing(
                    sig, DATA, enter=enter, exit_=exit_, min_hold=hold,
                    stop_loss=float(risk.get("stop_loss") or 0.0),
                    trail_stop=float(risk.get("trail_stop") or 0.0), research=rbars)
                moneymodel.write_sizing(overlay, str(scratch / "moneymodel.npz"))
            brain["size_signals"] = str(scratch / "moneymodel.npz")

        # NOTE the overlays above are built from research bars that include 2025.
        # The NET never saw 2025; the meta/sizing overlays' fitting procedure walks
        # expanding blocks internally (meta.py's discipline), so their 2025 verdicts
        # are causal. The BAND and RISK are the champion's, chosen before today.
        py = launch.per_year(rbars, rstamps, [2025], sig, brain_kwargs=brain)
        r = (py.get(2025) or py.get("2025")) or {}
        results[name] = {"return_2025": r.get("return_pct"),
                         "max_drawdown": r.get("max_drawdown"),
                         "trades": r.get("trades"),
                         "minutes": round((time.time() - t0) / 60, 1)}
        print(f"{name}  2025: {r.get('return_pct', 0):+.2%}  "
              f"maxDD {r.get('max_drawdown', 0):.1%}  trades {r.get('trades')}", flush=True)

    print("\n=== WALK-FORWARD VERDICT (2025, never seen by either net) ===")
    for name, r in results.items():
        print(f"  {name}: {r['return_2025']:+.2%}  DD {r['max_drawdown']:.1%}  "
              f"trades {r['trades']}")
    out = ROOT / "rnd" / f"a109_walkforward_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A109", "at": datetime.now(timezone.utc).isoformat(),
        "train_until": TRAIN_UNTIL, "exam_year": 2025, "arms": results,
        "band_and_risk": "champion verbatim; only the net differs between arms",
        "context": "filed after A103's sealed -18.04%: held-out splits are not honest "
                   "for nets that trained inside them; walk-forward is the mandated "
                   "instrument (2026-08-29) and this is its first architecture A/B",
        "note": "2026 not read; sealed readings for this family now require a "
                "walk-forward win",
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
