"""Market health: a model apart from the trading system that can stop it (operator, 2026-10-14).

*"A safety system, completely apart from the trading system, that notices something is going
on - the hit rate drops a lot, the market turns, positions start losing in a sustained or very
fast way because of a crash - and can stop the trading system to save funds. And an alarm
indicator: a bar from green to red."*

It reads only 15-minute closes of the 14-coin universe (BTC included) and, optionally, the
book's closed trades. No model is fitted: every component is a fixed, explainable mapping
from one measurement to 0-100 (100 = healthy). Components:

  crash     fastest drop of BTC or the equal-weight index over 1h / 4h / 24h, in units of
            its own 30-day volatility measured BEFORE the move (z); -1 sigma -> 100, -5 -> 0
  trend     the index's 7-day return in the same units; -1 -> 100, -4 -> 0
  vol       index realised vol over the last day / its 90-day level before it; 1.5x -> 100,
            4x -> 0 (half weight when the index is up on the day)
  breadth   share of coins down more than 1 own-sigma over the last 24 h; 40% -> 100, 90% -> 0
  corr      mean pairwise correlation of the coins' 15m returns over the last day, only while
            the index is down on the day ("falling together"); 0.55 -> 100, 0.85 -> 0
  book      (optional) the book's last 20 trades closed within 14 days: hit rate 45% -> 100, 20% -> 0;
            consecutive losses 3 -> 100, 10 -> 0; their summed return 0 -> 100, -40% -> 0;
            the worst of the three

score = half the weighted mean (crash x2, the rest x1) + half the worst component, so one
severe reading drags the score down and a broad deterioration does too.

The score (the green-to-red bar) is the MARKET's health: healthy >= 60, caution >= 40,
danger below. "halt" is the guard's state, not a score band. Every number above is fixed by
judgement; only the guard was chosen, on 2020-2025 books of the pinned release
(research/system10/HEALTH.md):

  * halting on the market score COSTS money: release 31 buys the capitulation bar (its best
    trades, e.g. 2023-06-10 and 2023-08-17 were entered on the bar the score hit 0);
  * the guard that paid on 2020-2025 is the book's losing streak: when the book score of
    the last 20 trades closed within 14 days falls below 40, close everything and stay flat
    until it is back at 50 (trades older than 14 days drop out, so a halt expires);
  * 2026, read once afterwards: it halved both the return and the drawdown (+9.1% / DD 8.4%
    against +22.4% / 17.3%). So it is ADVISORY: `recommendation` says "halt", nothing
    stops the paper book (`enforced: false`).

Backtest: `Guard` is the optional hook `conditions.book_year(..., guard=...)` reads.
Live: `python -m system010_conditioned_rl.health --once` (or `--loop`) writes
research/system10/paper/health_state.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "trading-system/backtester/data"
UNIVERSE = REPO / "research/system06/universe.json"
PAPER = REPO / "research/system10/paper"
STATE = PAPER / "health_state.json"
CYCLE_S = 15 * 60

BAR_NS = 15 * 60 * 10**9
DAY = 96
VOL_WIN = 30 * DAY          # the volatility a move is measured against
BASE_WIN = 90 * DAY         # the volatility level a spike is measured against
CRASH_K = (4, 16, 96)       # 1 h, 4 h, 24 h
TREND_K = 7 * DAY
WEIGHTS = {"crash": 2.0, "trend": 1.0, "vol": 1.0, "breadth": 1.0, "corr": 1.0, "book": 1.0}
# component -> (value that scores 100, value that scores 0)
MAP = {"crash": (-1.0, -5.0), "trend": (-1.0, -4.0), "vol": (1.5, 4.0), "breadth": (0.4, 0.9),
       "corr": (0.55, 0.85), "hit": (0.45, 0.20), "losses": (3.0, 10.0), "pnl": (0.0, -0.40)}
BOOK_N = 20
BOOK_DAYS = 14              # only trades closed in the last two weeks count (a halt can expire)

LEVELS = (("healthy", 60.0), ("caution", 40.0), ("danger", None))
# Chosen on 2020-2025 (HEALTH.md): max profit and optimal (return^2 / max DD) agree.
CHOSEN = {"guard": "book", "action": "flatten", "halt_below": 40.0, "resume_gap": 10.0,
          "book_n": BOOK_N, "book_days": BOOK_DAYS, "enforced": False}


def lin(x, good: float, bad: float):
    """0..100: `good` (and beyond) -> 100, `bad` (and beyond) -> 0, linear between."""
    return np.clip(100.0 * (np.asarray(x, dtype=float) - bad) / (good - bad), 0.0, 100.0)


def level_of(score: float, halted: bool = False) -> str:
    if halted:
        return "halt"
    if score >= LEVELS[0][1]:
        return "healthy"
    return "caution" if score >= LEVELS[1][1] else "danger"


# ---------------------------------------------------------------------------- rolling tools

def _rsum(x: np.ndarray, w: int) -> np.ndarray:
    """Trailing sum over w rows (axis 0), NaN for the first w-1 rows."""
    c = np.cumsum(np.vstack([np.zeros((1,) + x.shape[1:]), x]), axis=0)
    out = np.full(x.shape, np.nan)
    out[w - 1:] = c[w:] - c[:-w]
    return out


def _rstd(r: np.ndarray, w: int) -> np.ndarray:
    """Trailing std of r over w rows; rows with any NaN in the window are NaN."""
    bad = _rsum(np.isnan(r).astype(float), w) > 0
    z = np.nan_to_num(r)
    m1, m2 = _rsum(z, w) / w, _rsum(z * z, w) / w
    out = np.sqrt(np.maximum(m2 - m1 * m1, 0.0))
    out[bad] = np.nan
    return out


def _lag(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(x.shape, np.nan)
    out[k:] = x[:-k]
    return out


def _ret(logp: np.ndarray, k: int) -> np.ndarray:
    out = np.full(logp.shape, np.nan)
    out[k:] = logp[k:] - logp[:-k]
    return out


# ---------------------------------------------------------------------------- the market

def align(series: dict) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """{symbol: (ns, close)} -> (grid ns, T x S closes, symbols). The grid is BTC's bars; a
    coin's missing bar carries its last close, NaN before its first."""
    syms = ["BTCUSDT"] + [s for s in series if s != "BTCUSDT"]
    grid = np.asarray(series["BTCUSDT"][0], dtype=np.int64)
    close = np.full((len(grid), len(syms)), np.nan)
    for j, s in enumerate(syms):
        ns, c = np.asarray(series[s][0], dtype=np.int64), np.asarray(series[s][1], dtype=float)
        i = np.searchsorted(ns, grid, side="right") - 1
        ok = i >= 0
        close[ok, j] = c[i[ok]]
    return grid, close, syms


