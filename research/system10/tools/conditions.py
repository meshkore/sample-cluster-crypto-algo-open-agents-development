"""S10-6: where do the best trades live, how much of the tape is that, and can it pay?

The operator's question, 2026-09-27, answered before any policy is trained:

1. **The best trades.** 06's zigzag oracle (threshold 0.03) over every research symbol; the
   top quantile of its up-swings by net return after the 0.30% round trip.
2. **The conditions.** For each walk-forward year N, a shallow tree over the frozen
   registry's 44 market columns is fitted on years < N and its densest leaves are taken
   until they cover the target share of those swings (60/70/80/90%). The rules print.
3. **Coverage, out of sample.** In year N: share of bars inside R, share of year N's best
   swings (by the floor fitted on < N) inside R.
4. **Capturable return, out of sample.** A three-slot book, one third of equity per slot,
   enters where R holds and leaves by a CAUSAL exit that reads no model: 06's shipped hard
   stop and trailing stop, and a fixed horizon of 384 bars (four days - the best honest
   horizon in 06's exit study). Costs charged; each year a fresh $100,000 account. This is
   the return R makes reachable without a policy, not the cap.
5. **Version zero** - 06's gates (probability >= enter, slow trend up, breadth, fear) - and
   **everywhere** (enter whenever a slot is free) are scored by the same book, so the learned
   region is measured against the hand-built one and against nothing.
6. **Feasibility.** The 20,000-draw, 21-day-block bootstrap of 365-day years from each
   variant's out-of-sample daily returns: P(year >= +20%), p05, and the chance of a year as
   bad as the worst observed.

Why the exit reads no model. The first run of this tool (2026-09-30) left by 06's band exit
on the live net's probability, and version zero returned +3,313% in 2018. That is not a
result: the live net trained on the first 80% of every symbol's research history, so its
probability on those years is close to the oracle's own label, and an exit that reads it is
an exit with hindsight. Version zero's ENTRY still reads that probability, so version zero is
reported as an in-sample reference only and is excluded from the verdict. The learned region
and the exit read only causal indicators and prices.

No 2026 bar is loaded: bars come from `quantlab_catalog.candles.research()`, and the signal
arrays are joined on those bars' timestamps only.

Run from the repo root:
    PYTHONPATH="trading-system;trading-system/systems;backtester;live-trading" \
        python research/system10/tools/conditions.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for sub in ("backtester", "trading-system", "trading-system/systems", "live-trading"):
    sys.path.insert(0, str(REPO / sub))

from system010_conditioned_rl import features as registry  # noqa: E402
from system010_conditioned_rl import region as R  # noqa: E402

ENGINE = "v3-exit-010"
YEARS = tuple(range(2018, 2026))
BOOT_YEARS = tuple(range(2019, 2026))   # 2018's region is fitted on 4.5 months of 3 symbols
COVERAGES = (0.6, 0.7, 0.8, 0.9)
QUANTILES = (0.5, 0.3, 0.2)
SLOTS = 3
CAPITAL = 100_000.0
HALF_COST = R.ROUND_TRIP / 2
DD_FLOOR = 0.02
MANAGER_STEP = 16       # bars between a position manager's decisions (4 h)
HORIZON = 384           # bars: four days; 06's exit study's best honest horizon


def _q(ret: float, dd: float) -> float:
    return (1.0 if ret >= 0 else -1.0) * ret * ret / max(dd, DD_FLOOR)


# ---------------------------------------------------------------------------- data

def load(engine: str, include_sealed: bool = False) -> dict:
    """Bars, features and channels per symbol. `include_sealed` adds 2026 to today - the
    operator's forward window for system 10 - and is only ever passed by the continuous
    trainer's forward test; swings (the region's teacher) are computed on research bars only.
    """
    from quantlab_catalog.candles import candles, research
    from quantlab_catalog.paths import DATA_ROOT
    from quantlab_live.engine import EnginePackage
    from system006_oracle_net_15m.features import build_matrix, combined_store, research_store
    from system006_oracle_net_15m.moneymodel import _load_features
    from system006_oracle_net_15m.modules.crowd import Crowd

    package = EnginePackage.load(engine)
    symbols = json.loads((REPO / "research/system06/universe.json").read_text())["symbols"]
    bars = candles(symbols, include_sealed=True) if include_sealed else research(symbols)
    signals = REPO / "live-trading/state/engine_cache" / engine / "signals.npz"
    channels = _load_features(str(signals), str(DATA_ROOT), research=bars)
    store = combined_store() if include_sealed else research_store()
    crowd = Crowd(fng_min=1.0)
    fng_ns, fng_val = np.array(crowd._ns, dtype=np.int64), np.array(crowd._val, dtype=float)

    per: dict[str, dict] = {}
    for s in symbols:
        series = bars.get(s) or []
        if len(series) < 1000:
            continue
        X, _ = build_matrix(series, store=store, symbol=s)
        ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64")
                       for b in series], dtype=np.int64)
        close = np.array([b.close for b in series], dtype=float)
        ch = channels.get(s)
        prob = np.full(len(series), np.nan)
        trend = np.zeros(len(series))
        breadth = np.zeros(len(series))
        if ch is not None:
            pos = np.searchsorted(ch["ns"], ns)
            pos = np.clip(pos, 0, len(ch["ns"]) - 1)
            hit = ch["ns"][pos] == ns
            prob[hit] = ch["prob"][pos[hit]]
            trend[hit] = ch["trend"][pos[hit]]
            breadth[hit] = ch["breadth"][pos[hit]]
        i = np.searchsorted(fng_ns, ns, side="left") - 1
        fng = np.where(i >= 0, fng_val[np.clip(i, 0, None)], np.nan)
        year = ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970
        per[s] = {"X": X.astype(np.float32), "ns": ns, "close": close, "prob": prob,
                  "trend": trend, "breadth": breadth, "fng": fng, "year": year,
                  "swings": R.up_swings(close[year < 2026])}
        print(f"  {s}: {len(series):,} bars, {len(per[s]['swings']):,} oracle up-swings", flush=True)
    return {"per": per, "band": package.band, "risk": package.risk}


# ---------------------------------------------------------------------------- the book

DAY_NS = 86_400 * 10**9
CORR_DAYS = 30


def _daily_corr(per: dict, syms: list, grid: np.ndarray, days: int = CORR_DAYS):
    """Per calendar day k of the book: the coins' correlation matrix of daily log returns
    over the `days` complete days before k (causal). Returns (matrices, day index per bar).
    Pairs with fewer than 20 shared days read as uncorrelated."""
    d0 = int(grid[0] // DAY_NS) - days - 1
    d1 = int(grid[-1] // DAY_NS)
    D, S = d1 - d0 + 1, len(syms)
    dc = np.full((D, S), np.nan)
    for j, s in enumerate(syms):
        day = per[s]["ns"] // DAY_NS
        sel = (day >= d0) & (day <= d1)
        dd, c = day[sel] - d0, per[s]["close"][sel]
        if not len(dd):
            continue
        last = np.r_[dd[1:] != dd[:-1], True]
        dc[dd[last], j] = c[last]
    lr = np.full((D, S), np.nan)
    lr[1:] = np.log(dc[1:] / dc[:-1])                  # lr[k] = day k's return
    out = np.zeros((D, S, S))
    for k in range(days + 1, D):
        w = lr[k - days:k]
        ok = np.isfinite(w)
        n = ok.T.astype(float) @ ok.astype(float)
        mu = np.where(ok, w, 0).sum(0) / np.maximum(ok.sum(0), 1)
        z = np.where(ok, w - mu, 0.0)
        cov = z.T @ z
        var = np.sqrt(np.diag(cov))
        c = cov / np.maximum(np.outer(var, var), 1e-18)
        c[n < 20] = 0.0
        out[k] = c
    return out, (grid // DAY_NS - d0).astype(np.int64)


def _momentum_top(per: dict, syms: list, grid: np.ndarray, days: int, k: int) -> np.ndarray:
    """(bars x coins) True where the coin's `days`-day return, at the bar's close, ranks in
    the top k of the coins priced then. Causal: reads closes up to the bar only."""
    mom = np.full((len(grid), len(syms)), np.nan)
    for j, s in enumerate(syms):
        ns, c = per[s]["ns"], per[s]["close"]
        now = np.searchsorted(ns, grid, side="right") - 1
        then = np.searchsorted(ns, grid - days * DAY_NS, side="right") - 1
        ok = (now >= 0) & (then >= 0)
        mom[ok, j] = c[now[ok]] / c[then[ok]] - 1
    rank = np.argsort(np.argsort(-np.nan_to_num(mom, nan=-np.inf), axis=1, kind="stable"), axis=1)
    return (rank < k) & np.isfinite(mom)

def book_year(per: dict, masks: dict, year: int, band: dict, risk: dict,
              keep: dict | None = None, size: dict | None = None, keep_min_hold: int = 0,
              slots: int = SLOTS, stop: float | None = None, book_stop: float | None = None,
              cooldown: int = 288, dd_scale: float | None = None, manager=None,
              manager_pause: int = 0, strength: dict | None = None,
              size_signal: float | None = None, scale_in: bool = False,
              add_above: float = 0.006, trim_below: float = 0.0,
              start_ns: int | None = None, capital: float = CAPITAL, detail: bool = False,
              guard=None, corr_cap: int | None = None, corr_rho: float = 0.8,
              eq_filter: int | None = None, eq_cut: float = 0.75, min_edge: float | None = None,
              take_profit: float | None = None, breakeven: float | None = None,
              mom_rank: int | None = None, mom_days: int = 60, mom_in: float = 2.0,
              mom_out: float = 1.0, end_ns: int | None = None, init: dict | None = None) -> dict:
    """A fresh three-slot account over one year; enter where `masks` holds.

    Without `keep` the exit is 06's stop + trail + the fixed horizon. With `keep` (per
    symbol, True while the policy wants to stay long) the horizon is replaced by the
    policy's own exit; the stop and trail stay on as the book's safety net.

    Money management (operator, 2026-10-08: "a 50% drawdown is too risky - a model that
    perhaps earns less but does not expose the account"):
      slots      positions the book may hold; each stake is 1/slots of the book
      stop       per-trade stop, replacing 06's 16.3% when given
      book_stop  when the account is this far below its running peak, every position is
                 closed and nothing opens for `cooldown` bars (288 = 3 days); the peak is
                 then reset to the account's value, so the brake measures the new leg.
                 Measured 2026-10-08: it does NOT cap the year's drawdown - the legs add up
                 (8% brake, 56% year). Kept as a lever; dd_scale is the one that bounds.
      manager    a position manager (2026-10-09): every MANAGER_STEP bars a position is
                 held, manager(symbol, bar, entry_bar) -> True closes it. `bar` and
                 `entry_bar` index the symbol's own arrays in `per`. A coin the manager
                 closes is not re-entered for `manager_pause` bars.
      strength   the signal model's continuous forecast per bar (the exit regressor's
                 next-day return), the "strength of the signal" the operator asked for
                 on 2026-10-10. With size_signal, the entry stake is scaled by
                 clip(strength / size_signal, 0.25, 1). With scale_in, every MANAGER_STEP
                 bars a held position is ADDED to (a quarter slot, up to one full slot)
                 while strength >= add_above, and HALVED when strength < trim_below; the
                 rule exit still closes it. Both ignored when strength is None.
      dd_scale   new stakes shrink as the account falls below the year's true peak:
                 x max(0.25, 1 - drawdown / dd_scale). Never reset, so losses cannot
                 compound at full size.

    Paper trading (operator, 2026-10-13: "start it today with $50,000"): `start_ns` opens
    the account at that bar instead of on 1 January, with `capital`; `detail` adds every
    fill with its time and reason, the open positions and the equity curve.

    Market health (operator, 2026-10-14: "a safety system apart from the trading system
    that can stop it"): `guard(bar_ns, closed_trade_returns) -> "trade" | "block" |
    "flatten"` is asked once per bar, before the exits; "block" stops new entries and
    scale-in adds, "flatten" also closes every open position on this bar's close. None
    (the default) leaves the book exactly as it was. See system010_conditioned_rl/health.py.

    Levers of 2026-10-14 (each off by default; off = the book exactly as before):
      corr_cap     a coin is not entered while `corr_cap` held coins have a 30-day daily-
                   return correlation with it above `corr_rho` (days before today only)
      eq_filter    new stakes x `eq_cut` while the account is below the average of its last
                   `eq_filter` end-of-day values
      min_edge     enter only where the signal strength is >= min_edge (needs `strength`)
      take_profit  close a position once its close is this far above its entry price
      breakeven    once a position has been this far up, its stop moves to the entry price
                   plus the round trip and 0.1% (a small net win)
      mom_rank     cross-sectional momentum (challenger study, 2026-10-14): coins in the top
                   `mom_rank` by `mom_days`-day return at entry get stakes x `mom_in`, the
                   rest x `mom_out` (0 = not entered at all). Defaults = the 10-14 winner

    Hot swap (operator, 2026-10-15: "replace the engine immediately when we have a better
    one, even with positions open"): `end_ns` stops the book before that bar and `init`
    (the `state` a detail run returns: cash, high water, closed trades, open positions with
    units, entry and peak price, bars held) continues a book instead of opening a fresh one,
    so a new release takes over the same account on the next bar. Both None = as before.
    """
    def in_window(s):
        sel = per[s]["year"] == year
        if end_ns is not None:
            sel = sel & (per[s]["ns"] < end_ns)
        return sel & (per[s]["ns"] >= start_ns) if start_ns is not None else sel

    syms = [s for s in per if in_window(s).any()]
    grid = np.unique(np.concatenate([per[s]["ns"][in_window(s)] for s in syms]))
    T, S = len(grid), len(syms)
    close = np.full((T, S), np.nan)
    prob = np.full((T, S), np.nan)
    enter = np.zeros((T, S), dtype=bool)
    stay = np.ones((T, S), dtype=bool)
    scale = np.ones((T, S))
    sig = np.zeros((T, S))
    trader = strength is not None and (size_signal or scale_in)
    bar_of = np.full((T, S), -1, dtype=np.int64)
    for j, s in enumerate(syms):
        sel = in_window(s)
        at = np.searchsorted(grid, per[s]["ns"][sel])
        bar_of[at, j] = np.flatnonzero(sel)
        close[at, j] = per[s]["close"][sel]
        prob[at, j] = per[s]["prob"][sel]
        enter[at, j] = masks[s][sel]
        if keep is not None:
            stay[at, j] = keep[s][sel]
        if size is not None:
            scale[at, j] = size[s][sel]
        if trader:
            sig[at, j] = strength[s][sel]
    # Carry the last price across a symbol's missing bars so the book is marked, never
    # traded, on a price nobody printed.
    for j in range(S):
        col = close[:, j]
        ok = np.isfinite(col)
        if ok.any():
            idx = np.where(ok, np.arange(T), 0)
            np.maximum.accumulate(idx, out=idx)
            filled = col[idx]
            filled[: np.argmax(ok)] = np.nan
            close[:, j] = filled
            bar_of[:, j] = bar_of[idx, j]
    trail = float(risk.get("trail_stop") or 0)
    stop = float(stop) if stop is not None else float(risk.get("stop_loss") or 0)
    run_peak, frozen_until = capital, -1
    year_peak = capital
    if corr_cap:
        corr_of, corr_day = _daily_corr(per, syms, grid)
    if eq_filter:
        gday = grid // DAY_NS
        eod_eq: list[float] = []
    be_lock = 1 + R.ROUND_TRIP + 0.001
    if mom_rank:
        mom_top = _momentum_top(per, syms, grid, int(mom_days), int(mom_rank))

    cash = capital
    fills: list[dict] = []
    entry_t = np.zeros(S, dtype=np.int64)

    def fill(t, j, side, qty, price, notional, reason):
        if detail:
            row = {"t": int(grid[t]), "symbol": syms[j], "side": side, "quantity": float(qty),
                   "price": float(price), "notional": float(notional),
                   "fee": float(notional * HALF_COST), "reason": reason}
            if side == "SELL":   # profit of the part sold, both sides' costs charged
                row["realised"] = float(qty * (price * (1 - HALF_COST) - entry_px[j] * (1 + HALF_COST)))
            fills.append(row)
    units = np.zeros(S)
    entry_px = np.zeros(S)
    peak_px = np.zeros(S)
    held_for = np.zeros(S, dtype=int)
    entry_bar = np.zeros(S, dtype=np.int64)
    paused_until = np.full(S, -1, dtype=np.int64)
    held = np.zeros(S, dtype=bool)
    equity = np.empty(T)
    trades: list[float] = []
    entry_ns0 = np.full(S, -1, dtype=np.int64)   # entry time of a position carried in by `init`
    if init is not None:
        cash = float(init["cash"])
        year_peak = run_peak = float(init["high_water"])
        trades = [float(x) for x in init.get("trades", [])]
        for q in init.get("positions", []):
            j = syms.index(q["symbol"])
            units[j], entry_px[j], peak_px[j] = q["units"], q["entry_px"], q["peak_px"]
            held_for[j], held[j], entry_ns0[j] = int(q["held_for"]), True, int(q["entry_ns"])
    log: list[tuple] = []          # (symbol, entry bar in its own arrays, trade return)
    for t in range(T):
        px = close[t]
        action = guard(int(grid[t]), trades) if guard is not None else "trade"
        # exits first, on this bar's close
        for j in np.flatnonzero(held):
            if not np.isfinite(px[j]):
                continue
            held_for[j] += 1
            peak_px[j] = max(peak_px[j], px[j])
            why = ("stop" if stop and px[j] <= entry_px[j] * (1 - stop)
                   else "take profit" if take_profit and px[j] >= entry_px[j] * (1 + take_profit)
                   else "breakeven stop" if (breakeven and peak_px[j] >= entry_px[j] * (1 + breakeven)
                                             and px[j] <= entry_px[j] * be_lock)
                   else "trailing stop" if trail and px[j] <= peak_px[j] * (1 - trail)
                   else "time limit" if held_for[j] >= HORIZON
                   else "signal exit" if keep is not None and not stay[t, j] and held_for[j] >= keep_min_hold
                   else None)
            leave = why is not None
            if (not leave and manager is not None and held_for[j] % MANAGER_STEP == 0
                    and manager(syms[j], int(bar_of[t, j]), int(entry_bar[j]))):
                leave, why = True, "manager"
                paused_until[j] = t + manager_pause
            if leave:
                fill(t, j, "SELL", units[j], px[j], units[j] * px[j], why)
                cash += units[j] * px[j] * (1 - HALF_COST)
                trades.append(px[j] / entry_px[j] * (1 - HALF_COST) / (1 + HALF_COST) - 1)
                log.append((syms[j], int(entry_bar[j]), trades[-1]))
                units[j], held[j] = 0.0, False
            elif trader and scale_in and held_for[j] % MANAGER_STEP == 0 and (action == "trade" or sig[t, j] < trim_below):
                st = sig[t, j]
                book = cash + float(np.nansum(units * np.nan_to_num(px)))
                slot = book / slots
                value = units[j] * px[j]
                if st >= add_above and value < slot and cash > 0:
                    add = min(slot * 0.25, slot - value, cash)
                    new_units = add / (px[j] * (1 + HALF_COST))
                    fill(t, j, "BUY", new_units, px[j], new_units * px[j], "add: strong signal")
                    entry_px[j] = (units[j] * entry_px[j] + new_units * px[j]) / (units[j] + new_units)
                    units[j] += new_units
                    cash -= add
                elif st < trim_below:
                    half = units[j] / 2
                    fill(t, j, "SELL", half, px[j], half * px[j], "trim: signal weakened")
                    cash += half * px[j] * (1 - HALF_COST)
                    trades.append(px[j] / entry_px[j] * (1 - HALF_COST) / (1 + HALF_COST) - 1)
                    log.append((syms[j], int(entry_bar[j]), trades[-1]))
                    units[j] -= half
        if book_stop:
            mark = cash + float(np.nansum(units * np.nan_to_num(px)))
            run_peak = max(run_peak, mark)
            if mark <= run_peak * (1 - book_stop):
                for j in np.flatnonzero(held & np.isfinite(px)):
                    fill(t, j, "SELL", units[j], px[j], units[j] * px[j], "account brake")
                    cash += units[j] * px[j] * (1 - HALF_COST)
                    trades.append(px[j] / entry_px[j] * (1 - HALF_COST) / (1 + HALF_COST) - 1)
                    log.append((syms[j], int(entry_bar[j]), trades[-1]))
                    units[j], held[j] = 0.0, False
                frozen_until = t + cooldown
                run_peak = cash + float(np.nansum(units * np.nan_to_num(px)))
        if action == "flatten":
            for j in np.flatnonzero(held & np.isfinite(px)):
                fill(t, j, "SELL", units[j], px[j], units[j] * px[j], "health halt")
                cash += units[j] * px[j] * (1 - HALF_COST)
                trades.append(px[j] / entry_px[j] * (1 - HALF_COST) / (1 + HALF_COST) - 1)
                log.append((syms[j], int(entry_bar[j]), trades[-1]))
                units[j], held[j] = 0.0, False
        if eq_filter and t > 0 and gday[t] != gday[t - 1]:
            eod_eq.append(float(equity[t - 1]))
        free = slots - int(held.sum()) if t > frozen_until and action == "trade" else 0
        if free > 0:
            ok_in = enter[t] & ~held & np.isfinite(px) & (paused_until < t)
            if min_edge is not None and trader:
                ok_in &= sig[t] >= min_edge
            if mom_rank and not mom_out:
                ok_in &= mom_top[t]
            cand = np.flatnonzero(ok_in)
            if len(cand):
                order = cand if corr_cap else cand[:free]  # fixed universe order: priority must not read the in-sample net
                book = cash + float(np.nansum(units * np.nan_to_num(px)))
                eqf = 1.0
                if eq_filter and eod_eq and book < float(np.mean(eod_eq[-int(eq_filter):])):
                    eqf = float(eq_cut)
                if corr_cap:
                    cm, taken = corr_of[corr_day[t]], 0
                for j in order:
                    if corr_cap:
                        if taken >= free:
                            break
                        if int(np.count_nonzero(held & (cm[j] > corr_rho))) >= corr_cap:
                            continue
                        taken += 1
                    ddf = 1.0
                    if dd_scale:
                        ddf = max(0.25, 1.0 - (1.0 - book / year_peak) / dd_scale)
                    mult = 1.0
                    if trader and size_signal:
                        mult = float(np.clip(sig[t, j] / size_signal, 0.25, 1.0))
                    if eq_filter:
                        mult *= eqf
                    if mom_rank:
                        mult *= float(mom_in) if mom_top[t, j] else float(mom_out)
                    stake = min(book / slots * scale[t, j] * ddf * mult, cash)
                    if stake <= 0:
                        break
                    units[j] = stake / (px[j] * (1 + HALF_COST))
                    fill(t, j, "BUY", units[j], px[j], units[j] * px[j], "entry")
                    cash -= stake
                    entry_px[j] = peak_px[j] = px[j]
                    entry_bar[j] = bar_of[t, j]
                    entry_t[j] = t
                    entry_ns0[j] = -1
                    held_for[j], held[j] = 0, True
        equity[t] = cash + float(np.nansum(units * np.nan_to_num(px)))
        year_peak = max(year_peak, equity[t])
    peak = np.maximum.accumulate(equity)
    dd = float((1 - equity / peak).max())
    ret = float(equity[-1] / capital - 1)
    day = grid.astype("datetime64[ns]").astype("datetime64[D]")
    last_of_day = np.r_[day[1:] != day[:-1], True]
    eod = np.r_[capital, equity[last_of_day]]
    daily = eod[1:] / eod[:-1] - 1
    a = np.array(trades) if trades else np.zeros(0)
    out = {"return": round(ret, 4), "max_dd": round(dd, 4), "q": round(_q(ret, dd), 4),
           "trades": len(a), "mean_trade": round(float(a.mean()), 5) if len(a) else None,
           "win_rate": round(float((a > 0).mean()), 4) if len(a) else None,
           "symbols": S, "daily": daily.tolist(), "trade_log": log}
    if detail:
        px = close[-1]
        ens = lambda j: int(entry_ns0[j]) if entry_ns0[j] >= 0 else int(grid[entry_t[j]])  # noqa: E731
        out.update({
            "fills": fills, "cash": float(cash), "equity": float(equity[-1]),
            "high_water": float(peak.max()) if init is None else float(max(peak.max(), year_peak)),
            "last_ns": int(grid[-1]), "closed_returns": [float(x) for x in trades],
            "equity_curve": [(int(grid[t]), float(equity[t]), float(peak[t])) for t in range(T)],
            "positions": [{"symbol": syms[j], "quantity": float(units[j]), "entry_price": float(entry_px[j]),
                           "entry_ns": ens(j), "price": float(px[j]),
                           "value": float(units[j] * px[j]), "unrealised_pct": float(px[j] / entry_px[j] - 1)}
                          for j in np.flatnonzero(held)],
            "marks": {syms[j]: float(px[j]) for j in range(S) if np.isfinite(px[j])}})
        if init is not None or end_ns is not None:   # a segment of a hot-swapped book
            out["state"] = {"cash": float(cash), "high_water": float(year_peak), "trades": [float(x) for x in trades],
                            "positions": [{"symbol": syms[j], "units": float(units[j]), "entry_px": float(entry_px[j]),
                                           "peak_px": float(peak_px[j]), "held_for": int(held_for[j]),
                                           "entry_ns": ens(j)} for j in np.flatnonzero(held)]}
    return out


def bootstrap(daily: list[float], worst_year: float, draws: int = 20_000,
              block: int = 21, days: int = 365, seed: int = 7) -> dict:
    d = np.asarray(daily, dtype=float)
    rng = np.random.default_rng(seed)
    blocks = -(-days // block)
    starts = rng.integers(0, len(d) - block, size=(draws, blocks))
    paths = d[starts[..., None] + np.arange(block)].reshape(draws, -1)[:, :days]
    years = np.prod(1 + paths, axis=1) - 1
    return {"p_year_ge_20": round(float((years >= 0.20).mean()), 4),
            "p05": round(float(np.percentile(years, 5)), 4),
            "median": round(float(np.median(years)), 4),
            "p_as_bad_as_worst": round(float((years <= worst_year).mean()), 4)}


# ---------------------------------------------------------------------------- the study

def study(engine: str, quantile: float) -> dict:
    t0 = time.time()
    print(f"loading bars, indicators and {engine}'s channels (research only)...", flush=True)
    data = load(engine)
    per, band, risk = data["per"], data["band"], data["risk"]
    enter = float(band["enter"])
    breadth_gate = float(risk.get("breadth_gate") or 0)
    fng_min = float(risk.get("fng_min") or 0)

    v0 = {s: (np.nan_to_num(d["prob"]) >= enter) & (d["trend"] > 0)
          & (d["breadth"] >= breadth_gate) & ~(np.nan_to_num(d["fng"], nan=100) < fng_min)
          for s, d in per.items()}
    everywhere = {s: np.isfinite(d["X"]).all(axis=1) for s, d in per.items()}

    variants: dict[str, dict] = {"everywhere": {}, "version zero (06 gates)": {}}
    variants.update({f"R {int(c * 100)}%": {} for c in COVERAGES})
    coverage: dict[str, dict] = {k: {} for k in variants}
    folds: dict[int, dict] = {}

    for N in YEARS:
        # the swings and their floor, from years < N only
        train_nets = np.concatenate([d["swings"][d["year"][d["swings"][:, 0].astype(int)] < N, 2]
                                     for d in per.values() if len(d["swings"])])
        if len(train_nets) < 50:
            continue
        floor = float(np.quantile(train_nets, 1 - quantile))
        Xs, zones, ids, n_best, off = [], [], [], 0, 0
        eval_best: dict[str, np.ndarray] = {}
        for s, d in per.items():
            sw = d["swings"]
            start_year = d["year"][sw[:, 0].astype(int)] if len(sw) else np.zeros(0, int)
            best_train = sw[(start_year < N) & (sw[:, 2] >= floor)]
            eval_best[s] = sw[(start_year == N) & (sw[:, 2] >= floor)]
            tr = d["year"] < N
            if not tr.any():
                continue
            zone = R.entry_zone_mask(len(d["X"]), best_train)
            sid = np.full(len(d["X"]), -1, dtype=np.int64)
            for k, (a, b, _) in enumerate(best_train):
                a = int(a)
                sid[a:min(a + R.ENTRY_ZONE, int(b))] = off + k
            off += len(best_train)
            n_best += len(best_train)
            Xs.append(d["X"][tr]); zones.append(zone[tr]); ids.append(sid[tr])
        X, zone, sid = np.concatenate(Xs), np.concatenate(zones), np.concatenate(ids)
        fold = {"train_years": f"< {N}", "floor_net": round(floor, 4),
                "best_swings_train": int(n_best), "regions": {}}
        n_eval_best = sum(len(v) for v in eval_best.values())
        for c in COVERAGES:
            reg = R.fit(X, zone, sid, n_best, coverage=c, fitted_on=range(2017, N),
                        quantile=quantile, net_floor=floor)
            key = f"R {int(c * 100)}%"
            masks = {s: reg.holds(d["X"]) for s, d in per.items()}
            ev_bars = sum(int(masks[s][per[s]["year"] == N].sum()) for s in per)
            all_bars = sum(int(everywhere[s][per[s]["year"] == N].sum()) for s in per)
            hit = sum(int(R.swings_covered(masks[s], eval_best[s]).sum()) for s in per)
            coverage[key][N] = {"bar_share": round(ev_bars / max(all_bars, 1), 4),
                                "best_swings_inside": round(hit / max(n_eval_best, 1), 4),
                                "best_swings": n_eval_best,
                                "train_bar_share": round(reg.train_bar_share, 4),
                                "train_swing_coverage": round(reg.train_swing_coverage, 4)}
            variants[key][N] = book_year(per, masks, N, band, risk)
            fold["regions"][key] = {"rules": reg.rules(), "leaves": len(reg.leaves)}
        for key, masks in (("everywhere", everywhere), ("version zero (06 gates)", v0)):
            ev_bars = sum(int(masks[s][per[s]["year"] == N].sum()) for s in per)
            all_bars = sum(int(everywhere[s][per[s]["year"] == N].sum()) for s in per)
            hit = sum(int(R.swings_covered(masks[s], eval_best[s]).sum()) for s in per)
            coverage[key][N] = {"bar_share": round(ev_bars / max(all_bars, 1), 4),
                                "best_swings_inside": round(hit / max(n_eval_best, 1), 4),
                                "best_swings": n_eval_best}
            variants[key][N] = book_year(per, masks, N, band, risk)
        folds[N] = fold
        line = "  ".join(f"{k}: {variants[k][N]['return']:+.1%}/{variants[k][N]['max_dd']:.0%}"
                         f" cov {coverage[k][N]['best_swings_inside']:.0%} bars {coverage[k][N]['bar_share']:.0%}"
                         for k in variants)
        print(f"{N} [{time.time() - t0:.0f}s] {line}", flush=True)

    summary = {}
    for k, rows in variants.items():
        yrs = [y for y in BOOT_YEARS if y in rows]
        daily = [v for y in yrs for v in rows[y]["daily"]]
        worst = min(rows[y]["return"] for y in yrs)
        summary[k] = {
            "worst_year": round(worst, 4),
            "worst_q": round(min(rows[y]["q"] for y in yrs), 4),
            "max_dd": round(max(rows[y]["max_dd"] for y in yrs), 4),
            "mean_bar_share": round(float(np.mean([coverage[k][y]["bar_share"] for y in yrs])), 4),
            "mean_best_inside": round(float(np.mean([coverage[k][y]["best_swings_inside"] for y in yrs])), 4),
            "bootstrap": bootstrap(daily, worst),
        }
        for y in rows:
            rows[y].pop("daily")
    return {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "engine": ENGINE, "quantile": quantile, "oracle_threshold": R.ORACLE_THRESHOLD,
            "entry_zone_bars": R.ENTRY_ZONE, "feature_hash": registry.FEATURE_HASH,
            "book": {"slots": SLOTS, "fraction": round(1 / SLOTS, 4), "exit": f"06 stop + trail + {HORIZON}-bar horizon (no model)",
                     "band": band, "stop_loss": risk.get("stop_loss"),
                     "trail_stop": risk.get("trail_stop"), "round_trip": R.ROUND_TRIP},
            "caveat": ("version zero's entry reads the live net's probability, which saw the first "
                       "80% of the research years in training: it is an in-sample reference, not "
                       "a competitor. Every exit is causal and reads no model."),
            "summary": summary, "per_year": variants, "coverage": coverage, "folds": folds,
            "minutes": round((time.time() - t0) / 60, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quantile", type=float, nargs="*", default=[0.2])
    ap.add_argument("--engine", default=ENGINE)
    args = ap.parse_args()
    out_dir = REPO / "research/system10/rnd"
    out_dir.mkdir(parents=True, exist_ok=True)
    for q in args.quantile:
        result = study(args.engine, q)
        path = out_dir / f"conditions_q{int(q * 100)}_{datetime.now(timezone.utc):%Y-%m-%d}.json"
        path.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        print(f"\nquantile {q}: written {path.relative_to(REPO)}")
        for k, s in result["summary"].items():
            b = s["bootstrap"]
            print(f"  {k:<26} worst yr {s['worst_year']:+.1%}  maxdd {s['max_dd']:.0%}  "
                  f"bars {s['mean_bar_share']:.0%}  best inside {s['mean_best_inside']:.0%}  "
                  f"P(>=20%) {b['p_year_ge_20']:.0%}  p05 {b['p05']:+.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
