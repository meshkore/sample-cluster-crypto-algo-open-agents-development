"""Build the four labelled strategy variants — same champion model, different decision stack.

Run from REPO ROOT with PYTHONPATH=trading-system (else universe.load() -> BTCUSDT only).
Each variant is backtested per calendar year 2018-2025 (validation) plus the SEALED 2026
year (observation only, never selected on), with equity curves, and written to
research/system06/variants.json for the dashboard's "Strategy variants" rail group.

Model is fixed (research/system06/signals.npz, the champion's signals + baked trend gate);
only the risk/decision layer changes, so the comparison isolates the decision stack.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from system006_oracle_net_15m import autoloop as A
from system006_oracle_net_15m import launch, universe
from system006_oracle_net_15m.dataset import Dataset
from quantlab_catalog.paths import DATA_ROOT

ROOT = Path(__file__).resolve().parents[3]
S6 = ROOT / "research" / "system06"
SIG = str(S6 / "signals.npz")
OUT = S6 / "variants.json"

BAND = {"enter": 0.85, "exit_": 0.25, "min_hold": 192}
BASE = {"max_positions": 2, "position_fraction": 0.15, "stop_loss": 0.08, "trail_stop": 0.12}

# All four share the champion's exposure engine (regime deployment + stops) so the
# comparison ISOLATES the marginal effect of each added decision layer, not the
# exposure. V1 is therefore the real, strong champion-grade baseline.
VARIANTS = [
    {"id": "var-1", "name": "Trained model only",
     "note": "The oracle-clone as the champion deploys it: regime-scaled exposure and stops, no decision-support or money modules. The strong baseline everything else is measured against.",
     "risk": {"regime_deploy": 0.35}},
    {"id": "var-2", "name": "+ Decision-support modules",
     "note": "A decision tree over the model: a market-breadth risk-off (to cash in a broad bear) and a probabilistic meta-label that vetoes entries with low expected net after costs.",
     "risk": {"regime_deploy": 0.35, "breadth_gate": 0.30, "meta_margin": 0.0}},
    {"id": "var-3", "name": "+ Exquisite money management",
     "note": "The modules plus fractional-Kelly sizing by the meta edge, volatility-targeted sizing, and anti-martingale deployment (press winners, retreat in losses).",
     "risk": {"regime_deploy": 0.35, "breadth_gate": 0.30, "meta_margin": 0.0,
              "money_kelly": 0.5, "vol_scale": 1.5, "money_pyramid": 0.4}},
    {"id": "var-4", "name": "+ Occasional martingale",
     "note": "Same stack, but the defensive anti-martingale is swapped for the bounded OCCASIONAL martingale: press a shallow dip, stand down on a deep drawdown.",
     "risk": {"regime_deploy": 0.35, "breadth_gate": 0.30, "meta_margin": 0.0,
              "money_kelly": 0.5, "vol_scale": 1.5, "martingale": 0.5}},
]


def main() -> int:
    symbols = universe.load()
    assert len(symbols) >= 10, f"universe fell back to {symbols}; run from repo root"
    config = json.loads((S6 / "best.json").read_text()).get("config", {})
    dataset = Dataset(str(DATA_ROOT), symbols=symbols)
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for s in rbars.values() for b in s})
    cbars = dataset.combined()
    cstamps = sorted({b.timestamp for s in cbars.values() for b in s})
    ts = datetime.now(timezone.utc).isoformat()
    out = []
    for v in VARIANTS:
        t0 = time.time()
        bk = {**BAND, **BASE, **v["risk"]}
        py = launch.per_year(rbars, rstamps, A.RESEARCH_YEARS, SIG, brain_kwargs=bk, keep_equity=True)
        # sealed 2026 — observation only, never scored. year_window has no keep_equity
        # kwarg (run_window returns the equity curve by default), so call it plainly.
        try:
            r26 = launch.year_window(cbars, cstamps, 2026, SIG, brain_kwargs=bk)
        except Exception as exc:
            print(f"  2026 sealed failed for {v['id']}: {type(exc).__name__} {exc}", flush=True)
            r26 = None
        cons = A._consistency(py)
        annual = {str(y): round(float(py[y]["return_pct"]), 4)
                  for y in sorted(py) if py[y].get("return_pct") is not None}
        detail = {str(y): {k: py[y].get(k) for k in ("return_pct", "max_drawdown", "trades",
                  "average_exposure", "status")} for y in sorted(py) if py[y].get("return_pct") is not None}
        curves = {str(y): py[y].get("equity", []) for y in sorted(py) if py[y].get("equity")}
        if r26 is not None and r26.get("return_pct") is not None:
            annual["2026"] = round(float(r26["return_pct"]), 4)
            detail["2026"] = {k: r26.get(k) for k in ("return_pct", "max_drawdown", "trades",
                              "average_exposure", "status")}
            if r26.get("equity"):
                curves["2026"] = r26["equity"]
        risk = {**{k: bk.get(k) for k in ("max_positions", "position_fraction", "stop_loss", "trail_stop")},
                **{k: val for k, val in v["risk"].items()}}
        out.append({
            "id": v["id"], "kind": "variant", "name": v["name"], "note": v["note"],
            "hypothesis": v["name"], "at": ts, "config": config, "band": BAND, "risk": risk,
            "annual": annual, "annual_detail": detail, "curves": curves,
            "score": round(cons["score"], 4), "min_year": cons["min_year"], "cagr": cons["cagr"],
            "all_positive": cons["all_positive"],
        })
        g = " ".join(f"{y}:{py[y]['return_pct']:+.0%}" for y in sorted(py) if py[y].get("return_pct") is not None)
        s26 = annual.get("2026")
        print(f"{v['name']:32s} score {cons['score']:+.4f} worst {float(cons['min_year'] or 0):+.1%} "
              f"cagr {float(cons['cagr'] or 0):+.1%} 2026(sealed) {s26 if s26 is None else f'{s26:+.1%}'} "
              f"[{g}] {time.time()-t0:.0f}s", flush=True)
    OUT.write_text(json.dumps(out, default=str))
    print(f"wrote {OUT} ({len(out)} variants)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
