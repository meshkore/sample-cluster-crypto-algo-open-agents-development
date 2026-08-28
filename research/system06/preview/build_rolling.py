"""Compute the rolling one-year-hold statistic for the champion and the 4 variants.

Run from REPO ROOT with PYTHONPATH=trading-system. Uses the COMBINED dataset so the
monthly cohorts run through the sealed 2026 too (observation only). Writes
research/system06/rolling.json = {card_id: rolling_dict} for the dashboard.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from quantlab_system06 import rolling, universe
from quantlab_system06.dataset import Dataset

ROOT = Path(__file__).resolve().parents[3]
S6 = ROOT / "research" / "system06"
SIG = str(S6 / "signals.npz")
OUT = S6 / "rolling.json"

BAND = {"enter": 0.85, "exit_": 0.25, "min_hold": 192}
BASE = {"max_positions": 2, "position_fraction": 0.15, "stop_loss": 0.08, "trail_stop": 0.12}

# card_id -> the risk levers (same as the variant showcase; "best" == the champion == V1 stack)
CONFIGS = {
    "best":  {"regime_deploy": 0.35},
    "var-1": {"regime_deploy": 0.35},
    "var-2": {"regime_deploy": 0.35, "breadth_gate": 0.30, "meta_margin": 0.0},
    "var-3": {"regime_deploy": 0.35, "breadth_gate": 0.30, "meta_margin": 0.0,
              "money_kelly": 0.5, "vol_scale": 1.5, "money_pyramid": 0.4},
    "var-4": {"regime_deploy": 0.35, "breadth_gate": 0.30, "meta_margin": 0.0,
              "money_kelly": 0.5, "vol_scale": 1.5, "martingale": 0.5},
}


def main() -> int:
    symbols = universe.load()
    assert len(symbols) >= 10, f"universe fell back to {symbols}; run from repo root"
    dataset = Dataset("backtester/data", symbols=symbols)
    cbars = dataset.combined()
    cstamps = sorted({b.timestamp for s in cbars.values() for b in s})
    print(f"combined {cstamps[0].date()} -> {cstamps[-1].date()} ({len(cstamps)} stamps)", flush=True)
    out = {}
    for cid, risk in CONFIGS.items():
        t0 = time.time()
        bk = {**BAND, **BASE, **risk}
        try:
            res = rolling.rolling_12m(cbars, cstamps, SIG, bk)
        except Exception as exc:  # noqa: BLE001
            print(f"{cid}: FAILED {type(exc).__name__} {exc}", flush=True)
            continue
        if res:
            out[cid] = res
            print(f"{cid:7s} won {res['wins']}/{res['n']} ({res['win_rate']*100:.0f}%) "
                  f"lost {res['losses']}  worst {res['worst']*100:+.0f}%  best {res['best']*100:+.0f}%  "
                  f"median {res['median']*100:+.1f}%  {time.time()-t0:.0f}s", flush=True)
    OUT.write_text(json.dumps(out, default=str))
    print(f"wrote {OUT} ({len(out)} configs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
