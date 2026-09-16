"""Re-score the SHIPPED champion from its own artefacts, and say whether it reproduces.

    PYTHONPATH=trading-system;trading-system/systems python research/system06/tools/verify_champion.py

The first thing to establish after any change to the laboratory is not a new idea: it
is that the instrument still returns the number it returned yesterday. This reads
`best.json` for the genome, `signals.npz` for the net's probabilities, and replays every
research year plus the sealed 2026 readout through `launch.per_year` -- the same call the
loop scores with -- then diffs the result against the record.

Nothing here trains, samples or selects. It cannot promote anything. If it disagrees with
`best.json` by more than a rounding error, the disagreement IS the finding.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path("research/system06")
TOL = 0.005          # half a percentage point on a per-year return


def main() -> int:
    from system006_oracle_net_15m import autoloop, launch, universe
    from system006_oracle_net_15m.dataset import Dataset
    from quantlab_catalog.paths import DATA_ROOT

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    band, risk = dict(best["band"]), dict(best["risk"])
    band["meta_signals"] = str(ROOT / "meta.npz")
    kwargs = {**band, **risk, "size_signals": str(ROOT / "moneymodel.npz")}

    symbols = universe.load()
    if not isinstance(symbols, list) or len(symbols) < 5:
        raise SystemExit(f"degenerate universe: {symbols!r} -- run from the repository root")
    print(f"universe: {len(symbols)} symbols  {', '.join(symbols[:6])} ...", flush=True)

    dataset = Dataset(data_root=str(DATA_ROOT), symbols=symbols, interval="15m")
    signals = str(ROOT / "signals.npz")

    started = time.time()
    print("replaying the research years ...", flush=True)
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})
    print(f"  {len(rstamps):,} research bars, {time.time()-started:.0f}s to load", flush=True)

    per_year = launch.per_year(rbars, rstamps, autoloop.RESEARCH_YEARS, signals,
                               brain_kwargs=kwargs)
    cons = autoloop._consistency(per_year)

    recorded = {int(k): float(v) for k, v in (best.get("annual_returns") or {}).items()}
    print("\n year        recorded      measured        diff")
    worst = 0.0
    for year in sorted(per_year):
        got = (per_year[year] or {}).get("return_pct")
        if got is None:
            print(f" {year}   {'-':>12}  {'no result':>12}")
            continue
        want = recorded.get(int(year))
        if want is None:
            print(f" {year}   {'-':>12}  {got:+12.4f}")
            continue
        diff = got - want
        worst = max(worst, abs(diff))
        flag = "" if abs(diff) <= TOL else "   <-- DISAGREES"
        print(f" {year}   {want:+12.4f}  {got:+12.4f}  {diff:+10.4f}{flag}")

    print(f"\n score   recorded {best['score']:+.4f}   measured {cons['score']:+.4f}"
          f"   diff {cons['score']-best['score']:+.4f}")
    print(f" worst year {cons['min_year']:+.4f}   cagr {cons['cagr']:+.4f}"
          f"   all_positive {cons['all_positive']}")

    print("\nreading the sealed year (a READOUT: it selects nothing) ...", flush=True)
    fwd = launch.forward(dataset, signals, brain_kwargs=kwargs)
    rec_fwd = best.get("forward_2026") or {}
    print(f" 2026 sealed   recorded {rec_fwd.get('return_pct'):+.4f}"
          f"   measured {fwd.get('return_pct'):+.4f}"
          f"   dd {fwd.get('max_drawdown'):.4f}   trades {fwd.get('trades')}")

    out = ROOT / "rnd" / "verify_champion.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "recorded": {"score": best["score"], "annual": recorded, "forward_2026": rec_fwd},
        "measured": {"score": cons["score"], "annual": {int(y): (per_year[y] or {}).get("return_pct")
                                                        for y in sorted(per_year)},
                     "forward_2026": fwd},
        "worst_abs_year_diff": worst,
        "reproduces": worst <= TOL,
    }, indent=1, default=str), encoding="utf-8")
    print(f"\n{'REPRODUCES' if worst <= TOL else 'DOES NOT REPRODUCE'} "
          f"(worst per-year difference {worst:.4f}, tolerance {TOL})")
    print(f"written: {out}   elapsed {time.time()-started:.0f}s")
    return 0 if worst <= TOL else 1


if __name__ == "__main__":
    sys.exit(main())
