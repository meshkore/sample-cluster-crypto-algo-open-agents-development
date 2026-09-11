"""System 08: the properties that must hold, or the design is not the design.

These are not coverage tests. Each one guards a specific way this laboratory has already
been wrong, or a specific claim the published design rests on. If one fails, the thing
that fails is an argument, not a line of code.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from quantlab_system08 import book as B
from quantlab_system08 import residual as R
from quantlab_system08 import signal as S
from quantlab_system08 import stats as ST
from quantlab_system08.system import Config, build


class _Bar:
    """Minimal stand-in for a catalogue bar: the modules only read timestamp and close."""

    def __init__(self, ts: datetime, close: float):
        self.timestamp, self.close = ts, close


def _tape(n_days: int, start_price: float, step, seed: int = 0) -> list[_Bar]:
    """A synthetic daily tape. `step(i)` returns the multiplicative move for day i."""
    out, price = [], start_price
    t0 = datetime(2019, 1, 1, tzinfo=timezone.utc)
    for i in range(n_days):
        price *= step(i)
        out.append(_Bar(t0 + timedelta(days=i), price))
    return out


# --------------------------------------------------------------------------- #
# CAUSALITY. The single most expensive bug available in this design.
# --------------------------------------------------------------------------- #

def test_loading_window_never_touches_the_day_it_explains():
    """A loading for day d must be estimated only on days strictly before d.

    A window that includes d explains d, and a book sized on it is reading its own
    answer. This asserts the property on every day produced, not on a sample.
    """
    # The asset must carry a genuine idiosyncratic component, or it is dropped by the
    # residual-share floor and there is nothing to assert causality about.
    days = [f"2019-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
    factor = {d: 0.01 * math.sin(i / 4.0) for i, d in enumerate(days)}
    asset = {d: 1.2 * factor[d] + 0.008 * math.cos(i / 3.0)
             for i, d in enumerate(days)}
    loads = R.loadings(asset, factor, window=30, min_obs=20)

    assert loads, "no loadings produced - the fixture is too short to test anything"
    for day, load in loads.items():
        assert load.through < day, (
            f"loading for {day} used data through {load.through}: the window touched "
            f"the day it explains")


def test_residual_return_sign_is_what_the_formula_says():
    """eps = r_i - beta * r_B, checked by hand. A sign error here would be invisible
    everywhere else because the book would still produce a curve."""
    assert R.residual_return(0.05, 1.5, 0.02) == pytest.approx(0.05 - 1.5 * 0.02)
    # A name that moved exactly with its loading has no residual at all.
    assert R.residual_return(0.03, 1.5, 0.02) == pytest.approx(0.0)
    # And a name that fell while the factor rose has a residual more negative than
    # its own return.
    assert R.residual_return(-0.01, 1.2, 0.04) < -0.01


def test_factor_is_not_residualised_against_itself():
    """A symbol regressed on a set containing itself gets beta ~1 and a residual ~0,
    and a book sizing by inverse residual volatility would take an unbounded position."""
    rets = {
        "BTCUSDT": {f"2019-01-{d:02d}": 0.01 for d in range(1, 29)},
        "ETHUSDT": {f"2019-01-{d:02d}": 0.02 for d in range(1, 29)},
    }
    loads = R.residuals(rets, factors=R.BTC_ONLY, window=20, min_obs=10)
    assert "BTCUSDT" not in loads


def test_returns_are_simple_not_log():
    """Log returns do not average across assets, and residuals are aggregated across
    symbols. A previous measurement in this laboratory was wrong for exactly this."""
    closes = {"2019-01-01": 100.0, "2019-01-02": 110.0}
    assert R.simple_returns(closes)["2019-01-02"] == pytest.approx(0.10)
    assert R.simple_returns(closes)["2019-01-02"] != pytest.approx(math.log(1.1))


# --------------------------------------------------------------------------- #
# THE SIGNAL. Constraints forced by citations, enforced in code.
# --------------------------------------------------------------------------- #

def test_universe_must_stay_screened_or_the_design_is_invalid():
    """The design rejected size and reversal as signals BECAUSE they live below our
    turnover floor. Widening the universe silently invalidates that rejection."""
    S.require_screened_universe({"min_turnover": 10_000_000.0})
    with pytest.raises(S.UniverseNotScreened):
        S.require_screened_universe({"min_turnover": 50_000.0})
    with pytest.raises(S.UniverseNotScreened):
        S.require_screened_universe({})


def test_book_is_long_and_short_with_equal_gross_legs():
    """The short side is mandatory - the published alpha is largely on it - and the two
    legs must be equal in gross terms or the 'residual' book carries a net direction."""
    scores = {f"S{i}": float(i) for i in range(9)}
    vols = {f"S{i}": 0.02 + 0.001 * i for i in range(9)}
    targets = S.rank_and_size(scores, vols, side_fraction=1 / 3, gross_cap=1.0)

    longs = [t for t in targets if t.weight > 0]
    shorts = [t for t in targets if t.weight < 0]
    assert longs and shorts, "a residual book with only one side is not the design"
    assert len(longs) == len(shorts)
    assert sum(t.weight for t in longs) == pytest.approx(0.5)
    assert sum(abs(t.weight) for t in shorts) == pytest.approx(0.5)
    # Highest score long, lowest score short.
    assert max(longs, key=lambda t: t.weight).symbol in ("S8", "S7", "S6")
    assert {t.symbol for t in shorts} == {"S0", "S1", "S2"}


def test_lower_residual_volatility_earns_a_larger_weight():
    """Sizing by inverse residual volatility is a claim of the design: the book intends
    to own the residual, so the risk it equalises is the residual's."""
    scores = {"A": 3.0, "B": 2.0, "C": -2.0, "D": -3.0}
    vols = {"A": 0.01, "B": 0.04, "C": 0.01, "D": 0.04}
    targets = {t.symbol: t.weight for t in
               S.rank_and_size(scores, vols, side_fraction=0.5, gross_cap=1.0)}
    assert abs(targets["A"]) > abs(targets["B"])
    assert abs(targets["C"]) > abs(targets["D"])


