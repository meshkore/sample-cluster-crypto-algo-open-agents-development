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


RL_TIMELINE = S.OUT / "rnd" / "rl_timeline.jsonl"


def rl_reading(world, device: str, seen: set) -> None:
    """Every new RL release, through the same three-slot book: 2025 (in its training years)
    and 2026 (never seen). The policy's position is the stake; it opens only inside its gate."""
    import json
    from . import rl as RL
    for path in sorted(RL.RL_DIR.glob("rl_release_*.pt")):
        if path.name in seen:
            continue
        seen.add(path.name)
        saved = torch.load(path, map_location=device, weights_only=False)
        meta = saved["meta"]
        net = RL.Net(meta["obs_dim"]).to(device)
        net.load_state_dict(saved["net"])
        net.eval()
        g, regime = S.gate(world, meta["conditions"])
        row = {"at": S._now(), "release": meta["n"], "train_hours": meta["train_hours"],
               "updates": meta["updates"], "decisions": meta["decisions"],
               "mean_reward": meta["mean_reward"], "in_market_training": meta["in_market"],
               "gpu": S.gpu_snapshot()}
        for year, key in ((2025, "in_sample_2025"), (2026, "forward_2026")):
            pos = RL.positions(world, net, g, regime, year, device)
            want = {s: pos[s] > 0 for s in pos}
            r = world.book(want, year, 10 ** 9, size=pos, keep=want)
            r.pop("daily", None)
            row[key] = {k: r.get(k) for k in ("return", "max_dd", "q", "trades", "win_rate", "mean_trade")}
        with RL_TIMELINE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        f, i = row["forward_2026"], row["in_sample_2025"]
        print(f"[{S._now()}] evaluator: RL release {meta['n']} ({meta['train_hours']} h) -> 2025 "
              f"{i['return']:+.1%} | 2026 {f['return']:+.1%} dd {f['max_dd']:.0%} "
              f"win {(f['win_rate'] or 0):.0%} {f['trades']} trades", flush=True)
        S.write_card()


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
    seen_rl: set = set()
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
        rl_reading(world, device, seen_rl)
        time.sleep(30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