def market(grid: np.ndarray, close: np.ndarray) -> dict:
    """Every market component for every bar (causal: bar t reads closes up to t).
    Returns {"ns", name: (value array, score array) ...}."""
    T, S = close.shape
    lp = np.log(np.maximum(close, 1e-12))
    r = np.diff(lp, axis=0, prepend=np.nan)                   # T x S, NaN before listing
    have = np.isfinite(r)
    n = have.sum(axis=1)
    idx_r = np.where(n > 0, np.nansum(r, axis=1) / np.maximum(n, 1), 0.0)
    idx_lp = np.cumsum(np.nan_to_num(idx_r))
    btc_lp = lp[:, 0]

    def zmove(logp, rets, k):
        sig = _lag(_rstd(rets[:, None], VOL_WIN)[:, 0], k)
        return _ret(logp, k) / (sig * np.sqrt(k))

    crash = np.full(T, np.inf)
    for k in CRASH_K:
        crash = np.fmin(crash, np.fmin(zmove(btc_lp, r[:, 0], k), zmove(idx_lp, idx_r, k)))
    crash[~np.isfinite(crash)] = 0.0
    trend = np.nan_to_num(zmove(idx_lp, idx_r, TREND_K))
    day_up = np.nan_to_num(_ret(idx_lp, DAY)) >= 0

    v1 = _rstd(idx_r[:, None], DAY)[:, 0]
    base = _lag(_rstd(idx_r[:, None], BASE_WIN)[:, 0], DAY)
    vol = np.nan_to_num(v1 / base, nan=1.0)
    vol_score = lin(vol, *MAP["vol"])
    vol_score = np.where(day_up, 100 - (100 - vol_score) / 2, vol_score)

    sig_c = _lag(_rstd(r, VOL_WIN), DAY) * np.sqrt(DAY)
    r96 = _ret(lp, DAY)
    ok = np.isfinite(sig_c) & np.isfinite(r96)
    falling = (r96 < -sig_c) & ok
    nb = ok.sum(axis=1)
    breadth = np.where(nb >= 3, falling.sum(axis=1) / np.maximum(nb, 1), 0.0)

    # mean pairwise correlation over the last day, among coins with a full window
    full = _rsum((~have).astype(float), DAY) == 0
    z = np.nan_to_num(r)
    m = _rsum(z, DAY) / DAY
    sd = np.sqrt(np.maximum(_rsum(z * z, DAY) / DAY - m * m, 0.0))
    csum = np.zeros(T)
    cnt = np.zeros(T)
    for i in range(S):
        prod = _rsum(z[:, i:i + 1] * z[:, i + 1:], DAY) / DAY if i + 1 < S else None
        if prod is None:
            break
        cov = prod - m[:, i:i + 1] * m[:, i + 1:]
        den = sd[:, i:i + 1] * sd[:, i + 1:]
        pair_ok = full[:, i:i + 1] & full[:, i + 1:] & (den > 0)
        c = np.where(pair_ok, cov / np.where(den > 0, den, 1.0), 0.0)
        csum += c.sum(axis=1)
        cnt += pair_ok.sum(axis=1)
    corr = np.where(cnt >= 3, csum / np.maximum(cnt, 1), 0.0)
    corr_score = np.where(day_up, 100.0, lin(corr, *MAP["corr"]))

    return {"ns": np.asarray(grid, dtype=np.int64),
            "crash": (crash, lin(crash, *MAP["crash"])),
            "trend": (trend, lin(trend, *MAP["trend"])),
            "vol": (vol, vol_score),
            "breadth": (breadth, lin(breadth, *MAP["breadth"])),
            "corr": (corr, corr_score)}


