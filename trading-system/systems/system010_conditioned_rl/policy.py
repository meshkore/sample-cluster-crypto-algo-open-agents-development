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
        nn.init.zeros_(self.pi.bias)

    def forward(self, obs: torch.Tensor, mask: torch.Tensor):
        h = self.body(obs)
        logits = self.pi(h).masked_fill(~mask, -1e9)
        return torch.distributions.Categorical(logits=logits), self.v(h).squeeze(-1)

    @torch.no_grad()
    def act(self, obs: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """The deterministic decision used everywhere a number is reported."""
        dist, _ = self(obs, mask)
        return dist.probs.argmax(dim=-1)
