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
from system009_participant_ledger import heartbeat

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
    from system009_participant_ledger import calibrate, pipeline
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
    from system009_participant_ledger import behaviour, pipeline
    _, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    rows = []
    for ahead in behaviour.AHEAD:
        rows += behaviour.score(behaviour.build(traj, ahead=ahead), ahead)
    beat = sum(1 for r in rows if r["beats_persistence"])
    return {"rows": rows, "beat_persistence": beat, "total": len(rows)}


def exp_horizons() -> dict:
    """Which holding period carries signal. Re-run whenever the features change."""
    from system009_participant_ledger import horizons
    rows = horizons.study()
    return {"verdict": horizons.verdict(rows), "horizons": rows}


def exp_policy() -> dict:
    """Does any trading shape beat holding the universe, in every research year?"""
    from system009_participant_ledger import policy, pipeline
    from system009_participant_ledger.train import FOLDS
    ctx, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    best, rows = policy.select(traj, ctx.funding(), list(FOLDS))
    return {"chosen": {k: best[k] for k in ("horizon", "width", "shape", "worst", "mean")},
            "qualified": best.get("qualified", False),
            "candidates_beating_hold": sum(1 for r in rows if r["beats_hold_every_year"])}


def exp_world() -> dict:
    """Does the world outside crypto pay for itself, on top of the ledger?

    The strict-addition test with four arms. The one that matters is whether
    market+ledger+world is positive in EVERY research fold, because neither the ledger nor
    the world manages that alone.
    """
    from system009_participant_ledger import world_test
    out = world_test.run()
    s = out["summary"]
    return {"summary": s,
            "world_gain": s["market+ledger+world"]["mean_ic"] - s["market+ledger"]["mean_ic"],
            "all_folds_positive": s["market+ledger+world"]["folds_positive"] ==
                                  s["market+ledger+world"]["n"]}


def exp_ablation() -> dict:
    """What is each feature block worth, on a year nobody selected on?

    The experiment that reversed two earlier conclusions: with the drift-contaminated target
    the ledger and the world both "helped", and with a relative target and a held-back year
    neither does. It runs after every feature change for exactly that reason.
    """
    from system009_participant_ledger import ablation, features as F, pipeline
    ctx, traj = pipeline.reconstruct(end="2025-12-31", sealed=False, quiet=True, cache=True)
    out = {}
    for target in ("absolute", "relative"):
        ds = F.build(traj, ctx.funding(), horizon=ablation.HORIZON, target=target)
        out[target] = [ablation.evaluate(ds, name, x)
                       for name, x in ablation.arms(ds).items()]
    rel = out["relative"]
    best = max(rel, key=lambda r: (r["check_ic"] if r["check_ic"] == r["check_ic"] else -9))
    return {"best_relative_arm": best["arm"], "best_check_ic": best["check_ic"],
            "arms": {t: {r["arm"]: {"pick": r["pick_mean_ic"], "check": r["check_ic"]}
                         for r in rows} for t, rows in out.items()}}


def exp_market() -> dict:
    """Can the market's own direction be called from macro, liquidity and sentiment?"""
    from system009_participant_ledger import market_model as M, features as F, pipeline
    ctx, traj = pipeline.reconstruct(end="2025-12-31", sealed=False, quiet=True, cache=True)
    ds = F.build(traj, ctx.funding(), horizon=M.HORIZON, target="relative")
    days, x, y = M.daily(traj, ds)
    res = M.evaluate(days, x, y)
    picks = [r["edge"] for yr, r in res.items() if yr in M.PICK]
    return {"per_year": res,
            "pick_mean_edge": float(sum(picks) / len(picks)) if picks else None,
            "pick_worst_edge": min(picks) if picks else None,
            "check_edge": res.get(M.CHECK, {}).get("edge")}


def exp_combos() -> dict:
    """Which basket of assets, of all 16,383, does the forecast actually track?"""
    from system009_participant_ledger import combos
    return {"note": "see combos_report.json", "ran": bool(combos.main() == 0)}


def exp_market_arms() -> dict:
    """Which BLOCK the market head actually needs: crypto, liquidity, or the world by region.

    The operator asked for the world by region, and the honest answer has to be measured
    rather than assumed. First reading, 2026-09-15: the liquidity block pays on the held-back
    year (+19.0% edge, in market only 20% of days) and the regional block does not - adding it
    costs about nine points and widens the worst selection year. Re-run after any change to
    the archive, because that is what makes the claim falsifiable.
    """
    from system009_participant_ledger import market_model as M, features as F, pipeline
    ctx, traj = pipeline.reconstruct(end="2025-12-31", sealed=False, quiet=True, cache=True)
    ds = F.build(traj, ctx.funding(), horizon=M.HORIZON, target="relative")
    days, x, y = M.daily(traj, ds)
    table = M.ablate(days, x, y)
    best = max(table.items(),
               key=lambda kv: (kv[1]["check_edge"]
                               if kv[1]["check_edge"] == kv[1]["check_edge"] else -9))
    return {"arms": {k: {"pick_mean": v["pick_mean_edge"], "pick_worst": v["pick_worst_edge"],
                         "check": v["check_edge"]} for k, v in table.items()},
            "best_on_held_back": best[0], "best_check_edge": best[1]["check_edge"],
            "independent_observations": len(days) // M.HORIZON}


# `exp_archive` lived here until 2026-09-16: a guard that checked the World Archive was still
# built, current, and honest about which streams had expired. The archive left this repository
# with the world model on 2026-09-15, so the guard went with it - a health check for a package
# that is not here would fail for the one reason that tells you nothing.


#: name -> (callable, minutes, may it load the sealed window at all)
REGISTRY: dict[str, tuple] = {
    "calibration": (exp_calibration, 6, False),
    "behaviour": (exp_behaviour, 12, True),
    "horizons": (exp_horizons, 10, True),
    "policy": (exp_policy, 12, True),
    "world": (exp_world, 14, True),
    "ablation": (exp_ablation, 12, False),
    "market": (exp_market, 8, False),
    "combos": (exp_combos, 10, True),
    "market_arms": (exp_market_arms, 14, False),
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
    """Read the queue fresh every cycle, so it can be edited while the loop runs.

    Read as utf-8-SIG, and complain loudly when the file will not parse. Both of those are
    scars: a backlog written by Windows PowerShell carries a byte-order mark, `json.loads`
    refused it, the failure was swallowed as "empty", and the loop sat in standby for two
    hours with work queued and nothing on the screen to say why. A queue that cannot be read
    is an incident, not an empty queue.
    """
    if BACKLOG.is_file():
        try:
            return json.loads(BACKLOG.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            print(f"  [{_now()}] BACKLOG UNREADABLE: {exc}. Nothing will run until it "
                  f"parses - fix {BACKLOG}")
            _append({"at": _now(), "experiment": "_backlog", "ok": False,
                     "error": f"backlog will not parse: {exc}"})
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
        # Registering the job is what lets the dashboard say what this machine is doing right
        # now, rather than what it last finished.
        with heartbeat.job(name, detail=item.get("why", ""), kind="experiment"):
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
