"""Many candidate mechanisms, one pass over the tape, judged against the toll.

    python3 -m quantlab_intraday.survey

Writing a brain and backtesting it costs an afternoon. Asking whether the thing
it is built on predicts a move bigger than 0.30% costs one pass over the data,
and answers the only question that decides whether the afternoon is worth
spending. This module is that pass, for a whole shortlist at once.

**What is in the shortlist and why.** Each entry is a mechanism with published
evidence behind it or a structural reason to expect an uncapped payoff, because
the previous hypothesis (H-INTRA-001, reversion) failed for a reason that
generalises: reversion targets a move that is capped by construction -- price
returns to the anchor and the trade is over -- so its mean is bounded near the
toll however high the win rate. What can clear a fixed toll is a rule whose
right tail is open.

- **Intraday time-series momentum** (`itsm_*`). The return from the start of the
  UTC day to hour H predicts the return over the rest of the day. Documented in
  Bitcoin by Shen, Urquhart and Wang (Financial Review, 2022) and across 60+
  futures markets by Zhang, Ma and Bouri. One decision a day, held for hours,
  which is the trade profile a 0.30% toll can survive.
- **Breakout** (`donchian_*`). Close above the highest high of the trailing
  window. The classic uncapped-tail rule: losses are bounded by the stop, wins
  are bounded by nothing.
- **Volatility expansion** (`volexp`). A bar several ATR wide, closing on its
  high, on a volume spike -- the shape momentum ignition leaves behind.
- **Squeeze** (`squeeze`). Bollinger width in the bottom fifth of its own recent
  distribution, then a close above the upper band. Compression preceding
  expansion is the most-cited setup in the practitioner literature and the one
  most likely to be already arbitraged; it is here to be measured, not assumed.
- **Trend continuation** (`trend`, `continuation`). Long only when the slow and
  fast averages agree, or after a sharp up-move -- the deliberate opposite of
  the refuted reversion rule.
- **Reversion** (`reversion`). H-INTRA-001, kept as the control. A new
  mechanism that cannot beat the one already known to fail is not a finding.
- **Hour of day** (`hour_*`). Unconditional, by entry hour. Not a strategy: the
  drift table every conditional rule has to beat.

**How a row is read.** `net` is the mean forward return minus the round trip.
`excess` is `net` minus what the same horizon returned after *any* bar, which
is the number that separates a mechanism from a long position. `t*` is computed
on non-overlapping observations only -- see `edge.py` for why the naive one
cannot be trusted at these horizons. A candidate is worth building only if
`net` and `excess` are positive in BOTH eras with a `t*` that is not noise.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from quantlab_backtester.indicators import IndicatorSpec, panel_for
from quantlab_backtester.models import Bar

from .dataset import DEFAULT_SYMBOLS, INTERVAL, LOCK, IntradayDataset
from .moneymanagement import bar_turnover_floor, round_trip_cost

# 1h, 3h, 6h, 12h, 24h at 5 minutes. Short enough that a decision is intraday,
# long enough that the move can exceed the toll.
HORIZONS = (12, 36, 72, 144, 288)
SPLIT_YEAR = 2023  # discovery below, validation from here

# Only the columns the shortlist reads. `IndicatorPanel.at()` materialises all
# seventy-nine per bar, which across five symbols is ~340 million dictionary
# entries and was most of this pass's runtime -- for twelve values a rule
# actually looks at. Adding a rule that needs a new column means adding it
# here; a missing one reads as None, which every rule already treats as
# "warming" rather than as a value.
COLUMNS = (
    "atr_14",
    "natr_14",
    "dollar_volume_20",
    "vwap_rolling",
    "rsi_2",
    "internal_bar_strength",
    "range_vs_atr",
    "volume_ratio_20",
    "bb_width",
    "bb_upper",
    "high_55",
    "high_200",
    "sma_50",
    "sma_200",
    "macd_hist",
    "return_20",
)


@dataclass
class Context:
    """Everything a candidate may look at. All of it causal by construction."""

    symbol: str
    index: int
    bar: Bar
    row: dict[str, Any]
    hour: int
    minute: int
    # Return from the first bar of this UTC day to this bar's close. The
    # intraday-momentum family's whole signal.
    day_return: float
    # Rolling distributions the served columns do not carry.
    bb_width_rank: float | None


@dataclass
class Sample:
    total: float = 0.0
    count: int = 0
    independent_values: list[float] = field(default_factory=list)
    # Last accepted bar index PER SYMBOL. Keying this on the index alone was a
    # bug with a very quiet failure mode: symbols are scanned one after another
    # and each starts its index at zero again, so after the first symbol every
    # later one failed `index >= last_taken + horizon` for its whole history
    # and contributed nothing. The independent sample was silently one symbol's,
    # and `t*` -- the column this package tells everyone to trust -- was
    # computed on a fifth of the data it claimed.
    last_taken: dict[str, int] = field(default_factory=dict)

    def add(self, value: float, index: int, horizon: int, symbol: str = "") -> None:
        self.total += value
        self.count += 1
        if index >= self.last_taken.get(symbol, -(10**9)) + horizon:
            self.independent_values.append(value)
            self.last_taken[symbol] = index

    def document(self, cost: float, drift: float) -> dict[str, Any]:
        if not self.count:
            return {"n": 0}
        mean = self.total / self.count
        values = self.independent_values
        indep_n = len(values)
        result = {
            "n": self.count,
            "gross_mean": mean,
            "net_mean": mean - cost,
            "excess_mean": mean - cost - drift,
            "independent_n": indep_n,
        }
        if indep_n > 2:
            indep_mean = sum(values) / indep_n
            variance = sum((v - indep_mean) ** 2 for v in values) / (indep_n - 1)
            deviation = variance**0.5
            result["independent_net_mean"] = indep_mean - cost
            result["independent_t"] = (
                (indep_mean - cost) / (deviation / (indep_n**0.5)) if deviation else 0.0
            )
        return result


def candidates() -> dict[str, Callable[[Context], bool]]:
    """The shortlist. Add a line here to put a new mechanism in the next scan."""

    def itsm(hour: int, threshold: float) -> Callable[[Context], bool]:
        # Once a day, at a fixed hour, when the day so far has moved enough to
        # be a signal rather than noise. The threshold is what the cost-aware
        # ML literature found necessary: trade only when the forecast magnitude
        # clears the cost, not on the sign alone.
        def rule(ctx: Context) -> bool:
            return ctx.hour == hour and ctx.minute == 0 and ctx.day_return >= threshold

        return rule

    def value(ctx: Context, key: str) -> float | None:
        raw = ctx.row.get(key)
        return None if raw is None else float(raw)

    def donchian(key: str) -> Callable[[Context], bool]:
        def rule(ctx: Context) -> bool:
            high = value(ctx, key)
            return high is not None and ctx.bar.close > high

        return rule

    def volexp(ctx: Context) -> bool:
        span = value(ctx, "range_vs_atr")
        ibs = value(ctx, "internal_bar_strength")
        volume = value(ctx, "volume_ratio_20")
        return (
            span is not None
            and ibs is not None
            and volume is not None
            and span > 2.0
            and ibs > 0.8
            and volume > 3.0
        )

    def squeeze(ctx: Context) -> bool:
        upper = value(ctx, "bb_upper")
        return (
            ctx.bb_width_rank is not None
            and ctx.bb_width_rank <= 0.0
            and upper is not None
            and ctx.bar.close > upper
        )

    def trend(ctx: Context) -> bool:
        slow, fast = value(ctx, "sma_200"), value(ctx, "sma_50")
        hist = value(ctx, "macd_hist")
        return (
            slow is not None
            and fast is not None
            and hist is not None
            and ctx.bar.close > slow
            and fast > slow
            and hist > 0
        )

    def continuation(ctx: Context) -> bool:
        move = value(ctx, "return_20")
        ibs = value(ctx, "internal_bar_strength")
        return move is not None and ibs is not None and move > 0.01 and ibs > 0.7

    def reversion(ctx: Context) -> bool:
        anchor, atr = value(ctx, "vwap_rolling"), value(ctx, "atr_14")
        ibs, rsi = value(ctx, "internal_bar_strength"), value(ctx, "rsi_2")
        if None in (anchor, atr, ibs, rsi) or not atr or ctx.bar.close <= 0:
            return False
        return (
            (anchor - ctx.bar.close) / atr >= 1.5
            and (anchor - ctx.bar.close) / ctx.bar.close >= 0.006
            and ibs <= 0.30
            and rsi <= 15.0
        )

    def itsm_vol(hour: int, multiple: float) -> Callable[[Context], bool]:
        """Intraday momentum with the threshold in the symbol's OWN volatility.

        A fixed 1.5% is a different rule on BTC than on SOL, and it is a
        different rule in 2018 than in 2026. The toll, though, is fixed at
        0.30% however volatile the symbol is -- which is precisely why a
        volatile asset can clear it on a move that a quiet one cannot, and why
        this variant exists. `natr_14` is the average true range as a percentage
        of price per bar, so `natr * 12` is roughly what an hour normally
        moves.
        """

        def rule(ctx: Context) -> bool:
            if ctx.hour != hour or ctx.minute != 0:
                return False
            natr = ctx.row.get("natr_14")
            if natr is None:
                return False
            return ctx.day_return >= multiple * float(natr) / 100.0 * 12

        return rule

    rules: dict[str, Callable[[Context], bool]] = {
        "itsm_12h_vol1": itsm_vol(12, 1.0),
        "itsm_12h_vol2": itsm_vol(12, 2.0),
        "itsm_06h_vol2": itsm_vol(6, 2.0),
        "itsm_06h_0.0%": itsm(6, 0.0),
        "itsm_06h_0.5%": itsm(6, 0.005),
        "itsm_06h_1.5%": itsm(6, 0.015),
        "itsm_12h_0.0%": itsm(12, 0.0),
        "itsm_12h_0.5%": itsm(12, 0.005),
        "itsm_12h_1.5%": itsm(12, 0.015),
        "itsm_18h_1.5%": itsm(18, 0.015),
        "donchian_55": donchian("high_55"),
        "donchian_200": donchian("high_200"),
        "volexp": volexp,
        "squeeze": squeeze,
        "trend": trend,
        "continuation": continuation,
        "reversion": reversion,
    }
    # The drift table: every bar whose hour is H, unconditionally. What each
    # conditional rule above has to beat, hour by hour.
    for hour in (0, 6, 12, 18):
        rules[f"hour_{hour:02d}"] = lambda ctx, h=hour: (
            ctx.hour == h and ctx.minute == 0
        )
    return rules


def scan(
    bars_by_symbol: dict[str, list[Bar]],
    horizons: tuple[int, ...] = HORIZONS,
    bars_per_day: int = 288,
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
    minimum_daily_turnover: float = 10_000_000.0,
    split_year: int = SPLIT_YEAR,
    spec: IndicatorSpec | None = None,
) -> dict[str, Any]:
    """Every candidate, every horizon, both eras. One pass per symbol."""
    spec = spec or IndicatorSpec()
    cost = round_trip_cost(commission_bps, slippage_bps)
    floor = bar_turnover_floor(minimum_daily_turnover, bars_per_day)
    rules = candidates()
    reference = max(horizons)

    samples: dict[tuple[str, str, int], Sample] = {}
    drift: dict[tuple[str, int], Sample] = {}

    for symbol, bars in sorted(bars_by_symbol.items()):
        if len(bars) < reference + 2:
            continue
        panel = panel_for(bars, spec)
        # Bound to the arrays once, so the inner loop indexes instead of
        # rebuilding a dictionary of every column on every bar.
        series = {
            name: panel.columns[name] for name in COLUMNS if name in panel.columns
        }
        widths: deque = deque(maxlen=bars_per_day * 7)
        quiet_threshold: float | None = None
        day_open = None
        current_day = None
        print(f"  {symbol}: {len(bars):,} bars", flush=True)

        for index in range(panel.warmup_bars, len(bars) - reference - 1):
            bar = bars[index]
            row = {
                name: (None if column[index] != column[index] else column[index])
                for name, column in series.items()
            }
            stamp = bar.timestamp
            if stamp.date() != current_day:
                current_day, day_open = stamp.date(), bar.open
            if not day_open:
                continue

            # The squeeze threshold is refreshed once a day rather than sorted
            # on every bar. Sorting a week-long deque per bar is 19 billion
            # comparisons across this universe and it dominated everything else
            # in the pass; a threshold that is at most one day stale is still
            # strictly causal and answers the same question.
            width = row.get("bb_width")
            rank = None
            if width is not None:
                widths.append(float(width))
                if index % bars_per_day == 0 and len(widths) >= bars_per_day:
                    ordered = sorted(widths)
                    quiet_threshold = ordered[len(ordered) // 5]
                if quiet_threshold is not None:
                    rank = 0.0 if float(width) <= quiet_threshold else 1.0

            turnover = row.get("dollar_volume_20")
            if turnover is None or float(turnover) < floor:
                continue
            entry = bars[index + 1].open
            if entry <= 0:
                continue

            era = "validation" if stamp.year >= split_year else "discovery"
            for horizon in horizons:
                value = bars[index + 1 + horizon].open / entry - 1
                drift.setdefault((era, horizon), Sample()).add(
                    value, index, horizon, symbol
                )

            ctx = Context(
                symbol=symbol,
                index=index,
                bar=bar,
                row=row,
                hour=stamp.hour,
                minute=stamp.minute,
                day_return=bar.close / day_open - 1,
                bb_width_rank=rank,
            )
            for name, rule in rules.items():
                if not rule(ctx):
                    continue
                for horizon in horizons:
                    value = bars[index + 1 + horizon].open / entry - 1
                    key = (name, era, horizon)
                    samples.setdefault(key, Sample()).add(value, index, horizon, symbol)

    drift_means = {
        key: (sample.total / sample.count if sample.count else 0.0)
        for key, sample in drift.items()
    }
    report: dict[str, Any] = {
        "round_trip_cost": cost,
        "split_year": split_year,
        "horizons": list(horizons),
        "bars_per_day": bars_per_day,
        "symbols": sorted(bars_by_symbol),
        "drift": {f"{era}|{h}": mean for (era, h), mean in sorted(drift_means.items())},
        "candidates": {},
    }
    for name in rules:
        entry: dict[str, Any] = {}
        for era in ("discovery", "validation"):
            for horizon in horizons:
                sample = samples.get((name, era, horizon))
                if sample is None:
                    continue
                entry[f"{era}|{horizon}"] = sample.document(
                    cost, drift_means.get((era, horizon), 0.0)
                )
        report["candidates"][name] = entry
    return report


def table(report: dict[str, Any], horizon: int | None = None) -> str:
    """Both eras side by side, sorted by the validation excess. Read `excess`."""
    horizons = report["horizons"] if horizon is None else [horizon]
    lines = []
    for h in horizons:
        hours = h / (report["bars_per_day"] / 24)
        lines += [
            "",
            f"=== horizon {h} bars ({hours:.0f}h) · "
            f"cost {report['round_trip_cost']:.2%} · "
            f"drift disc {report['drift'].get(f'discovery|{h}', 0):+.3%} / "
            f"val {report['drift'].get(f'validation|{h}', 0):+.3%} ===",
            f"{'candidate':<16}{'disc n':>8}{'net':>9}{'excess':>9}"
            f"{'val n':>8}{'net':>9}{'excess':>9}{'ind n':>7}{'t*':>7}{'be bps':>8}",
            "-" * 90,
        ]
        rows = []
        for name, entry in report["candidates"].items():
            disc = entry.get(f"discovery|{h}", {})
            val = entry.get(f"validation|{h}", {})
            if not disc.get("n") or not val.get("n"):
                continue
            rows.append((val.get("excess_mean", -1), name, disc, val))
        drift_val = report["drift"].get(f"validation|{h}", 0.0)
        for _, name, disc, val in sorted(rows, reverse=True):
            # The round trip at which this mechanism stops beating a long
            # position: its gross edge over drift, in basis points. This is the
            # number the academic literature quotes as a breakeven cost, and
            # the one to compare against whatever you actually pay.
            breakeven = (val["gross_mean"] - drift_val) * 10_000
            lines.append(
                f"{name:<16}{disc['n']:>8,}{disc['net_mean']:>9.3%}"
                f"{disc['excess_mean']:>9.3%}{val['n']:>8,}{val['net_mean']:>9.3%}"
                f"{val['excess_mean']:>9.3%}{val.get('independent_n', 0):>7,}"
                f"{val.get('independent_t', 0.0):>7.1f}{breakeven:>8.1f}"
            )
    lines += [
        "",
        "be bps = the round trip at which this stops beating a long position,",
        "         in the validation era. Compare it to what you actually pay",
        "         (this laboratory models 30 bps: 10 commission + 5 slippage,",
        "         each way). The published Bitcoin intraday-momentum breakevens",
        "         are 3-10 bps, so agreement here is agreement with the papers.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--interval", default=INTERVAL)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--report", default="research/agent_runs/intraday/survey.json")
    parser.add_argument(
        "--horizons",
        default=",".join(str(h) for h in HORIZONS),
        help="forward horizons in BARS. The toll is fixed per trade, so a "
        "longer hold amortises it over a bigger move -- worth measuring "
        "before concluding that a mechanism is dead rather than mistimed.",
    )
    args = parser.parse_args(argv)

    dataset = IntradayDataset(
        args.data_root,
        LOCK,
        [s for s in args.symbols.split(",") if s],
        interval=args.interval,
    )
    print(f"loading {args.interval} research bars", flush=True)
    bars = dataset.research()
    horizons = tuple(sorted(int(h) for h in args.horizons.split(",") if h.strip()))
    report = scan(bars, horizons=horizons, bars_per_day=dataset.bars_per_day)
    print(table(report))
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str))
        print(f"\nreport: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
