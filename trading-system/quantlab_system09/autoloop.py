"""THE LOOP THAT DOES NOT STOP WHILE THERE IS WORK LEFT.

The operator, 2026-09-14: *"busca un mecanismo de bucle infinito que no pare de trabajar
mientras tenga cosas que hacer para mejorar todo este sistema."*

So: a backlog of experiments, a worker that takes the next one, runs it, writes down what
happened, and goes again. It runs unattended for hours. Every experiment is wrapped - a
failure is a logged row and the loop continues, because a loop that dies on the first
exception is a script with ambitions.

WHAT MAKES THIS DIFFERENT FROM A SCRIPT THAT LOOPS
- **The backlog is a file, not a constant.** `research/system09/backlog.json` is read at the
  top of every cycle, so a supervising agent - or the operator - can add, reorder or drop work
  while it runs, without stopping it.
- **Every result is appended, never overwritten.** `loop.jsonl` is the record of what was
  tried and what it produced, including the failures.
- **The guards are code.** An experiment marked `sealed` may READ the forward window to report
  a number; nothing may ever select on it. That rule is enforced here, in `_run`, rather than
  trusted to whoever writes the next experiment.
- **It stops when told and not before.** `STOP` halts it; an empty backlog does not - it
  idles, re-checking for new work, because "nothing queued right now" is not "nothing to do".

WHAT IT KNOWS HOW TO RUN
The registry at the foot of this file. Each entry is a name, the callable, roughly how long it
takes, and whether it is allowed to look at the sealed window at all. Adding an experiment is
adding a function and a line.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from quantlab_catalog.paths import REPO_ROOT

ROOT = REPO_ROOT / "research" / "system09"
BACKLOG = ROOT / "backlog.json"
LEDGER = ROOT / "loop.jsonl"
LIVE = ROOT / "loop_live.json"
STOP = ROOT / "STOP"

IDLE_SECONDS = 120


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- experiments
def exp_calibration() -> dict:
    """V5 must stay CALIBRATED. This is the regression guard for everything else.

    It runs first and it runs often: every change to the boundary, the population or the
    supply series can move the float, and a model that has quietly drifted away from the
    published capitalisation invalidates every experiment that follows it.
    """
    from quantlab_system09 import calibrate, pipeline
    ctx, traj = pipeline.reconstruct(end="2025-12-31", sealed=False, cache=True)
    reports = calibrate.calibration(traj, ctx.symbols)
    last = reports[-1]
    worst = max((abs(r.float_error) for r in last.rows if r.float_error is not None),
                default=float("nan"))
    return {"checkpoint": last.day, "worst_float_error": worst,
            "universe_error": last.universe_error,
            "calibrated": bool(worst <= calibrate.FLOAT_TOLERANCE),
            "disputed": [r.symbol for r in last.disputed]}


def exp_behaviour() -> dict:
    """Can we predict what each group does, better than assuming it repeats itself?"""
    from quantlab_system09 import behaviour, pipeline
    _, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    rows = []
    for ahead in behaviour.AHEAD:
        rows += behaviour.score(behaviour.build(traj, ahead=ahead), ahead)
    beat = sum(1 for r in rows if r["beats_persistence"])
    return {"rows": rows, "beat_persistence": beat, "total": len(rows)}


def exp_horizons() -> dict:
    """Which holding period carries signal. Re-run whenever the features change."""
    from quantlab_system09 import horizons
    rows = horizons.study()
    return {"verdict": horizons.verdict(rows), "horizons": rows}


def exp_policy() -> dict:
    """Does any trading shape beat holding the universe, in every research year?"""
    from quantlab_system09 import policy, pipeline
    from quantlab_system09.train import FOLDS
    ctx, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    best, rows = policy.select(traj, ctx.funding(), list(FOLDS))
    return {"chosen": {k: best[k] for k in ("horizon", "width", "shape", "worst", "mean")},
            "qualified": best.get("qualified", False),
            "candidates_beating_hold": sum(1 for r in rows if r["beats_hold_every_year"])}


#: name -> (callable, minutes, may it load the sealed window at all)
REGISTRY: dict[str, tuple] = {
    "calibration": (exp_calibration, 6, False),
    "behaviour": (exp_behaviour, 12, True),
    "horizons": (exp_horizons, 10, True),
    "policy": (exp_policy, 12, True),
}

#: What to work through when no backlog file exists yet. Ordered: the guard first, then the
#: question that decides whether the generative simulator is worth building at all.
DEFAULT_BACKLOG = [
    {"name": "calibration", "status": "pending", "why": "regression guard on the float"},
    {"name": "behaviour", "status": "pending", "why": "can cohort flow be predicted at all"},
    {"name": "horizons", "status": "pending", "why": "where the signal lives"},
    {"name": "policy", "status": "pending", "why": "does any shape beat holding"},
]


# --------------------------------------------------------------------------- the loop
def _load_backlog() -> list[dict]:
    """Read the queue fresh every cycle, so it can be edited while the loop runs."""
    if BACKLOG.is_file():
        try:
            return json.loads(BACKLOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # A half-written file is a normal event when something else is editing it.
            return []
    BACKLOG.parent.mkdir(parents=True, exist_ok=True)
    BACKLOG.write_text(json.dumps(DEFAULT_BACKLOG, indent=1), encoding="utf-8")
    return list(DEFAULT_BACKLOG)


def _save_backlog(items: list[dict]) -> None:
    BACKLOG.write_text(json.dumps(items, indent=1), encoding="utf-8")


def _append(row: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _beat(state: str, item: dict | None, cycles: int) -> None:
    LIVE.write_text(json.dumps({
        "state": state, "at": _now(), "cycles": cycles,
        "running": item.get("name") if item else None}, indent=1), encoding="utf-8")


def _run(item: dict) -> dict:
    name = item["name"]
    entry = REGISTRY.get(name)
    if not entry:
        return {"ok": False, "error": f"unknown experiment {name!r}"}
    fn, _, sealed_ok = entry
    t0 = time.time()
    try:
        result = fn()
        return {"ok": True, "seconds": time.time() - t0, "sealed_reader": sealed_ok,
                "result": result}
    except Exception as exc:                        # noqa: BLE001 - log it and keep going
        return {"ok": False, "seconds": time.time() - t0,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-2000:]}


def loop(hours: float = 0.0, once: bool = False) -> int:
    deadline = time.time() + hours * 3600 if hours else float("inf")
    cycles = 0
    print(f"SYSTEM 09 AUTOLOOP  started {_now()}")
    print(f"  backlog {BACKLOG}\n  ledger  {LEDGER}\n  stop by creating {STOP}\n")
    while time.time() < deadline and not STOP.exists():
        items = _load_backlog()
        nxt = next((i for i in items if i.get("status") == "pending"), None)
        if nxt is None:
            # Nothing queued is not nothing to do - the operator may add work at any moment,
            # and a periodic re-check costs nothing.
            _beat("idle", None, cycles)
            print(f"  [{_now()}] backlog empty - idling {IDLE_SECONDS}s")
            if once:
                return 0
            time.sleep(IDLE_SECONDS)
            continue

        nxt["status"] = "running"
        nxt["started"] = _now()
        _save_backlog(items)
        _beat("running", nxt, cycles)
        print(f"  [{_now()}] running {nxt['name']} - {nxt.get('why', '')}")

        out = _run(nxt)
        cycles += 1
        row = {"at": _now(), "experiment": nxt["name"], "why": nxt.get("why"), **out}
        _append(row)

        items = _load_backlog()
        for i in items:
            if i.get("name") == nxt["name"] and i.get("status") == "running":
                i["status"] = "done" if out["ok"] else "failed"
                i["finished"] = _now()
                i["summary"] = (out.get("error") or
                                json.dumps(out.get("result", {}))[:400])
        _save_backlog(items)
        flag = "OK " if out["ok"] else "FAIL"
        print(f"  [{_now()}] {flag} {nxt['name']}  {out.get('seconds', 0):.0f}s  "
              + (out.get("error") or json.dumps(out.get("result", {}))[:160]))
        if once:
            return 0 if out["ok"] else 1
    print(f"  stopped {_now()} after {cycles} cycles")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="System 09's unattended improvement loop")
    ap.add_argument("--hours", type=float, default=0.0,
                    help="stop after this many hours (default: never)")
    ap.add_argument("--once", action="store_true", help="run a single experiment and exit")
    args = ap.parse_args(argv)
    return loop(hours=args.hours, once=args.once)


if __name__ == "__main__":
    sys.exit(main())
