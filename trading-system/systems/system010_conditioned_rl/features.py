"""The frozen feature registry: every number 010's state is allowed to contain.

Two blocks. The MARKET block is system 06's 44 causal columns, the exact layout of the
live net's standardizer (`live-trading/engines/v3-exit-010/standardizer.json`) - all of
them derived from the symbol's own candles, none from an external series, so none of
them carries a publication lag. The BOOK block is what 06 never saw and the design says
the policy must: where the book stands when it is asked to act.

The list is copied here as literals, not imported, so that a change to 06's feature
module cannot silently change 010's state. `test_system010_seal.py` pins FEATURE_HASH
and checks the MARKET block still matches 06's; either failing means a feature was
added or moved, and that needs a row in docs/SUMMARY.md "What helped" or "What hurt"
before the hash is updated (S10-4).
"""

from __future__ import annotations

import hashlib
import json

WINDOW_BARS = 96  # one day of 15-minute bars

MARKET: tuple[str, ...] = (
    "return_1", "return_5", "return_20", "return_60", "return_252",
    "rsi_2", "rsi_7", "rsi_14", "rsi_21", "stoch_k", "stoch_d", "williams_r", "cci",
    "adx", "di_plus", "di_minus", "aroon_up", "aroon_down", "aroon_osc",
    "vortex_plus", "vortex_minus", "supertrend_direction",
    "distance_to_sma_20", "distance_to_sma_50", "distance_to_sma_200",
    "macd_hist", "natr_14", "natr_20", "bb_width", "bb_percent_b", "range_vs_atr",
    "pct_below_high_20", "pct_below_high_55", "pct_below_high_200", "drawdown_from_high",
    "internal_bar_strength", "body_fraction", "upper_wick_fraction", "lower_wick_fraction",
    "up_streak", "down_streak", "volume_ratio_20", "chaikin_money_flow", "money_flow_index",
)

BOOK: tuple[str, ...] = (
    "position_held",        # 0 flat, 0.5 half slot, 1 full slot - in THIS symbol
    "unrealised_return",    # of the open position, 0 when flat
    "bars_held",            # of the open position, scaled by WINDOW_BARS
    "slots_free",           # of the book's max_positions, as a fraction
    "drawdown_from_peak",   # the account's, from the year's equity peak
    "region_id",            # which cell of R the bar sits in; -1 outside
)


def registry() -> dict:
    return {"window_bars": WINDOW_BARS, "market": list(MARKET), "book": list(BOOK)}


def content_hash() -> str:
    blob = json.dumps(registry(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


FEATURE_HASH = "fa689b86f14e85c979cac86727085791a1a1414ec6b428838b947ef030c87e3c"
