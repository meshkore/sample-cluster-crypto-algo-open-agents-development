"""R5 (review 2026-10-15): does a one-hour lag in the 06 breadth channel matter?

Re-books a release on today's 14 coins twice with search.evaluate, same seeds: as recorded, and
with every coin's breadth read 4 bars (1 h) late - b'[t] = b[t-4], so the gate, the selector's
training rows and the exit model's breadth input all see the lagged channel. Reports the law
difference against the measured swap band (0.10). Research bars only (<= 2025): no 2026 read.

    R=$(pwd -W); PYTHONPATH="$R/trading-system;$R/trading-system/systems;$R/research/system10/tools" \
        python research/system10/tools/breadth_lag.py --release 34
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for sub in ("trading-system", "trading-system/systems", "research/system10/tools"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

OUT = REPO / "research/system10/rnd/breadth_lag.json"
BAND = 0.10


def lag(b: np.ndarray, k: int) -> np.ndarray:
    """b read k bars late; the first k bars read 0 (no channel yet)."""
    out = np.zeros_like(b)
    out[k:] = b[:-k]
    return out


def summary(r: dict) -> dict:
    from system010_conditioned_rl import search as S
    ys = {int(k): v for k, v in r["years"].items()}
    return {"law": S.law(ys, max(v["max_dd"] for v in ys.values())), "cagr": r["cagr"],
            "worst_year": r["worst_year"], "max_dd": r["max_dd"], "eligible": r["eligible"],
            "years": {str(y): {k: ys[y][k] for k in ("return", "max_dd", "trades", "share")} for y in sorted(ys)}}


def main() -> int:
    import torch

    from book_inputs import wait_for_ram
    from system010_conditioned_rl import search as S
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--release", type=int, default=34)
    ap.add_argument("--bars", type=int, default=4)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    torch.set_num_threads(4)
    rel = next(r for r in S.releases() if int(r["n"]) == a.release)
    cfg = rel["cfg"]
    wait_for_ram(5.0)
    t0 = time.time()
    world = S.World()
    print(f"world: {len(world.per)} coins in {(time.time() - t0) / 60:.1f} min", flush=True)
    base = S.evaluate(world, cfg, a.device)
    print(f"as recorded: law {summary(base)['law']:+.4f} [{base['minutes']:.1f} min]", flush=True)
    for d in world.per.values():
        d["breadth"] = lag(d["breadth"], a.bars)
    S._SIGNALS.clear()
    lagged = S.evaluate(world, cfg, a.device)
    sb, sl = summary(base), summary(lagged)
    rec = {str(y): {"return": v["return"], "max_dd": v["max_dd"]} for y, v in rel["years"].items()}
    doc = {"at": S._now(), "release": a.release, "id": rel["id"], "lag_bars": a.bars, "seeds": list(S.SEEDS),
           "recorded": rec, "baseline": sb, "lagged": sl,
           "law_diff": round(sl["law"] - sb["law"], 4), "band": BAND,
           "immaterial": abs(sl["law"] - sb["law"]) < BAND,
           "baseline_reproduces": all(abs(sb["years"][y]["return"] - rec[y]["return"]) < 1e-4 for y in rec)}
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("law_diff", "immaterial", "baseline_reproduces")}), flush=True)
    print(f"-> {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
