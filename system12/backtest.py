"""The backtest engine: net returns of target weights, equity over any window, and yearly statistics.

Execution model: weights decided at the close of bar t earn bar t -> t+1. Each change of weight pays 0.10% per side
plus square-root impact; funding is paid on longs and received on shorts every bar.

    python -m system12.backtest     # yearly table of the frozen system on all history (in-sample before 2026)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import market, strategy
from .config import FIRST_YEAR, HALF_COST
from .market import Market


def bar_returns(m: Market, W: np.ndarray) -> np.ndarray:
    """Net return of each 4h bar. The last bar's outcome is not known yet and reads 0."""
    c = m.close4
    moves = np.zeros_like(c)
    moves[:-1] = np.nan_to_num(c[1:] / c[:-1] - 1)
    W = np.where(np.isfinite(c), W, 0.0)
    traded = np.abs(np.diff(np.r_[np.zeros((1, W.shape[1])), W], axis=0))
    years = np.clip(m.year4 - FIRST_YEAR, 0, m.impact.shape[0] - 1)
    cost = (traded * (HALF_COST + m.impact[years])).sum(axis=1)
    r = (W * moves).sum(axis=1) - cost - (W * m.funding4).sum(axis=1)
    r[-1] = 0.0
    return r


@dataclass
class Run:
    rows: np.ndarray  # 4h bar indices inside the window
    equity: np.ndarray  # growth of 1 over the window

    @property
    def ret(self) -> float:
        return float(self.equity[-1] - 1) if len(self.equity) else 0.0

    @property
    def max_dd(self) -> float:
        return float((1 - self.equity / np.maximum.accumulate(self.equity)).max()) if len(self.equity) else 0.0


def run(m: Market, W: np.ndarray, rows: np.ndarray) -> Run:
    """Trade W only on `rows`, starting flat: the first bar pays the cost of entering."""
    held = np.zeros_like(W)
    held[rows] = W[rows]
    return Run(rows, np.cumprod(1 + bar_returns(m, held)[rows]))


def yearly(m: Market, W: np.ndarray, years) -> dict[int, Run]:
    """Each year from the same capital, starting flat."""
    return {y: run(m, W, np.flatnonzero(m.year4 == y)) for y in years if (m.year4 == y).any()}


def btc_yearly(m: Market, years) -> dict[int, float]:
    c, yr = m.close4[:, 0], m.year4
    out = {}
    for y in years:
        cur, prev = np.flatnonzero((yr == y) & np.isfinite(c)), np.flatnonzero((yr == y - 1) & np.isfinite(c))
        if len(cur) and len(prev):
            out[y] = float(c[cur[-1]] / c[prev[-1]] - 1)
    return out


def main() -> int:
    m = market.load()
    years = sorted(set(m.year4.tolist()) - {FIRST_YEAR})
    runs, btc = yearly(m, strategy.target_weights(m), years), btc_yearly(m, years)
    print("year   System 12   max DD     BTC   (frozen selection; in-sample before 2026, see docs/RESULTS.md)")
    for y, r in runs.items():
        print(f"{y}   {r.ret:+9.1%}   {r.max_dd:6.1%}   {btc.get(y, np.nan):+6.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
