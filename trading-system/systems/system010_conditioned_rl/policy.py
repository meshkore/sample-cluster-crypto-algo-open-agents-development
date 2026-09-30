"""pi(a | s): the policy and its action head. Task S10-8 fills this in.

The action space is small on purpose - `{abstain, enter half, enter full, hold, exit}`,
long-only - and that is a choice against variance, not a simplification. This laboratory's
record on added levers is explicit: nine of thirty-three of system 06's levers are set and
the rest never earned their place, a 96-trial search over eleven levers turned out to be
carried by two numbers (P58), and the seed alone moves the consistency score by up to 0.21
(P54) - which is larger than most effects anyone here has tried to measure. A large action
space in that environment buys variance, not expressiveness.

The training order is fixed by the design and each step is a gate, not a stage:

1. **Behaviour cloning** of system 06's conviction, mapped to the action set inside R. This
   is free - the net is already trained - and it is the baseline everything else must beat
   *on validation years*. If nothing beats it, the honest outcome of this system is "06's
   decision rule is the best policy we could find", written down as such.
2. **Offline RL** (CQL or IQL; S10-3's dossier picks, with a citation) on transitions
   replayed from the environment. Offline comes first because the market is ONE trajectory:
   an on-policy learner exploring a single price history memorises it, which is the failure
   that killed six systems here, and conservative offline methods are built to stay near the
   data they were given.
3. **PPO**, warm-started from step 2, and only if step 2 passed its gate on two validation
   years.
4. **An action-vote ensemble**, and only if the seed spread is wider than the edge. It votes
   over ACTIONS, never averaging probabilities - A43 and P22 both lost by averaging the
   probabilities of identically-trained nets (bag of 3: -0.1587), because the average pulls
   convictions off the extremes this book trades on.

Every run reports four seeds and the spread. A mean over seeds, without the spread beside
it, is not a result in this laboratory.
"""

from __future__ import annotations

_TODO = (
    "S10-8 implements the policy. The behaviour-cloning baseline is scored FIRST and is "
    "what every later step is measured against."
)


class Policy:
    """The action head over 06's feature window plus the book state."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(_TODO)

    def act(self, state):
        raise NotImplementedError(_TODO)


def clone_of_champion(*args, **kwargs):
    """The baseline: 06's conviction mapped to the action set inside R."""
    raise NotImplementedError(_TODO)
