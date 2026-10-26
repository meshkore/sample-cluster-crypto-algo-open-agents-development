"""The market as the strategy and the backtest see it: BTC and ETH on aligned 4h and daily grids."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import data
from .config import BAR_NS, BARS_PER_DAY, COINS, FIRST_YEAR, IMPACT_BOOK_USD


def year_of(ns: np.ndarray) -> np.ndarray:
    """A bar stamped at its close belongs to the year its open is in."""
    return (np.asarray(ns, dtype=np.int64) - 1).astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970


@dataclass
class Market:
    coins: tuple[str, ...]
    grid4: np.ndarray  # 4h close times (ns)
    close4: np.ndarray  # (T4, coins)
    usd4: np.ndarray  # quote volume per 4h bar
    grid1: np.ndarray  # daily close times (ns)
    close1: np.ndarray  # (T1, coins)
    funding4: np.ndarray  # funding rate accrued per 4h bar
    perp4: np.ndarray  # a perpetual existed at that bar
    day_of_bar: np.ndarray  # last daily bar closed before each 4h decision, -1 if none
    impact: np.ndarray  # square-root impact per (year - FIRST_YEAR, coin)

    @property
    def year4(self) -> np.ndarray:
        return year_of(self.grid4)

    @property
    def tradable(self) -> np.ndarray:
        return self.perp4 & np.isfinite(self.close4)


def _panel(frames: dict, cut_ns: int | None):
    grid = np.unique(np.concatenate([np.asarray(f.index, dtype=np.int64) for f in frames.values()]))
    if cut_ns is not None:
        grid = grid[grid < cut_ns]
    grid = grid[year_of(grid) >= FIRST_YEAR]
    cols = {c: np.column_stack([frames[k][c].reindex(grid).values for k in COINS]).astype(float) for c in ("close", "usd")}
    return grid, cols["close"], cols["usd"]


def _funding_panel(grid4: np.ndarray, settlements: dict) -> tuple[np.ndarray, np.ndarray]:
    """Each 8h settlement is spread over two 4h bars: rate / 2 of the last settlement at or before the bar's open."""
    opens = grid4 - BAR_NS["4h"]
    rate = np.zeros((len(grid4), len(COINS)))
    live = np.zeros((len(grid4), len(COINS)), dtype=bool)
    for j, coin in enumerate(COINS):
        t = np.asarray(settlements[coin].index, dtype=np.int64)
        i = np.searchsorted(t, opens, side="right") - 1
        rate[i >= 0, j] = settlements[coin].values[i[i >= 0]] / 2
        live[:, j] = grid4 >= t[0]
    return rate, live


def impact_table(close4: np.ndarray, usd4: np.ndarray, year4: np.ndarray, last_year: int = 2100) -> np.ndarray:
    """Daily volatility x sqrt(book / 3 / median daily dollar volume), measured on the previous year."""
    n = BARS_PER_DAY
    out = np.zeros((last_year - FIRST_YEAR, close4.shape[1]))
    for i, y in enumerate(range(FIRST_YEAR, last_year)):
        for j in range(close4.shape[1]):
            sel = (year4 == y - 1) & np.isfinite(close4[:, j])
            if sel.sum() < 30 * n:
                sel = (year4 == y) & np.isfinite(close4[:, j])
            if sel.sum() < 10 * n:
                out[i, j] = 0.003
                continue
            daily_close = close4[sel, j][n - 1 :: n]
            daily_usd = usd4[sel, j][: (sel.sum() // n) * n].reshape(-1, n).sum(axis=1)
            vol = np.std(np.diff(np.log(daily_close))) if len(daily_close) > 2 else 0.05
            out[i, j] = float(vol * np.sqrt(IMPACT_BOOK_USD / 3 / max(np.median(daily_usd), 1.0)))
    return out


def load(cut_ns: int | None = None) -> Market:
    """Download (or read from cache) and align everything the system needs."""
    grid4, close4, usd4 = _panel({c: data.klines(c, "4h") for c in COINS}, cut_ns)
    grid1, close1, _ = _panel({c: data.klines(c, "1d") for c in COINS}, cut_ns)
    funding4, perp4 = _funding_panel(grid4, {c: data.funding(c) for c in COINS})
    prev = np.r_[grid4[0], grid4[:-1]]
    return Market(
        coins=COINS,
        grid4=grid4,
        close4=close4,
        usd4=usd4,
        grid1=grid1,
        close1=close1,
        funding4=funding4,
        perp4=perp4,
        day_of_bar=np.searchsorted(grid1, prev, side="right") - 1,
        impact=impact_table(close4, usd4, year_of(grid4)),
    )
