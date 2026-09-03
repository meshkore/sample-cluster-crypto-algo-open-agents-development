"""Rebuild champion_curves.json for the CHAMPION THAT IS ACTUALLY SHIPPING.

    PYTHONPATH=trading-system python research/system06/tools/rebuild_curves.py

Why this exists (2026-09-03). The equity paths on the monitor are written by
`autoloop._champion_curves`, which only runs when the LOOP promotes a champion. But the
last three champions were adopted by hand - `adopt_192.py`, `adopt_realism.py`,
`adopt_impact.py` - each of which rewrote `best.json:annual_returns` and never touched
`champion_curves.json`. So the stored paths belonged to a champion several generations
old, and the card was drawing one strategy's curve above another strategy's table:

    year   stored path   best.json
    2018      +20.5%      +178.7%
    2021     +281.5%    +14553.8%
    2026       +3.5%       +25.7%

Nobody had noticed because the paths were only ever drawn as 46-pixel sparklines, where
a wrong shape looks like a right shape. Asking them to carry a full-size equity chart is
what made it visible.

This tool re-runs the shipping recipe - `best.json`'s own band + risk, the same
`signals.npz` the realism and impact runs used - and rewrites the paths so the chart and
the table describe the same strategy. It is a MEASUREMENT REPAIR, not a new result: the
per-year returns it reproduces must match `best.json`, and it prints the comparison so a
mismatch cannot pass silently. CPU only (the signals are already exported), so it does
not contend with a training run on the GPU.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
SEALED = 2026
TOLERANCE = 0.02          # 2 percentage points of drift between path end and table


def main() -> int:
    sys.path.insert(0, "trading-system")
    from quantlab_system06 import launch, universe
    from quantlab_system06.dataset import Dataset

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    kwargs = {**best["band"], **best["risk"]}
    if float(best["risk"].get("money_model") or 0) > 0:
        kwargs["size_signals"] = str(ROOT / "moneymodel.npz")
    sig = str(ROOT / "signals.npz")

    syms = universe.load()
    print(f"universe: {len(syms)} symbols", flush=True)
    ds = Dataset(data_root=DATA, symbols=syms, interval="15m")
    rbars = ds.research()
    rstamps = sorted({b.timestamp for s in rbars.values() for b in s})
    cbars = ds.combined()
    cstamps = sorted({b.timestamp for s in cbars.values() for b in s})

    table = dict(best.get("annual_returns") or {})
    fw = best.get("forward_2026") or {}
    if fw.get("return_pct") is not None:
        table[str(SEALED)] = fw["return_pct"]

    curves: dict[str, list] = {}
    checks: list[tuple[str, float | None, float | None]] = []
    for y in sorted(int(k) for k in table):
        bars, stamps = (cbars, cstamps) if y >= SEALED else (rbars, rstamps)
        try:
            r = launch.year_window(bars, stamps, y, sig, brain_kwargs=kwargs)
        except Exception as exc:  # noqa: BLE001 -- one bad year must not lose the rest
            print(f"  {y}: FAILED ({exc})", flush=True)
            checks.append((str(y), None, table.get(str(y))))
            continue
        if r is None:
            checks.append((str(y), None, table.get(str(y))))
            continue
        curves[str(y)] = r.get("equity", [])
        got, want = r.get("return_pct"), table.get(str(y))
        checks.append((str(y), got, want))
        print(f"  {y}: rebuilt {got:+.4f} (table {want:+.4f})", flush=True)

    print(f"\n{'year':6}{'rebuilt':>14}{'best.json':>14}   verdict")
    drift = []
    for y, got, want in checks:
        if got is None or want is None:
            print(f"{y:6}{'—':>14}{'—' if want is None else f'{want:+.4f}':>14}   MISSING")
            drift.append(y)
            continue
        # Compare on the MULTIPLE, so a 145x year is judged on relative error rather
        # than on 14,000 percentage points of absolute difference.
        rel = abs((1 + got) / (1 + want) - 1)
        ok = rel <= TOLERANCE
        print(f"{y:6}{got:+14.4f}{want:+14.4f}   {'ok' if ok else f'DRIFT {rel:.1%}'}")
        if not ok:
            drift.append(y)

    if drift:
        print(f"\nREFUSING to write: {len(drift)} year(s) do not reproduce {best['at']}'s "
              f"table ({', '.join(drift)}). The paths would disagree with the card again, "
              "which is the exact bug this tool exists to end. Investigate before writing.")
        return 1

    out = ROOT / "champion_curves.json"
    out.write_text(json.dumps(curves, default=str), encoding="utf-8")
    stamp = ROOT / "rnd" / f"curves_rebuilt_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    stamp.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(),
        "why": ("champion_curves.json belonged to a champion several hand-adoptions old; "
                "the monitor was drawing one strategy's path above another's table."),
        "champion_at": best.get("at"),
        "reproduced": {y: got for y, got, _ in checks if got is not None},
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {out} ({len(curves)} years) — every year reproduces the shipping table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
