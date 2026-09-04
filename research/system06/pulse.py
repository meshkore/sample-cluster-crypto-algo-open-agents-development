"""The hourly pulse: an automatic, plain-language trace of where the research stands.

Operator requirement (2026-08-29): the circuit never stops, and there must always be
a trace - every hour - saying where development is, visible in the agent or on the
public QuantLab front end. The R&D diary carries the AGENT's reasoning, but only
when the agent is awake. This daemon writes the MACHINE's own hourly account from
the live files, so the trail never has an hour-shaped hole in it:

  - what is training right now (autotest + autoloop heartbeats, and whether they
    are stale - a dead daemon must read as dead, never as silence),
  - what experiments are running/queued/done since the previous pulse,
  - the shipping champion's score and the promotion bar,
  - what landed in the last hour (new program results, new diary decisions).

Writes one line per hour to rnd/pulse.jsonl, which mock_server._rnd() publishes to
the dashboard alongside the diary. Read-only on every other file: this daemon never
touches the loop's state, so it can never corrupt an experiment.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

S6 = Path(__file__).resolve().parent
RND = S6 / "rnd"
PULSE = RND / "pulse.jsonl"
EVERY_S = 3600.0
# A heartbeat older than this is reported as STALE. Raised from 30 to 50 minutes on
# 2026-08-30 after a measured false-alarm risk: with three GPU jobs sharing one 4060,
# a single training epoch stretched past 15 minutes, and the runner - verified busy at
# 100% CPU and 100% GPU - would have been reported as dead. A trace that cries wolf
# under normal contention is worse than one that waits: the threshold must sit above
# the slowest legitimate gap between beats, not above the fastest.
STALE_S = 3000.0

# --- neglect thresholds ------------------------------------------------------------
# A daemon that is alive says nothing about whether the RESEARCH is moving. Three ways
# it silently stops, all of them observed on 2026-09-04 in the same afternoon:
#   - an experiment finished and nobody wrote down what it meant (P46, three hours),
#   - a row was left in `failed` and nobody noticed (P47, crashed on a bug),
#   - a manual row sat queued with the GPU free and nobody launched it (two and a half
#     hours, while the hourly trace cheerfully reported an empty agenda).
# Every one of those hours looked healthy in the pulse. These thresholds are what turns
# "nothing is broken" into "nothing is happening", which is the failure that matters.
JUDGE_GRACE_S = 7200.0    # a finished experiment with no written reading
MANUAL_GRACE_S = 3600.0   # a hand-launched row nobody launched


def _load(p: Path, retries: int = 3):
    """Read a JSON file, tolerating the moment it is being rewritten.

    The daemons write their heartbeats with a truncate-and-write, so a reader can
    catch the file empty or half-written. Observed 2026-08-31: the pulse reported
    "no heartbeat file" for a runner that was demonstrably training. A transient
    read must never be reported as a dead daemon - that is the cry-wolf failure
    this trace exists to avoid - so a failed parse is retried before it counts.
    """
    for attempt in range(retries):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except Exception:  # noqa: BLE001 - partial read; give the writer a moment
            if attempt == retries - 1:
                return None
            time.sleep(0.25)
    return None


def _jsonl(p: Path) -> list[dict]:
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return rows


def _age_s(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        t = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds()


def _daemon(name: str, live: dict | None) -> tuple[str, bool]:
    """(line, is_stale). The flag is what callers should trust - the dashboard and the
    tests read it, never the prose, so wording can change without breaking either."""
    if not live:
        return f"{name}: no heartbeat file", True
    age = _age_s(live.get("heartbeat"))
    detail = live.get("detail") or live.get("phase") or live.get("state") or "?"
    if age is None:
        return f"{name}: {detail} (heartbeat unreadable)", True
    if age > STALE_S:
        return f"{name}: STALE - last beat {age/60:.0f} min ago ({detail})", True
    return f"{name}: {detail} ({age/60:.0f} min ago)", False


def neglected(program: list[dict], brakes: dict[str, bool] | None = None) -> list[str]:
    """What is quietly NOT being done, in plain words. Empty = the research is moving.

    Separate from `stale_daemons` on purpose: that flag answers "is anything broken",
    this one answers "is anything happening". A machine can be perfectly healthy and
    have been idle for three hours, and on 2026-09-04 it was.

    `brakes` are the deliberate stop files. A brake is not a fault - it is how the GPU
    gets handed to one job - but an UNRELEASED brake is indistinguishable from a dead
    lab, and the only thing standing between the two is somebody remembering to delete
    a file. So it is reported every hour until it is gone.
    """
    out: list[str] = []
    for name, on in (brakes or {}).items():
        if on:
            out.append(f"{name} is present - that daemon is deliberately stopped and "
                       f"will NOT come back until the file is deleted")
    running = [r for r in program if r.get("status") == "running"]
    queued = [r for r in program if r.get("status") == "queued"]
    auto_queued = [r for r in queued if r.get("kind") != "manual"]

    for r in program:
        if r.get("status") != "failed":
            continue
        out.append(f"{r['id']} FAILED and is still sitting there"
                   + (f": {r['error']}" if r.get("error") else ""))

    for r in program:
        if r.get("status") != "done" or (r.get("result") or "").strip():
            continue
        age = _age_s(r.get("finished_at"))
        if age is not None and age > JUDGE_GRACE_S:
            out.append(f"{r['id']} finished {age/3600:.1f}h ago and no reading of it "
                       f"has been written")

    for r in queued:
        if r.get("kind") != "manual":
            continue
        age = _age_s(r.get("created_at"))
        if age is None or age > MANUAL_GRACE_S:
            out.append(f"{r['id']} is a manual row waiting to be launched by hand")

    if not running and not auto_queued:
        out.append("the runner has NOTHING to run - the GPU is idle and the agenda "
                   "needs extending")
    return out


def snapshot(since_iso: str | None) -> dict:
    now = datetime.now(timezone.utc)
    autotest = _load(S6 / "autotest_live.json")
    loop = _load(S6 / "live.json")
    best = _load(S6 / "best.json") or {}
    program = _jsonl(RND / "program.jsonl")
    results = _jsonl(RND / "program_results.jsonl")
    diary = _jsonl(RND / "diary.jsonl")

    by_status: dict[str, int] = {}
    for r in program:
        by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
    running = [r["id"] for r in program if r.get("status") == "running"]
    queued = [r["id"] for r in program if r.get("status") == "queued"]

    fresh_results = [r for r in results
                     if since_iso is None or str(r.get("at") or "") > since_iso]
    fresh_diary = [d for d in diary
                   if since_iso is None or str(d.get("at") or "") > since_iso]

    runner_line, runner_stale = _daemon("experiment runner", autotest)
    loop_line, loop_stale = _daemon("autoloop", loop)
    stale = ([n for n, s in (("autotest", runner_stale), ("autoloop", loop_stale)) if s])
    lines = [runner_line, loop_line]
    if running:
        lines.append(f"running: {', '.join(running)}")
    lines.append(f"queue: {len(queued)} waiting" + (f" (next: {queued[0]})" if queued else
                 " - AGENDA EMPTY, the runner will idle until it is extended"))
    if fresh_results:
        # The arms of a result live under `summary`, one entry per arm - `arms` is the
        # EXPERIMENT's key, not the result's. Reading the wrong one made every landing
        # report "(0 arms)", so P46's five measured arms were announced as nothing.
        lines.append("landed this hour: " + ", ".join(
            f"{r.get('id')} ({len(r.get('summary') or {})} arms)" for r in fresh_results))
    if fresh_diary:
        lines.append(f"agent decisions this hour: {len(fresh_diary)} "
                     f"(latest: {fresh_diary[-1].get('kind')})")
    if not fresh_results and not fresh_diary:
        lines.append("nothing completed this hour - long training in progress is normal; "
                     "a STALE line above is not")
    brakes = {n: (S6 / n).exists() for n in ("STOP", "STOP_AUTOLOOP", "STOP_AUTOTEST")}
    slack = neglected(program, brakes)
    if slack:
        lines.append("NOT MOVING: " + "; ".join(slack))

    return {
        "at": now.isoformat(),
        "stale_daemons": stale,          # empty = everything beating; the flag to trust
        "neglected": slack,              # empty = the research is actually moving
        "champion_score": best.get("score"),
        "promotion_bar": best.get("reproducible_bar"),
        "program": by_status,
        "running": running,
        "queued": queued,
        "results_this_hour": [r.get("id") for r in fresh_results],
        "diary_this_hour": len(fresh_diary),
        "summary": " | ".join(lines),
    }


SINGLETON_PORT = 57306   # not 8799 (mock_server, deliberately off) nor 5570-5589 (daemon)


def _claim_singleton():
    """Return the socket holding the single-instance claim, or None if one is running.

    A manual start racing the watchdog's 5-minute check produced TWO pulse daemons on
    2026-08-29, which would have written duplicate hourly lines - a trace that lies
    about its own cadence. A bound socket is the right lock here: the OS releases it
    the instant the process dies, so a crash cannot leave a stale lock behind (which a
    PID file would, and which would then silence the pulse entirely - a worse failure).
    """
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", SINGLETON_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main() -> int:
    claim = _claim_singleton()
    if claim is None:
        print("another pulse daemon is already running; exiting quietly", flush=True)
        return 0
    RND.mkdir(parents=True, exist_ok=True)
    prev = _jsonl(PULSE)
    since = prev[-1].get("at") if prev else None
    while True:
        try:
            row = snapshot(since)
            with PULSE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            since = row["at"]
            print(f"{row['at']}  {row['summary']}", flush=True)
        except Exception as exc:  # noqa: BLE001 - the pulse must outlive any single failure
            print(f"pulse error (continuing): {exc}", flush=True)
        time.sleep(EVERY_S)


if __name__ == "__main__":
    raise SystemExit(main())

