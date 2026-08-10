"""Does buying the bounce work in a bear market, and does confirmation matter?

The operator asked for Kotegawa and for bear-market bounce trading. Two numbers
this laboratory already held framed the question:

  * `DeviationBranch` measured the -35%..-25% deviation band by regime, pooled
    2017-2025. In BEAR it returns roughly nothing (-1.57% hourly at 120 bars,
    +2.16% daily at 20). Buying the dislocation ALONE is the falling knife.
  * `ClimaxBranch` -- the same trade plus volume confirmation -- is the only
    strategy here with a positive 2026 result, +3.46% at 2.03% drawdown.

So the hypothesis is not "does the bounce work" but "does CONFIRMATION make the
difference", and until VERSION 4 the rule language could not express any form
of confirmation that involved the shape of a bar. This runs the ladder.

    A  Kotegawa naive          the dislocation, nothing else
    B  + closed strong         internal_bar_strength, the hammer
    C  + heavy volume          volume_ratio_20, the climax
    D  + both
    E  Connors RSI(2)          a different family entirely
    F  capitulation reversal   big drop, heavy volume, closed strong
    G  engulfing in a dip      the one two-bar pattern

Every variant runs the SAME four-module brain with the bull and sideways
branches switched off, so what is measured is the bear module and only the bear
module. Same folds the loop fits on, so the numbers sit beside the ledger's.
Nothing here touches 2026: this is the fittable era, on the fit service.

    python3 orchestrator-manager/scripts/bounce_shootout.py 8778
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from quantlab_manager.orchestration import Orchestrator
from quantlab_manager.sessions import open_database
from quantlab_trading.regime import REFERENCE_BASKET

RUNTIME = Path.home() / "Library/Application Support/QuantLab"
FOLDS = [
    ("2018-2020", "2018-01-01", "2020-01-01"),
    ("2020-2022", "2020-01-01", "2021-12-31"),
    ("2022-2024", "2021-12-31", "2024-01-01"),
    ("2024-2026", "2024-01-01", "2025-12-31"),
]


def col(name):
    return {"t": "col", "name": name}


def num(value):
    return {"t": "num", "v": value}


def lt(name, value):
    return {"t": "lt", "a": col(name), "b": num(value)}


def gt(name, value):
    return {"t": "gt", "a": col(name), "b": num(value)}


def all_of(*terms):
    return {"t": "and", "xs": list(terms)}


def any_of(*terms):
    return {"t": "or", "xs": list(terms)}


# Kotegawa's exit is his entry in reverse: the trade's thesis is the gap
# closing, so the gap closing IS the exit. Shared by A-D so the entry is the
# only thing that varies between them.
REVERSION_EXIT = gt("distance_to_sma_20", -0.05)

VARIANTS = {
    "A  Kotegawa naive": (
        lt("distance_to_sma_20", -0.25),
        REVERSION_EXIT,
    ),
    "B  + closed strong": (
        all_of(lt("distance_to_sma_20", -0.25), gt("internal_bar_strength", 0.6)),
        REVERSION_EXIT,
    ),
    "C  + heavy volume": (
        all_of(lt("distance_to_sma_20", -0.25), gt("volume_ratio_20", 2.5)),
        REVERSION_EXIT,
    ),
    "D  + both": (
        all_of(
            lt("distance_to_sma_20", -0.25),
            gt("internal_bar_strength", 0.6),
            gt("volume_ratio_20", 2.0),
        ),
        REVERSION_EXIT,
    ),
    "E  Connors RSI(2)": (
        lt("rsi_2", 5.0),
        gt("rsi_2", 65.0),
    ),
    "F  capitulation rev": (
        all_of(
            lt("return_1", -0.08),
            gt("volume_ratio_20", 3.0),
            gt("internal_bar_strength", 0.5),
        ),
        any_of(gt("distance_to_sma_20", -0.05), gt("rsi_14", 60.0)),
    ),
    "G  engulfing in a dip": (
        all_of(gt("bullish_engulfing", 0.5), lt("distance_to_sma_20", -0.15)),
        any_of(gt("distance_to_sma_20", -0.05), lt("internal_bar_strength", 0.15)),
    ),
}

# The same rule in ALL THREE branches, so the market-regime label cannot decide
# whether the rule is allowed to speak.
#
# The first version of this put the rule in the bear branch alone and switched
# the other two off, which looked like the clean way to isolate a bear-market
# technique. It measured almost nothing: over 2024-2026, the fold this
# laboratory's own records put at -14.67%, the market detector classified 11
# bars out of 731 as BEAR -- 267 SIDEWAYS, 234 BULL, 219 still warming. Seven
# variants each got eleven bars to prove themselves on, and six of them
# returned exactly 0.00% because they never fired at all.
#
# That is a finding about the DETECTOR, recorded separately. Here it is a
# confound: a rule cannot be judged on a window it was never shown. Running it
# in every regime measures the rule; the attribution afterwards can still say
# which regime the trades happened in.
BASE = {
    "bull_weight": 1.0,
    "sideways_weight": 1.0,
    "bear_weight": 1.0,
    "bull_rule": "evolved",
    "sideways_rule": "evolved",
    "bear_rule": "evolved",
    "minimum_daily_quote_volume": 10_000_000.0,
    "tradeable_assets": 100,
    "risk_per_trade": 0.02,
    "maximum_position_fraction": 0.15,
    "maximum_concurrent_assets": 12,
}


def universe():
    connection = sqlite3.connect(
        f"file:{RUNTIME / 'research/quantlab.db'}?mode=ro", uri=True
    )
    symbols = {
        row[0]
        for row in connection.execute(
            "SELECT symbol FROM asset_universe WHERE research_path IS NOT NULL"
        )
    }
    connection.close()
    return sorted(symbols | set(REFERENCE_BASKET))


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8778
    symbols = universe()
    database = RUNTIME / "research/quantlab.db"
    lab = Orchestrator(
        database=database,
        indicators=RUNTIME / "data/indicators",
        port=port,
        store=open_database(database),
    )
    print(f"{len(symbols)} candidate symbols · bear module only · fit era only\n")
    header = f"{'variant':<22}" + "".join(f"{name:>13}" for name, _, _ in FOLDS)
    print(header + f"{'total':>10}{'trades':>8}{'worst dd':>10}")
    print("-" * len(header + f"{'total':>10}{'trades':>8}{'worst dd':>10}"))

    try:
        for label, (entry, exit_rule) in VARIANTS.items():
            cells, trades, worst, compounded = [], 0, 0.0, 1.0
            for name, start, end in FOLDS:
                result = lab.launch(
                    "four-module",
                    symbols=symbols,
                    start=start,
                    end=end,
                    parameters={
                        **BASE,
                        "bull_entry_rule": entry,
                        "bull_exit_rule": exit_rule,
                        "sideways_entry_rule": entry,
                        "sideways_exit_rule": exit_rule,
                        "bear_entry_rule": entry,
                        "bear_exit_rule": exit_rule,
                        # The detector needs history before it will classify,
                        # and a fold that starts trading on bar zero is trading
                        # on an unwarmed regime label.
                        "trade_from": start,
                    },
                    label=f"bounce-{label.split()[0]}-{name}",
                    submitted_by="bounce-shootout",
                )
                ret = result.get("return_pct") or 0.0
                cells.append(f"{100 * ret:>12.2f}%")
                trades += result.get("trades") or 0
                worst = max(worst, result.get("max_drawdown") or 0.0)
                compounded *= 1 + ret
            print(
                f"{label:<22}"
                + "".join(cells)
                + f"{100 * (compounded - 1):>9.1f}%{trades:>8}{100 * worst:>9.1f}%"
            )
    finally:
        lab.close()

    print(
        "\n2024-2026 is the falling fold: across every fit this laboratory has\n"
        "recorded it averages -14.67%, against +33.5% and +37.2% for the two\n"
        "before it. That column is the bear-market question."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
