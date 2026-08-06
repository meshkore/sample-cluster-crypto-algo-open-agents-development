"""Choosing which coins we trade, and being honest about how they were chosen.

The operator wants the top ~100 by capitalisation *today*, because those are the
coins the laboratory will actually trade in 2026, and because the large moves
often come from a Solana rather than from Bitcoin.

**We do not hold market-cap data.** Nothing in this repository knows a
circulating supply. What we do hold, measured bar by bar, is dollar turnover,
and turnover is the honest proxy available offline: it ranks the same names in
roughly the same order and it is what our own liquidity constraint is expressed
in anyway. Where it disagrees with capitalisation is at the edges -- a coin with
a huge float and thin trading ranks lower here than on a market-cap table.

If a true ranking matters, `select_universe` takes an explicit `symbols` list,
so the operator can paste one from any source and it becomes the universe.

**The survivorship point, stated once.** Selecting today's leaders and then
backtesting them through history is survivorship bias: the coins that failed are
absent, so historical returns come out flatter than a live trader would have
experienced. That is a real distortion and it inflates the past. It is also the
right choice for the operator's purpose -- the question is not "what would I
have earned" but "how does this behave on the coins I will trade" -- so the bias
is accepted deliberately rather than overlooked. Any pre-2026 number produced on
this universe carries it.

Stablecoins are excluded outright. They dominate turnover, they cannot trend,
and a long-only trend system holding one is holding cash with extra steps.
"""

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any
import json
import sqlite3

from quantlab_backtester.data import DataManager

from .config import Settings

# Quoted in USDT, so the base asset is what matters. Anything pegged to a fiat
# unit is here: it has turnover and no trend, which is the worst possible
# combination for a ranking built on turnover.
STABLE_BASES = {
    "USDC",
    "FDUSD",
    "TUSD",
    "BUSD",
    "DAI",
    "USDP",
    "USTC",
    "UST",
    "EURI",
    "EUR",
    "GBP",
    "AEUR",
    "PYUSD",
    "USDE",
    "SUSD",
    "FRAX",
    "LUSD",
    "USD1",
    "XUSD",
    "RLUSD",
    "USDD",
    "USDS",
}


def _base(symbol: str) -> str:
    for quote in ("USDT", "USDC", "BUSD", "FDUSD", "TUSD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)]
    return symbol


def rank_by_turnover(
    settings: Settings,
    lookback_days: int = 90,
    minimum_bars: int = 250,
) -> list[dict[str, Any]]:
    """Every usable symbol, ranked by recent median dollar turnover.

    Median rather than mean: one listing-day volume spike would otherwise carry
    a coin into the top ten on a single bar.
    """
    connection = sqlite3.connect(f"file:{settings.database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT symbol, research_path FROM asset_universe "
            "WHERE research_path IS NOT NULL ORDER BY symbol"
        ).fetchall()
    finally:
        connection.close()

    ranked: list[dict[str, Any]] = []
    for row in rows:
        symbol = row["symbol"]
        if _base(symbol).upper() in STABLE_BASES:
            continue
        bars = DataManager.load_csv(row["research_path"])
        if len(bars) < minimum_bars:
            continue
        window = bars[-lookback_days:]
        turnover = median([bar.close * bar.volume for bar in window]) if window else 0.0
        ranked.append(
            {
                "symbol": symbol,
                "median_turnover": turnover,
                "bars": len(bars),
                "first_bar": bars[0].timestamp.date().isoformat(),
                "last_bar": bars[-1].timestamp.date().isoformat(),
            }
        )
    ranked.sort(key=lambda entry: entry["median_turnover"], reverse=True)
    for position, entry in enumerate(ranked, 1):
        entry["rank"] = position
    return ranked


def select_universe(
    settings: Settings,
    size: int = 100,
    symbols: list[str] | None = None,
    minimum_bars: int = 250,
    lookback_days: int = 90,
) -> dict[str, Any]:
    """The trading universe: an explicit list if given, otherwise the top `size`."""
    ranked = rank_by_turnover(settings, lookback_days, minimum_bars)
    by_symbol = {entry["symbol"]: entry for entry in ranked}

    if symbols:
        chosen, missing = [], []
        for symbol in symbols:
            entry = by_symbol.get(symbol)
            (chosen if entry else missing).append(entry or symbol)
        return {
            "source": "explicit",
            "size": len(chosen),
            "symbols": [entry["symbol"] for entry in chosen],
            "detail": chosen,
            "missing": missing,
            "survivorship": "explicit list; selection bias is the caller's to state",
        }

    chosen = ranked[:size]
    return {
        "source": f"median dollar turnover over the last {lookback_days} bars",
        "size": len(chosen),
        "symbols": [entry["symbol"] for entry in chosen],
        "detail": chosen,
        "missing": [],
        "candidates": len(ranked),
        "survivorship": (
            "today's leaders, backtested through history: coins that failed are "
            "absent, so pre-2026 returns are flattered. Accepted deliberately -- "
            "these are the coins we will trade in 2026."
        ),
    }


def save_universe(path: Path | str, selection: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selection, indent=2, default=str) + "\n")
    return path


def load_universe(path: Path | str) -> list[str]:
    return json.loads(Path(path).read_text())["symbols"]


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="orchestrator-manager/config/default.json", type=Path
    )
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--minimum-bars", type=int, default=250)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--save", type=Path, default=None)
    parser.add_argument("--show", type=int, default=30)
    args = parser.parse_args(argv)

    settings = Settings.load(args.config)
    selection = select_universe(
        settings, size=args.size, symbols=args.symbols, minimum_bars=args.minimum_bars
    )
    print(f"source     {selection['source']}")
    print(
        f"selected   {selection['size']} of {selection.get('candidates', '?')} candidates"
    )
    if selection["missing"]:
        print(f"missing    {', '.join(map(str, selection['missing']))}")
    print(f"\n{'#':>4}  {'symbol':<14}{'median turnover':>18}  {'bars':>6}  history")
    for entry in selection["detail"][: args.show]:
        print(
            f"{entry['rank']:>4}  {entry['symbol']:<14}"
            f"{entry['median_turnover']:>18,.0f}  {entry['bars']:>6}  "
            f"{entry['first_bar']} .. {entry['last_bar']}"
        )
    if selection["size"] > args.show:
        print(f"      ... {selection['size'] - args.show} more")
    print(f"\nsurvivorship: {selection['survivorship']}")
    if args.save:
        print(f"\nsaved {save_universe(args.save, selection)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
