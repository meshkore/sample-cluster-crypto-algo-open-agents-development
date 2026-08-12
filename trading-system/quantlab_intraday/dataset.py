"""15-minute bars, the 2026 lock, and the windows a run is measured on.

**Nothing here downloads anything the instrument could not already download.**
It calls `quantlab_backtester.data.FocusedDataset`, which is the mechanism this
laboratory already uses for families that opt out of the shared daily universe
(QUANT5). The consequences are the ones that matter:

- the cache lands under `data/research/processed/binance/<SYMBOL>/15m/` and
  `data/forward/...`, so 15-minute candles get their own subfolder for free
  and never mix with the daily panel;
- pre-2026 bars come from `DataManager`, which refuses 2026 data outright, and
  2026 bars from `ForwardDataManager`. The lock is enforced by the same code
  that enforces it everywhere else rather than by this module remembering to;
- indicators are the instrument's, unchanged. A 15-minute candle is a candle;
  `sma_200` simply means fifty hours here instead of two hundred days. There
  was no argument for a second indicator implementation and there is no second
  indicator implementation.

**Why a run is 5,000 bars and why one run is not enough.** The operator's cap
keeps a session to about 52 days of tape, which is the right size for a run and
the wrong size for a conclusion: 52 days is one market mood, and a mechanism
fitted to the mood preceding the lock has learned the mood. So the same window
is walked across the whole history and reported per block. That is also the
only way to test this system's central claim -- that its edge is a liquidity
premium and therefore cycle-agnostic -- instead of asserting it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from quantlab_backtester.data import FocusedDataset
from quantlab_backtester.indicator_store import IndicatorStore
from quantlab_backtester.indicators import IndicatorSpec
from quantlab_backtester.models import Bar

# One timeframe. Everything in this package defaults to it, and every entry
# point takes `--interval` if a different one is ever wanted -- but the system
# is not a timeframe study, it is a 5-minute system.
INTERVAL = "5m"
BARS_PER_DAY = {"5m": 288, "15m": 96, "30m": 48, "1h": 24, "4h": 6}

# `FocusedDataset` compares this against timezone-aware bar timestamps, so the
# offset is not optional: passing the bare "2026-01-01" raises deep inside the
# loader with "can't compare offset-naive and offset-aware datetimes", which
# reads as a broken checkout and is a missing suffix.
LOCK = "2026-01-01T00:00:00+00:00"

# The five deepest USDT majors. Same scope as H-SMARSI-001's hourly universe,
# deliberately: a new system whose result cannot be put beside the laboratory's
# best existing one is a number without a comparison.
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

# The operator's cap: bars a run may actually trade on. At 5 minutes that is
# about 17 days of tape per block, which is why the default block count is 12 --
# one run is a sample, twelve spread across the history is a measurement.
WINDOW_BARS = 5_000
DEFAULT_BLOCKS = 12

# Bars served before trading opens. The session itself trims the indicator
# warm-up (`IndicatorSpec.warmup_bars()`, 252 by default) and never serves it;
# the rest is for the brain's own state -- `VolatilityWatch` wants two days of
# NATR before it will express an opinion, and two days is 576 bars at this
# resolution. Without the margin the veto starts cold and nothing says so.
WARMUP_BARS = 1_000


@dataclass(frozen=True)
class Window:
    """One measurable stretch of tape: what to serve, and when trading opens."""

    index: int
    start: datetime  # first bar handed to the session, warm-up included
    trade_from: datetime  # first bar the brain is allowed to trade
    end: datetime
    label: str

    def document(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "start": self.start.isoformat(),
            "trade_from": self.trade_from.isoformat(),
            "end": self.end.isoformat(),
        }


class IntradayDataset:
    """15-minute bars for the intraday system, cached and era-split."""

    def __init__(
        self,
        data_root: Path | str,
        lock: str = LOCK,
        symbols: Iterable[str] = DEFAULT_SYMBOLS,
        interval: str = INTERVAL,
    ):
        self.root = Path(data_root)
        self.lock = datetime.fromisoformat(lock)
        self.interval = interval
        self.bars_per_day = BARS_PER_DAY.get(interval, 288)
        self.symbols = list(symbols)
        self.source = FocusedDataset(self.root, lock)
        # Indicators computed once per window and read from disk afterwards,
        # which is what makes iterating on hypotheses cheap: the first run over
        # a window pays for the panel, every later run reads it.
        #
        # A root per interval, because `BacktestSession` calls the store with
        # its default `timeframe="1d"` and this package cannot change the frozen
        # instrument. The path therefore says `1d` inside a `5m` root; the cache
        # key is a digest of the actual candles, so nothing can be mis-served --
        # only mis-named, and only inside a directory that says which interval
        # it holds.
        self.indicators = IndicatorStore(self.root / "indicators" / interval)

    # -- the tape ------------------------------------------------------------- #

    def research(self, symbols: Iterable[str] | None = None) -> dict[str, list[Bar]]:
        """Everything strictly before the lock. Downloads once, then reads."""
        return self.source.research_bars(list(symbols or self.symbols), self.interval)

    def combined(
        self, symbols: Iterable[str] | None = None, end: datetime | None = None
    ) -> dict[str, list[Bar]]:
        """History spliced with the sealed window, for a forward run."""
        return self.source.combined_bars(
            list(symbols or self.symbols),
            self.interval,
            end or datetime.now(timezone.utc),
        )

    # -- windows -------------------------------------------------------------- #

    @staticmethod
    def timeline(bars_by_symbol: dict[str, list[Bar]]) -> list[datetime]:
        """Every distinct bar time, in order -- the session's own definition."""
        return sorted(
            {bar.timestamp for bars in bars_by_symbol.values() for bar in bars}
        )

    @classmethod
    def blocks(
        cls,
        bars_by_symbol: dict[str, list[Bar]],
        count: int = DEFAULT_BLOCKS,
        window_bars: int = WINDOW_BARS,
        warmup_bars: int = WARMUP_BARS,
    ) -> list[Window]:
        """`count` non-overlapping windows spread evenly across the history.

        Evenly spaced rather than randomly sampled, and stated here because it
        is a methodological choice with a cost: even spacing guarantees era
        coverage and gives up the ability to quote a sampling distribution.
        For the question being asked -- does this work in bear tape as well as
        bull -- coverage is what matters, and a seeded random sample of eight
        windows out of fifty-three would answer a different, weaker question.
        """
        stamps = cls.timeline(bars_by_symbol)
        span = warmup_bars + window_bars
        if len(stamps) < span:
            raise ValueError(
                f"{len(stamps)} bars is fewer than one window of {span}; "
                "download more history or shrink window_bars"
            )
        maximum = len(stamps) // span
        if count > maximum:
            count = maximum
        step = (len(stamps) - span) // max(count - 1, 1) if count > 1 else 0
        windows = []
        for index in range(count):
            first = index * step
            windows.append(
                Window(
                    index=index,
                    start=stamps[first],
                    trade_from=stamps[first + warmup_bars],
                    end=stamps[first + span - 1],
                    label=f"block{index:02d}-{stamps[first + warmup_bars]:%Y-%m}",
                )
            )
        return windows

    @classmethod
    def forward_window(
        cls,
        bars_by_symbol: dict[str, list[Bar]],
        lock: datetime,
        warmup_bars: int = WARMUP_BARS,
    ) -> Window:
        """The sealed window, with just enough history in front of it to warm up.

        The whole of 2026 is served -- not the last 5,000 bars of it. Capping
        the sealed window would mean choosing which part of the only untouched
        evidence this project has to look at, which is not a resolution
        decision but a selection one.
        """
        stamps = cls.timeline(bars_by_symbol)
        forward = [stamp for stamp in stamps if stamp >= lock]
        if not forward:
            raise ValueError("no bars at or after the lock: nothing to forward-test")
        history = [stamp for stamp in stamps if stamp < lock]
        if len(history) < warmup_bars:
            raise ValueError(
                f"only {len(history)} bars before the lock, {warmup_bars} needed "
                "for warm-up"
            )
        return Window(
            index=-1,
            start=history[-warmup_bars],
            trade_from=forward[0],
            end=forward[-1],
            label=f"forward-{forward[0]:%Y}",
        )

    # -- payloads ------------------------------------------------------------- #

    @staticmethod
    def candles_payload(
        bars_by_symbol: dict[str, list[Bar]], window: Window
    ) -> dict[str, list[dict[str, Any]]]:
        """Inline candles for `POST /sessions`, or `Orchestrator.launch(candles=)`.

        Supplying the tape inline is what lets this system run at its own
        resolution without the instrument learning a second universe table:
        the backtester is handed candles and stays exactly as brainless as
        `CONTRACT.md` says it is.
        """
        payload: dict[str, list[dict[str, Any]]] = {}
        for symbol, bars in bars_by_symbol.items():
            rows = [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in bars
                if window.start <= bar.timestamp <= window.end
            ]
            # Two bars is the session's own minimum; anything less is a symbol
            # that did not exist yet, not a symbol with a problem.
            if len(rows) >= 2:
                payload[symbol] = rows
        return payload

    @staticmethod
    def warmup_check(spec: IndicatorSpec | None = None) -> int:
        """The indicator warm-up the session will trim from the front.

        Exposed so a caller can assert that `WARMUP_BARS` still leaves the
        brain's own state something to warm up on: if the catalogue grows a
        longer window than 500 bars, this system's volatility veto would start
        cold and nothing would say so.
        """
        return (spec or IndicatorSpec()).warmup_bars()
