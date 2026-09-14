"""The System 08 experiment loop: a queue of hypotheses, run honestly, forever.

WHY A LOOP AND NOT A SCRIPT

The operator's standing instruction is the maximum measurable result in the minimum time,
and the binding constraint on that is not compute - it is how long a hypothesis waits
between being thought of and being measured. Five cycles and seven experiments were run by
hand today; four of them refuted the idea that produced them. That ratio is the normal one,
and it is the argument for a queue: the cost of testing a wrong idea has to be small enough
that nobody is tempted to argue about it instead.

WHAT THIS ENFORCES, BECAUSE GUARDS THAT LIVE IN A HUMAN'S MEMORY ARE NOT GUARDS

  RESEARCH ONLY. Every experiment here runs on `cat.research()`, which cannot return a
  sealed bar even if a caller asks wrongly. 2026 is NEVER read by this loop. Spending a
  sealed read is a separate, deliberate act - `iterate.run_cycle` - and it stays that way
  because a forward year read by a daemon is a forward year nobody decided to spend.

  TRIALS ACCUMULATE. Every configuration evaluated increments a counter stored on disk and
  declared in every result. Understating it is the specific lie the six dead systems were
  built on, and a counter that resets when a process restarts is an understatement with
  extra steps.

  CONSISTENCY IS THE CRITERION, NOT THE HEADLINE. This laboratory's standing measure is
  profit in every calendar year, not the compounded total - the total is dominated by 2021
  in every configuration measured so far, and the binding constraint is the worst year. So
  the rank reads positive years, the worst year and drawdown, and never the total.

  EVERY RESULT IS WRITTEN, INCLUDING THE BAD ONES. There is no branch in this file that
  declines to record an outcome. A laboratory that records only the runs it liked has no
  record at all, and this repository already spent six systems learning that.

  NOTHING IS ADOPTED HERE. The loop measures and writes. Promoting a configuration is a
  decision, it belongs to the operator, and a daemon that could make it would eventually
  make it at three in the morning on a t-statistic of 1.4.

Run it deliberately:
    PYTHONPATH=trading-system python research/system08/loop.py            # forever
    PYTHONPATH=trading-system python research/system08/loop.py --once     # one experiment
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from quantlab_system08.system import Config, build          # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import propose as P                                          # noqa: E402

ROOT = Path("research/system08")
PROGRAM = ROOT / "program.jsonl"
RESULTS = ROOT / "loop_results.jsonl"
STATE = ROOT / "loop_state.json"
LOG = ROOT / "loop.log"

IDLE_SLEEP = 60           # only reached when even the proposer has nothing
DEFAULT_UNIVERSE = "universe_wide.json"

# The cumulative trial count through cycle 5, carried forward by hand exactly once. A
# counter that starts at zero on a fresh machine would silently forgive every
# configuration this system has already tried.
TRIALS_THROUGH_CYCLE_5 = 81


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# State: the cumulative trial count, which must survive a restart.
# --------------------------------------------------------------------------- #

def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"trials": TRIALS_THROUGH_CYCLE_5, "experiments_run": 0}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------- #
# The queue.
# --------------------------------------------------------------------------- #

def read_program() -> list[dict]:
    if not PROGRAM.exists():
        return []
    rows = []
    for line in PROGRAM.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            log(f"program: unparseable line skipped: {line[:80]}")
    return rows


def write_program(rows: list[dict]) -> None:
    PROGRAM.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def pick_queued(rows: list[dict]) -> dict | None:
    """The highest-priority queued experiment, lowest number first.

    A row whose `kind` is "manual" is never picked. It sits in the queue as the visible
    reminder it was written to be, which is the behaviour System 06's runner arrived at
    after a manual row crashed it.
    """
    queued = [r for r in rows if r.get("status") == "queued" and r.get("kind") != "manual"]
    queued.sort(key=lambda r: (r.get("priority", 99), str(r.get("id", ""))))
    return queued[0] if queued else None


# --------------------------------------------------------------------------- #
# Scoring.
# --------------------------------------------------------------------------- #

def score(report: dict) -> dict:
    """Consistency first, worst year second. The total return is reported, never ranked."""
    years = {k: v for k, v in report["by_year"].items() if abs(v) > 1e-9}
    worst = min(years.values()) if years else 0.0
    n_pos = sum(1 for v in years.values() if v > 0)
    return {
        "years_live": len(years),
        "years_positive": n_pos,
        "worst_year": worst,
        "consistency": (n_pos / len(years)) if years else 0.0,
        "total_return": report["total_return"],
        "max_drawdown": report["max_drawdown"],
        "sharpe": report["sharpe"],
        "t_stat": report["t_stat"],
        "clears_hurdle": report["clears_statistical_hurdle"],
        # The rank key, stated as an expression rather than as a mystery number: every
        # positive year is worth a point, the worst year is worth its own magnitude, and
        # drawdown is subtracted. Nothing here reads the total return.
        #
        # KEPT FOR READING, NOT FOR DECIDING. E01 showed why: an arm with a Sharpe of
        # 0.893 lost to one with 0.573 because it carried nine points more drawdown, and
        # a single weighted sum has no way to say that those two facts are not
        # commensurable. `rank_key` decides instead, and it is lexicographic precisely so
        # that no weight has to be invented to trade one criterion against another.
        "rank": n_pos + worst - report["max_drawdown"],
    }


def rank_key(sc: dict) -> tuple:
    """How two arms are actually compared. Lexicographic, in the lab's own order.

    Positive years first, because the standing criterion is profit in every calendar year.
    Then the worst year, rounded, since a difference in the fourth decimal of one year is
    not evidence of anything. Only then risk-adjusted return, and drawdown last as the
    tiebreak. The total return never appears: it is dominated by 2021 in every
    configuration measured so far, and ranking on it would pick whichever arm happened to
    be long the right names in one year out of nine.
    """
    return (sc["years_positive"], round(sc["worst_year"], 3),
            sc["sharpe"], -sc["max_drawdown"])


# --------------------------------------------------------------------------- #
# Running one experiment.
# --------------------------------------------------------------------------- #

_BARS_CACHE: dict[str, dict] = {}


def load_bars(universe: str) -> dict:
    """Research bars for a universe, cached: reloading them per experiment costs minutes."""
    if universe not in _BARS_CACHE:
        meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
        got = cat.research([str(s) for s in meta["symbols"]])
        _BARS_CACHE[universe] = {s: b for s, b in got.items() if b}
        log(f"loaded {len(_BARS_CACHE[universe])} tapes from {universe}")
    return _BARS_CACHE[universe]


def run_experiment(row: dict, state: dict) -> dict:
    """One experiment: a baseline and its arms, each scored on research years only."""
    universe = row.get("universe", DEFAULT_UNIVERSE)
    bars = load_bars(universe)
    base_cfg = row.get("baseline") or {}
    arms = row.get("arms") or []
    if not arms:
        raise ValueError(f"{row.get('id')}: an experiment with no arms measures nothing")

    out = {
        "id": row.get("id"),
        "title": row.get("title", ""),
        "hypothesis": row.get("hypothesis", ""),
        "at": datetime.now(timezone.utc).isoformat(),
        "universe": universe,
        "baseline": base_cfg,
        "arms": [],
    }

    for arm in [{"label": "baseline", "config": {}}] + list(arms):
        cfg_dict = dict(base_cfg)
        cfg_dict.update(arm.get("config") or {})
        state["trials"] += 1
        cfg = Config(**cfg_dict)
        try:
            rep = build(bars, cfg, trials=state["trials"]).report()
        except Exception as exc:                                # noqa: BLE001
            # ONE ARM THAT CANNOT RUN IS NOT A FAILED EXPERIMENT. A01 proposed a 20-day
            # beta window, which is below the observation count a loading needs, and the
            # single unrunnable arm threw away the four beside it that were fine. The arm
            # is recorded as unrunnable - never silently skipped, because a configuration
            # that cannot be built is itself a result about the parameter's range.
            log(f"  {str(arm.get('label', '?')):<22} UNRUNNABLE  "
                f"{type(exc).__name__}: {str(exc)[:80]}")
            out["arms"].append({
                "label": arm.get("label", "?"), "config": asdict(cfg),
                "trials_at_run": state["trials"],
                "unrunnable": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        sc = score(rep)
        out["arms"].append({
            "label": arm.get("label", "?"),
            "config": asdict(cfg),
            "trials_at_run": state["trials"],
            "score": sc,
            "by_year": rep["by_year"],
        })
        log(f"  {str(arm.get('label', '?')):<22} rank {sc['rank']:+.3f}  "
            f"years+ {sc['years_positive']}/{sc['years_live']}  "
            f"worst {sc['worst_year']:+.3f}  sharpe {sc['sharpe']:.3f}  "
            f"t {sc['t_stat']:.2f}")

    scored = [a for a in out["arms"] if "score" in a]
    base = scored[0]["score"] if scored else None
    rest = [a for a in scored[1:]]
    if rest and base is not None:
        best = max(rest, key=lambda a: rank_key(a["score"]))
        out["verdict"] = {
            "best_arm": best["label"],
            "beats_baseline": rank_key(best["score"]) > rank_key(base),
            "rank_delta": best["score"]["rank"] - base["rank"],
            # INERTNESS, borrowed from System 06's runner: an arm whose per-year returns
            # are identical to baseline did NOT ENGAGE - a missing precondition or a knob
            # that reached nothing. That is a broken experiment, not a null result, and
            # reporting it as "no effect" is how a wiring bug becomes a finding.
            "inert": all(a["by_year"] == scored[0]["by_year"] for a in rest),
        }
    return out


def record(result: dict) -> None:
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, default=str) + "\n")


# --------------------------------------------------------------------------- #

def refill(rows: list[dict]) -> list[dict]:
    """Put a new experiment on an empty queue, derived from what has been measured.

    The loop slept from 18:26 onward on 2026-09-13 because it had run everything a person
    had written for it. A research loop that stops when its author stops is a script with a
    timer. The proposer reads the results on disk and asks the next question itself - one
    knob at a time, around the current best, and periodically attacking that best instead of
    extending it.
    """
    used = [r.get("id", "") for r in rows]
    n = 1 + sum(1 for i in used if str(i).startswith("A"))
    try:
        nxt = P.propose(P.load_results(), n)
    except Exception as exc:                                    # noqa: BLE001
        log(f"proposer failed: {type(exc).__name__}: {exc}")
        return rows
    if not nxt:
        return rows
    if nxt["id"] in used:
        return rows
    log(f"PROPOSED {nxt['id']} ({nxt.get('kind')}): {nxt['title']}")
    rows.append(nxt)
    write_program(rows)
    return rows


def step() -> bool:
    """One pass. True if an experiment ran, False if the queue was empty."""
    rows = read_program()
    row = pick_queued(rows)
    if row is None:
        rows = refill(rows)
        row = pick_queued(rows)
    if row is None:
        return False

    state = load_state()
    log(f"RUN {row.get('id')}: {row.get('title', '')}")
    row["status"] = "running"
    row["started_at"] = datetime.now(timezone.utc).isoformat()
    write_program(rows)

    try:
        result = run_experiment(row, state)
    except Exception as exc:                                    # noqa: BLE001
        # A crashed experiment is recorded as crashed rather than quietly requeued: a row
        # that fails forever would otherwise hold the front of the queue against every
        # hypothesis behind it.
        log(f"FAILED {row.get('id')}: {type(exc).__name__}: {exc}")
        log(traceback.format_exc(limit=4))
        row["status"] = "failed"
        row["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        record({"id": row.get("id"), "at": datetime.now(timezone.utc).isoformat(),
                "failed": row["error"]})
    else:
        record(result)
        v = result.get("verdict") or {}
        row["status"] = "done"
        row["verdict"] = v
        log(f"DONE {row.get('id')}: best={v.get('best_arm')} "
            f"beats_baseline={v.get('beats_baseline')} "
            f"delta={v.get('rank_delta', 0):+.3f} inert={v.get('inert')}")
    finally:
        state["experiments_run"] = state.get("experiments_run", 0) + 1
        save_state(state)
        row["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_program(rows)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="run one experiment and stop")
    ap.add_argument("--idle", type=int, default=IDLE_SLEEP,
                    help="seconds to wait when the queue is empty")
    args = ap.parse_args(argv)

    log(f"system08 loop starting; trials so far = {load_state()['trials']}")
    while True:
        try:
            ran = step()
        except Exception as exc:                                # noqa: BLE001
            log(f"loop error: {type(exc).__name__}: {exc}")
            ran = False
        if args.once:
            return 0
        if ran:
            # Deliberate pause between experiments. The bottleneck in this project is
            # supposed to be thought, not compute, and a loop that runs flat out spends the
            # significance of every result it will ever produce on trials nobody asked for.
            log(f"pausing {P.PAUSE_BETWEEN_EXPERIMENTS}s before the next experiment")
            time.sleep(P.PAUSE_BETWEEN_EXPERIMENTS)
        else:
            log(f"queue empty; sleeping {args.idle}s")
            time.sleep(args.idle)


if __name__ == "__main__":
    sys.exit(main())
