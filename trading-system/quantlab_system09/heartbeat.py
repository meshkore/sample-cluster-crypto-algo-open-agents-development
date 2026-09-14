"""WHAT IS THIS MACHINE DOING RIGHT NOW - a job registry any process can write to.

The operator wants to look at one screen and know: is something running, what is it, how long
has it been going, and if nothing is running, say so plainly rather than showing a stale
number that looks alive.

The design constraint is that work here does not all come from one place. The autoloop runs
experiments unattended; a training or a backtest may also be launched by hand at the same
moment, on the same GPU. A heartbeat written by the loop alone would show "idle" while the
card is at 100%. So this is a REGISTRY rather than a status file: every process that does
work writes its own small file into `research/system09/jobs/`, refreshes it every few seconds
from a background thread, and deletes it on the way out.

Two consequences worth stating, because they are what make it trustworthy:

- **A crashed job does not linger as "running".** The reader treats a file whose heartbeat is
  older than `STALE_AFTER` as dead and says so. A process killed with -9 never gets to clean
  up, and pretending otherwise is how dashboards start lying.
- **Nothing is inferred.** The panel shows the jobs that registered themselves. It does not
  scan the process table and guess which python belongs to this laboratory.

Usage is one line:

    with heartbeat.job("phase 3 backtest", detail="sealed 2026"):
        ...
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from quantlab_catalog.paths import REPO_ROOT

JOBS = REPO_ROOT / "research" / "system09" / "jobs"
#: A heartbeat older than this means the process is gone, not slow. The writer refreshes
#: every 5 seconds, so a minute of silence is twelve missed beats.
STALE_AFTER = 60.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def job(name: str, detail: str = "", kind: str = "task"):
    """Register this process as doing `name` until the block exits."""
    JOBS.mkdir(parents=True, exist_ok=True)
    path = JOBS / f"{os.getpid()}_{abs(hash(name)) % 10_000}.json"
    started = time.time()
    stop = threading.Event()

    def write(state: str) -> None:
        path.write_text(json.dumps({
            "name": name, "detail": detail, "kind": kind, "pid": os.getpid(),
            "state": state, "started": started, "started_at": _now(),
            "beat": time.time(), "beat_at": _now(),
            "elapsed": time.time() - started}, indent=1), encoding="utf-8")

    def pulse() -> None:
        while not stop.wait(5.0):
            try:
                write("running")
            except OSError:
                return

    write("running")
    t = threading.Thread(target=pulse, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def active() -> list[dict]:
    """Every job that is currently alive, plus any whose heartbeat has gone stale."""
    if not JOBS.is_dir():
        return []
    out = []
    now = time.time()
    for p in sorted(JOBS.glob("*.json")):
        try:
            row = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        age = now - float(row.get("beat", 0))
        row["stale"] = age > STALE_AFTER
        row["elapsed"] = now - float(row.get("started", now))
        row["silent_for"] = age
        out.append(row)
    return sorted(out, key=lambda r: r.get("started", 0))
