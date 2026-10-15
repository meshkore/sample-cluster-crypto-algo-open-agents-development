"""The daily review and the weekly report: the loop that keeps questioning the work.

The operator, 2026-10-12: *"never stop the loop that questions things every day, every seven
days, so we never stop iterating."* On 2026-10-14 the side lines (RL, forecaster) were
retired and the work focused on the main line, so the daily gate is the main line's alone.

Called by review.py on every pass; acts at most once a day and once a week. Reads files
only; 2026 is reported, never used to choose.

  daily    if no new release for STALL_DAYS, research/system10/EXPLORE is created and the
           search mixes random configurations into its walk (removed on the next release)
  daily    challengers.py (subprocess, time budget): simple strategies on the same candles
           and costs -> rnd/challengers.json; an event when one beats the main line
  weekly   rnd/weekly/<date>.md and an event: releases, the live release's unseen record,
           the 2026 reading, the paper book, the challengers, the decisions taken

research/system10/jobs.json is the switchboard: a job set to false is stopped by review.py
and not relaunched by the watchdog.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "research" / "system10"
RND = OUT / "rnd"
JOBS = OUT / "jobs.json"
EXPLORE = OUT / "EXPLORE"
DAILY_STAMP = RND / "last_strategy.txt"
WEEKLY_STAMP = RND / "last_weekly.txt"
STRATEGY_LOG = RND / "strategy.jsonl"
DEFAULT_JOBS = {"w1": True, "w2": True, "w3": True, "w4": True, "status": True,
                "evaluator": True, "paper": True}
STALL_DAYS = 3
CHALLENGERS = RND / "challengers.json"
CHALLENGE_BUDGET_S = 300


def now() -> datetime:
    return datetime.now(timezone.utc)


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        if x.strip():
            try:
                out.append(json.loads(x))
            except ValueError:
                pass
    return out


def jobs() -> dict:
    if JOBS.is_file():
        try:
            return {**DEFAULT_JOBS, **json.loads(JOBS.read_text(encoding="utf-8"))}
        except ValueError:
            pass
    return dict(DEFAULT_JOBS)


def age_days(path: Path) -> float | None:
    return (time.time() - path.stat().st_mtime) / 86400 if path.is_file() else None


def main_line_gate(event, acts: list) -> dict:
    rel = sorted((OUT / "releases").glob("release_*.json"))
    last = json.loads(rel[-1].read_text(encoding="utf-8")) if rel else None
    days = (now() - datetime.fromisoformat(last["at"])).total_seconds() / 86400 if last else None
    info = {"releases": len(rel), "days_since_release": round(days, 2) if days is not None else None}
    if days is not None and days >= STALL_DAYS and not EXPLORE.exists():
        EXPLORE.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")
        text = (f"main line: no new release for {days:.1f} days - the search now mixes random "
                f"configurations into its walk (EXPLORE)")
        event("pivot", text)
        acts.append(text)
    elif days is not None and days < 1 and EXPLORE.exists():
        EXPLORE.unlink()
        text = f"main line: release {last['n']} arrived - exploration back to the walk"
        event("review", text)
        acts.append(text)
    return info


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return {}


def challengers(event) -> None:
    """Book the challengers in a child process (own memory, killed past the budget); an event
    for every challenger that newly beats the main line on 2022-2025 worst year and CAGR
    within the 25% drawdown cap."""
    before = set(_read(CHALLENGERS).get("alerts") or [])
    try:
        p = subprocess.run([sys.executable, "-m", "system010_conditioned_rl.challengers", "--quiet"],
                           cwd=REPO, capture_output=True, text=True, timeout=CHALLENGE_BUDGET_S)
        if p.returncode:
            event("review", "challengers failed: " + ((p.stderr or '').strip().splitlines() or ['?'])[-1][:200])
            return
    except Exception as exc:  # noqa: BLE001
        event("review", f"challengers failed: {type(exc).__name__}: {exc}"[:240])
        return
    doc = _read(CHALLENGERS)
    main = (doc.get("main_line") or {}).get("newest") or {}
    for name in [a for a in doc.get("alerts") or [] if a not in before]:
        c = doc["challengers"][name]
        event("pivot", f"challenger beats main line: {name} - 2022-25 worst year {c['worst_year']:+.1%}, "
                       f"CAGR {c['cagr']:+.1%}, DD {c['max_dd']:.0%} vs release {main.get('release')} "
                       f"{main.get('worst_year', 0):+.1%} / {main.get('cagr', 0):+.1%}")


def challenger_lines() -> list[str]:
    doc = _read(CHALLENGERS)
    if not doc.get("challengers"):
        return []
    m = (doc.get("main_line") or {}).get("newest") or {}
    ch = {k: v for k, v in doc["challengers"].items() if "cagr" in v}
    top = sorted(ch, key=lambda k: -ch[k]["score"])[:3]
    out = [f"- Challengers ({len(ch)} simple strategies, same candles and costs, 2022-2025):"]
    if m:
        out.append(f"  - release {m['release']}: worst {m['worst_year']:+.1%}, CAGR {m['cagr']:+.1%}, "
                   f"DD {m['max_dd']:.0%}")
    for k in top:
        c, f = ch[k], ch[k].get("forward_2026") or {}
        out.append(f"  - {k}: worst {c['worst_year']:+.1%}, CAGR {c['cagr']:+.1%}, DD {c['max_dd']:.0%}"
                   + (f"; 2026 {f['return']:+.1%}" if f else ""))
    out.append(f"  - beat the main line: {', '.join(doc.get('alerts') or []) or 'none'}")
    return out


def overfit_lines() -> list[str]:
    """rnd/overfit.json (written by review.py's 8-hour pass): PBO, DSR, nested vs champion."""
    doc = _read(RND / "overfit.json")
    if not doc:
        return []
    nc = (doc.get("nested") or {}).get("curve") or {}
    ch = doc.get("champion") or {}
    cc = ch.get("curve") or {}
    fmt = lambda c: (" / ".join(f"{v:+.0%}" for v in (c.get("years") or {}).values())  # noqa: E731
                     + f"; CAGR {c.get('cagr', 0):+.1%}, worst {c.get('worst_year', 0):+.1%}, "
                       f"DD {c.get('max_dd', 0):.0%}") if c else "-"
    dsr = doc.get("dsr") or {}
    return ["- Overfitting (rnd/overfit.json, OVERFIT.md):",
            f"  - PBO {doc.get('pbo')} ({doc.get('pbo_basis')}); releases refused above 0.5: "
            f"{'YES' if (doc.get('gate') or {}).get('refuses') else 'no'}",
            f"  - Deflated Sharpe {dsr.get('dsr')} ({dsr.get('basis')}, {dsr.get('trials')} trials)",
            f"  - chosen on the past, 2023-25: {fmt(nc)}",
            f"  - champion (release {ch.get('release')}), 2023-25: {fmt(cc)}"]


def weekly(event) -> None:
    rel = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / "releases").glob("release_*.json"))]
    cut = now() - timedelta(days=7)
    week = [r for r in rel if datetime.fromisoformat(r["at"]) >= cut]
    tl = [r for r in rows(RND / "training_timeline.jsonl") if isinstance(r.get("forward_2026"), dict)
          and r["at"] >= "2026-10-10T00:00:00+00:00"]
    f = tl[-1]["forward_2026"] if tl else {}
    acts = [a for r in rows(STRATEGY_LOG) if datetime.fromisoformat(r["at"]) >= cut for a in r.get("actions", [])]
    best = rel[-1] if rel else None
    lines = [f"# System 10 - week to {now().date().isoformat()}", "",
             f"- Releases this week: {len(week)} (total {len(rel)})"]
    if best:
        lines.append(f"- Live release {best['n']}: {best['label']}")
        lines.append(f"  - unseen 2022-2025: worst year {best['worst_year']:+.1%}, CAGR {best['cagr']:+.1%}, "
                     f"win {best['unseen']['win_rate']}")
    if f:
        lines.append(f"- 2026 forward (never used to choose): {f.get('return', 0):+.1%}, "
                     f"DD {f.get('max_dd', 0):.0%}, win {f.get('win_rate')}")
    paper = OUT / "paper" / "paper_state.json"
    if paper.is_file():
        a = json.loads(paper.read_text(encoding="utf-8")).get("account", {})
        lines.append(f"- Paper book: ${a.get('equity', 0):,.0f} ({a.get('return_pct', 0):+.2%}), "
                     f"{a.get('trades_closed', 0)} closed trades")
    lines += challenger_lines()
    lines += overfit_lines()
    lines.append("- Decisions this week:" + ("" if acts else " none"))
    lines += [f"  - {a}" for a in acts]
    (RND / "weekly").mkdir(exist_ok=True)
    (RND / "weekly" / f"{now().date().isoformat()}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    event("review", f"weekly report: {len(week)} releases this week; live release "
                    f"{best['n'] if best else '-'}; {len(acts)} decisions")
    WEEKLY_STAMP.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")


def run(event) -> list[str]:
    """Daily gate (and weekly report when due). Returns the actions taken."""
    acts: list[str] = []
    if DAILY_STAMP.is_file() and age_days(DAILY_STAMP) < 1:
        return acts
    DAILY_STAMP.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")
    info = {"main": main_line_gate(event, acts)}
    with STRATEGY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now().isoformat(timespec="seconds"), "jobs": jobs(), "info": info,
                             "actions": acts}, default=str) + "\n")
    try:
        challengers(event)
    except Exception as exc:  # noqa: BLE001 - never block the weekly report
        event("review", f"challengers failed: {type(exc).__name__}: {exc}"[:240])
    if not WEEKLY_STAMP.is_file() or age_days(WEEKLY_STAMP) >= 7:
        weekly(event)
    return acts
