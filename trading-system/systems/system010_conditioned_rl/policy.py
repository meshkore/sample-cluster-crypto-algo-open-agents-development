"""pi(a | s): a small actor-critic, two actions, masked.

Small on purpose. The laboratory's record on added capacity and levers is explicit - the seed
alone moves 06's consistency score by up to 0.21 (P54), more than most effects measured here
- and the operator asked for the simplest thing that can work. Two hidden layers of 128, one
head for the two actions (be flat / be long), one for the value.
"""

from __future__ import annotations

import torch
from torch import nn


class Policy(nn.Module):
    def __init__(self, obs_dim: int, hidden: int = 128):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(obs_dim, hidden), nn.Tanh(),
                                  nn.Linear(hidden, hidden), nn.Tanh())
        self.pi = nn.Linear(hidden, 2)
        self.v = nn.Linear(hidden, 1)
        nn.init.zeros_(self.pi.weight)
        # keep / switch: start at about a 5% chance of switching per bar (see env.py)
        with torch.no_grad():
            self.pi.bias.copy_(torch.tensor([0.0, -3.0]))

    def forward(self, obs: torch.Tensor, mask: torch.Tensor):
        h = self.body(obs)
        logits = self.pi(h).masked_fill(~mask, -1e9)
        return torch.distributions.Categorical(logits=logits), self.v(h).squeeze(-1)

    @torch.no_grad()
    def act(self, obs: torch.Tensor, mask: torch.Tensor,
            generator: torch.Generator | None = None) -> torch.Tensor:
        """The decision used everywhere a number is reported: SAMPLED, from a fixed seed.

        Not argmax. With keep/switch the switch probability on a given bar is small even
        when the policy means to trade - it acts on a hazard, not a verdict - so argmax
        says "keep" forever and the first reading of this design showed zero trades from
        a policy that was 10% of the time in the market. A seeded sample is the policy as
        it actually behaves, and the same seed gives the same reading.
        """
        dist, _ = self(obs, mask)
        return torch.multinomial(dist.probs, 1, generator=generator).squeeze(-1)