def book_component(returns) -> tuple[dict, float]:
    """The book's last BOOK_N closed trades -> (values, score)."""
    a = np.asarray(list(returns)[-BOOK_N:], dtype=float)
    if len(a) < 5:
        return {"hit_rate": None, "losses_in_row": 0, "pnl": 0.0}, 100.0
    hit = float((a > 0).mean())
    run = 0
    for x in a[::-1]:
        if x > 0:
            break
        run += 1
    pnl = float(a.sum())
    s = min(float(lin(hit, *MAP["hit"])), float(lin(run, *MAP["losses"])), float(lin(pnl, *MAP["pnl"])))
    return {"hit_rate": round(hit, 3), "losses_in_row": run, "pnl": round(pnl, 4)}, s


def combine(scores: dict) -> np.ndarray | float:
    """Half the weighted mean, half the worst."""
    keys = list(scores)
    w = np.array([WEIGHTS[k] for k in keys])
    stack = np.stack([np.asarray(scores[k], dtype=float) for k in keys])
    mean = np.tensordot(w / w.sum(), stack, axes=1)
    return 0.5 * mean + 0.5 * stack.min(axis=0)


def history(series: dict) -> dict:
    """Vectorised: {symbol: (ns, close)} -> ns, score, and every component, per bar."""
    grid, close, _ = align(series)
    mk = market(grid, close)
    names = [k for k in mk if k != "ns"]
    score = combine({k: mk[k][1] for k in names})
    return {"ns": mk["ns"], "score": score, **{k: mk[k] for k in names}}


# ---------------------------------------------------------------------------- the guard

