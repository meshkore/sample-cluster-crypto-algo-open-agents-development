#!/usr/bin/env python3
"""The research ledger: what has been tried, what it measured, what it killed.

This is the memory of the loop. Iteration N reads it to avoid re-running what
iterations 1..N-1 already settled, and writes to it so iteration N+1 inherits
the result. An iteration that ends without a record here did not happen.

Storage is deliberately dumb -- one append-only JSONL file plus a small state
document -- so that a half-finished iteration can never corrupt the history and
so a human can read it with `tail`.

    ledger.py status
    ledger.py backlog
    ledger.py open   <id>
    ledger.py record <id> --verdict REFUTED --metrics '{"holdout":0.89}' --notes '...'
    ledger.py abandon <id> --notes 'why'
    ledger.py seen   '<config json>'      # fingerprint check, exit 1 if already run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HYPOTHESES = ROOT / "ledger" / "hypotheses.jsonl"
STATE = ROOT / "ledger" / "state.json"
LOCK = ROOT / "ledger" / "iteration.lock"

VERDICTS = ("CONFIRMED", "REFUTED", "INCONCLUSIVE", "ABANDONED")
# An iteration that has held the lock longer than this is assumed dead: the
# process was killed, the machine slept, the session was closed. The tick
# reclaims it rather than blocking the loop forever.
#
# This was 90 minutes and it was wrong. H-014 was reclaimed as ABANDONED while
# it was actively running -- implementing a router change, five rounds of
# sabotage verification and a six-cell 386-asset holdout sweep is simply longer
# than ninety minutes, and the loop declared its own live iteration dead. Four
# hours is the ceiling on a real iteration; anything past that is genuinely
# stuck. `heartbeat` exists so a long iteration can say so rather than relying
# on the window being generous enough.
STALE_LOCK_SECONDS = 14400


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE.exists():
        return {
            "iteration": 0,
            "champion_2026_pct": 3.46,
            "champion_id": "S00743",
            "gate": {
                "holdout_return_pct": 0.0,
                "holdout_capital_drawdown_max": 0.30,
                "minimum_assets": 100,
                "note": "clear this on 2022-2025 before 2026 may be opened",
            },
            "open_hypothesis": None,
            "updated": now(),
        }
    return json.loads(STATE.read_text())


def save_state(state: dict) -> None:
    state["updated"] = now()
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def records() -> list[dict]:
    if not HYPOTHESES.exists():
        return []
    out = []
    for line in HYPOTHESES.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append(record: dict) -> None:
    HYPOTHESES.parent.mkdir(parents=True, exist_ok=True)
    with HYPOTHESES.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def fingerprint(config: dict) -> str:
    """A stable identity for a tested configuration.

    Sorted keys and normalised floats, so that {"a": 1} and {"a": 1.0} written
    on different days collapse to the same cell instead of being re-run.
    """

    def norm(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: norm(v) for k, v in sorted(value.items())}
        if isinstance(value, list):
            return [norm(v) for v in value]
        return value

    blob = json.dumps(norm(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# commands


def cmd_status(args: argparse.Namespace) -> int:
    state = load_state()
    done = records()
    by_verdict: dict[str, int] = {}
    for r in done:
        by_verdict[r.get("verdict", "?")] = by_verdict.get(r.get("verdict", "?"), 0) + 1
    held = lock_age()
    print(f"iteration      : {state['iteration']}")
    print(
        f"champion 2026  : {state['champion_id']} at {state['champion_2026_pct']:+.2f}%"
    )
    print(f"open hypothesis: {state.get('open_hypothesis') or '-'}")
    print(
        f"lock           : {'held ' + str(round(held)) + 's' if held is not None else 'free'}"
    )
    print(
        f"records        : {len(done)}  "
        + "  ".join(f"{k}={v}" for k, v in sorted(by_verdict.items()))
    )
    if done:
        print("\nlast 5:")
        for r in done[-5:]:
            print(f"  {r['id']:<12} {r.get('verdict', '?'):<13} {r['statement'][:78]}")
    return 0


def cmd_backlog(args: argparse.Namespace) -> int:
    path = ROOT / "ledger" / "backlog.md"
    print(path.read_text() if path.exists() else "(backlog empty)")
    return 0


def lock_age() -> float | None:
    if not LOCK.exists():
        return None
    return time.time() - LOCK.stat().st_mtime


def cmd_open(args: argparse.Namespace) -> int:
    age = lock_age()
    if age is not None and age < STALE_LOCK_SECONDS and not args.force:
        held = json.loads(LOCK.read_text() or "{}")
        print(
            f"refused: iteration {held.get('id')} still open ({round(age)}s). --force to steal.",
            file=sys.stderr,
        )
        return 1
    if any(r["id"] == args.id for r in records()):
        print(f"refused: {args.id} is already recorded; pick a new id", file=sys.stderr)
        return 1
    LOCK.write_text(
        json.dumps({"id": args.id, "opened": now(), "pid": os.getpid()}) + "\n"
    )
    state = load_state()
    state["open_hypothesis"] = args.id
    save_state(state)
    print(f"opened {args.id}")
    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    """Say the open iteration is still alive.

    Call this from anything long -- a multi-cell sweep, a 386-asset backtest --
    so the tick does not mistake work for death. Cheap enough to call between
    every cell.
    """
    if not LOCK.exists():
        print("no iteration is open", file=sys.stderr)
        return 1
    LOCK.touch()
    held = json.loads(LOCK.read_text() or "{}")
    print(f"heartbeat {held.get('id', 'unknown')}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    if args.verdict not in VERDICTS:
        print(f"verdict must be one of {VERDICTS}", file=sys.stderr)
        return 2
    try:
        metrics = json.loads(args.metrics)
    except json.JSONDecodeError as exc:
        print(f"--metrics is not valid JSON: {exc}", file=sys.stderr)
        return 2
    state = load_state()
    record = {
        "id": args.id,
        "iteration": state["iteration"] + 1,
        "recorded": now(),
        "piece": args.piece,
        "statement": args.statement or "",
        "verdict": args.verdict,
        "metrics": metrics,
        "config_fingerprint": fingerprint(metrics.get("config", {}))
        if metrics.get("config")
        else None,
        "opened_2026": bool(args.opened_2026),
        "consulted_cluster": bool(args.consulted),
        "notes": args.notes or "",
        "commit": args.commit or "",
    }
    append(record)
    state["iteration"] += 1
    state["open_hypothesis"] = None
    if args.champion_2026 is not None:
        state["champion_2026_pct"] = args.champion_2026
        if args.champion_id:
            state["champion_id"] = args.champion_id
    save_state(state)
    LOCK.unlink(missing_ok=True)
    print(f"recorded {args.id} as {args.verdict} (iteration {state['iteration']})")
    return 0


def cmd_abandon(args: argparse.Namespace) -> int:
    state = load_state()
    append(
        {
            "id": args.id,
            "iteration": state["iteration"] + 1,
            "recorded": now(),
            "piece": args.piece or "unknown",
            "statement": args.statement or "",
            "verdict": "ABANDONED",
            "metrics": {},
            "notes": args.notes or "iteration did not finish",
            "opened_2026": False,
            "consulted_cluster": False,
            "commit": "",
        }
    )
    state["iteration"] += 1
    state["open_hypothesis"] = None
    save_state(state)
    LOCK.unlink(missing_ok=True)
    print(f"abandoned {args.id}")
    return 0


def cmd_seen(args: argparse.Namespace) -> int:
    want = fingerprint(json.loads(args.config))
    for r in records():
        if r.get("config_fingerprint") == want:
            print(f"ALREADY RUN in {r['id']} ({r['verdict']}): {r['notes'][:120]}")
            return 1
    print(f"new configuration ({want})")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("backlog").set_defaults(fn=cmd_backlog)
    sub.add_parser("heartbeat").set_defaults(fn=cmd_heartbeat)

    p = sub.add_parser("open")
    p.add_argument("id")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_open)

    p = sub.add_parser("record")
    p.add_argument("id")
    p.add_argument("--verdict", required=True)
    p.add_argument("--metrics", default="{}")
    p.add_argument(
        "--piece",
        default="unknown",
        help="detector | bull | sideways | bear | sizing | news | harness",
    )
    p.add_argument("--statement", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--commit", default="")
    p.add_argument("--opened-2026", action="store_true", dest="opened_2026")
    p.add_argument("--consulted", action="store_true")
    p.add_argument("--champion-2026", type=float, default=None)
    p.add_argument("--champion-id", default=None)
    p.set_defaults(fn=cmd_record)

    p = sub.add_parser("abandon")
    p.add_argument("id")
    p.add_argument("--piece", default=None)
    p.add_argument("--statement", default="")
    p.add_argument("--notes", default="")
    p.set_defaults(fn=cmd_abandon)

    p = sub.add_parser("seen")
    p.add_argument("config")
    p.set_defaults(fn=cmd_seen)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
