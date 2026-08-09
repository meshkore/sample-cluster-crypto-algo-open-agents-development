#!/usr/bin/env python3
"""Is the laboratory actually working? One command, one screen, one exit code.

A loop that runs for days fails in ways nobody watches for: the process is alive
but every iteration errors; the fit service died and the forward one did not; the
cluster stopped accepting posts; both advisors have been resting for six hours
and nobody noticed. This is what a reviewer checks, so that checking is thirty
seconds rather than an archaeology session in a log file.

    python3 orchestrator-manager/scripts/loop_health.py
    python3 orchestrator-manager/scripts/loop_health.py --json

Exit status is the point: 0 healthy, 1 degraded (working, something is off),
2 stopped (the loop is not running). A scheduled reviewer can branch on that
without parsing anything.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(
    os.environ.get("QUANTLAB_REPOSITORY_ROOT", Path(__file__).resolve().parents[2])
)
RUNTIME = Path.home() / "Library" / "Application Support" / "QuantLab"
LEDGER = REPO / "orchestrator-manager" / "loop" / "ledger"
OUTBOX = REPO / "orchestrator-manager" / "loop" / "cluster" / "outbox"

# How long an iteration may reasonably take before silence is suspicious. A fit
# is four folds times a population, so tens of minutes is normal and two hours
# is not.
STALL_MINUTES = 120


def _running(pattern: str) -> list[int]:
    try:
        out = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(p) for p in out.stdout.split() if p.isdigit()]


def _http(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _age_minutes(moment: str | None) -> float | None:
    if not moment:
        return None
    try:
        when = datetime.fromisoformat(str(moment))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 60.0


def collect() -> dict:
    report: dict = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    problems: list[str] = []
    notes: list[str] = []

    # -- processes --------------------------------------------------------- #
    loop_pids = _running("quantlab_manager.*loop")
    report["loop_pids"] = loop_pids
    if not loop_pids:
        problems.append("the research loop is not running")

    report["backtesters"] = {
        "fit_8770": bool(_http("http://127.0.0.1:8770/health")),
        "forward_8771": bool(_http("http://127.0.0.1:8771/health")),
    }
    monitor = _http("http://127.0.0.1:8766/health")
    report["monitor_8766"] = bool(monitor)
    if not monitor:
        problems.append("the monitor daemon is not answering on 8766")

    # A forward service that cannot serve the forward window is the one
    # misconfiguration that silently produces "no trades in 2026".
    forward_health = _http("http://127.0.0.1:8771/health")
    if forward_health is not None and not forward_health.get("forward"):
        problems.append(
            "the forward backtester on 8771 was started WITHOUT --forward; "
            "every 2026 run it serves stops at 2025-12-31"
        )

    # -- the loop's own state ---------------------------------------------- #
    state_path = LEDGER / "loop-state.json"
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}
        notes.append("no loop state yet (the first iteration has not finished)")
    history = state.get("history") or []
    report["iteration"] = state.get("iteration", 0)
    report["incumbent_forward"] = state.get("incumbent_forward")
    report["consecutive_failures"] = state.get("consecutive_failures", 0)
    report["recent"] = [
        {
            "n": h.get("iteration"),
            "module": h.get("module"),
            "verdict": h.get("verdict"),
            "forward": h.get("forward"),
            "seconds": h.get("seconds"),
            "at": h.get("at"),
        }
        for h in history[-6:]
    ]
    if state.get("consecutive_failures", 0) >= 3:
        problems.append(
            f"{state['consecutive_failures']} iterations in a row without an "
            "improvement or with errors"
        )

    last_at = history[-1].get("at") if history else None
    stalled = _age_minutes(last_at)
    report["minutes_since_last_iteration"] = round(stalled, 1) if stalled else None
    if stalled is not None and stalled > STALL_MINUTES and loop_pids:
        problems.append(
            f"the last iteration finished {stalled:.0f} minutes ago; a fit takes "
            f"tens of minutes, so this looks stuck"
        )

    # -- the ledger --------------------------------------------------------- #
    verdicts: dict[str, int] = {}
    total = 0
    try:
        for line in (LEDGER / "hypotheses.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            total += 1
            verdicts[str(record.get("verdict") or "OPEN")] = (
                verdicts.get(str(record.get("verdict") or "OPEN"), 0) + 1
            )
    except OSError:
        problems.append("the ledger is unreadable")
    report["ledger"] = {"records": total, "verdicts": verdicts}

    # -- the cluster -------------------------------------------------------- #
    posts = sorted(OUTBOX.glob("*.md")) if OUTBOX.is_dir() else []
    report["cluster_posts"] = len(posts)
    if posts:
        newest = posts[-1].stat().st_mtime
        minutes = (time.time() - newest) / 60.0
        report["minutes_since_last_post"] = round(minutes, 1)
        if minutes > STALL_MINUTES and loop_pids:
            notes.append(f"nothing posted to the cluster for {minutes:.0f} minutes")

    # -- recorded runs ------------------------------------------------------ #
    sidebar = _http("http://127.0.0.1:8766/api/backtests")
    if sidebar:
        report["runs_recorded"] = len(sidebar.get("history") or []) + len(
            sidebar.get("live") or []
        )
        best = sidebar.get("best_2026") or {}
        report["best_2026"] = {
            "label": best.get("label"),
            "return_pct": best.get("return_pct"),
            "trades": best.get("trades"),
        }

    report["problems"] = problems
    report["notes"] = notes
    report["status"] = (
        "stopped" if not loop_pids else ("degraded" if problems else "healthy")
    )
    return report


def render(report: dict) -> str:
    lines = [
        f"QuantLab loop · {report['status'].upper()} · {report['at']}",
        "",
        f"  iteration            {report.get('iteration', 0)}"
        f"   (last {report.get('minutes_since_last_iteration', '?')} min ago)",
        f"  loop process         {'up · pid ' + str(report['loop_pids'][0]) if report['loop_pids'] else 'DOWN'}",
        f"  backtester (fit)     {'up' if report['backtesters']['fit_8770'] else 'down'}",
        f"  backtester (forward) {'up' if report['backtesters']['forward_8771'] else 'down'}",
        f"  monitor daemon       {'up' if report['monitor_8766'] else 'DOWN'}",
        f"  incumbent forward    {report.get('incumbent_forward')}",
        f"  consecutive failures {report.get('consecutive_failures', 0)}",
        f"  ledger               {report['ledger']['records']} records "
        f"{report['ledger']['verdicts']}",
        f"  cluster posts        {report.get('cluster_posts', 0)}"
        f" (last {report.get('minutes_since_last_post', '?')} min ago)",
    ]
    if report.get("best_2026"):
        best = report["best_2026"]
        lines.append(
            f"  best in 2026         {best.get('label')} "
            f"{(best.get('return_pct') or 0):+.2%} on {best.get('trades') or 0} trades"
        )
    if report.get("recent"):
        lines += ["", "  recent iterations:"]
        for entry in report["recent"]:
            forward = entry.get("forward")
            lines.append(
                f"    {entry['n']:>3}  {str(entry['module'] or '?'):<9} "
                f"{str(entry['verdict'] or '?'):<12} "
                f"{'—' if forward is None else format(forward, '+.2%'):>8}"
                f"  {entry.get('seconds', '?')}s"
            )
    for problem in report["problems"]:
        lines += ["", f"  PROBLEM  {problem}"]
    for note in report["notes"]:
        lines.append(f"  note     {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--errors",
        type=Path,
        default=None,
        help="a loop log to scan for recent tracebacks",
    )
    args = parser.parse_args(argv)

    report = collect()
    if args.errors and args.errors.exists():
        try:
            tail = args.errors.read_text()[-200_000:]
        except OSError:
            tail = ""
        report["error_events"] = len(re.findall(r'"stage": "error"', tail))
        if report["error_events"]:
            report["problems"].append(
                f"{report['error_events']} error events in the log"
            )
            if report["status"] == "healthy":
                report["status"] = "degraded"

    print(json.dumps(report, indent=2, default=str) if args.json else render(report))
    return {"healthy": 0, "degraded": 1, "stopped": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