def test_thin_cross_section_stands_aside_rather_than_concentrating():
    """Standing aside is a position. A one-name leg is an idiosyncratic bet wearing a
    portfolio's label, and the operator's execution-risk constraint argues for flat."""
    assert S.rank_and_size({"A": 1.0}, {"A": 0.02}) == []
    assert S.rank_and_size({"A": 1.0, "B": 0.0}, {"A": 0.02, "B": 0.02}) == []


def test_momentum_needs_a_full_window_and_compounds():
    eps = {f"2019-01-{d:02d}": 0.01 for d in range(1, 21)}
    # Not enough history before the asked-for day.
    assert S.residual_momentum(eps, "2019-01-05", lookback=10, skip=1) is None
    # Full window: compounded, not summed.
    got = S.residual_momentum(eps, "2019-01-20", lookback=10, skip=1)
    assert got == pytest.approx(1.01 ** 10 - 1.0)
    assert got != pytest.approx(0.10)


def test_momentum_skip_actually_skips():
    """The skip exists to keep short-term reversal out of the formation window. If it
    silently did nothing, the signal would be a different signal than the one argued."""
    eps = {f"2019-01-{d:02d}": 0.0 for d in range(1, 21)}
    eps["2019-01-19"] = 5.0                      # a huge move in the skipped day
    scored = S.residual_momentum(eps, "2019-01-20", lookback=5, skip=1)
    assert scored == pytest.approx(0.0), "the skipped day leaked into the score"


def test_hedge_cancels_the_books_net_loading():
    """h = -sum(w * beta). Computed explicitly rather than assumed to net out."""
    targets = [S.Target("A", 0.5, 1.0, 0.02), S.Target("B", -0.5, -1.0, 0.02)]
    betas = {"A": 1.4, "B": 0.6}
    h = S.hedge_weight(targets, betas)
    assert h == pytest.approx(-(0.5 * 1.4 - 0.5 * 0.6))
    net = sum(t.weight * betas[t.symbol] for t in targets) + h
    assert net == pytest.approx(0.0), "net factor exposure is the whole point"


# --------------------------------------------------------------------------- #
# THE BOOK. Costs, drift and funding - the three things that actually cost money.
# --------------------------------------------------------------------------- #

def test_round_trip_costs_thirty_basis_points():
    """The operator's cost model: 10 bps commission + 5 bps slippage per side."""
    assert B.COST_PER_SIDE == pytest.approx(0.0015)
    assert 2 * B.COST_PER_SIDE == pytest.approx(0.0030)


def test_turnover_is_charged_and_holding_is_not():
    """A book that rebalances silently every day and pays nothing is the most common way
    a cross-sectional backtest reports a return nobody could have earned."""
    days = ["2019-01-01", "2019-01-02", "2019-01-03"]
    rets = {"A": {d: 0.0 for d in days}, "BTCUSDT": {d: 0.0 for d in days}}
    targets = {"2019-01-01": [S.Target("A", 1.0, 1.0, 0.02)]}
    res = B.run_book(days, rets, targets, {"2019-01-01": 0.0}, "BTCUSDT",
                     initial_equity=100_000.0)
    assert res.days[0].cost == pytest.approx(100_000.0 * B.COST_PER_SIDE)
    assert res.days[1].cost == 0.0 and res.days[2].cost == 0.0


