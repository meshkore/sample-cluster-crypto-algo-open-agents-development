"""The single sealed readout for the A83 threshold set.

    PYTHONPATH=trading-system python research/system06/tools/a83_sealed.py

Order matters and it is structural, not a matter of good intentions. Everything that
decides anything is already on disk before this runs:

  rnd/numerical_optimization_*.json   the study
  rnd/a83_pick.json                   the selection rule and the point it returned,
                                      chosen on FIT score and drawdown alone
  rnd/crossnet_*.json                 the same thresholds against nets they were never
                                      tuned on

So 2026 cannot influence the choice - the choice is made. This opens the window once,
prints what it says, and writes it down whether it flatters the candidate or not.

The incumbent's own 2026 figure is printed beside it from best.json, because a forward
number with nothing to compare it to is not a readout, it is a decoration.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"


def main() -> int:
    from system006_oracle_net_15m import autoloop, launch, universe
    from system006_oracle_net_15m.dataset import Dataset

    pick = json.loads((ROOT / "rnd" / "a83_pick.json").read_text(encoding="utf-8"))
    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    band, risk = dict(best["band"]), dict(best["risk"])
    point = dict(pick["pick"]["params"])

    kw = {
        "enter": float(band["enter"]),
        "exit_": float(point["exit_"]), "min_hold": int(point["min_hold"]),
        "max_drawdown": float(risk.get("max_drawdown") or 0.0),
        "min_notional": float(risk.get("min_notional") or 0.0),
        "max_participation": float(risk.get("max_participation") or 0.0),
    }
    for k in ("max_positions", "position_fraction", "stop_loss", "trail_stop",
              "breadth_gate", "regime_deploy", "meta_margin", "money_model", "fng_min"):
        kw[k] = point[k]
    kw["max_positions"] = int(kw["max_positions"])
    if band.get("meta_signals"):
        kw["meta_signals"] = band["meta_signals"]
    if kw["money_model"] > 0 and (ROOT / "moneymodel.npz").exists():
        kw["size_signals"] = str(ROOT / "moneymodel.npz")

    symbols = universe.load()
    if not isinstance(symbols, list) or len(symbols) < 5:
        raise SystemExit(f"degenerate universe: {symbols!r}")
    sig = str(ROOT / "signals.npz")
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")

    # The full research record first, so the candidate's own numbers are on the page
    # above the forward one rather than below it.
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for s in rbars.values() for b in s})
    py = launch.per_year(rbars, rstamps, autoloop.RESEARCH_YEARS, sig, brain_kwargs=kw)
    rows = {int(y): py[y] for y in py if py.get(y)}
    cons = autoloop._consistency(rows)
    print(f"A83 pick (study trial {pick['pick']['trial']}) - RESEARCH YEARS")
    for y in sorted(rows):
        r = rows[y]
        print(f"  {y}  {r['return_pct']:+9.2%}   maxDD {r.get('max_drawdown', 0):5.1%}   "
              f"trades {r.get('trades')}")
    print(f"\nscore {cons['score']:+.4f}   worst year {cons['min_year']:+.2%}   "
          f"CAGR {cons['cagr']:+.2%}   all years positive: {cons['all_positive']}")
    print(f"incumbent on record: score {best.get('consistency', {}).get('score'):+.4f}   "
          f"worst year {best.get('consistency', {}).get('min_year'):+.2%}   "
          f"all positive: {best.get('consistency', {}).get('all_positive')}")

    fwd = launch.forward(dataset, sig, brain_kwargs=kw)
    inc = best.get("forward_2026") or {}
    print("\n" + "=" * 78)
    print("SEALED 2026 - the only year never trained or selected on")
    print("=" * 78)
    print(f"  candidate  {fwd['return_pct']:+.2%}   maxDD {fwd['max_drawdown']:.2%}   "
          f"trades {fwd['trades']}   exposure {(fwd.get('average_exposure') or 0):.2%}")
    print(f"  incumbent  {inc.get('return_pct', float('nan')):+.2%}   "
          f"maxDD {inc.get('max_drawdown', float('nan')):.2%}   "
          f"trades {inc.get('trades')}")
    print(f"\n  operator's mandate: +30% every calendar year. "
          f"candidate 2026 {'CLEARS' if fwd['return_pct'] >= 0.30 else 'MISSES'} it.")

    out = ROOT / "rnd" / f"a83_sealed_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(),
        "trial": pick["pick"]["trial"], "params": point,
        "research": {str(y): rows[y]["return_pct"] for y in sorted(rows)},
        "consistency": cons,
        "sealed_2026": {k: fwd.get(k) for k in ("return_pct", "max_drawdown", "trades",
                                                "average_exposure", "status", "stop_reason")},
        "incumbent_2026": inc,
        "basis": ["rnd/a83_pick.json", "rnd/crossnet_2026-09-04.json"],
    }, indent=1), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
