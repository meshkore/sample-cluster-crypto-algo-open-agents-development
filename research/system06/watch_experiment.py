"""One line per ARM of a running experiment, and one per problem. Nothing else.

    python research/system06/watch_experiment.py

A paired experiment is twelve nets and most of a day, and the runner's heartbeat moves
every few seconds: fifty epochs, then eight scoring years, per net. Watching the
heartbeat directly means one notification a minute for hours, which is the same as no
notification at all - it trains the reader to ignore the channel.

So this reports the only two things worth interrupting anyone for: the arm changed, or
something broke. The arm is read as `seed N | label` from whichever shape the heartbeat
happens to be in - the runner writes the label before the colon while scoring and after
it while training - so the watch does not lose track of which arm is running halfway
through each net.

Exits when every arm has a verdict, printing the verdicts.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time

S6 = pathlib.Path("research/system06")
LIVE = S6 / "autotest_live.json"
LOG = S6 / "autotest.log"
TAPE = S6 / "rnd" / "program_progress.jsonl"
ERR = S6 / "autotest.err"
PROBLEM = re.compile(r"autotest error|Traceback|CUDA out of memory|MemoryError|arm .* FAILED")


_last_arm: list[str] = []


def _arms() -> list[str]:
    """The arm labels, in the order the runner walks them, from the queued row."""
    try:
        for line in (S6 / "rnd" / "program.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line) if line.strip() else {}
            if row.get("status") == "running":
                return list((row.get("train_variants") or row.get("arms") or {}).keys())
    except (OSError, ValueError):
        pass
    return []


def _arm_from_log() -> str | None:
    """Which arm is running, counted from the log rather than read from the heartbeat.

    A cold start has no previous heartbeat to be sticky about, and the heartbeat carries
    no arm at all while a net trains. Every net announces itself with `epoch 1/50`, so
    counting those and indexing into the arm list survives a restart of this watcher.
    """
    arms = _arms()
    if not arms:
        return None
    try:
        text = LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    starts = len(re.findall(r"epoch\s+1/\d+", text))
    if not starts:
        return None
    return arms[(starts - 1) % len(arms)]


def where() -> str | None:
    """`seed N | arm label`, whichever way round the heartbeat wrote it.

    The label is STICKY. While a net trains, the heartbeat is overwritten by the epoch
    counter and carries no arm at all, so reading it literally made the watch announce
    "starting" every time an arm began - the one moment it was supposed to name.
    """
    try:
        live = json.loads(LIVE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    detail = str(live.get("detail") or "")
    seed = re.search(r"seed (\d+)", detail)
    arm = re.search(r"\[([^\]]+)\]", detail)
    if arm:
        _last_arm[:] = [arm.group(1)]
    elif not _last_arm:
        counted = _arm_from_log()
        if counted:
            _last_arm[:] = [counted]
    if not seed and not arm:
        return f"{live.get('state')} | {detail[:60]}"
    return (f"{live.get('state')} | seed {seed.group(1) if seed else '?'}"
            f" | {_last_arm[0] if _last_arm else 'starting'}")


def tape(seen: int) -> tuple[int, list[str]]:
    """New finished-arm rows as one line of FIGURES each.

    Operator, 2026-09-16: "when you finish a cycle give me figures, one line, under
    twenty words". An arm is the cycle that produces figures - eighty minutes, a score,
    a worst year and a delta against the same seed's baseline - so each one is announced
    the moment the runner writes it, and nothing else is.
    """
    try:
        lines = TAPE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return seen, []
    out = []
    for line in lines[seen:]:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        d = r.get("delta_vs_base")
        out.append(f"{r.get('id')} seed {r.get('seed')} | {r.get('arm')} | "
                   f"score {r.get('score', 0):+.4f} | worst {100 * (r.get('min_year') or 0):+.1f}% | "
                   + ("baseline" if d is None else f"delta {d:+.4f}"))
    return len(lines), out


def verdicts() -> list[str]:
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    # The runner prints one indented `label: +0.1234` line per arm when it finishes.
    return [ln.strip() for ln in lines
            if re.match(r"^  \S.*: [+-]\d", ln) and "epoch" not in ln]


def main() -> int:
    # The FIRST reading is swallowed on purpose. A long watch gets re-armed every half
    # hour, and announcing "still on the same arm" at each re-arm is precisely the
    # minute-by-minute noise this file exists to avoid. Only a CHANGE is news.
    seen_where, seen_problem = where(), None
    seen_tape, _ = tape(0)          # the tape so far is history, not news
    # The verdict lines ALREADY in the log belong to the experiment that just finished.
    # Counting them as this run's verdicts made a re-armed watch exit within seconds,
    # reporting the previous row's result as though it had just landed.
    already = len(verdicts())
    while True:
        seen_tape, fresh = tape(seen_tape)
        for line in fresh:
            print(line, flush=True)

        now = where()
        if now and now != seen_where:
            print(now, flush=True)
            seen_where = now

        for path in (LOG, ERR):
            try:
                tail = path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                continue
            hit = [ln for ln in tail.splitlines() if PROBLEM.search(ln)]
            if hit and hit[-1] != seen_problem:
                print(f"PROBLEM: {hit[-1][:200]}", flush=True)
                seen_problem = hit[-1]

        done = verdicts()
        if len(done) >= already + 3:
            print("VERDICT: " + "  |  ".join(done[-3:]), flush=True)
            return 0
        time.sleep(90)


if __name__ == "__main__":
    sys.exit(main())