class Guard:
    """The hook `conditions.book_year(guard=...)` calls once per bar with (bar ns, the
    book's closed trade returns so far); it returns "trade", "block" (no new entries or
    adds) or "flatten" (close everything and block). Hysteresis: a state is left only when
    the score is back above its threshold + `resume_gap`. A fresh Guard per book.

    Variants studied (HEALTH.md): `smooth` > 1 reads the trailing mean of the market parts
    over that many bars (a sustained deterioration, not one bar); `exclude` drops market
    components; `use_book` adds the book component to the score; `book_only` reads the
    book component alone."""

    def __init__(self, hist: dict, block_below: float | None = None, halt_below: float | None = None,
                 resume_gap: float = 15.0, use_book: bool = False, smooth: int = 1,
                 exclude: tuple = (), book_only: bool = False):
        self.ns = hist["ns"]
        names = [k for k in hist if k not in ("ns", "score") and k not in exclude]
        w = np.array([WEIGHTS[k] for k in names])
        stack = np.stack([hist[k][1] for k in names])
        self.wsum, self.wtot = (w[:, None] * stack).sum(axis=0), w.sum()
        self.worst = stack.min(axis=0)
        if smooth > 1:
            self.wsum = np.nan_to_num(_rsum(self.wsum[:, None], smooth)[:, 0] / smooth, nan=self.wtot * 100)
            self.worst = np.nan_to_num(_rsum(self.worst[:, None], smooth)[:, 0] / smooth, nan=100.0)
        self.block_below, self.halt_below, self.gap, self.use_book = block_below, halt_below, resume_gap, use_book
        self.book_only = book_only
        self.blocked = self.halted = False
        self.log: list[tuple[int, str, float]] = []       # (ns, state entered, score)
        self._closed_at: list[int] = []                   # when each of the book's trades closed

    def score_at(self, t_ns: int, trades) -> float:
        if self.book_only:
            return book_component(trades)[1]
        i = int(np.searchsorted(self.ns, t_ns, side="right") - 1)
        if i < 0:
            return 100.0
        wsum, wtot, worst = self.wsum[i], self.wtot, self.worst[i]
        if self.use_book:
            _, b = book_component(trades)
            wsum, wtot, worst = wsum + WEIGHTS["book"] * b, wtot + WEIGHTS["book"], min(worst, b)
        return float(0.5 * wsum / wtot + 0.5 * worst)

    def __call__(self, t_ns: int, trades) -> str:
        if self.block_below is None and self.halt_below is None:
            return "trade"
        recent = ()
        if self.use_book or self.book_only:
            self._closed_at += [t_ns] * (len(trades) - len(self._closed_at))
            cut = t_ns - BOOK_DAYS * 96 * BAR_NS
            k = int(np.searchsorted(self._closed_at, cut))
            recent = trades[max(k, len(trades) - BOOK_N):]
        s = self.score_at(t_ns, recent)
        if self.halt_below is not None:
            if not self.halted and s < self.halt_below:
                self.halted = True
                self.log.append((t_ns, "halt", s))
            elif self.halted and s >= self.halt_below + self.gap:
                self.halted = False
                self.log.append((t_ns, "resume", s))
        if self.block_below is not None:
            if not self.blocked and s < self.block_below:
                self.blocked = True
                self.log.append((t_ns, "block", s))
            elif self.blocked and s >= self.block_below + self.gap:
                self.blocked = False
                self.log.append((t_ns, "unblock", s))
        return "flatten" if self.halted else "block" if self.blocked else "trade"


# ---------------------------------------------------------------------------- live

