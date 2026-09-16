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
ERR = S6 / "autotest.err"
PROBLEM = re.compile(r"autotest error|Traceback|CUDA out of memory|MemoryError|arm .* FAILED")


def where() -> str | None:
    """`seed N | arm label`, whichever way round the heartbeat wrote it."""
    try:
        live = json.loads(LIVE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    detail = str(live.get("detail") or "")
    seed = re.search(r"seed (\d+)", detail)
    arm = re.search(r"\[([^\]]+)\]", detail)
    if not seed and not arm:
        return f"{live.get('state')} | {detail[:60]}"
    return (f"{live.get('state')} | seed {seed.group(1) if seed else '?'}"
            f" | {arm.group(1) if arm else 'starting'}")


def verdicts() -> list[str]:
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    # The runner prints one indented `label: +0.1234` line per arm when it finishes.
    return [ln.strip() for ln in lines
            if re.match(r"^  \S.*: [+-]\d", ln) and "epoch" not in ln]


def main() -> int:
    seen_where, seen_problem = None, None
    while True:
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
        if len(done) >= 3:
            print("VERDICT: " + "  |  ".join(done[-3:]), flush=True)
            return 0
        time.sleep(90)


if __name__ == "__main__":
    sys.exit(main())
