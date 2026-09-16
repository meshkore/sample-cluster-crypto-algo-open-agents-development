"""The trade ledger: what was possible, what we did, and whether the two reconcile.

The operator's complaint that produced this file: iteration after iteration the yearly
numbers swing wildly and nothing explains WHY, so improvement is indistinguishable from
random search. A ledger is only worth having if it partitions the year exactly - every
leg either captured or missed, every trade either won, lost or unforced - because a row
that can fall through the cracks is a place where a real problem can hide.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from system006_oracle_net_15m import attribution


class _Bar:
    __slots__ = ("timestamp", "open", "high", "low", "close", "volume")

    def __init__(self, ts, o, h, l, c, v):
        self.timestamp, self.open, self.high, self.low, self.close, self.volume = ts, o, h, l, c, v


def _bars_from(close, t0=datetime(2021, 1, 1, tzinfo=timezone.utc)):
    out = []
    for i, c in enumerate(close):
        o = float(close[i - 1]) if i else float(c)
        out.append(_Bar(t0 + timedelta(minutes=15 * i), o, max(o, float(c)) * 1.001,
                        min(o, float(c)) * 0.999, float(c), 100.0))
    return out


def _sawtooth(legs=3, up=0.20, down=0.10, span=40):
    """A price path with unmistakable up-legs, so the opportunity set is known a priori."""
    close = [100.0]
    for _ in range(legs):
        for _ in range(span):
            close.append(close[-1] * (1 + up / span))
        for _ in range(span):
            close.append(close[-1] * (1 - down / span))
    return np.array(close)


def test_only_legs_that_survive_a_round_trip_count_as_opportunities():
    """A 'possible' trade that cannot pay its own costs was never possible. The book is
    charged 30 bps a round trip, so the opportunity set must be charged it too - an
    opportunity table built on gross moves would indict the model for declining trades
    that lose money."""
    opps = attribution.opportunities(_bars_from(_sawtooth()), threshold=0.03, symbol="X")
    assert opps, "a 20% up-leg repeated three times must register as opportunity"
    assert all(o.net == pytest.approx(o.gross - attribution.ROUND_TRIP) for o in opps)
    assert all(o.net > 0 for o in opps)

    # Legs below the cost floor are not opportunities at all.
    tiny = attribution.opportunities(_bars_from(_sawtooth(up=0.031, down=0.031, span=10)),
                                     threshold=0.03, cost=0.40, symbol="X")
    assert tiny == []


def test_the_ledger_partitions_the_year_with_nothing_falling_through():
    """Every leg is captured or missed; every trade won, lost or unforced. If a row can
    escape both partitions the table stops being a reconciliation and becomes a summary,
    which is the thing it exists to replace."""
    bars = _bars_from(_sawtooth())
    opps = attribution.opportunities(bars, threshold=0.03, symbol="X")
    entry = opps[0]
    trips = [
        # inside the first leg and profitable -> won
        {"symbol": "X", "opened": str(np.datetime64(entry.start_ns, "ns")),
         "closed": str(np.datetime64(entry.end_ns, "ns")), "net_pct": 0.11},
        # a trade at a moment no leg covers -> unforced, and it never consumes a leg
        {"symbol": "X", "opened": str(np.datetime64(entry.start_ns - 10**12, "ns")),
         "closed": str(np.datetime64(entry.start_ns, "ns")), "net_pct": -0.02},
    ]
    rows = attribution.reconcile(opps, trips)
    kinds = [r.kind for r in rows]
    assert kinds.count("won") == 1
    assert kinds.count("unforced") == 1
    assert kinds.count("missed") == len(opps) - 1
    assert set(kinds) <= {"won", "lost", "unforced", "missed"}

    table = attribution.yearly(rows)
    for year, row in table.items():
        assert row["opportunities"] == row["won"] + row["lost"] + row["missed"]
        assert row["trades"] == row["won"] + row["lost"] + row["unforced"]


def test_a_losing_trade_inside_a_real_leg_is_lost_not_unforced():
    """The distinction carries the whole diagnosis. A trade that lost inside a genuine
    up-move is a TIMING failure - entered late, stopped early. A trade that lost where
    there was no up-move at all is a SELECTION failure. Collapsing them into 'a losing
    trade' is precisely the aggregate that makes progress unaimable."""
    bars = _bars_from(_sawtooth())
    opps = attribution.opportunities(bars, threshold=0.03, symbol="X")
    mid = (opps[0].start_ns + opps[0].end_ns) // 2
    rows = attribution.reconcile(opps, [
        {"symbol": "X", "opened": str(np.datetime64(mid, "ns")),
         "closed": str(np.datetime64(opps[0].end_ns, "ns")), "net_pct": -0.03}])
    assert [r.kind for r in rows if r.kind != "missed"] == ["lost"]
    assert rows[0].opportunity_net > 0 or any(r.opportunity_net > 0 for r in rows)


