"""Record the impact-priced table as the shipping numbers. An honest downgrade.

Market impact is a property of the SHARED ENGINE (CostModel.impact_bps), not a brain
lever, so it re-prices every strategy at once and there is nothing to "adopt" in the
config - only the measurement to correct on the record. What changes here is what the
project claims:

  sealed 2026: +33.86% -> +25.71%   (drawdown 21.3% -> 22.1%)
  2025:        +0.20%  -> -2.96%    (green again only in the no-impact world)
  2021:        x199    -> x146

Stated without softening: with our own market impact priced in, the book NO LONGER
meets the operator's +30% forward target, and the all-years-green property is lost.
Both were true only while the cost model assumed our orders were invisible. The
previous figures stay on the record as `superseded_by_impact` rather than being
deleted - they were honestly measured under a model we now know was too kind.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
TABLE = json.loads((ROOT / "rnd" / "realism_2026-09-02.json").read_text(encoding="utf-8"))
CALIB = json.loads((ROOT / "rnd" / "impact_calibration.json").read_text(encoding="utf-8"))


def main() -> int:
    sys.path.insert(0, "trading-system")
    from quantlab_system06 import registry

    now = datetime.now(timezone.utc).isoformat()
    years = TABLE["years"]
    real = {y: v["realistic"] for y, v in years.items()}

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    best["superseded_by_impact"] = {
        "note": ("Measured before CostModel.impact_bps existed - our own order was "
                 "priced as invisible. Kept as an honest record, not a claim."),
        "annual_returns": best.get("annual_returns"),
        "forward_2026": best.get("forward_2026")}
    best["annual_returns"] = {y: real[y]["return_pct"] for y in sorted(real) if y != "2026"}
    best["annual_detail"] = {y: real[y] for y in sorted(real) if y != "2026"}
    best["forward_2026"] = {**real["2026"], "average_exposure": None,
                            "status": "complete", "stop_reason": None}
    best["cost_model"] = {
        "commission_bps": 10.0, "slippage_bps": 5.0,
        "impact_bps": CALIB["impact_bps"],
        "impact_law": "slippage_bps + impact_bps * sqrt(notional / bar traded value)",
        "calibration": ("median 15m bar range across the 14-symbol universe = "
                        f"{CALIB['median_range_bps']:.1f} bps, rounded up "
                        "(tools/calibrate_impact.py)")}
    best["adoption_impact"] = {
        "at": now,
        "what": "size-dependent market impact priced on every fill, entries and exits",
        "effect": {"sealed_2026": [0.3385828635848145, real["2026"]["return_pct"]],
                   "2025": [0.0020, real["2025"]["return_pct"]],
                   "2021": [198.1374, real["2021"]["return_pct"]]},
        "verdict": ("The +30% forward target is NOT met under impact (+25.71%), and the "
                    "all-years-green property is lost (2025 -2.96%). Both held only "
                    "while our own volume was assumed free. This is the number to "
                    "improve from, not a number to explain away.")}
    best["at"] = now
    (ROOT / "best.json").write_text(json.dumps(best, indent=1, default=str),
                                    encoding="utf-8")
    print(f"best.json: sealed 2026 = {real['2026']['return_pct']:+.2%} "
          f"@ {real['2026']['max_drawdown']:.1%} (impact priced)")

    registry.attach_backtest("ARCH-0005", {
        "at": now, "kind": "impact-priced-per-year",
        "source": "tools/realism_run.py with CostModel.impact_bps=60",
        "cost_model": best["cost_model"], "years": {y: real[y] for y in sorted(real)},
        "note": ("Honest downgrade: sealed 2026 +33.86% -> +25.71%, 2025 back to "
                 "-2.96%, 2021 x199 -> x146. Same architecture, same config, truer "
                 "cost model.")})
    print("ARCH-0005: impact-priced backtest attached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
