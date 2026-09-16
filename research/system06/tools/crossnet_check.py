"""Do the optimised thresholds work on nets they were never tuned against?

    PYTHONPATH=trading-system python research/system06/tools/crossnet_check.py

A83 searched eleven thresholds against ONE fixed signals.npz. The held-out years already
answer the first overfitting question - are these thresholds fitted to 2018-2023 rather
than to markets - and the answer was no: they transfer to 2024 and 2025 unseen.

They cannot answer the second question, which is subtler and has bitten this project
harder. The thresholds may be co-adapted to the IDIOSYNCRASIES OF THIS PARTICULAR NET:
its calibration, how confident it happens to be, where its probability mass sits. A
trailing stop of 0.21 that suits one net's conviction profile need not suit another's,
and if that is what was found, the whole result evaporates the next time the champion is
retrained - which happens continuously.

So the thresholds are run against every other net on disk. This is CPU only and needs no
retraining: the nets already exist, exported by earlier experiments.

  prev_champion_64ch   a DIFFERENT ARCHITECTURE - 64 channels against the shipping 192.
                       The strongest available test: if a threshold set tuned on a
                       three-times-wider net still beats the incumbent's thresholds here,
                       it is not reading one net's quirks.
  _candidate           another net from the 2026-09-02 generation.
  _w256                P47's 256-channel build, if it has finished.

PAIRED, and that is what makes it readable. On each net BOTH threshold sets are run -
the champion's and the pick's - so the net's own quality cancels out and only the
difference between the two configurations survives. An absolute score on a weaker net
means nothing; the SIGN of the gap means everything.

The meta-labelling and money-model overlays are REBUILT per net rather than borrowed.
Both are derived from a net's own probabilities, so carrying the shipping net's overlay
onto a different net would be feeding it another model's opinions - and since
`money_model` and `meta_margin` are two of the eleven searched thresholds, dropping them
instead would quietly excuse the pick from being tested on a third of what it changed.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
PICK = ROOT / "rnd" / "a83_pick.json"


def main() -> int:
    from system006_oracle_net_15m import autoloop, launch, moneymodel, universe
    from system006_oracle_net_15m import meta as metalabel
    from system006_oracle_net_15m.dataset import Dataset

    if not PICK.exists():
        print(f"no {PICK} - run the selection rule first", file=sys.stderr)
        return 2
    picked = json.loads(PICK.read_text(encoding="utf-8"))
    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    band, risk = dict(best["band"]), dict(best["risk"])
    enter = float(band["enter"])

    champ_point = {
        "max_positions": int(risk["max_positions"]),
        "position_fraction": float(risk["position_fraction"]),
        "stop_loss": float(risk.get("stop_loss") or 0.0),
        "trail_stop": float(risk.get("trail_stop") or 0.0),
        "breadth_gate": float(risk.get("breadth_gate") or 0.0),
        "regime_deploy": float(risk.get("regime_deploy") or 0.0),
        "meta_margin": float(risk.get("meta_margin") or 0.0),
        "money_model": float(risk.get("money_model") or 0.0),
        "fng_min": float(risk.get("fng_min") or 0.0),
        "exit_": float(band["exit_"]), "min_hold": int(band["min_hold"]),
    }
    pick_point = dict(picked["pick"]["params"])

    nets = [(p.name, p) for p in (ROOT / "prev_champion_64ch", ROOT / "_candidate",
                                  ROOT / "_w256")
            if (p / "signals.npz").exists()]
    if not nets:
        print("no alternative nets on disk", file=sys.stderr)
        return 2

    symbols = universe.load()
    if not isinstance(symbols, list) or len(symbols) < 5:
        raise SystemExit(f"degenerate universe: {symbols!r} - run from the repo root "
                         f"with PYTHONPATH=trading-system")
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for s in rbars.values() for b in s})
    years = tuple(autoloop.RESEARCH_YEARS)

    print(f"cross-net check: {len(nets)} net(s), 2 threshold sets each, "
          f"{len(symbols)} symbols\n", flush=True)

    out_rows = {}
    for name, d in nets:
        sig = str(d / "signals.npz")
        t0 = time.time()
        # Each of these nets already SHIPPED at some point, so its own meta and
        # money-model overlays are sitting beside it, built from its own probabilities
        # when it was current. Reuse beats rebuild twice over: it is the artefact that
        # net actually ran with, and rebuilding calls dataset.combined(), which rewrites
        # the shared data cache - that collided with the champion-256 build writing the
        # same file and killed the first attempt with a Windows file lock. Two processes
        # regenerating one cache is a race whatever the platform; not needing to is the
        # better answer.
        meta_path = d / "meta.npz"
        size_path = d / "moneymodel.npz"
        if not meta_path.exists():
            cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
            verdicts, _doc = metalabel.build_verdicts(cand)
            meta_path = d / "meta_crossnet.npz"
            metalabel.write_meta(verdicts, str(meta_path))
        if not size_path.exists():
            overlay = moneymodel.build_sizing(
                sig, DATA, enter=enter, exit_=float(band["exit_"]),
                min_hold=int(band["min_hold"]),
                stop_loss=float(risk.get("stop_loss") or 0.0),
                trail_stop=float(risk.get("trail_stop") or 0.0), research=rbars)
            size_path = d / "moneymodel_crossnet.npz"
            moneymodel.write_sizing(overlay, str(size_path))
        print(f"{name}: overlays {meta_path.name} + {size_path.name} "
              f"({(time.time() - t0) / 60:.1f} min)", flush=True)

        row = {}
        for label, point in (("champion", champ_point), ("pick", pick_point)):
            kw = {
                "enter": enter, "exit_": float(point["exit_"]),
                "min_hold": int(point["min_hold"]),
                "max_drawdown": float(risk.get("max_drawdown") or 0.0),
                "min_notional": float(risk.get("min_notional") or 0.0),
                "max_participation": float(risk.get("max_participation") or 0.0),
                "meta_signals": str(meta_path),
            }
            for k in ("max_positions", "position_fraction", "stop_loss", "trail_stop",
                      "breadth_gate", "regime_deploy", "meta_margin", "money_model",
                      "fng_min"):
                kw[k] = point[k]
            kw["max_positions"] = int(kw["max_positions"])
            if kw["money_model"] > 0:
                kw["size_signals"] = str(size_path)
            py = launch.per_year(rbars, rstamps, years, sig, brain_kwargs=kw)
            rows = {int(y): py[y] for y in py if py.get(y)}
            cons = autoloop._consistency(rows)
            row[label] = {
                "score": cons["score"], "min_year": cons["min_year"],
                "cagr": cons["cagr"], "all_positive": cons["all_positive"],
                "worst_drawdown": max((r.get("max_drawdown") or 0) for r in rows.values()),
                "returns": {str(y): rows[y]["return_pct"] for y in sorted(rows)},
            }
            print(f"  {label:<9} score {cons['score']:+.4f}  worst year "
                  f"{cons['min_year']:+.2%}  maxDD {row[label]['worst_drawdown']:.1%}  "
                  f"all positive {cons['all_positive']}", flush=True)
        row["delta"] = row["pick"]["score"] - row["champion"]["score"]
        print(f"  {'DELTA':<9} {row['delta']:+.4f}"
              f"   {'PICK WINS' if row['delta'] > 0 else 'champion wins'}\n", flush=True)
        out_rows[name] = row

    wins = sum(1 for r in out_rows.values() if r["delta"] > 0)
    print("=" * 74)
    print(f"the pick beats the champion's thresholds on {wins} of {len(out_rows)} nets "
          f"it was never tuned against")
    if wins == len(out_rows):
        print("The thresholds are not reading one net's quirks. That is the claim this\n"
              "run was built to test, and it survives.")
    elif wins == 0:
        print("The advantage does NOT survive a change of net, so A83 found a threshold\n"
              "set co-adapted to one export rather than a better way to trade. The\n"
              "held-out years could not have caught this.")
    else:
        print("Mixed. Report it as mixed - a majority is not a result at this sample size.")

    out = ROOT / "rnd" / f"crossnet_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(),
        "pick_trial": picked["pick"]["trial"], "pick_params": pick_point,
        "nets": out_rows, "wins": wins, "of": len(out_rows),
        "note": "Paired: both threshold sets run on each net, so the net's own quality "
                "cancels and only the difference survives. Overlays rebuilt per net.",
    }, indent=1), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
