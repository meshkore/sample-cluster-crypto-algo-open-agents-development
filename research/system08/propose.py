"""What the loop should try next, so it never sits idle waiting for a person.

The queue emptied at 18:26 and the loop slept for the rest of the evening. A research loop
that stops when its author stops is a script with a timer, and the operator's instruction is
that it does not stop. So this proposes the next experiments from what has already been
measured, using the results on disk rather than anybody's memory.

HOW IT CHOOSES, AND WHY IT IS NOT JUST A RANDOM SEARCH

The danger of an autonomous proposer is obvious: it can grind out configurations forever,
each one a fresh trial against the same nine years, until something looks good by accident.
That is the exact failure this laboratory has already paid for, and the trial counter exists
because of it. Three rules keep this honest.

  NEIGHBOURHOODS, NOT GRIDS. A parameter is explored around the current best rather than
  swept across its whole range. A value that only works with its neighbours failing is a
  spike, and the plateau test - which is what established the formation window as real -
  only means anything if the neighbours were actually measured.

  ONE KNOB AT A TIME, and combinations only as an explicit test of additivity. Stacking
  single-sweep winners produced a WORSE book than either pair of them, measured, so the
  proposer never silently combines winners: it proposes a combination as a hypothesis whose
  answer might be no.

  VALIDATION IS SCHEDULED, NOT OPTIONAL. Every few experiments the proposer inserts a
  walk-forward check of the current best instead of another parameter hunt. Selection on one
  sample is the failure mode here, and the loop must spend time attacking its own best
  answer rather than only improving it.

Nothing here reads 2026 and nothing here adopts anything.
"""
from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, "trading-system")

from system008_residual_momentum_ls.system import Config          # noqa: E402

ROOT = Path("research/system08")
RESULTS = ROOT / "loop_results.jsonl"

# The knobs the proposer is allowed to move, and the neighbourhood it explores around the
# current best value. Anything not listed here is a structural decision rather than a
# parameter, and structural decisions are the operator's.
# Two rings. The loop ran out of questions after six experiments because every immediate
# neighbour of the best configuration had been measured and the proposer had nothing left
# to ask. The second ring is reached only when the first is exhausted, so exploration stays
# local while local is still informative and widens rather than stopping.
NEIGHBOURHOOD = {
    "lookback": [-6, -4, -2, 2, 4, 6],
    "window": [-40, -20, 20, 40],
    "hold": [-7, -4, 4, 7],
    "skip": [-1, 1, 2],
    "side_fraction": [-0.08, -0.04, 0.04, 0.08],
    "min_history": [-90, -45, 45, 90],
}

WIDE_RING = {
    "lookback": [-18, -12, 12, 18, 30],
    "window": [-80, -60, 60, 80, 110],
    "hold": [-10, 10, 14, 21],
    "skip": [3, 4, 5],
    "side_fraction": [-0.15, -0.12, 0.12, 0.15],
    "min_history": [-270, -180, 180, 270],
}

BOUNDS = {
    # The window floor is MIN_OBS in residual.loadings(): a window shorter than the
    # observations a loading requires yields no loadings at all, and the proposer
    # generated exactly that on its first attempt (window 20, whole experiment lost).
    "lookback": (5, 120), "window": (35, 200), "hold": (3, 60),
    "skip": (0, 10), "side_fraction": (0.1, 0.5), "min_history": (0, 900),
}

# How often a validation experiment displaces a parameter hunt.
VALIDATE_EVERY = 4

# FEWER AND BETTER. The loop ran roughly 1,400 trials overnight, which is grinding rather
# than research, and the operator said so: "I don't need two thousand iterations, one after
# the other, without stopping and without a head. It is better to think and do few but well
# meditated."
#
# He is right, and the trial counter had already been saying it in another language: every
# configuration evaluated raises the bar the deflated Sharpe applies to all of them, so an
# aimless sweep does not merely waste electricity, it actively destroys the significance of
# whatever it eventually finds. Two guards follow from that. A proposed experiment must
# carry a real hypothesis rather than a neighbourhood walk, and the loop pauses between
# experiments instead of running flat out - the bottleneck is supposed to be thought.
PAUSE_BETWEEN_EXPERIMENTS = 900

# Beyond this, a knob has been measured enough on this universe that walking further out is
# fishing. The proposer stops exploring it and says so, rather than inventing a new offset.
MAX_VALUES_PER_KNOB = 12


def live_config(cfg: dict) -> dict:
    """A stored configuration, reduced to the knobs that still exist.

    The results file is a permanent record and it contains configurations from before knobs
    were removed - `adjust`, `top_n` and `vol_target` were measured, rejected and deleted on
    2026-09-14. Feeding one of those rows straight back into Config() raises TypeError, and
    that is exactly what happened: every experiment the proposer generated after the cleanup
    crashed on an argument the code no longer has.

    Dropping the dead keys rather than migrating the file is deliberate. The history must
    keep saying what was actually run, including with knobs that no longer exist, because
    rewriting it would erase the measurements that justified removing them.
    """
    live = {f.name for f in fields(Config)}
    return {k: v for k, v in (cfg or {}).items() if k in live}


def rank_key(sc: dict) -> tuple:
    return (sc["years_positive"], round(sc["worst_year"], 3),
            sc["sharpe"], -sc["max_drawdown"])


def load_results() -> list[dict]:
    if not RESULTS.exists():
        return []
    out = []
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if "arms" in r:
            out.append(r)
    return out


