"""The learned money-management module: sizes entries by the walk-forward channel,
abstains without a verdict, and its exporter's folds can never see their own year."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from system006_oracle_net_15m.channels import Channels
from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.sizing import MULT_CAP, MULT_FLOOR, Sizing
from system006_oracle_net_15m.moneymodel import MULTS, mults_from_preds, train_mask

NS = 1_700_000_000_000_000_000


def _view(channels: Channels, held: set[str] | None = None) -> MarketView:
    return MarketView(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=NS,
        candles={"AAA": {"close": 100.0}, "BBB": {"close": 50.0}},
        account={"equity": 10_000.0, "positions": {}},
        channels=channels, held=held or set(), peaks={},
    )


def _channels(size_map: dict[str, dict[int, float]]) -> Channels:
    table = {}
    for sym in ("AAA", "BBB"):
        table[sym] = {"prob": {NS: 0.9}, "trend": {NS: 1}, "vol": {}, "mom": {},
                      "hurst": {}, "feargreed": {}, "sweep": {}}
        if sym in size_map:
            table[sym]["size"] = size_map[sym]
    return Channels(table)


def test_lever_off_is_a_noop():
    out = Sizing(money_model=0.0).evaluate(_view(_channels({"AAA": {NS: 2.0}})))
    assert out.votes == {}


def test_missing_channel_abstains():
    out = Sizing(money_model=1.0).evaluate(_view(_channels({})))
    assert out.votes == {}


def test_full_intensity_applies_the_channel_multiplier():
    out = Sizing(money_model=1.0).evaluate(
        _view(_channels({"AAA": {NS: 2.0}, "BBB": {NS: 0.5}})))
    assert out.votes["AAA"].size_mult == pytest.approx(2.0)
    assert out.votes["BBB"].size_mult == pytest.approx(0.5)
    # Sizing never votes direction and never vetoes.
    assert out.votes["AAA"].conviction == 0.0
    assert not out.votes["AAA"].veto


def test_intensity_scales_toward_neutral():
    """money_model 0.5 takes the multiplier halfway between neutral and the channel."""
    out = Sizing(money_model=0.5).evaluate(_view(_channels({"AAA": {NS: 2.0}})))
    assert out.votes["AAA"].size_mult == pytest.approx(1.5)


def test_multiplier_is_bounded():
    out = Sizing(money_model=3.0).evaluate(
        _view(_channels({"AAA": {NS: 2.0}, "BBB": {NS: 0.1}})))
    assert out.votes["AAA"].size_mult == MULT_CAP
    assert out.votes["BBB"].size_mult == MULT_FLOOR


def test_held_names_are_never_resized():
    """The channel decides how much to BUY; it must never touch an open position."""
    out = Sizing(money_model=1.0).evaluate(
        _view(_channels({"AAA": {NS: 2.0}}), held={"AAA"}))
    assert out.votes == {}


def test_train_mask_never_sees_its_own_year_or_the_embargoed_december():
    """The leak this guards: a trade opened in December can CLOSE inside the test year."""
    years = np.array([2019, 2020, 2020, 2021, 2021])
    months = np.array([5, 11, 12, 1, 6])
    mask = train_mask(years, months, 2021)
    assert mask.tolist() == [True, True, False, False, False]


def test_mults_are_monotone_in_the_prediction_and_use_train_bounds():
    train_pred = np.linspace(-0.05, 0.05, 100)
    preds = np.array([-0.10, -0.02, 0.0, 0.02, 0.10])
    mult = mults_from_preds(preds, train_pred)
    assert all(a <= b for a, b in zip(mult, mult[1:]))       # monotone
    assert mult[0] == MULTS[0] and mult[-1] == MULTS[-1]     # extremes hit the ends
    # Bounds come from the TRAIN fold: identical preds under a shifted train
    # distribution must map differently (nothing of the scored year shapes itself).
    shifted = mults_from_preds(preds, train_pred + 0.04)
    assert shifted.tolist() != mult.tolist()


def test_verification_fails_closed_when_the_sizing_channel_cannot_be_built(monkeypatch):
    """A money_model config verified WITHOUT its channel would score a different strategy.

    The Sizing module abstains when the channel is missing, so a failed rebuild would
    silently verify a plain config and compare it against a bar that includes sizing -
    the recurring 'measure the same quantity' error. It must block promotion instead.
    """
    from system006_oracle_net_15m import autoloop

    monkeypatch.setattr(autoloop.train, "train",
                        lambda **k: {"enter": 0.75, "exit": 0.25, "min_hold": 16})
    monkeypatch.setattr(autoloop.infer, "export", lambda **k: None)

    def boom(**k):
        raise RuntimeError("sklearn unavailable")

    monkeypatch.setattr(autoloop.moneymodel, "build_sizing", boom)
    monkeypatch.setattr(autoloop.launch, "per_year",
                        lambda *a, **k: {2018: {"return_pct": 0.5}, 2019: {"return_pct": 0.5}})

    out = autoloop._score_genome(
        {"threshold": 0.03, "window": 96, "epochs": 1, "lr": 1e-3, "dropout": 0.1},
        seed=7, data_root="d", symbols=["A"], rbars={}, rstamps=[], dataset=None, grid=[],
        scratch=autoloop.ROOT / "_verify_sizing_test",
        risk={"max_positions": 2, "money_model": 1.0})
    assert out is None, "a config needing sizing must not verify without it"


def test_verification_passes_the_rebuilt_channel_into_the_backtest(monkeypatch):
    """The rebuilt overlay must actually reach the brain, or sizing silently abstains."""
    from system006_oracle_net_15m import autoloop

    seen = {}

    monkeypatch.setattr(autoloop.train, "train",
                        lambda **k: {"enter": 0.75, "exit": 0.25, "min_hold": 16})
    monkeypatch.setattr(autoloop.infer, "export", lambda **k: None)
    monkeypatch.setattr(autoloop.moneymodel, "build_sizing", lambda *a, **k: {"A": {1: 2.0}})
    monkeypatch.setattr(autoloop.moneymodel, "write_sizing", lambda overlay, path: None)

    def fake_per_year(bars, stamps, years, signals, brain_kwargs=None, **k):
        seen.update(brain_kwargs or {})
        return {2018: {"return_pct": 0.1}, 2019: {"return_pct": 0.2}}

    monkeypatch.setattr(autoloop.launch, "per_year", fake_per_year)

    out = autoloop._score_genome(
        {"threshold": 0.03, "window": 96, "epochs": 1, "lr": 1e-3, "dropout": 0.1},
        seed=7, data_root="d", symbols=["A"], rbars={}, rstamps=[], dataset=None, grid=[],
        scratch=autoloop.ROOT / "_verify_sizing_test2",
        risk={"max_positions": 2, "money_model": 1.0})
    assert out is not None
    assert seen.get("money_model") == 1.0
    assert "size_signals" in seen and seen["size_signals"].endswith("moneymodel.npz")
