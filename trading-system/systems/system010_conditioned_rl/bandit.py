"""S10-8b: one decision per trade - which opportunities inside the region to take.

Why, after S10-8a: a policy deciding every 15 minutes sees a reward that is noise around the
0.30% toll, and it learned only that trading costs money (churn, then silence, no profitable
checkpoint). The operator asked for the simplest thing that can work, trained and executed
only inside the conditions. So the decision is moved to where it matters:

    at every bar inside R, for a flat symbol:  TAKE the trade, or SKIP it
    a taken trade leaves by the book's causal exit - 06's stop, its trailing stop, or 384
    bars (four days) - the same model-free exit S10-6 measured the region with

That is a contextual bandit: one action, one outcome, no credit assignment across bars. Every
opportunity's outcome is known from the tape, so the learner is fitted on all of them at once
- a small MLP predicting the operator's criterion per trade, net return after costs minus
lambda times the trade's worst excursion - and it takes the trades it scores above a bar.

The bar is the one knob, and it is set on the selection year by the operator's two rules:
the book must actually trade (at least MIN_TRADES a year), and among the bars that satisfy
that, the one with the best Q. Then it is read on a year it was not chosen on.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

HORIZON = 384
ROUND_TRIP = 0.003


def outcomes(close: np.ndarray, starts: np.ndarray, stop: float, trail: float,
             horizon: int = HORIZON, chunk: int = 20_000) -> tuple[np.ndarray, np.ndarray]:
    """Net return and worst excursion of a trade opened at each `starts` bar.

    Vectorised over windows: the path of each trade is close[s : s + horizon + 1], the stop
    and the trail are found as the first bar that breaches them, and the trade closes there
    or at the horizon. Excursion is the deepest fall below the entry while the trade is open.
    """
    n = len(close)
    net = np.full(len(starts), np.nan)
    mae = np.full(len(starts), np.nan)
    for a in range(0, len(starts), chunk):
        s = starts[a:a + chunk]
        idx = s[:, None] + np.arange(horizon + 1)[None, :]
        valid = idx < n
        path = close[np.minimum(idx, n - 1)]
        path = np.where(valid, path, np.nan)
        entry = path[:, :1]
        rel = path / entry
        peak = np.fmax.accumulate(np.nan_to_num(path, nan=-np.inf), axis=1)
        hit = np.zeros_like(valid)
        if stop:
            hit |= rel <= 1 - stop
        if trail:
            hit |= path <= peak * (1 - trail)
        hit[:, 0] = False
        last = np.where(valid.any(axis=1), valid.sum(axis=1) - 1, 0)
        first = np.where(hit.any(axis=1), hit.argmax(axis=1), last)
        exit_rel = rel[np.arange(len(s)), first]
        net[a:a + chunk] = exit_rel - 1 - ROUND_TRIP
        span = np.arange(horizon + 1)[None, :] <= first[:, None]
        mae[a:a + chunk] = 1 - np.nanmin(np.where(span, rel, np.inf), axis=1)
    return net, np.clip(mae, 0, None)


class Scorer(nn.Module):
    def __init__(self, dim: int, hidden: int = 128):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(dim, hidden), nn.GELU(), nn.Dropout(0.1),
                                 nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(0.1),
                                 nn.Linear(hidden, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


def fit(x: np.ndarray, y: np.ndarray, seed: int, device: str, epochs: int = 8,
        batch: int = 8192, lr: float = 1e-3) -> Scorer:
    """Regress the per-trade criterion on the opportunity's features (Huber, it is fat-tailed)."""
    torch.manual_seed(seed)
    xt = torch.tensor(x, dtype=torch.float32, device=device)
    yt = torch.tensor(y, dtype=torch.float32, device=device)
    model = Scorer(x.shape[1]).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.HuberLoss(delta=0.05)
    gen = torch.Generator(device=device).manual_seed(seed)
    for _ in range(epochs):
        perm = torch.randperm(len(xt), generator=gen, device=device)
        model.train()
        for i in range(0, len(xt), batch):
            j = perm[i:i + batch]
            loss = loss_fn(model(xt[j]), yt[j])
            opt.zero_grad()
            loss.backward()
            opt.step()
    model.eval()
    return model


@torch.no_grad()
def score(model: Scorer, x: np.ndarray, device: str) -> np.ndarray:
    out = []
    for i in range(0, len(x), 65_536):
        out.append(model(torch.tensor(x[i:i + 65_536], dtype=torch.float32, device=device)).cpu().numpy())
    return np.concatenate(out) if out else np.zeros(0)