def _latest_csv(directory: Path) -> Path | None:
    """The cached CSV reaching furthest forward (by its manifest's observed_end)."""
    if not directory.is_dir():
        return None
    best = None
    mans = sorted(directory.glob("*.manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    for mp in mans:
        try:
            m = json.loads(mp.read_text())
            end, csv = m["audit"]["observed_end"], mp.with_name(m["file"])
        except (OSError, ValueError, KeyError):
            continue
        if csv.exists() and (best is None or end > best[0]):
            best = (end, csv)
    return best[1] if best else None


def _read(path: Path, tail: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    import pandas as pd
    df = pd.read_csv(path, usecols=["timestamp", "close"])
    if tail:
        df = df.iloc[-tail:]
    ns = pd.DatetimeIndex(pd.to_datetime(df["timestamp"], utc=True)).as_unit("ns").asi8
    return ns, df["close"].to_numpy(dtype=float)


def load_recent(days: int = 130) -> dict:
    """The last `days` of 15m closes per universe coin, straight from the candle cache that
    the system 06 live process keeps current (no download, no World)."""
    syms = json.loads(UNIVERSE.read_text())["symbols"]
    need = days * DAY
    out = {}
    for s in syms:
        fwd = _latest_csv(DATA / "forward/processed/binance" / s / "15m")
        ns, c = _read(fwd) if fwd else (np.zeros(0, np.int64), np.zeros(0))
        if len(ns) < need:
            res = _latest_csv(DATA / "research/processed/binance" / s / "15m")
            if res:
                rns, rc = _read(res, need)
                keep = rns < (ns[0] if len(ns) else np.iinfo(np.int64).max)
                ns, c = np.r_[rns[keep], ns], np.r_[rc[keep], c]
        if len(ns):
            out[s] = (ns[-need:], c[-need:])
    return out


def paper_trades() -> list[float]:
    """Closed-trade returns of the paper book over the last BOOK_DAYS, oldest first, from its SELL fills."""
    p = PAPER / "paper_state.json"
    if not p.is_file():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    cut = datetime.fromtimestamp(time.time() - BOOK_DAYS * 86400, timezone.utc).isoformat(timespec="seconds")
    rows = [o for o in doc.get("orders", []) if o.get("side") == "SELL" and "realised" in o and o["at"] >= cut]
    rows.sort(key=lambda o: o["at"])
    return [o["realised"] / max(o["notional"] - o["realised"], 1e-9) for o in rows]


NOTES = {
    "crash": "fastest 1h/4h/24h drop of BTC or the coin index, in sigmas of its prior 30-day volatility",
    "trend": "coin index 7-day return in sigmas",
    "vol": "coin index volatility over the last day vs its 90-day level (x)",
    "breadth": "share of coins down more than one own-sigma over 24 h",
    "corr": "mean pairwise correlation of the coins over the last day (counts only on a down day)",
    "book": "paper book's last 20 closed trades (14 days): hit rate, losses in a row, summed return; drives the guard, not the score",
}


def _previous_halt() -> bool:
    try:
        return bool(json.loads(STATE.read_text(encoding="utf-8")).get("guard", {}).get("halted"))
    except (OSError, ValueError, AttributeError):
        return False


def current(series: dict | None = None, trades: list[float] | None = None,
            was_halted: bool | None = None) -> dict:
    """The health now, as written to health_state.json. The guard's hysteresis carries over
    from the previous state file."""
    series = series if series is not None else load_recent()
    h = history(series)
    i = len(h["ns"]) - 1
    comps, scores = [], {}
    for k in ("crash", "trend", "vol", "breadth", "corr"):
        v, sc = float(h[k][0][i]), float(h[k][1][i])
        scores[k] = sc
        comps.append({"name": k, "value": round(v, 4), "score": round(sc, 1), "note": NOTES[k]})
    trades = paper_trades() if trades is None else trades
    vals, b = book_component(trades)
    comps.append({"name": "book", "value": vals, "score": round(b, 1), "note": NOTES["book"]})
    score = float(combine(scores))
    halted = _previous_halt() if was_halted is None else was_halted
    th, gap = CHOSEN["halt_below"], CHOSEN["resume_gap"]
    halted = b < th + gap if halted else b < th
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bar": datetime.fromtimestamp(int(h["ns"][i]) / 1e9, timezone.utc).isoformat(timespec="seconds"),
            "bar_age_min": round((time.time() - int(h["ns"][i]) / 1e9) / 60, 1),
            "score": round(score, 1), "level": level_of(score, halted),
            "recommendation": "halt" if halted else "trade",
            "guard": {"halted": halted, "book_score": round(b, 1), "halt_below": th, "resume_at": th + gap},
            "components": comps,
            "thresholds": {**CHOSEN, "levels": {"healthy": LEVELS[0][1], "caution": LEVELS[1][1]}},
            "coins": len(series)}


def write_state(doc: dict) -> None:
    PAPER.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    for _ in range(10):
        try:
            os.replace(tmp, STATE)
            return
        except PermissionError:
            time.sleep(0.5)


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 market health -> health_state.json")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true")
    g.add_argument("--loop", action="store_true")
    ap.add_argument("--hours", type=float, default=24.0)
    a = ap.parse_args()
    started = time.time()
    while True:
        t0 = time.time()
        try:
            doc = current()
            write_state(doc)
            print(f"[{doc['at']}] health {doc['score']:.0f} {doc['level']} -> {doc['recommendation']} "
                  f"(bar {doc['bar']}, {time.time() - t0:.1f}s)", flush=True)
        except Exception as exc:  # noqa: BLE001 - one bad read must not end the loop
            print(f"health: failed: {type(exc).__name__}: {exc}", flush=True)
        if not a.loop or time.time() - started > a.hours * 3600:
            return 0
        nxt = (int(time.time() // CYCLE_S) + 1) * CYCLE_S + 120     # after the feed lands the bar
        while time.time() < nxt:
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