def test_weights_drift_between_rebalances():
    """Positions are set at the rebalance and then left alone; the weight moves with the
    price. Constant weights would mean free daily rebalancing."""
    days = ["2019-01-01", "2019-01-02"]
    rets = {"A": {"2019-01-01": 0.0, "2019-01-02": 0.50},
            "BTCUSDT": {d: 0.0 for d in days}}
    res = B.run_book(days, rets, {"2019-01-01": [S.Target("A", 0.4, 1.0, 0.02)]},
                     {"2019-01-01": 0.0}, "BTCUSDT")
    assert res.days[-1].gross == pytest.approx(0.4 * 1.5)


def test_gross_cap_is_enforced_every_day_not_only_at_rebalances():
    """The design states the cap as a STANDING constraint, "subject to sum|w| <= L".

    The first real run applied it only at rebalances, and drift carried gross exposure
    to 2.67x on a 1.0 cap - the book levered itself simply by holding winners, and spent
    its worst nine days there. Leverage is permitted but minimal, so this is a constraint
    that has to hold on every day, not on rebalance days.

    A book cannot trim intraday, before it knows the move - so gross is allowed to end a
    day above the cap by that day's return, and is brought back at the next open. What it
    must NOT do is compound: here a name gains 50% every day for ten days, which without
    enforcement carries gross to 1.5**9, about 38x.
    """
    days = [f"2019-01-{d:02d}" for d in range(1, 11)]
    rets = {"A": {d: (0.50 if i > 0 else 0.0) for i, d in enumerate(days)},
            "BTCUSDT": {d: 0.0 for d in days}}
    res = B.run_book(days, rets, {days[0]: [S.Target("A", 1.0, 1.0, 0.02)]},
                     {days[0]: 0.0}, "BTCUSDT", gross_cap=1.0, cap_band=0.10)

    ceiling = 1.0 * (1.0 + 0.10) * 1.50          # cap, plus band, plus one day's move
    worst = max(d.gross for d in res.days)
    assert worst <= ceiling + 1e-9, (
        f"gross exposure reached {worst:.2f} against a ceiling of {ceiling:.2f} - the "
        f"constraint is not being enforced between rebalances")
    # And it must be bounded, not merely slow: the last day is no worse than the first.
    assert res.days[-1].gross <= ceiling + 1e-9


def test_trimming_back_to_the_cap_is_paid_for():
    """Trimming is trading. A book that de-levers for free is understating its costs."""
    days = [f"2019-01-{d:02d}" for d in range(1, 6)]
    rets = {"A": {d: (0.60 if i > 0 else 0.0) for i, d in enumerate(days)},
            "BTCUSDT": {d: 0.0 for d in days}}
    res = B.run_book(days, rets, {days[0]: [S.Target("A", 1.0, 1.0, 0.02)]},
                     {days[0]: 0.0}, "BTCUSDT", gross_cap=1.0)
    assert sum(d.cost for d in res.days[1:]) > 0, "the book de-levered for free"


def test_positive_funding_pays_the_short_and_charges_the_long():
    """The ledger's convention, kept identical. This is the design's weakest claim and
    the one K3 fires on, so it is pinned by a test rather than trusted."""
    days = ["2019-01-01"]
    rets = {"A": {"2019-01-01": 0.0}, "BTCUSDT": {"2019-01-01": 0.0}}
    funding = {"A": {"2019-01-01": 0.001}}

    short = B.run_book(days, rets, {"2019-01-01": [S.Target("A", -1.0, 1.0, 0.02)]},
                       {"2019-01-01": 0.0}, "BTCUSDT", funding=funding)
    assert short.days[0].funding_pnl > 0, "a short must RECEIVE positive funding"

    long = B.run_book(days, rets, {"2019-01-01": [S.Target("A", 1.0, 1.0, 0.02)]},
                      {"2019-01-01": 0.0}, "BTCUSDT", funding=funding)
    assert long.days[0].funding_pnl < 0, "a long must PAY positive funding"


def test_funding_settlements_are_summed_within_the_day():
    """Averaging instead of summing would understate the carry by the number of
    settlements, which is the whole size of the effect the design leans on."""
    rows = [{"t_ms": 1_546_300_800_000, "rate": 0.0001},
            {"t_ms": 1_546_329_600_000, "rate": 0.0002},
            {"t_ms": 1_546_358_400_000, "rate": 0.0003}]
    got = B.daily_funding(rows)
    assert sum(got.values()) == pytest.approx(0.0006)


def test_yearly_returns_are_reported_per_calendar_year():
    """The mandate is stated per calendar year, so the report is too. A mean across
    years hides the year that kills you."""
    days = [f"2019-01-{d:02d}" for d in range(1, 4)] + \
           [f"2020-01-{d:02d}" for d in range(1, 4)]
    rets = {"A": {d: 0.01 for d in days}, "BTCUSDT": {d: 0.0 for d in days}}
    res = B.run_book(days, rets, {days[0]: [S.Target("A", 1.0, 1.0, 0.02)]},
                     {days[0]: 0.0}, "BTCUSDT")
    years = res.by_year()
    assert set(years) == {2019, 2020}


