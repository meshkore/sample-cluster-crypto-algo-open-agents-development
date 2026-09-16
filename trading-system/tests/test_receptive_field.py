"""A window the net is fed is not a window the net can see.

A103, measured 2026-09-05. The shipping champion is handed 96 bars per decision and
its readout depends on 15 of them. The other 81 are read from disk, standardised,
copied to the GPU and multiplied by nothing. Nothing errored, no metric moved, and the
config file says "window": 96 in plain sight.

These tests exist so the gap between `window` and `receptive_field` is a number
somebody has to look at, rather than an arithmetic identity nobody recomputes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from system006_oracle_net_15m.model import ModelConfig, OracleNet  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _bars_actually_seen(config: ModelConfig) -> int:
    """Gradient probe: how many input timesteps the output genuinely depends on.

    This is the measurement the arithmetic is checked against. A formula can be wrong
    about a network; a gradient cannot - a timestep whose gradient is exactly zero
    cannot influence the prediction, whatever any config says.
    """
    net = OracleNet(ModelConfig(**{**config.to_dict(), "dropout": 0.0})).eval()
    x = torch.randn(1, config.window, config.n_features, requires_grad=True)
    net(x).backward()
    return int((x.grad.abs().sum(dim=2)[0] > 0).sum().item())


@pytest.mark.parametrize("channels,expected", [
    ((64, 64, 64), 15),
    ((192, 192, 192), 15),          # the shipping champion: width does not buy reach
    ((192,) * 4, 31),
    ((192,) * 6, 127),              # A103's treatment arm: covers a 96-bar window
])
def test_the_formula_agrees_with_the_gradient(channels, expected):
    cfg = ModelConfig(n_features=44, window=128, channels=channels)
    assert cfg.receptive_field == expected
    assert _bars_actually_seen(cfg) == expected, (
        "the analytic receptive field must match what the network actually reads")


def test_width_does_not_widen_the_view():
    """The distinction that hid A103 for as long as it hid. The project has tuned
    capacity repeatedly - 64 channels, then 192, then 256, adopted as the champion -
    and every one of those changes left the reach at 15 bars. Capacity is how much the
    net can represent about what it sees; the receptive field is what it sees at all."""
    narrow = ModelConfig(n_features=44, window=96, channels=(64, 64, 64))
    wide = ModelConfig(n_features=44, window=96, channels=(256, 256, 256))
    assert narrow.receptive_field == wide.receptive_field == 15
    assert not narrow.sees_whole_window() and not wide.sees_whole_window()


def test_depth_is_the_lever_and_it_needs_no_new_code():
    """resolved_dilations doubles per block, so blocks are what buy reach. Six of them
    cover a 96-bar window - which means A103 is a training run, not a rewrite."""
    deep = ModelConfig(n_features=44, window=96, channels=(192,) * 6)
    assert deep.resolved_dilations() == (1, 2, 4, 8, 16, 32)
    assert deep.receptive_field == 127
    assert deep.sees_whole_window()


def test_the_shipping_champion_is_recorded_as_blind():
    """Pinned deliberately, and NOT as an assertion that the champion is fine.

    It fails the moment the champion's config changes, which is exactly when somebody
    should be made to state whether the new one can see the window it is given. If a
    later champion covers its window this test should be rewritten to assert that
    permanently - it is a ratchet, not a description.
    """
    # Read from best.json, which is the champion's OWN artefact and travels with it.
    # This used to read research/system06/_w192/config.json - a scratch directory from
    # the experiment that produced the champion - and when that directory was cleared
    # on 2026-09-09 the ratchet went dormant in silence. A guard that can be disarmed
    # by tidying up is not a guard.
    card_path = REPO / "research/system06/model_card.json"
    if not card_path.exists():
        pytest.skip("no champion on this machine")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    cfg = ModelConfig(
        n_features=int(card["features"]),
        window=int(card["window"]),
        channels=tuple(card["channels"]),
    )
    assert cfg.window == 96
    assert cfg.receptive_field == 15, (
        "the champion's reach changed - state whether the new model can see its window")
    assert cfg.window - cfg.receptive_field == 81, (
        "81 bars per decision are prepared and ignored; see A103")
