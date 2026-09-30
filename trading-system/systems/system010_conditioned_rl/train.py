"""Walk-forward training: clone, then offline RL, then PPO. Task S10-8 fills this in.

    for N in validation years:
        fit the region on years <= N-1          (region.py)
        fit the policy on years <= N-1          (policy.py)
        score on year N                         (env.py + autoloop._consistency + quality.Q)

Four seeds, the spread reported, selection on validation years and never on 2026. "Continuous
learning" in this laboratory means exactly this loop rescheduled - retrain on closed years and
promote through the live engine swap - never an online update on live prices, because 2026 is
a sealed window and a reading is spent, not repeated.

Compute discipline (`research/system06/RESOURCE_POLICY.md`): ONE heavy training on the card
at a time. This trainer takes the GPU lane by braking 06's genome search and releases it
afterwards; three concurrent trainings cost P22 a MemoryError on a 32 GB box and stretched an
epoch past fifteen minutes. The live trader and the publisher are never stopped for a
training - the book has to be managed while the laboratory works.

Every finished arm appends one line to `research/system10/rnd/program_progress.jsonl` in the
same shape as 06's tape, so the operator's one-line figures need no new plumbing.
"""

from __future__ import annotations

_TODO = (
    "S10-8 implements the trainer. It does not start until the operator has agreed the "
    "S10-3 design dossier."
)


def walk_forward(years, seeds=(77101, 77102, 91002, 51015), step: str = "clone"):
    """`step` is one of clone | offline | ppo | ensemble, each gated on the previous one."""
    raise NotImplementedError(_TODO)
