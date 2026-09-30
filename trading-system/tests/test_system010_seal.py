"""System 10 cannot see 2026 by accident, and its state cannot change by accident.

The seal: every research path 010 trains from - the catalogue's `research()` and 06's
`Dataset.research()`, which 010 reads as its declared lineage - must end at or before
2025-12-31 23:45 UTC and hold no bar dated 2026. Reading the sealed window is S10-11's
one deliberate act, and nothing else.

The registry: 010's state is the frozen list in `features.py`. Its hash is pinned here,
and its market block must still be the layout 06's live net was trained on. A mismatch
means a feature moved; that needs a written reason before the hash moves with it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "trading-system/backtester/data"
UNIVERSE = REPO / "research/system06/universe.json"
LIVE_SCALER = REPO / "live-trading/engines/v3-exit-010/standardizer.json"
LAST_RESEARCH_BAR = datetime(2025, 12, 31, 23, 45, tzinfo=timezone.utc)
LOCK = datetime(2026, 1, 1, tzinfo=timezone.utc)
PINNED = "fa689b86f14e85c979cac86727085791a1a1414ec6b428838b947ef030c87e3c"


def _symbols() -> list[str]:
    return json.loads(UNIVERSE.read_text(encoding="utf-8"))["symbols"]


def _assert_sealed(bars_by_symbol: dict) -> None:
    assert bars_by_symbol, "the research loader returned nothing"
    for symbol, bars in bars_by_symbol.items():
        assert bars, symbol
        assert all(b.timestamp < LOCK for b in bars), f"{symbol}: a 2026 bar reached research"
        assert bars[-1].timestamp <= LAST_RESEARCH_BAR, symbol


@pytest.mark.skipif(not (DATA.is_dir() and UNIVERSE.is_file()), reason="no candles on this machine")
def test_the_catalogue_research_path_is_sealed():
    from quantlab_catalog.candles import research
    _assert_sealed(research(_symbols()))


@pytest.mark.skipif(not (DATA.is_dir() and UNIVERSE.is_file()), reason="no candles on this machine")
def test_the_inherited_dataset_research_path_is_sealed():
    from system006_oracle_net_15m.dataset import Dataset
    _assert_sealed(Dataset(data_root=str(DATA), symbols=_symbols()).research())


def test_the_feature_registry_is_frozen():
    from system010_conditioned_rl import features
    assert features.content_hash() == features.FEATURE_HASH == PINNED
    assert len(features.MARKET) == 44 and len(set(features.MARKET)) == 44


def test_the_market_block_is_the_layout_the_teacher_was_trained_on():
    from system006_oracle_net_15m.features import FEATURE_COLUMNS
    from system010_conditioned_rl import features
    assert tuple(FEATURE_COLUMNS) == features.MARKET
    if LIVE_SCALER.is_file():
        columns = json.loads(LIVE_SCALER.read_text(encoding="utf-8"))["columns"]
        assert tuple(columns) == features.MARKET