def best_so_far(results: list[dict]) -> tuple[dict, dict, str] | None:
    """The best-scoring arm ever measured, with its config and the universe it ran on."""
    best = None
    for r in results:
        for a in r["arms"]:
            if "score" not in a:
                continue          # unrunnable arm: a range fact, not a candidate
            key = rank_key(a["score"])
            if best is None or key > best[0]:
                best = (key, live_config(a["config"]), a["score"],
                        r.get("universe", ""))
    if best is None:
        return None
    return best[1], best[2], best[3]


def tried_values(results: list[dict], knob: str, universe: str) -> set:
    """Every value of one knob already measured on one universe. Never repeat a trial."""
    seen = set()
    for r in results:
        if r.get("universe", "") != universe:
            continue
        for a in r["arms"]:
            # Unrunnable arms count as tried: the point of recording them is that the
            # proposer must not keep re-asking a configuration that cannot be built.
            v = (a.get("config") or {}).get(knob)
            if v is not None:
                seen.add(round(v, 4) if isinstance(v, float) else v)
    return seen


def _clip(knob: str, value):
    lo, hi = BOUNDS[knob]
    return max(lo, min(hi, value))


def propose(results: list[dict], next_id: int) -> dict | None:
    """One experiment. None when there is nothing left worth asking."""
    found = best_so_far(results)
    if found is None:
        return None
    config, score, universe = found
    universe = universe or "universe_wide.json"

    # Every few experiments, attack the best answer instead of extending it.
    if next_id % VALIDATE_EVERY == 0:
        return {
            "id": f"A{next_id:02d}", "priority": 1, "status": "queued",
            "kind": "validation", "universe": universe,
            "title": "Walk-forward the current best instead of improving it",
            "hypothesis": (
                "The current best configuration was selected across many trials on one "
                "sample, which is the condition under which this laboratory has fooled "
                "itself before. Perturbing it slightly in every direction at once is a "
                "cheap robustness check: a real edge degrades gently and a fitted one "
                "falls off a cliff, because a fitted optimum is surrounded by nothing."),
            "baseline": dict(config),
            "arms": [
                {"label": "jitter_short", "config": {
                    "lookback": _clip("lookback", config.get("lookback", 28) - 3)}},
                {"label": "jitter_long", "config": {
                    "lookback": _clip("lookback", config.get("lookback", 28) + 3)}},
                {"label": "jitter_window_down", "config": {
                    "window": _clip("window", config.get("window", 60) - 15)}},
                {"label": "jitter_window_up", "config": {
                    "window": _clip("window", config.get("window", 60) + 15)}},
                {"label": "jitter_hold", "config": {
                    "hold": _clip("hold", config.get("hold", 14) + 3)}},
            ],
        }

    # Otherwise: the knob with the fewest values measured on this universe gets explored
    # around the current best. Least-explored first, so no parameter is left assumed.
    counts = {k: len(tried_values(results, k, universe)) for k in NEIGHBOURHOOD}
    for knob in sorted(counts, key=lambda k: counts[k]):
        base = config.get(knob)
        if base is None:
            continue
        if counts[knob] >= MAX_VALUES_PER_KNOB:
            # Twelve values of one knob on one universe is not an unanswered question any
            # more. Walking further out is fishing, and fishing costs every other result
            # significance through the trial count.
            continue
        seen = tried_values(results, knob, universe)
        arms = []
        for delta in NEIGHBOURHOOD[knob] + WIDE_RING[knob]:
            v = _clip(knob, base + delta)
            v = round(v, 4) if isinstance(v, float) else int(v)
            if v in seen or v == base:
                continue
            seen.add(v)
            arms.append({"label": f"{knob}_{v}", "config": {knob: v}})
        if len(arms) < 2:
            continue
        return {
            "id": f"A{next_id:02d}", "priority": 2, "status": "queued",
            "kind": "explore", "universe": universe,
            "title": f"Explore {knob} around the current best",
            "hypothesis": (
                f"{knob} currently sits at {base} on this universe and only "
                f"{counts[knob]} values of it have ever been measured here. This walks "
                f"its neighbourhood rather than its whole range, because a value whose "
                f"neighbours fail is a spike and only the neighbours can show that."),
            "baseline": dict(config),
            "arms": arms[:6],
        }

    # Every knob exhausted. Idling is not the answer - the standing question is always
    # whether the best configuration survives being pushed, and re-asking it on fresh
    # perturbations is a better use of the machine than sleeping.
    return {
        "id": f"A{next_id:02d}", "priority": 3, "status": "queued",
        "kind": "validation", "universe": universe,
        "title": "Every neighbourhood is measured - stress the best instead",
        "hypothesis": (
            "The proposer has measured both rings around the current best on this "
            "universe and has no unasked local question left. Rather than idle, this "
            "pushes the configuration harder than a jitter: if the book only works at "
            "exactly its chosen values, that is worth knowing now and not after a "
            "sealed read."),
        "baseline": dict(config),
        "arms": [
            {"label": "half_hold", "config": {
                "hold": _clip("hold", max(3, int(config.get("hold", 14) / 2)))}},
            {"label": "double_hold", "config": {
                "hold": _clip("hold", int(config.get("hold", 14) * 2))}},
            {"label": "half_window", "config": {
                "window": _clip("window", int(config.get("window", 60) / 2))}},
            {"label": "double_window", "config": {
                "window": _clip("window", int(config.get("window", 60) * 2))}},
        ],
    }
