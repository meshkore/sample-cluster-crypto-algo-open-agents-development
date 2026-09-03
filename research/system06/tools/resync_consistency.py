"""Recompute best.json's `consistency` from the table it actually ships.

    PYTHONPATH=trading-system python research/system06/tools/resync_consistency.py

Third instance of the same bug (2026-09-03). `adopt_impact.py` rewrote
`annual_returns`, `annual_detail` and `forward_2026` when market impact re-priced every
fill - and left `consistency` untouched. So the champion card has been showing:

    "positive every year"  and  "worst year +5.1%"

while its own table says 2025 = -2.96%. The badge is the single most load-bearing claim
on the page - it is the operator's consistency law - and it was reporting the pre-impact
strategy. adopt_impact's own verdict text said the opposite in plain words ("the
all-years-green property is lost (2025 -2.96%)"), so the file has been contradicting
itself in two adjacent fields.

Same family as champion_curves.json: a derived field stored beside the numbers it is
derived from, updated by the loop but not by hand-adoption. This tool re-derives it
using `autoloop._consistency`, the one definition of record, and keeps the stale block
as `superseded_consistency` rather than deleting it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")


def main() -> int:
    sys.path.insert(0, "trading-system")
    from quantlab_system06.autoloop import _consistency

    path = ROOT / "best.json"
    best = json.loads(path.read_text(encoding="utf-8"))
    old = best.get("consistency") or {}
    ann = best.get("annual_returns") or {}
    if not ann:
        print("best.json has no annual_returns", file=sys.stderr)
        return 1

    # _consistency scores the RESEARCH years only - 2026 is sealed and never enters a
    # selection metric, exactly as the loop computes it.
    detail = best.get("annual_detail") or {}
    per_year = {int(y): {"return_pct": ann[y],
                         "status": (detail.get(y) or {}).get("status")}
                for y in ann}
    new = _consistency(per_year)

    print(f"{'field':14}{'stored':>14}{'from the table':>18}")
    for k in ("score", "min_year", "cagr", "all_positive", "n"):
        o, n = old.get(k), new.get(k)
        fmt = lambda v: f"{v:+.4f}" if isinstance(v, float) else str(v)
        mark = "" if o == n else "   <-- WRONG"
        print(f"{k:14}{fmt(o):>14}{fmt(n):>18}{mark}")

    if old == new:
        print("\nalready in sync; nothing written")
        return 0

    best["superseded_consistency"] = {
        "note": ("Computed before market impact re-priced every fill (adopt_impact.py, "
                 "2026-09-02), which turned 2025 from +0.20% to -2.96%. The card kept "
                 "showing 'positive every year' and 'worst year +5.1%' from this block "
                 "while annual_returns said otherwise. Kept as the honest record of what "
                 "was true under the old cost model, not deleted."),
        "consistency": old,
    }
    best["consistency"] = new
    best["consistency_resynced_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(best, indent=1, default=str), encoding="utf-8")

    neg = sorted(y for y in ann if ann[y] < 0)
    print(f"\nwritten. all_positive = {new['all_positive']}"
          f"{'  (negative years: ' + ', '.join(neg) + ')' if neg else ''}")
    print(f"worst year = {new['min_year']:+.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