def test_a_trade_on_another_symbol_cannot_claim_this_symbols_leg():
    """Matching is per symbol. A cross-symbol match would inflate the capture rate with
    coincidence - the failure mode that makes a diagnostic worse than no diagnostic."""
    bars = _bars_from(_sawtooth())
    opps = attribution.opportunities(bars, threshold=0.03, symbol="X")
    rows = attribution.reconcile(opps, [
        {"symbol": "OTHER", "opened": str(np.datetime64(opps[0].start_ns, "ns")),
         "closed": str(np.datetime64(opps[0].end_ns, "ns")), "net_pct": 0.09}])
    assert [r.kind for r in rows if r.symbol == "OTHER"] == ["unforced"]
    assert all(r.kind == "missed" for r in rows if r.symbol == "X")


def test_left_on_table_separates_a_thin_market_from_a_blind_model():
    """The number the aggregates never gave us. A year that returned nothing because
    the market offered nothing is a fact to accept; a year that returned nothing while
    declining 400 points of harvestable move is a model to fix, and until now the two
    were reported identically."""
    bars = _bars_from(_sawtooth())
    opps = attribution.opportunities(bars, threshold=0.03, symbol="X")
    rows = attribution.reconcile(opps, [])
    table = attribution.yearly(rows)
    year = next(iter(table.values()))
    assert year["capture_rate"] == 0.0
    assert year["left_on_table_pp"] == pytest.approx(
        round(sum(o.net for o in opps) * 100.0, 2), abs=0.01)


def test_indicators_are_read_at_the_decision_bar_or_not_at_all():
    """A near-miss lookup would report the indicators of a DIFFERENT bar and quietly
    answer a different question. Unmatched rows must be dropped, loudly, by the mask."""
    bars = _bars_from(np.cumprod(np.concatenate([[100.0], 1 + np.random.default_rng(3)
                                                 .normal(0, 0.004, 5000)])))
    X, ok = attribution.features_at(bars, [attribution._ns(bars[4000].timestamp),
                                           attribution._ns(bars[0].timestamp) - 10**15])
    assert ok[0] and not ok[1], "an exact bar resolves, an invented timestamp does not"
    assert X.shape[1] == len(attribution.tree.FEATURES)


def test_the_sealed_year_heads_the_table_but_never_enters_the_fit():
    """2026 is the only year never trained or selected on, so it heads every table the
    operator reads - and for exactly the same reason a rule fitted on its rows would
    destroy it. The report separates the two by construction, not by discipline."""
    rows = [attribution.Row("X", 2024, "won", 1, 0.05, 0.06),
            attribution.Row("X", 2026, "lost", 2, -0.02, 0.06)]
    rep = attribution.report(rows, sealed_year=2026)
    assert rep["sealed"]["trades"] == 1
    assert 2026 not in rep["research"]
    assert 2024 in rep["research"]


def test_a_response_curve_finds_a_real_optimum_and_calls_a_flat_curve_flat():
    """A73's two obligations in one instrument. When win rate genuinely peaks at an
    interior value, the curve must locate it and declare the high and low regions
    separated. When the indicator carries nothing, the bootstrap band must overlap and
    the curve must say NOT separated - because a sweep that can only ever return
    'here is your optimum' is a multiple-comparisons engine, not a measurement."""
    rng = np.random.default_rng(11)
    x = rng.uniform(0, 300, 6000)
    # Win probability peaks at 162 - the operator's own worked example.
    p = 0.45 + 0.35 * np.exp(-0.5 * ((x - 162.0) / 45.0) ** 2)
    won = (rng.uniform(size=len(x)) < p).astype(float)
    c = attribution.response_curve(x, won)
    assert c is not None and c["separated"]
    assert abs(c["optimum"] - 162.0) < 40.0, f"optimum found at {c['optimum']}"
    assert c["optimum_rate"] > c["base_rate"] > c["worst_rate"]

    flat = attribution.response_curve(x, (rng.uniform(size=len(x)) < 0.5).astype(float))
    assert flat is not None and not flat["separated"], (
        "an uninformative indicator must report itself as flat, not offer an optimum")


def test_a_response_curve_refuses_thin_or_degenerate_data():
    """Too few rows, or an indicator stuck on a handful of values, cannot support a
    curve at all - None, never a confident shape."""
    rng = np.random.default_rng(2)
    assert attribution.response_curve(rng.uniform(size=50), np.ones(50) * 0.5) is None
    x = np.repeat([1.0, 2.0], 300)
    assert attribution.response_curve(x, rng.uniform(size=600)) is None


def test_a_rule_is_only_reported_when_real_support_stands_behind_it():
    """Depth and leaf floors are the difference between a sentence about the market and
    a sentence about this sample. Too few rows must return NOTHING rather than a
    confident rule backed by nine trades."""
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, len(attribution.tree.FEATURES)))
    y = (X[:, 0] > 0).astype(int)
    assert attribution.explain(X, y, min_leaf=25) == []

    X = rng.normal(size=(600, len(attribution.tree.FEATURES)))
    y = (X[:, 15] > 0.5).astype(int)          # range_pos_96 in the A32 feature list
    rules = attribution.explain(X, y, min_leaf=25)
    assert rules, "with real support a separable signal must produce readable rules"
    assert all(r["support"] >= 25 for r in rules)
    assert any("range_pos_96" in r["rule"] for r in rules), (
        "the rule must name the indicator an operator can act on")
