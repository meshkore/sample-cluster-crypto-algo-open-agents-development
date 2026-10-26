import numpy as np
import pytest

from system12 import backtest, paper, strategy
from system12.config import HALF_COST


def test_bar_returns_charge_costs_and_funding(market):
    W = np.zeros_like(market.close4)
    W[10:, 0] = 0.5
    r = backtest.bar_returns(market, W)
    c, f = market.close4[:, 0], market.funding4[:, 0]
    entry_cost = 0.5 * (HALF_COST + market.impact[0, 0])
    assert r[10] == pytest.approx(0.5 * (c[11] / c[10] - 1) - entry_cost - 0.5 * f[10])
    assert r[11] == pytest.approx(0.5 * (c[12] / c[11] - 1) - 0.5 * f[11])
    assert r[-1] == 0.0


def test_a_window_starts_flat_and_pays_to_enter(market):
    W = np.full_like(market.close4, 0.5)
    rows = np.arange(100, 200)
    r = backtest.run(market, W, rows)
    assert len(r.equity) == 100
    held = np.zeros_like(W)
    held[rows] = W[rows]
    assert r.ret == pytest.approx(np.prod(1 + backtest.bar_returns(market, held)[rows]) - 1)
    assert 0 <= r.max_dd < 1


def test_paper_state_is_consistent(market, monkeypatch):
    monkeypatch.setitem(paper.SELECTION, "paper", {"start": "2019-06-01T00", "book_usd": 50_000.0})
    W = strategy.target_weights(market)
    s = paper.state(market, W)
    assert s["bars"] == len(s["curve"]) > 0
    assert s["equity_usd"] == pytest.approx(50_000 * (1 + s["ret"]), rel=1e-4)
    assert s["net_exposure"] == pytest.approx(sum(s["target"].values()), abs=1e-3)
