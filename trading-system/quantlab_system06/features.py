"""What the net sees at a bar — causal, stationary, normalised on train only.

Two rules govern every column here, and both are the difference between a
measurement and a leak:

1. **Causal.** A feature at bar `i` uses only bars `<= i`. The instrument already
   computes ~91 indicator columns this way, so the feature set is a *subset* of
   that panel — never a fresh calculation that might reach forward by accident.
2. **Stationary.** Raw price levels (`sma_50`, `bb_upper`, …) are excluded: a net
   trained on 2019 prices has learned a number that never recurs. Everything kept
   is a ratio, an oscillator, a return, a channel position or a candle shape —
   quantities whose meaning is the same at $100 and at $100,000.

The curated set below is deliberately small and readable. It includes the candle
geometry (`body_fraction`, wick fractions, `internal_bar_strength`) and the
multi-horizon returns, which is how a window of these rows encodes "the shape of
the candles going back" without a second indicator implementation.

Normalisation statistics are fitted on the **training slice only** and then
applied everywhere, so no bar is ever standardised by a mean that its own future
helped compute. The fitted stats are exported with the model — the brain must
standardise a live bar exactly as training did.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from quantlab_backtester.indicator_store import IndicatorStore
from quantlab_backtester.indicators import IndicatorSpec, panel_for
from quantlab_backtester.models import Bar

# Indicator panels are precomputed once and read from disk thereafter, so a
# training run or an inference pass never pays the ~91-column arithmetic again.
# Research and forward series for the same symbol are DIFFERENT candles, and the
# store keys on (symbol, spec, timeframe) not on the candles, so they must live
# in separate roots or each would overwrite the other's cache — the exact trap
# the intraday system documents. Two roots, two caches.
def research_store(data_root: str = "backtester/data") -> IndicatorStore:
    return IndicatorStore(Path(data_root) / "indicators" / "system06" / "research")


def combined_store(data_root: str = "backtester/data") -> IndicatorStore:
    return IndicatorStore(Path(data_root) / "indicators" / "system06" / "combined")

# A stationary subset of the instrument's panel. Grouped by what they measure so
# the list is auditable; order is fixed because it defines the model's input
# layout and the export must reproduce it exactly.
FEATURE_COLUMNS: tuple[str, ...] = (
    # multi-horizon returns — the recent trajectory
    "return_1", "return_5", "return_20", "return_60", "return_252",
    # oscillators, already bounded
    "rsi_2", "rsi_7", "rsi_14", "rsi_21",
    "stoch_k", "stoch_d", "williams_r", "cci",
    # trend strength / direction, dimensionless
    "adx", "di_plus", "di_minus", "aroon_up", "aroon_down", "aroon_osc",
    "vortex_plus", "vortex_minus", "supertrend_direction",
    # distance to moving averages — relative, not levels
    "distance_to_sma_20", "distance_to_sma_50", "distance_to_sma_200",
    "macd_hist",
    # volatility, as fractions
    "natr_14", "natr_20", "bb_width", "bb_percent_b", "range_vs_atr",
    # position within the recent range
    "pct_below_high_20", "pct_below_high_55", "pct_below_high_200",
    "drawdown_from_high", "internal_bar_strength",
    # candle geometry — "the shape of the candles"
    "body_fraction", "upper_wick_fraction", "lower_wick_fraction",
    "up_streak", "down_streak",
    # flow / participation
    "volume_ratio_20", "chaikin_money_flow", "money_flow_index",
)


def build_matrix(
    bars: list[Bar],
    spec: IndicatorSpec | None = None,
    store: IndicatorStore | None = None,
    symbol: str | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-bar feature matrix `X` (n_bars x n_features) and the bar timestamps.

    With a `store` and `symbol` the ~91-column panel is read from (or written to)
    the cache instead of recomputed — the digest inside the cache file guards
    against a stale panel. `macd_hist` is the one column carried in price units by
    the instrument, so it is divided by close here to make it a fraction like
    everything else; every other column is already dimensionless.
    """
    if store is not None and symbol is not None:
        panel = store.panel(symbol, bars, spec or IndicatorSpec())
    else:
        panel = panel_for(bars, spec)
    missing = [c for c in FEATURE_COLUMNS if c not in panel.columns]
    if missing:
        raise KeyError(f"panel is missing expected columns: {missing}")

    close = np.array([b.close for b in bars], dtype=float)
    cols = []
    for name in FEATURE_COLUMNS:
        values = np.asarray(panel.columns[name], dtype=float)
        if name == "macd_hist":
            values = values / np.where(close > 0, close, np.nan)
        cols.append(values)
    matrix = np.column_stack(cols)
    timestamps = np.array([b.timestamp for b in bars], dtype="datetime64[ns]")
    return matrix, timestamps


@dataclass
class Standardizer:
    """z-score per column, fitted on a training slice, with outlier clipping.

    Serialisable to a plain dict so it can be exported next to the model and
    reproduced verbatim by the brain. `clip` tames the fat tails crypto features
    carry — an unclipped 40-sigma volume spike would dominate a linear layer's
    first step and teach the net nothing.
    """

    mean: np.ndarray
    std: np.ndarray
    clip: float = 5.0

    @classmethod
    def fit(
        cls, matrix: np.ndarray, train_rows: np.ndarray, clip: float = 5.0
    ) -> "Standardizer":
        """Fit on `train_rows` only — the whole no-leak guarantee lives here."""
        block = matrix[train_rows]
        mean = np.nanmean(block, axis=0)
        std = np.nanstd(block, axis=0)
        std = np.where(std > 1e-9, std, 1.0)  # a constant column standardises to 0
        return cls(mean=mean, std=std, clip=clip)

    def transform(self, matrix: np.ndarray) -> np.ndarray:
        """Standardise, clip, and replace warm-up NaNs with 0 (the column mean)."""
        z = (matrix - self.mean) / self.std
        z = np.clip(z, -self.clip, self.clip)
        return np.nan_to_num(z, nan=0.0, posinf=self.clip, neginf=-self.clip)

    def to_dict(self) -> dict:
        return {
            "columns": list(FEATURE_COLUMNS),
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "clip": self.clip,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Standardizer":
        if tuple(payload["columns"]) != FEATURE_COLUMNS:
            raise ValueError(
                "exported feature columns do not match the current FEATURE_COLUMNS; "
                "the model was trained on a different feature layout"
            )
        return cls(
            mean=np.asarray(payload["mean"], dtype=float),
            std=np.asarray(payload["std"], dtype=float),
            clip=float(payload["clip"]),
        )


def finite_rows(matrix: np.ndarray) -> np.ndarray:
    """Indices whose every feature is finite — the warm-up front is excluded.

    Indicators are `None`/NaN until their window fills (the instrument leaves them
    so on purpose, so a rule cannot read a warm-up bar as a zero signal). A
    windowed model needs a fully-formed row, so training and inference both draw
    only from here.
    """
    return np.where(np.all(np.isfinite(matrix), axis=1))[0]
