"""The working process, as a gate a candidate has to walk through rather than a habit.

System 06 did not lose three sealed readings because anyone was careless. It lost them
because the method lived in prose - in a CLAUDE.md line, in a memory file, in the good
intentions of whoever was at the keyboard - and prose does not stop you at 3am on the
day a result looks wonderful. So here the method is code, the stages are ordered, and a
candidate that has not cleared stage N cannot be presented at stage N+1.

    STAGE 1  FRAME      a hypothesis in one sentence, and the kill criterion that would
                        refute it, both written BEFORE any number exists.
    STAGE 2  MEASURE    research years only. 2026 is not opened, not for shape, not for
                        a sanity check, not once.
    STAGE 3  EXAM 1     a walk-forward net that never saw the exam year. Lose and stop.
    STAGE 4  EXAM 2     a DIFFERENT training cutoff. 2-of-2 or stop. Four candidates in
                        system 06 won exam 1 and lost exam 2; one exam year is a coin flip.
    STAGE 5  POWER      the per-year ratio spread against the incumbent, across every
                        walk-forward net-year available. IF THAT SPREAD STRADDLES 1.0 THE
                        SEALED YEAR CANNOT SETTLE IT and the reading is not spent. All
                        three of system 06's sealed losses failed exactly here, and
                        nobody noticed because nobody computed it.
    STAGE 6  SEALED     one reading, recorded whatever it says, in the ledger.
    STAGE 7  WRITE UP   a row in docs/SUMMARY.md - "what helped" or "what hurt" - in the
                        same commit as the result. A minute now, an afternoon of
                        archaeology later.

WHY A CANDIDATE CANNOT SKIP AHEAD. `Candidate.advance()` refuses a stage whose
predecessor has not been recorded as passed, and `may_open_sealed_window()` is the only
door to 2026 and answers False unless stages 3, 4 and 5 all hold. There is no override
argument. If a future operator genuinely needs one, they can write it and the diff will
say what they did.

Nothing in this file runs a backtest. It is the referee, not the player: the system it
belongs to has no hypothesis yet, and the referee is ready first on purpose.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import INCUMBENT_SEALED_2026, SYSTEM_ID

STAGES = ("frame", "measure", "exam1", "exam2", "power", "sealed", "writeup")

# A spread that straddles 1.0 means the candidate beats the incumbent in some years and
# loses in others, so one sealed year is a draw from a distribution rather than a verdict.
# The margin is what the ratio's LOW end must clear: strictly above 1.0 would be the pure
# rule, and a hair above it is the same rule with room for arithmetic noise.
POWER_FLOOR = 1.0
LEDGER = Path("research") / SYSTEM_ID / "rnd" / "sealed_readouts.jsonl"


@dataclass
class Candidate:
    """One idea, walking the gate. Every stage it clears is recorded with its evidence."""

    name: str
    hypothesis: str = ""
    kill_criterion: str = ""
    passed: dict[str, dict] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # -- the gate ---------------------------------------------------------------------

    def advance(self, stage: str, evidence: dict) -> None:
        """Record a stage as cleared. Refuses to skip, and refuses to re-write history."""
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")
        index = STAGES.index(stage)
        if index and STAGES[index - 1] not in self.passed:
            raise RuntimeError(
                f"{self.name}: cannot reach {stage!r} - {STAGES[index - 1]!r} has not "
                f"been cleared. The order is the method; skipping it is how three "
                f"sealed readings were lost.")
        if stage in self.passed:
            raise RuntimeError(
                f"{self.name}: {stage!r} is already recorded. A stage is cleared once; "
                f"re-running it until it passes is selection, not measurement.")
        if stage == "frame" and not (self.hypothesis and self.kill_criterion):
            raise ValueError(
                "a hypothesis AND the kill criterion that would refute it, both before "
                "any number exists. A criterion written after the numbers is a story.")
        self.passed[stage] = {"at": datetime.now(timezone.utc).isoformat(), **evidence}

    def may_open_sealed_window(self) -> tuple[bool, str]:
        """The only door to 2026. Says why, so a refusal is actionable."""
        for stage, why in (
            ("exam1", "no walk-forward exam has been passed"),
            ("exam2", "one exam is a coin flip; four system 06 candidates won exam 1 "
                      "and lost exam 2"),
            ("power", "the edge has not been priced; an edge whose year-to-year spread "
                      "straddles 1.0 cannot be settled by one year"),
        ):
            if stage not in self.passed:
                return False, f"{self.name}: {why}"
        if not self.passed["power"].get("decisive"):
            return False, (f"{self.name}: the power check ran and said the spread "
                           f"straddles {POWER_FLOOR}; the reading would settle nothing")
        return True, f"{self.name}: cleared exams 1 and 2 and priced its edge"


# -- stage 5, the one that was missing ------------------------------------------------

def price_the_edge(ratios: list[float]) -> dict:
    """Is this edge large enough for one year to settle it?

    `ratios` are per-year growth multiples against the incumbent - (1 + candidate) /
    (1 + incumbent) for each walk-forward net-year available. Ratios of (1+r), never
    differences of percentages: a year going +8.7% to +32.8% multiplied the account by
    1.22, and calling that "+24 points" makes a bad year look like a good one's equal.

    DECISIVE means the WORST observed year still beats the incumbent. That is a hard bar
    and it is meant to be: min_hold 32 had a median of 1.02x, won 71% of years, and lost
    the sealed one - because a 71% coin is a coin.
    """
    clean = [float(r) for r in ratios if r == r]
    if len(clean) < 4:
        return {"decisive": False, "n": len(clean),
                "why": "fewer than four net-years; a spread cannot be estimated from three"}
    ordered = sorted(clean)
    q = statistics.quantiles(ordered, n=4)
    out = {
        "n": len(ordered), "min": ordered[0], "q1": q[0],
        "median": statistics.median(ordered), "q3": q[2], "max": ordered[-1],
        "share_above_1": sum(1 for v in ordered if v > POWER_FLOOR) / len(ordered),
    }
    out["decisive"] = out["min"] > POWER_FLOOR
    out["why"] = ("every measured year beats the incumbent" if out["decisive"] else
                  f"the spread runs {out['min']:.2f}x to {out['max']:.2f}x and straddles "
                  f"{POWER_FLOOR}; one sealed year is a draw from that, not a verdict")
    return out


def record_sealed(candidate: Candidate, sealed_return: float, detail: dict,
                  ledger: Path = LEDGER) -> dict:
    """Append the reading to the ledger. A loss is written with the same keystrokes."""
    ok, why = candidate.may_open_sealed_window()
    if not ok:
        raise RuntimeError(f"refusing to record a sealed reading: {why}")
    row = {
        "system": SYSTEM_ID, "candidate": candidate.name,
        "at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": candidate.hypothesis, "kill_criterion": candidate.kill_criterion,
        "earned_by": {k: v for k, v in candidate.passed.items()
                      if k in ("exam1", "exam2", "power")},
        "sealed_2026": sealed_return,
        "incumbent_sealed_2026": INCUMBENT_SEALED_2026,
        "beat_incumbent": bool(sealed_return > INCUMBENT_SEALED_2026),
        "detail": detail,
    }
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row
