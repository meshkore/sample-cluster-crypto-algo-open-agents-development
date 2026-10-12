"""The daily strategy review and the weekly report: the loop that keeps questioning the work.

The operator, 2026-10-12: *"keep improving and training. Of the two lines of work, decide
whether to continue with them or pivot to one. Never stop the loop that questions things
every day, every seven days, so we never stop iterating."*

Called by review.py on every pass; acts at most once a day (strategy) and once a week
(report). It reads files only and decides nothing from 2026: every gate below judges on the
validation year or on the unseen 2022-2025 record, and 2026 is reported, never used.

The lever it pulls is research/system10/jobs.json - which jobs the watchdog keeps alive. A
job switched off is stopped by review.py's health pass and not relaunched; its RAM and
GPU go back to the line that works.

Daily gates (each pivot is an event on the monitor):
  RL trader    after RL_DAYS of the current design: kept if its best release beats both
               buy-and-hold and the trend follower on the median coin of its validation
               year AND does not lose to hold in 2025; otherwise retired, and search
               worker w4 takes its place.
  forecaster   once FORECAST_MIN_TRIALS search trials have used its ensemble: kept if one
               of them beats the best standard trial's score; otherwise paused for
               FORECAST_PAUSE_DAYS (the GPU goes to the search workers), then retried.
  main line    if no new release for STALL_DAYS, research/system10/EXPLORE is created and
               the search mixes random configurations into its walk (removed again on the
               next release).
Weekly: rnd/weekly/<date>.md and an event - releases, best unseen record, the 2026 reading,
the side lines' state, what the gates decided.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "research" / "system10"
RND = OUT / "rnd"
JOBS = OUT / "jobs.json"
EXPLORE = OUT / "EXPLORE"
DAILY_STAMP = RND / "last_strategy.txt"
WEEKLY_STAMP = RND / "last_weekly.txt"
STRATEGY_LOG = RND / "strategy.jsonl"
DEFAULT_JOBS = {"w1": True, "w2": True, "w3": True, "w4": False, "trader": True,
                "forecaster": True, "status": True, "evaluator": True}
RL_DAYS = 3
FORECAST_MIN_TRIALS = 40
FORECAST_PAUSE_DAYS = 7
STALL_DAYS = 3


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


def set_jobs(j: dict) -> None:
    JOBS.write_text(json.dumps(j, indent=1), encoding="utf-8")


def age_days(path: Path) -> float | None:
    return (time.time() - path.stat().st_mtime) / 86400 if path.is_file() else None


def _event(event, kind: str, text: str, acts: list) -> None:
    event(kind, text)
    acts.append(text)


def rl_gate(j: dict, event, acts: list) -> dict:
    """RL v5: keep or retire, after RL_DAYS of its current design."""
    from . import trader_rl as TR
    rel = sorted(TR.REL_DIR.glob("trader_release_*.json")) if TR.REL_DIR.is_dir() else []
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in rel]
    cur = [m for m in metas if m.get("design") == TR.DESIGN]
    info = {"design": TR.DESIGN, "releases": len(cur)}
    if not j.get("trader") or not cur:
        return info
    hours = max(m["train_hours"] for m in cur)
    first = datetime.fromisoformat(cur[0]["at"])
    days = (now() - first).total_seconds() / 86400
    v = [m["validation"] for m in cur]
    best = max(v, key=lambda x: x["agent"]["median_coin_return"])
    beats_val = (best["agent"]["median_coin_return"] > best["hold"]["median_coin_return"]
                 and best["agent"]["median_coin_return"] > best["trend"]["median_coin_return"])
    tl = [r for r in rows(RND / "trader_timeline.jsonl") if r["release"] in {m["n"] for m in cur}]
    oos = [r["out_of_sample_2025"] for r in tl]
    beats_2025 = any(o["agent"]["median_coin_return"] >= o["hold"]["median_coin_return"] for o in oos)
    info.update(days=round(days, 2), train_hours=hours, beats_validation=beats_val, beats_2025=beats_2025,
                best_val_median=best["agent"]["median_coin_return"])
    if days >= RL_DAYS and not (beats_val and beats_2025):
        j.update(trader=False, w4=True)
        _event(event, "pivot", f"RL trader ({TR.DESIGN}) retired after {days:.1f} days / {hours:.0f} h: best "
               f"{best['year'] if 'year' in best else 'validation'} median coin "
               f"{best['agent']['median_coin_return']:+.1%} vs hold {best['hold']['median_coin_return']:+.1%}, "
               f"trend {best['trend']['median_coin_return']:+.1%}; 2025 beat hold: {beats_2025}. "
               f"Its RAM goes to search worker w4.", acts)
    elif days >= RL_DAYS:
        _event(event, "review", f"RL trader ({TR.DESIGN}) kept: beats hold and trend on validation and "
               f"holds up in 2025", acts)
    return info


def forecaster_gate(j: dict, done: list[dict], event, acts: list) -> dict:
    ens = [r for r in done if r["cfg"].get("forecast") == "ensemble"]
    std = [r for r in done if r["cfg"].get("forecast") != "ensemble" and r["eligible"]]
    best_ens = max((r["score"] for r in ens if r["eligible"]), default=None)
    best_std = max((r["score"] for r in std), default=None)
    info = {"ensemble_trials": len(ens), "best_ensemble_score": best_ens, "best_standard_score": best_std}
    paused = j.get("forecaster") is False
    if paused:
        since = j.get("forecaster_paused_at")
        if since and (now() - datetime.fromisoformat(since)).days >= FORECAST_PAUSE_DAYS:
            j["forecaster"] = True
            j.pop("forecaster_paused_at", None)
            _event(event, "pivot", f"forecaster resumed after its {FORECAST_PAUSE_DAYS}-day pause", acts)
        return info
    if len(ens) >= FORECAST_MIN_TRIALS and (best_ens is None or best_std is None or best_ens <= best_std):
        j.update(forecaster=False, forecaster_paused_at=now().isoformat(timespec="seconds"))
        _event(event, "pivot", f"forecaster paused for {FORECAST_PAUSE_DAYS} days: {len(ens)} search trials on "
               f"its ensemble, best score {best_ens} vs {best_std} with the standard signal. GPU goes to "
               f"the search workers.", acts)
    return info


def main_line_gate(event, acts: list) -> dict:
    rel = sorted((OUT / "releases").glob("release_*.json"))
    last = json.loads(rel[-1].read_text(encoding="utf-8")) if rel else None
    days = (now() - datetime.fromisoformat(last["at"])).total_seconds() / 86400 if last else None
    info = {"releases": len(rel), "days_since_release": round(days, 2) if days is not None else None}
    if days is not None and days >= STALL_DAYS and not EXPLORE.exists():
        EXPLORE.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")
        _event(event, "pivot", f"main line: no new release for {days:.1f} days - the search now mixes "
               f"random configurations into its walk (EXPLORE)", acts)
    elif days is not None and days < 1 and EXPLORE.exists():
        EXPLORE.unlink()
        _event(event, "review", f"main line: release {last['n']} arrived - exploration back to the walk", acts)
    return info


def weekly(event, daily_info: dict) -> None:
    import statistics as st
    rel = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / "releases").glob("release_*.json"))]
    cut = now() - timedelta(days=7)
    week = [r for r in rel if datetime.fromisoformat(r["at"]) >= cut]
    tl = [r for r in rows(RND / "training_timeline.jsonl") if isinstance(r.get("forward_2026"), dict)
          and r["at"] >= "2026-10-10T00:00:00+00:00"]
    f = tl[-1]["forward_2026"] if tl else {}
    strat = [r for r in rows(STRATEGY_LOG) if datetime.fromisoformat(r["at"]) >= cut]
    acts = [a for r in strat for a in r.get("actions", [])]
    best = rel[-1] if rel else None
    lines = [f"# System 10 - week to {now().date().isoformat()}", "",
             f"- Releases this week: {len(week)} (total {len(rel)})"]
    if best:
        lines.append(f"- Live release {best['n']}: {best['label']}")
        lines.append(f"  - unseen 2022-2025: worst year {best['worst_year']:+.1%}, CAGR {best['cagr']:+.1%}, "
                     f"win {best['unseen']['win_rate']}")
    if f:
        lines.append(f"- 2026 forward (never used to choose): {f.get('return', 0):+.1%}, DD {f.get('max_dd', 0):.0%}, "
                     f"win {f.get('win_rate')}")
    lines.append(f"- Side lines: {json.dumps(daily_info, default=str)}")
    lines.append("- Decisions this week:" + ("" if acts else " none"))
    lines += [f"  - {a}" for a in acts]
    (RND / "weekly").mkdir(exist_ok=True)
    (RND / "weekly" / f"{now().date().isoformat()}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    event("review", f"weekly report: {len(week)} releases this week; live release "
                    f"{best['n'] if best else '-'}; {len(acts)} strategy decisions")
    WEEKLY_STAMP.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")


def run(event, ledger_loader) -> list[str]:
    """Daily strategy (and weekly report when due). Returns the actions taken."""
    acts: list[str] = []
    if DAILY_STAMP.is_file() and age_days(DAILY_STAMP) < 1:
        return acts
    DAILY_STAMP.write_text(now().isoformat(timespec="seconds"), encoding="utf-8")
    j = jobs()
    info = {"main": main_line_gate(event, acts)}
    try:
        info["rl"] = rl_gate(j, event, acts)
    except Exception as exc:  # noqa: BLE001
        info["rl"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    try:
        info["forecaster"] = forecaster_gate(j, ledger_loader(), event, acts)
    except Exception as exc:  # noqa: BLE001
        info["forecaster"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    set_jobs(j)
    with STRATEGY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now().isoformat(timespec="seconds"), "jobs": j, "info": info,
                             "actions": acts}, default=str) + "\n")
    if not WEEKLY_STAMP.is_file() or age_days(WEEKLY_STAMP) >= 7:
        weekly(event, info)
    return acts
