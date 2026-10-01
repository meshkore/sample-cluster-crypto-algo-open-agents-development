"""The release evaluator: backtests the PUBLISHED model while the trainers keep training.

The operator, 2026-10-01: *"the model never stops training - they must be isolated
processes: every so often you make a release of the model, you keep training, and with the
published one you do the backtest. That way the CPUs and the GPU never stop."*

So this process never trains a candidate and never chooses anything. It watches
`research/system10/releases/`; for the newest release it fits that release's fold-2026
selector (trained on <= 2024, its take-bar set on 2025 - the same rule every trial was judged
by) and runs the three-slot book on 2026-01-01..today. One point goes on the success chart
every hour and immediately when a new release appears. 2026 is read here and only here, and
nothing read here flows back to the trainers.

It reloads the bars every `--hours` (default 6) by exiting; the watchdog relaunches it.
"""

from __future__ import annotations

import argparse
import sys
import time

import torch

from . import search as S


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 release evaluator (the only reader of 2026)")
    ap.add_argument("--hours", type=float, default=6.0)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    started = time.time()
    print(f"[{S._now()}] evaluator: loading bars through today", flush=True)
    world = S.World(include_sealed=True)
    cache: dict = {}
    last_read = 0.0
    seen_release = None
    while time.time() - started < args.hours * 3600 and not S.STOP.exists():
        rel = S.releases()
        latest = rel[-1] if rel else None
        fresh = latest is not None and latest["id"] != seen_release
        if fresh or time.time() - last_read >= S.READ_EVERY_S:
            champ = None
            if latest:
                champ = {"id": latest["id"], "cfg": latest["cfg"], "score": latest["score"],
                         "years": latest["years"]}
            done = S.ledger()
            hours = sum(r.get("minutes", 0) for r in done) / 60
            row = S.timeline_reading(world, champ, device, hours, len(done), cache)
            if latest:
                row_note = row.get("forward_2026") or {}
                print(f"[{S._now()}] evaluator: release {latest['n']} -> 2026 "
                      f"{(row_note.get('return') or 0):+.1%} dd {(row_note.get('max_dd') or 0):.0%} "
                      f"win {(row_note.get('win_rate') or 0):.0%} {row_note.get('trades')} trades | "
                      f"unseen 2022-25 win {(row['unseen']['win_rate'] or 0):.0%}", flush=True)
                seen_release = latest["id"]
            last_read = time.time()
            S.write_card()
        time.sleep(30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
