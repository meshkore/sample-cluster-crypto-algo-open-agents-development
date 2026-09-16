"""The extreme-fear veto (A65): the first lever built on non-price information."""
import json

import pytest

from system006_oracle_net_15m.modules.crowd import Crowd

DAY = 86_400
NS = 1_000_000_000


@pytest.fixture
def feed(tmp_path):
    # three days: greed (70), extreme fear (12), neutral (50)
    rows = [{"t_s": 1_600_000_000, "value": 70},
            {"t_s": 1_600_000_000 + DAY, "value": 12},
            {"t_s": 1_600_000_000 + 2 * DAY, "value": 50}]
    p = tmp_path / "feargreed.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def test_off_by_default_abstains_even_with_a_feed(feed):
    c = Crowd(data_path=feed)
    assert c.fng_min == 0.0
    assert c.value_at((1_600_000_000 + DAY + 3600) * NS) is None  # feed not even loaded


def test_it_reads_only_values_published_strictly_before_the_bar(feed):
    c = Crowd(fng_min=25, data_path=feed)
    t0 = 1_600_000_000
    # a bar exactly at a publication instant must NOT see that publication
    assert c.value_at(t0 * NS) is None
    assert c.value_at((t0 + 1) * NS) == 70
    assert c.value_at((t0 + DAY) * NS) == 70          # not yet the fear print
    assert c.value_at((t0 + DAY + 3600) * NS) == 12   # now it is published


def test_a_bar_before_any_publication_abstains(feed):
    c = Crowd(fng_min=25, data_path=feed)
    assert c.value_at((1_500_000_000) * NS) is None


def test_a_missing_feed_abstains_instead_of_crashing(tmp_path):
    c = Crowd(fng_min=25, data_path=tmp_path / "nope.json")
    assert c.value_at(1_600_000_000 * NS) is None


def test_the_threshold_is_the_indexs_own_boundary_not_a_fitted_one():
    from system006_oracle_net_15m.modules import crowd
    assert crowd.EXTREME_FEAR == 25.0


def test_the_lever_is_known_to_the_loop_and_the_adapter():
    import inspect

    from system006_oracle_net_15m import autoloop, orchestrator, strategy
    assert "fng_min" in autoloop.KNOWN_LEVERS
    assert "fng_min" in inspect.signature(orchestrator.build_ensemble).parameters
    assert "fng_min" in inspect.signature(strategy.OracleNetBrain.__init__).parameters


def test_the_fingerprint_carries_the_lever_only_when_active():
    from system006_oracle_net_15m.strategy import OracleNetBrain
    import inspect
    src = inspect.getsource(OracleNetBrain)
    assert '"fng_min": self.fng_min} if self.fng_min else {}' in src