# --------------------------------------------------------------------------- #
# THE STATISTICAL GUARDS. These exist because six systems died in the same year.
# --------------------------------------------------------------------------- #

def test_more_trials_makes_the_same_result_less_believable():
    """The core of the deflated Sharpe: trying more configurations makes the best of
    them look good for free, so the same returns must survive a higher bar."""
    returns = [0.001 * ((i % 7) - 2) + 0.0015 for i in range(600)]
    one = ST.deflated_sharpe(returns, trials=1)
    many = ST.deflated_sharpe(returns, trials=500)
    assert one.sharpe == pytest.approx(many.sharpe)       # same raw result
    assert many.probability < one.probability             # less believable
    assert many.deflated_sharpe < one.deflated_sharpe


def test_trials_must_be_stated():
    with pytest.raises(ValueError):
        ST.deflated_sharpe([0.01] * 100, trials=0)


def test_the_hurdle_is_harvey_liu_zhu_not_the_conventional_one():
    assert ST.T_HURDLE == 3.0


def test_expected_max_sharpe_grows_with_the_number_of_trials():
    assert ST.expected_max_sharpe(2) < ST.expected_max_sharpe(50) \
        < ST.expected_max_sharpe(1000)


def test_a_pure_noise_strategy_does_not_clear_the_hurdle():
    """The guard has to be able to say no, or it is decoration."""
    noise = [0.01 * math.sin(i) for i in range(500)]
    assert not ST.deflated_sharpe(noise, trials=50).clears_hurdle


# --------------------------------------------------------------------------- #
# END TO END, on a synthetic tape whose answer is known.
# --------------------------------------------------------------------------- #

def test_end_to_end_runs_and_never_reads_the_future():
    """Assembles the whole system on a synthetic tape and re-asserts causality on the
    real code path, not on the unit fixture."""
    def wobble(k):
        return lambda i: 1.0 + 0.02 * math.sin((i + k) / 5.0)

    bars = {"BTCUSDT": _tape(400, 30_000.0, wobble(0))}
    for j in range(1, 6):
        bars[f"ALT{j}USDT"] = _tape(400, 100.0 * j, wobble(j * 3))

    run = build(bars, Config(window=40, lookback=20, skip=1, hold=14), trials=1)
    assert run.result.days, "the book produced no days"
    assert run.rebalances > 0, "the book never took a position"

    rets = {s: R.simple_returns(R.daily_closes(b)) for s, b in bars.items()}
    loads = R.residuals(rets, window=40)
    for per_day in loads.values():
        for day, load in per_day.items():
            assert load.through < day


def test_a_market_with_no_residual_produces_no_position():
    """If every alt is exactly its loading times the factor, there is no residual to
    own, and the book must stand aside rather than invent one.

    This is the sharpest available test of the design's premise. The system claims to
    own the idiosyncratic part; a world with no idiosyncratic part is a world where it
    must do nothing, and a book that trades anyway is trading noise in its own
    estimator.
    """
    factor = _tape(300, 30_000.0, lambda i: 1.0 + 0.02 * math.sin(i / 5.0))
    f_rets = R.simple_returns(R.daily_closes(factor))
    days = sorted(f_rets)

    bars = {"BTCUSDT": factor}
    for j in range(1, 6):
        beta, price, series = 0.5 + 0.3 * j, 100.0 * j, []
        t0 = datetime(2019, 1, 1, tzinfo=timezone.utc)
        series.append(_Bar(t0, price))
        for i, d in enumerate(days, start=1):
            price *= (1.0 + beta * f_rets[d])     # pure factor, zero residual
            series.append(_Bar(t0 + timedelta(days=i), price))
        bars[f"ALT{j}USDT"] = series

    with pytest.raises(ValueError, match="no residual series"):
        build(bars, Config(window=40, lookback=20, hold=14), trials=1)


def test_costs_are_real_and_show_up_in_the_result():
    """Whatever the tape does, a book that traded must report what the trading cost.
    A run with rebalances and zero reported cost is a run that is lying."""
    def wobble(k):
        return lambda i: 1.0 + 0.02 * math.sin((i + k) / 5.0) + 0.004 * math.cos(i / 3.0)

    bars = {"BTCUSDT": _tape(400, 30_000.0, wobble(0))}
    for j in range(1, 6):
        bars[f"ALT{j}USDT"] = _tape(400, 100.0 * j, wobble(j * 3))

    run = build(bars, Config(window=40, lookback=20, hold=14), trials=1)
    assert run.rebalances > 0
    assert run.result.total_costs > 0.0, "the book traded and reported no cost"
