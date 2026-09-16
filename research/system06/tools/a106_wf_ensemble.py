"""P51 reframed: does bagging five seeds of the CHAMPION architecture help, walk-forward?

A109 settled the architecture question the honest way: trained only through 2024 and
examined on 2025 alone, the deep-field 192x6 (-25.84%) lost badly to the shipping
192x3 (-6.54%). The 15-bar reach turns out to be a structural REGULARISER - the net
generalises better because it cannot memorise the long context. So there is no new
architecture to bag, and the original P51 died with that verdict.

What remains alive is A106's plain claim: train(ensemble=N) - implemented, tested,
and shipped with N=1 - averages seed-varied nets, and variance reduction is the most
reliable free gain in noisy-label learning. One lever, alone, per the operator's
one-at-a-time instruction (2026-09-05), measured by the instrument that just proved
it can predict sealed behaviour:

    arm       ensemble=5, channels 192x3, train_until=2024, seed 91002
    control   wf192x3 single seed, ALREADY MEASURED: 2025 = -6.54%, DD 21.9%, 72 trades
    exam      2025 alone, champion band+risk verbatim
    2026      not read; nothing here touches the sealed year

Run from repo root: PYTHONPATH=trading-system python research/system06/tools/a106_wf_ensemble.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
SCRATCH = ROOT / "_wf192x3e5"
CONTROL = {"return_2025": -0.0654, "max_drawdown": 0.219, "trades": 72,
           "source": "rnd/a109_walkforward_2026-09-05.json, arm wf192x3"}


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

    if not (SCRATCH / "oracle_net.pt").exists():
        print("training 5-seed ensemble, 192x3, train_until=2024 ...", flush=True)
        train.train(data_root=DATA, symbols=symbols, threshold=cfg["threshold"],
                    window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"],
                    dropout=cfg["dropout"], out_dir=str(SCRATCH), seed=91002,
                    uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                    enter=enter, exit_=exit_, min_hold=hold,
                    channels=(192, 192, 192), train_until=2024, ensemble=5)
        print(f"trained in {(time.time() - t0) / 60:.1f} min", flush=True)

    sig = str(SCRATCH / "signals.npz")
    if not Path(sig).exists():
        infer.export(data_root=DATA, symbols=symbols, model_dir=str(SCRATCH),
                     out_path=sig,
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

    py = launch.per_year(rbars, rstamps, [2025], sig, brain_kwargs=brain)
    r = (py.get(2025) or py.get("2025")) or {}
    print("\n=== WALK-FORWARD 2025: ensemble=5 vs single seed (both 192x3) ===")
    print(f"  single (control) : {CONTROL['return_2025']:+.2%}  DD {CONTROL['max_drawdown']:.1%}  "
          f"trades {CONTROL['trades']}")
    print(f"  ensemble of 5    : {r.get('return_pct', 0):+.2%}  "
          f"DD {r.get('max_drawdown', 0):.1%}  trades {r.get('trades')}")
    wins = (r.get("return_pct") or -9) > CONTROL["return_2025"]
    print(f"  ensemble wins the exam: {wins}")

    out = ROOT / "rnd" / f"a106_wf_ensemble_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "id": "A106-wf", "at": datetime.now(timezone.utc).isoformat(),
        "minutes": round((time.time() - t0) / 60, 1),
        "arm": {"return_2025": r.get("return_pct"), "max_drawdown": r.get("max_drawdown"),
                "trades": r.get("trades"), "ensemble": 5, "channels": [192, 192, 192],
                "train_until": 2024},
        "control": CONTROL, "wins": bool(wins),
        "note": "one lever alone (operator 2026-09-05); 2026 not read",
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}   ({(time.time() - t0) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
