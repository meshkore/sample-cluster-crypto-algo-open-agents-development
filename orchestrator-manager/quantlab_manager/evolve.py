"""Every Nth iteration, the loop stops researching and reviews itself.

The research loop gets better at trading. Nothing was making it better at being
a loop. Its cadence, its search width, the rate at which it spends the sealed
window, and its own account of what it has learned were all fixed the day they
were written, and the only thing that ever revised them was a person reading
logs on a Tuesday.

An evolve session is one turn where the subject is the loop. It reads what the
loop has actually done -- the digest of every hypothesis, what each advisor
answered or failed to answer, how the search has been spending its time -- and
returns two things:

  * KNOB CHANGES, from the fixed whitelist in `tuning.py`, each range-checked.
  * A MEMORY NOTE: prose for `loop/MEMORY.md`, the durable, human-readable
    account of what has been explored, what worked, what looked promising and
    died, and what should be tried next.

**What it may not do.** Write code. Touch the contract, the lock, the drawdown
mandate, the fold layout, or any parameter of a strategy. Reach a credential.
Its entire output is four bounded numbers and some prose, both validated before
use. This is the line the self-evolving-agent literature settles on -- bound
evolution to text-mutable artifacts, never source -- and it is the same line
`team.py` already draws for the advisors.

**Why the memory note matters as much as the knobs.** `ledger_digest` gives the
proposer arithmetic: counts, verdicts, scores. It cannot say "we tried three
variations of buying dips in a downtrend and all three failed for the same
reason, so the direction is dead rather than the parameters wrong." That
judgement is what a research group's notebook holds and what a fresh proposer
has no way to reconstruct from a table of numbers. MEMORY.md is that notebook,
and it is written by the only participant that has seen every iteration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from . import tuning

EVOLVE_SYSTEM = """You are reviewing an autonomous research loop. Not its
results -- the loop itself. You are the only participant that sees every
iteration at once.

The loop searches for a long-only crypto trading strategy. It fits on folds
ending 2025-12-31 and opens a sealed 2026 window at most once per hypothesis.
2026 is reported and never fed back into selection. That rule is not yours to
change and neither is anything else about the protocol.

You may change exactly two things.

1. The numbered knobs listed in `knobs_you_may_change`, within their stated
   ranges. Propose only knobs you want to MOVE, and say why in `reasoning`.
   Proposing nothing is a good answer when nothing is wrong.

2. `memory_note`: prose appended to the laboratory's research notebook. This is
   where judgement goes that arithmetic cannot carry -- which directions are
   exhausted and why, what a cluster of failures had in common, what looked
   promising and died, what nobody has tried. Write it for a researcher joining
   tomorrow with no memory of any of this. Be specific and cite hypothesis ids.

Return JSON only:

{"knobs": {"<name>": <number>, ...},
 "memory_note": "<markdown, a few paragraphs>",
 "reasoning": "<why these changes, referencing the evidence>",
 "observations": ["<something worth a human's attention>", ...]}

Do not propose code, files, protocol changes, or strategy parameters. Do not
restate the briefing. If the loop is behaving well, return empty knobs and
write the note."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate(answer: Any) -> dict[str, Any] | None:
    """The evolve reply, field by field. Anything unrecognised is dropped.

    Knob names not in the whitelist and values outside their range never reach
    `tuning.apply` -- it would reject them too, but a proposal is easier to
    audit when the thing that recorded it already agreed with the thing that
    applied it.
    """
    if not isinstance(answer, dict):
        return None
    knobs: dict[str, Any] = {}
    raw = answer.get("knobs")
    if isinstance(raw, dict):
        for name, value in raw.items():
            knob = tuning.BY_NAME.get(str(name))
            if knob is None:
                continue
            cleaned = knob.clean(value)
            if cleaned is not None:
                knobs[knob.name] = cleaned
    note = answer.get("memory_note")
    return {
        "knobs": knobs,
        "memory_note": str(note)[:6000] if note else None,
        "reasoning": str(answer.get("reasoning") or "")[:2000],
        "observations": [str(o)[:300] for o in (answer.get("observations") or [])][:8],
    }


def briefing(
    digest: dict[str, Any],
    settings: dict[str, Any],
    history: list[dict[str, Any]],
    advisors: dict[str, Any] | None = None,
) -> str:
    """What the reviewer is shown: how the loop has behaved, not how it is coded.

    Deliberately excludes the source. A reviewer reading `loop.py` would
    propose changes to `loop.py`, which is the one thing it may not have, and
    an advisor that spends its turn wanting something it cannot have is worse
    than one that never saw it.
    """
    return json.dumps(
        {
            "what_you_are_reviewing": (
                "an autonomous research loop's own behaviour over its recorded history"
            ),
            "knobs_you_may_change": tuning.catalogue(),
            "current_settings": settings,
            "memory": digest,
            # How the last stretch actually went: what module, what it scored,
            # how long it took. A loop spending forty minutes an iteration to
            # produce nothing is visible here and nowhere else.
            "recent_iterations": [
                {
                    "iteration": h.get("iteration"),
                    "module": h.get("module"),
                    "fit_score": h.get("fit_score"),
                    "verdict": h.get("verdict"),
                    "seconds": h.get("seconds"),
                }
                for h in history[-25:]
            ],
            "advisor_health": advisors or {},
            "you_may_not_change": [
                "any source file",
                "the 2025-12-31 lock or anything about how 2026 is used",
                "the drawdown mandate",
                "the fold layout",
                "strategy parameters -- that is the loop's job, not yours",
            ],
        },
        default=str,
        indent=2,
    )[:20_000]


def append_memory(path: Path | str, note: str, iteration: int) -> bool:
    """Append to the notebook. Append only, like the ledger and for the reason.

    A self-improving process that can REWRITE its own account of what it
    learned can quietly delete the evidence that it was wrong, and the deletion
    looks exactly like a tidy-up. Growth is the acceptable failure mode here.
    """
    if not note or not note.strip():
        return False
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        header = f"\n\n## Iteration {iteration} · {_now()}\n\n"
        with target.open("a") as handle:
            handle.write(header + note.strip() + "\n")
    except OSError:
        return False
    return True
