"""The environment the policy acts in. Task S10-7 fills this in.

**It calls the frozen backtester's accounting; it never re-implements it.** That is the one
non-negotiable property of this file. A reinforcement learner optimises whatever it is
actually rewarded for, so an environment that charges its own costs or keeps its own book
teaches the policy to exploit the difference between itself and the instrument - and the
difference only shows up when the policy is run for real. The golden test in S10-7 exists
for exactly this: replay system 06's champion decisions through this environment and the
equity curve must equal `launch.per_year`'s to the cent. A mismatch is a bug here, never a
tolerance to widen.

Shape:

    reset(year, seed)  -> state      one calendar year, a fresh $100,000 account
    step(action)       -> state, reward, done, info

    action in {abstain, enter half, enter full, hold, exit}     long-only, three slots
    state  = 06's causal feature window + BOOK state + the region's regime id

**Book state is what makes this reinforcement learning rather than classification.** The
same market bar is a different decision when the book is full, when the position is already
under water, or when the account is near its drawdown ceiling - and 06's net sees none of
that. It is also the measured reason 06 cannot harvest its own per-entry edge: P59 found a
four-day hold worth +2.07% a trade against the shipped rule's +0.44%, and the same hold
scored -0.5252 in the book, because three slots cannot hold four days of positions and keep
taking new ones. A policy that sees the slots can make that trade-off; a classifier cannot.

Reward, per the design's section 4:

    per bar   d(log equity) - lambda * d(drawdown from the year's peak) - costs charged
    terminal  Q = sign(r) * r^2 / max(drawdown, 0.02)        the operator's criterion

Costs are the laboratory's: 10 bps commission, 5 bps slippage each way, next-bar-open fills,
square-root market impact. Never weakened to make learning easier - an easier environment is
a policy trained for a market that does not exist.

Outside the region the policy is not consulted: open positions are managed by 06's shipped
exit rule and the clock advances. That asymmetry is deliberate. The region is a claim about
where the *entry* edge lives, and abandoning a position because the regime left the region
would be a second, untested claim.
"""

from __future__ import annotations

_TODO = (
    "S10-7 implements the environment. It must pass the golden test against "
    "launch.per_year before any training runs against it."
)

ACTIONS = ("abstain", "enter_half", "enter_full", "hold", "exit")


class YearEnv:
    """One calendar year, a fresh $100,000 account, the backtester's own accounting."""

    def __init__(self, year: int, seed: int, region=None, lambda_drawdown: float = 1.0):
        raise NotImplementedError(_TODO)

    def reset(self):
        raise NotImplementedError(_TODO)

    def step(self, action: str):
        raise NotImplementedError(_TODO)
