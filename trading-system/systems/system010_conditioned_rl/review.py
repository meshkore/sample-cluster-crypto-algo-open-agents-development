"""Health every 15 minutes, a written review every 8 hours: corrections that need no one's permission.

The operator, 2026-10-08: *"run an evaluation about every eight hours, on a schedule, and
make the corrections automatically without asking me anything."*

The watchdog launches this every 15 minutes. It reads files only and imports no model code.
  health   a job whose log has not moved for too long is hung: stopped, and the watchdog
           relaunches it within five minutes. research/system10/RESTART_<job> asks for one
           restart (new code). A job set to false in jobs.json is stopped; retired jobs are
           stopped on sight.
  daily    pivots.run: the main line's stall gate and the weekly report
  8-hour   one row in rnd/reviews.jsonl and an event: trials, the optimal and the
           maximum-profit configurations under the drawdown cap, the 2026 reading; and
           overfit.py (subprocess, time budget) -> rnd/overfit.json: nested curve, PBO, DSR
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "research" / "system10"
RND = OUT / "rnd"
STAMP = RND / "last_review.txt"
REVIEWS = RND / "reviews.jsonl"
EVENTS = RND / "events.jsonl"
WINDOW_H = 8
STALE_MIN = {"w1": 120, "w2": 120, "w3": 120, "w4": 120, "evaluator": 180, "paper": 75}
PATTERN = {**{f"w{i}": f"*system010_conditioned_rl.search*--worker w{i}*" for i in (1, 2, 3, 4)},
           "status": "*system010_conditioned_rl.status*",
           "evaluator": "*system010_conditioned_rl.evaluator*",
           "paper": "*system010_conditioned_rl.paper*",
           # the venue mirror (live-trading/quantlab_live/mirror.py): shadow unless armed
           "mirror": "*quantlab_live.mirror*",
           "health": "*system010_conditioned_rl.health*",
           # the public page's publisher (restart-on-request only: it has no s10 log)
           "pusher": "*preview\\cf_pusher.py*"}
# Lines retired on 2026-10-14 (research/system10/README.md): stopped if ever found running.
RETIRED = {"trader": "*system010_conditioned_rl.trader_rl*",
           "forecaster": "*system010_conditioned_rl.forecaster*"}
DD_CAP = 0.25
OVERFIT_BUDGET_S = 600


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def event(kind: str, text: str) -> None:
    with EVENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now(), "kind": kind, "text": text}) + "\n")


def age_min(path: Path) -> float | None:
    return (time.time() - path.stat().st_mtime) / 60 if path.is_file() else None


def stop_process(pattern: str) -> bool:
    ps = (f"$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          f"Where-Object {{ $_.CommandLine -like '{pattern}' }}; "
          f"$p | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}; @($p).Count")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return out not in ("", "0")
    except Exception:  # noqa: BLE001
        return False


def health(jobs: dict) -> list[str]:
    acts = []
    for tag, pat in PATTERN.items():
        flag = OUT / f"RESTART_{tag}"
        if flag.is_file():
            flag.unlink()
            if stop_process(pat):
                acts.append(f"{tag} restarted on request")
    for tag, limit in STALE_MIN.items():
        a = age_min(OUT / f"s10_{tag}.log")
        if jobs.get(tag, True) and a is not None and a > limit and stop_process(PATTERN[tag]):
            acts.append(f"{tag} log silent {a:.0f} min - stopped, the watchdog relaunches it")
    for tag, on in jobs.items():
        if on is False and tag in PATTERN and stop_process(PATTERN[tag]):
            acts.append(f"{tag} stopped - switched off in jobs.json")
    for tag, pat in RETIRED.items():
        if stop_process(pat):
            acts.append(f"{tag} stopped - retired line")
    return acts


def law(years: dict, max_dd: float) -> float:
    """search.law, repeated here because this module imports no model code."""
    ordered = [float(years[k]["return"]) for k in sorted(years, key=lambda k: int(k))]
    rets = sorted(ordered)
    w = (0.5, 0.3, 0.2)[:max(1, len(rets) - 1)]
    floor = sum(wi * r for wi, r in zip(w, rets)) / sum(w)
    rw = list(range(1, len(ordered) + 1))
    recent = sum(wi * min(r, 0.50) for wi, r in zip(rw, ordered)) / sum(rw)
    return round(0.5 * floor + 0.5 * recent - 0.25 * float(max_dd), 4)


def search_review() -> dict:
    done = rows(RND / "search_trials.jsonl")
    for r in done:
        if r.get("years"):
            r["score"] = law(r["years"], max(float(v["max_dd"]) for v in r["years"].values()))
            c = r.get("confirm") or {}
            if c.get("years"):
                r["score"] = min(r["score"], law(c["years"], max(float(v["max_dd"]) for v in c["years"].values())))
    cut = time.time() - WINDOW_H * 3600
    ts = lambda r: datetime.fromisoformat(r["at"]).timestamp()  # noqa: E731
    recent = [r for r in done if ts(r) >= cut]
    ok = [r for r in done if r["eligible"] and r["max_dd"] <= DD_CAP and r["cfg"].get("size_down", 1) > 0]
    optimal = max(ok, key=lambda r: (r["score"], r["worst_q"])) if ok else None
    most = max(ok, key=lambda r: r["cagr"]) if ok else None
    pick = lambda r: r and {"cfg": r["cfg"], "worst_year": r["worst_year"], "cagr": r["cagr"],  # noqa: E731
                            "max_dd": r["max_dd"]}
    rel = sorted((OUT / "releases").glob("release_*.json"))
    fwd = rows(RND / "training_timeline.jsonl")
    return {"trials": len(done), "trials_window": len(recent),
            "eligible_window": sum(r["eligible"] and r["max_dd"] <= DD_CAP for r in recent),
            "optimal": pick(optimal), "max_profit": pick(most),
            "latest_release": rel[-1].stem if rel else None,
            "release_forward_2026": (fwd[-1].get("forward_2026") if fwd else None)}


def overfit() -> dict | None:
    """overfit.py in a child process (it reads the ledger through search; this module imports
    no model code). Returns the brief, or None on failure (an event says why)."""
    repo = OUT.parents[1]
    try:
        p = subprocess.run([sys.executable, "-m", "system010_conditioned_rl.overfit", "--quiet"],
                           cwd=repo, capture_output=True, text=True, timeout=OVERFIT_BUDGET_S)
        if p.returncode:
            event("review", "overfit failed: " + ((p.stderr or "").strip().splitlines() or ["?"])[-1][:200])
            return None
        doc = json.loads((RND / "overfit.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        event("review", f"overfit failed: {type(exc).__name__}: {exc}"[:240])
        return None
    nc, ch = (doc.get("nested") or {}).get("curve") or {}, (doc.get("champion") or {}).get("curve") or {}
    pbo, dsr = doc.get("pbo"), (doc.get("dsr") or {}).get("dsr")
    text = (f"overfit: PBO {pbo} ({doc.get('pbo_basis')}), DSR {dsr}; chosen-on-the-past 2023-25 CAGR "
            f"{nc.get('cagr', 0):+.1%} worst {nc.get('worst_year', 0):+.1%} vs champion "
            f"{ch.get('cagr', 0):+.1%} / {ch.get('worst_year', 0):+.1%}")
    if (doc.get("gate") or {}).get("refuses"):
        text += " - releases refused (PBO > 0.5)"
    event("pivot" if (doc.get("gate") or {}).get("refuses") else "review", text)
    return {"pbo": pbo, "pbo_basis": doc.get("pbo_basis"), "dsr": dsr, "nested": nc, "champion": ch}


BOOK_PBO_FLAG = OUT / "ENABLE_BOOK_PBO"     # absent (default): the book PBO step is skipped


def book_overfit() -> dict | None:
    """Book audit 2026-10-15, phase 4: PBO (CSCV) over the book ledger, in a child process
    (book_worker --pbo -> rnd/book_overfit.json); the book worker refuses releases above 0.5.
    Off unless ENABLE_BOOK_PBO exists."""
    if not BOOK_PBO_FLAG.is_file():
        return None
    repo = OUT.parents[1]
    try:
        p = subprocess.run([sys.executable, "-m", "system010_conditioned_rl.book_worker", "--pbo"],
                           cwd=repo, capture_output=True, text=True, timeout=OVERFIT_BUDGET_S)
        if p.returncode:
            event("review", "book PBO failed: " + ((p.stderr or "").strip().splitlines() or ["?"])[-1][:200])
            return None
        doc = json.loads((RND / "book_overfit.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        event("review", f"book PBO failed: {type(exc).__name__}: {exc}"[:240])
        return None
    event("pivot" if doc.get("refuses") else "review",
          f"book PBO {doc.get('pbo')} over {doc.get('books')} books" + (" - book releases refused" if doc.get("refuses") else ""))
    return {k: doc.get(k) for k in ("pbo", "books", "refuses")}


def main() -> int:
    from . import pivots as P
    force = "--force" in sys.argv
    acts = health(P.jobs())
    for a in acts:
        event("review", f"health: {a}")
    try:
        P.run(event)
    except Exception as exc:  # noqa: BLE001
        event("review", f"daily review failed: {type(exc).__name__}: {exc}"[:240])
    if not force and STAMP.is_file() and age_min(STAMP) < WINDOW_H * 60:
        return 0
    STAMP.write_text(now(), encoding="utf-8")
    se = search_review()
    row = {"at": now(), "search": se, "actions": acts, "overfit": overfit()}
    bo = book_overfit()
    if bo is not None:
        row["book_overfit"] = bo
    with REVIEWS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    opt, mp = se["optimal"], se["max_profit"]
    head = (f"optimal: worst year {opt['worst_year']:+.1%}, CAGR {opt['cagr']:+.1%}, DD {opt['max_dd']:.0%}"
            if opt else f"no trial yet under {DD_CAP:.0%} DD every year")
    if mp:
        head += f"; max profit: CAGR {mp['cagr']:+.1%}, worst {mp['worst_year']:+.1%}, DD {mp['max_dd']:.0%}"
    event("review", f"8-hour review: {se['trials_window']} trials; {head}")
    print(json.dumps(row, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
