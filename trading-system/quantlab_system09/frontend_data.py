"""PHASE 4, part one - the single payload the local dashboard reads.

Everything the page shows comes from here, and everything here comes from artefacts the
phases actually wrote. Nothing is computed twice and nothing is invented: if phase 3 has not
run, the 2026 section arrives as `null` and the page says so rather than drawing an empty
chart that looks like a flat year.

The long series are thinned to one point a week for the charts - eight years of daily points
is three thousand dots on a line that is two hundred pixels tall - but every TOTALISER is
taken from the last daily observation, never from the thinned series.
"""

from __future__ import annotations

import json
import sys

from quantlab_catalog.paths import REPO_ROOT

from . import cohorts as C
from . import pipeline
from . import segments as SEG

OUT = REPO_ROOT / "research" / "system09"
SEALED_FROM = "2026-01-01"


def _thin(days: list[str], step: int) -> list[int]:
    """Indices of every `step`-th day, always including the last one."""
    idx = list(range(0, len(days), step))
    if idx and idx[-1] != len(days) - 1:
        idx.append(len(days) - 1)
    return idx


def build(end: str = "2026-09-14") -> dict:
    ctx, traj = pipeline.reconstruct(end=end, sealed=True, quiet=True)
    days = traj.days
    keep = _thin(days, 7)

    series = {
        "days": [days[i] for i in keep],
        "market_cap": [traj.market_cap[i] for i in keep],
        "players": [traj.headcount[i] for i in keep],
        "assets_listed": [traj.listed[i] for i in keep],
        "btc": [traj.prices[i].get("BTCUSDT", 0.0) for i in keep],
        "segments": {k: {"players": [traj.segments[i][k]["players"] for i in keep],
                         "represents": [traj.segments[i][k]["represents"] for i in keep],
                         "cash": [traj.segments[i][k]["cash"] for i in keep],
                         "assets": [traj.segments[i][k]["assets"] for i in keep]}
                     for k in SEG.ORDER},
    }

    last = traj.segments[-1]
    prices = traj.prices[-1]
    snapshot = {}
    for k in SEG.ORDER:
        v = last[k]
        basis = sum(v["basis"].values())
        snapshot[k] = {
            "label": SEG.LABELS[k], "description": SEG.DESCRIPTIONS[k],
            "players": v["players"], "represents": v["represents"],
            "cash": v["cash"], "assets": v["assets"],
            "total": v["cash"] + v["assets"],
            "unrealized": v["assets"] - basis,
            "holdings": sorted(
                ({"symbol": s, "units": q, "value": q * prices.get(s, 0.0)}
                 for s, q in v["coins"].items() if q > 0),
                key=lambda r: -r["value"]),
        }

    floats: dict[str, float] = {}
    for v in last.values():
        for s, q in v["coins"].items():
            floats[s] = floats.get(s, 0.0) + q
    assets = sorted(({"symbol": s, "price": prices.get(s, 0.0), "units": q,
                      "value": q * prices.get(s, 0.0),
                      "listed": ctx.listings.get(s, "")} for s, q in floats.items()),
                    key=lambda r: -r["value"])

    payload = {
        "generated_for": {"record_start": days[0], "record_end": days[-1]},
        "totals": {
            "players": traj.headcount[-1],
            "represents": sum(v["represents"] for v in last.values()),
            "assets": traj.listed[-1],
            "market_cap": traj.market_cap[-1],
            "cash": sum(v["cash"] for v in last.values()),
            "assets_value": sum(v["assets"] for v in last.values()),
            "buckets": traj.buckets,
            "days": len(days),
            "fill": traj.overall_fill,
            "fiat_ramped_by_year": ctx.fiat_ramped_by_year,
        },
        "series": series,
        "segments": snapshot,
        "segment_order": list(SEG.ORDER),
        "assets": assets,
        "population": {"segmentation": ctx.segmentation,
                       "agent_budget": C.AGENT_BUDGET,
                       "represents": dict(C.REPRESENTS)},
        "forward_2026": _phase3(),
    }
    payload["totals"]["wealth"] = (payload["totals"]["cash"]
                                   + payload["totals"]["assets_value"])
    return payload


def _phase3() -> dict | None:
    """The sealed-window result, if phase 3 has run. `None` is an honest answer."""
    path = OUT / "phase3_report.json"
    if not path.is_file():
        return None
    r = json.loads(path.read_text(encoding="utf-8"))
    m = r.get("market_2026", [])
    return {
        "window": r["window"], "capital": r["capital"], "rules": r["rules"],
        "model": r["model"],
        "sealed_ic": r["sealed_ic"],
        "directional_accuracy": r["sealed_directional_accuracy"],
        "n_trades": r["n_trades"], "wins": r["wins"], "losses": r["losses"],
        "hit_rate": r["hit_rate"], "return_pct": r["return_pct"],
        "max_drawdown": r["max_drawdown"], "final_equity": r["final_equity"],
        "avg_win": r["avg_win"], "avg_loss": r["avg_loss"],
        "baselines": r["baselines"],
        "equity": r["equity"],
        "trades": sorted(r["trades"], key=lambda t: t["entry_day"]),
        "market": [{"day": d["day"], "btc": d["btc"], "market_cap": d["market_cap"],
                    "players": d["players"]} for d in m],
        # What the world did, and what the model said would happen. Kept separate from the
        # P&L on purpose: one is a calibration statement about the simulation, the other is
        # a trading result from a window that has been read four times.
        "reality": r.get("reality", []),
        "divergence": r.get("divergence", []),
        "divergence_stats": r.get("divergence_stats", {}),
    }


def main() -> int:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "frontend.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    t = payload["totals"]
    print(f"players {t['players']}   assets {t['assets']}   "
          f"market cap ${t['market_cap']/1e12:.2f}T   dry powder ${t['cash']/1e9:,.0f}B")
    print(f"2026 section: {'present' if payload['forward_2026'] else 'NOT RUN YET'}")
    print(f"written {path}  ({path.stat().st_size/1024:.0f}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
