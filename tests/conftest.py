"""A synthetic BTC/ETH market on the real grid conventions, so no test touches the network."""

from __future__ import annotations

import numpy as np
import pytest

from system12.config import BAR_NS
from system12.market import Market, impact_table, year_of


def make_market(days: int = 900, seed: int = 0, crash_from: int | None = None) -> Market:
    rng = np.random.default_rng(seed)
    bars = days * 6
    r = rng.normal(0.0004, 0.02, (bars, 2))
    if crash_from is not None:
        r[crash_from:] = rng.normal(-0.01, 0.05, (bars - crash_from, 2))
    close4 = 10_000 * np.exp(np.cumsum(r, axis=0))
    t0 = np.datetime64("2018-01-01", "ns").astype(np.int64)
    grid4 = t0 + BAR_NS["4h"] * np.arange(1, bars + 1)
    grid1 = t0 + BAR_NS["1d"] * np.arange(1, days + 1)
    usd4 = np.full_like(close4, 1e8)
    prev = np.r_[grid4[0], grid4[:-1]]
    return Market(
        coins=("BTC", "ETH"),
        grid4=grid4,
        close4=close4,
        usd4=usd4,
        grid1=grid1,
        close1=close4[5::6],
        funding4=np.full_like(close4, 0.0001 / 2),
        perp4=np.ones_like(close4, dtype=bool),
        day_of_bar=np.searchsorted(grid1, prev, side="right") - 1,
        impact=impact_table(close4, usd4, year_of(grid4)),
    )


@pytest.fixture
def market() -> Market:
    return make_market(seed=2)
