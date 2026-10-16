"""The 24/7 condition search: the system's intelligence is choosing the conditions.

The operator, 2026-10-01: *"the beauty of this project is to know how to choose the ideal
conditions - either to train, or to operate, or to separate two models. That is the key. Not
to plug a reinforcement-learning algorithm, because anyone can do that."* And: *"a model that
never stops training and never stops improving... if the initial hypothesis doesn't work, we
change"*; *"train two models, one for rising sections and another for falling ones... some
average, 200, 123, 111 or 350, able to know which market we are in"*; 2026 is the forward
test only and the model never sees it.

So one trial = one CONDITION SET, and the search walks through them without end:

    regime_ma     BTC above/below its N-day average splits the market in two (None = one regime)
    b_up, b_down  per regime, the share of the universe in an uptrend required to operate
                  (1.1 = never operate in that regime)
    selector      per regime, a trade scorer trained only on that regime's opportunities
                  decides which trades to take (four seeds, taken only on a 3-of-4 vote);
                  off = take every opportunity the gate allows
    horizon       the fixed causal exit: 06's stop, its trail, or this many bars

Each trial is judged walk-forward on 2022-2025, every year unseen by what is read on it
(scorers fitted on years < N-1, their take-bar chosen on N-1, read on N), with the
selection law (2026-10-15, see law()): regular floor of the worst years, recent years weighted
more, drawdown subtracted; Q of the worst year beside it. The operator's availability rule is a hard filter: the gate must leave >= 70% of days
with an option to trade and no pause over 40 days, every year. The search starts from the
operator's averages and the one construction that held in both unseen years (breadth >= 50%),
then explores one-step neighbours of the three best - never random draws.

Every five hours the current champion is fitted the same way one fold further (scorers on
< 2025, bar chosen on 2025) and read on 2026-01-01..today. That reading is drawn on the
dashboard and NEVER feeds back: no trial, champion or bar is chosen on 2026.

The process runs for `--hours` (5), takes its reading, and exits; the watchdog relaunches it
with fresh bars, and the trial ledger carries the search across restarts.
Brake: research/system10/STOP_S10.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from . import bandit as B

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "research/system10"
TRIALS = OUT / "rnd/search_trials.jsonl"
CHAMPION = OUT / "rnd/search_champion.json"
LOG = OUT / "rnd/forward_log.jsonl"
CARD = OUT / "model_card.json"
TIMELINE = OUT / "rnd/training_timeline.jsonl"
EVENTS = OUT / "rnd/events.jsonl"
READ_EVERY_S = 3600      # the operator: "one of those tests every hour"
STOP = OUT / "STOP_S10"

SEEDS = (77101, 77102, 91002, 51015)
# A second, independent set. Release 20 did not reproduce (2026-10-08: re-run, 2024 went
# from +54% to -2%), so a new champion must pass again with these before it is released,
# and it is ranked by the worse of the two runs.
CONFIRM_SEEDS = (13001, 13002, 13003, 13004)
TEST_YEARS = (2022, 2023, 2024, 2025)
FORWARD = 2026
SHARES = (0.5, 0.3, 0.2, 0.1, 0.05)
MIN_TRADES = 50
DAY_SHARE_MIN, GAP_MAX = 0.70, 40
MAX_FIT_ROWS = 600_000

SEED_CONFIGS = [
    {"regime_ma": None, "b_up": 0.5, "b_down": 0.5, "selector": False, "horizon": 384},
    {"regime_ma": None, "b_up": 0.5, "b_down": 0.5, "selector": True, "horizon": 384},
] + [
    {"regime_ma": ma, "b_up": 0.0, "b_down": 0.5, "selector": sel, "horizon": 384}
    for ma in (111, 123, 200, 350) for sel in (False, True)
] + [
    # The feasible side, added after the first 43 trials all missed the availability rule:
    # a bear regime that keeps the door open (breadth 0 or 0.2) and lets the per-regime
    # selector decide, rather than a gate that shuts for three months.
    {"regime_ma": ma, "b_up": bu, "b_down": bd, "selector": True, "horizon": 384}
    for ma in (111, 123, 200, 350) for bu in (0.0, 0.5) for bd in (0.0, 0.2)
] + [
    {"regime_ma": ma, "b_up": 0.0, "b_down": 0.0, "selector": True, "horizon": h, "size_down": sd}
    for ma in (100, 111, 200) for h in (384, 768) for sd in (0.25, 0.5)
]
MA_STEPS = (None, 50, 80, 100, 111, 123, 150, 200, 250, 300, 350)
B_STEPS = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.1)
H_STEPS = (96, 192, 384, 768)
SIZE_STEPS = (0.25, 0.5, 0.75, 1.0)   # stake in the falling regime, x a full slot (never 0, see champion())
# Money management, 2026-10-08. The operator: "operating with a 50% drawdown is very risky -
# we need a model that perhaps earns less but does not expose the account". Release 20 won
# every unseen year (+21.6..+54%) with drawdowns of 45% and 53%; of 1,954 eligible trials
# none held every year under 25%. So the cap is now part of eligibility, and the book has
# levers to meet it.
DD_CAP = 0.25
BOOK_STOP_STEPS = (None, 0.08, 0.12, 0.16, 0.20)
STOP_STEPS = (None, 0.05, 0.08, 0.12)          # None = 06's 16.3%
SLOT_STEPS = (3, 5, 8)
DD_SCALE_STEPS = (None, 0.15, 0.25, 0.35)
# Book levers of 2026-10-14 (conditions.book_year): optional, absent = the book as before.
LEVER_KEYS = ("corr_cap", "corr_rho", "eq_filter", "eq_cut", "min_edge", "take_profit", "breakeven",
              "mom_rank", "mom_days", "mom_in", "mom_out")
# Book audit 2026-10-15 (tools/book_lab.py): book-only levers; never drawn by this search.
LEVER_KEYS += ("add_above", "trim_below", "port_vol", "size_kelly", "atr_trail")
MM_KEYS = ("book_stop", "stop", "slots", "dd_scale", "veto", "vol_target", "size_signal", "scale_in") + LEVER_KEYS
# Their steps. A/B on release 31 (tools/levers_study.py): the momentum boost (top-k coins by
# 60/90-day return get 2x stake) lifted 2022-25 CAGR +30.8% -> +41.5% at DD 24%; the rest
# were neutral. Defaults of the companion keys (mom_days 60, mom_in 2, mom_out 1, corr_rho
# 0.8, eq_cut 0.75) live in conditions.book_year.
MOM_STEPS = (None, 3, 5, 7)
MOM_DAYS_STEPS = (30, 60, 90)
MOM_IN_STEPS = (1.5, 2.0)
CORR_STEPS = (None, 3, 2)
EQ_STEPS = (None, 10, 30)
EDGE_STEPS = (None, 0.004, 0.005)
TP_STEPS = (None, 0.2, 0.12)
BE_STEPS = (None, 0.08)
BOOK_V = 2       # trial rows booked with the levers carry it (see ledger())

# The selection law (operator, 2026-10-15: "as regular as possible, one good year alone is no
# use to me" and "I prefer models that do better the closer they get to today ... consistent,
# stable, profit, min drawdown"). Three parts, all on the unseen years 2022-2025 only:
#   floor   0.5 x worst + 0.3 x second worst + 0.2 x third - the best year counts for nothing
#   recent  years weighted 1:2:3:4 from oldest to newest, each capped at +50% so one boom
#           year cannot carry it
#   dd      the worst year's max drawdown, subtracted at a quarter of its size
# score = 0.5 x floor + 0.5 x recent - 0.25 x dd. It replaced worst + 0.10 x CAGR, whose CAGR
# term let one +92% year win (release 38: 17/18/92/42).
LAW_FLOOR = (0.5, 0.3, 0.2)
LAW_CAP = 0.50
LAW_DD = 0.25


def law(years: dict, max_dd: float) -> float:
    ordered = [float(years[k]["return"]) for k in sorted(years, key=lambda k: int(k))]
    rets = sorted(ordered)
    w = LAW_FLOOR[:max(1, len(rets) - 1)]
    floor = sum(wi * r for wi, r in zip(w, rets)) / sum(w)
    rw = list(range(1, len(ordered) + 1))
    recent = sum(wi * min(r, LAW_CAP) for wi, r in zip(rw, ordered)) / sum(rw)
    return round(0.5 * floor + 0.5 * recent - LAW_DD * float(max_dd), 4)

LEVER_P = 0.25   # random_config: chance each lever is switched on
# The study's chosen settings, probed first on the best configurations.
LEVER_PROBES = ({"mom_rank": 5}, {"mom_rank": 5, "mom_days": 90}, {"mom_rank": 3, "mom_days": 90},
                {"mom_rank": 5, "mom_days": 90, "mom_in": 1.5})
# The signal-strength trader (operator, 2026-10-10: "a system that gives continuous buy or
# sell signals, and a trader that opens progressively and sells a piece or a lot depending
# on the signal's strength"). Deterministic first: if the forecast's magnitude carries
# information, these show it in hours; the RL trader comes only if they do.
SIZE_SIGNAL_STEPS = (None, 0.005, 0.01, 0.02)
VOL_STEPS = (None, 0.75, 1.0, 1.5)


def mm_kwargs(cfg: dict) -> dict:
    out = {"book_stop": cfg.get("book_stop"), "stop": cfg.get("stop"), "slots": cfg.get("slots", 3),
           "dd_scale": cfg.get("dd_scale"), "size_signal": cfg.get("size_signal"),
           "scale_in": bool(cfg.get("scale_in", False))}
    out.update({k: cfg[k] for k in LEVER_KEYS if cfg.get(k) is not None})
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cfg_id(cfg: dict) -> str:
    return hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:10]


def _tools():
    sys.path.insert(0, str(OUT / "tools"))
    import conditions as C  # noqa: WPS433
    return C


# ------------------------------------------------------------------ the data, once per run

class World:
    def __init__(self, include_sealed: bool = False, universe: int | None = None, cap: int | None = None):
        """Trainers load research bars only (<= 2025) and so cannot see 2026 even by
        accident; only the release evaluator passes include_sealed=True.
        universe=None: today's 14 coins (default). universe=N: the point-in-time coins of
        test year N, top `cap` by turnover (pit.py; audit 2026-10-15)."""
        C = _tools()
        self.C = C
        if universe is None:
            data = C.load(C.ENGINE, include_sealed=include_sealed)
        elif universe == "union":
            # Review round 2 (R6): ONE world holding every coin of any year's PIT list, each
            # bar a member only in its own year's list (pit.load_union). Research bars only.
            from . import pit
            data = pit.load_union(cap if cap is not None else pit.CAP)
        else:
            from . import pit
            data = pit.load(int(universe), include_sealed, cap if cap is not None else pit.CAP)
        self.per, self.band, self.risk = data["per"], data["band"], data["risk"]
        self.member = data.get("member")      # None = every coin trades every year (default)
        self.stop = float(self.risk.get("stop_loss") or 0)
        self.trail = float(self.risk.get("trail_stop") or 0)
        btc = self.per["BTCUSDT"]
        self.btc_ns, self.btc_close = btc["ns"], btc["close"]
        self.valid = {s: np.isfinite(d["X"]).all(axis=1) for s, d in self.per.items()}
        if self.member is not None:
            # a bar outside its year's list is never gated in, trained on or standardised on
            self.valid = {s: v & self.member[s] for s, v in self.valid.items()}
        # Standardise on years <= 2020: before every fold's training cut, so causal for all.
        early = np.concatenate([d["X"][(d["year"] <= 2020) & self.valid[s]] for s, d in self.per.items()])
        self.mean, self.std = early.mean(axis=0), early.std(axis=0) + 1e-8
        del early
        self.x = {s: np.nan_to_num(np.clip((d["X"] - self.mean) / self.std, -5, 5), nan=0.0).astype(np.float32)
                  for s, d in self.per.items()}
        if self.member is not None:
            # RAM (34 GB box): the raw columns are read only above; keep the row count alone
            for d in self.per.values():
                d["X"] = np.empty((len(d["X"]), 0), dtype=np.float32)
        self._regime: dict = {}
        self._out: dict = {}
        self._full: dict | None = None

    def full(self) -> dict:
        """The full picture (operator, 2026-10-06): the coin's 44 columns, plus the same
        market seen at 1h / 4h / 1d / 1w (its own and BTC's), plus the markets around crypto
        - VIX, Nasdaq, the dollar, oil, the 10-year yield and the curve - each lagged by its
        measured publication delay (06's A96 panel, which halved drawdown in its 2025 exam).
        Standardised on years <= 2020, like the rest; missing early rows read as zero."""
        if self._full is None:
            from system006_oracle_net_15m.reference import ReferenceTable
            ref = ReferenceTable()
            btc_c = self.btc_close
            lags = (4, 16, 96, 672)

            def mtf(close):
                cols = []
                for k in lags:
                    r = np.full(len(close), np.nan)
                    r[k:] = close[k:] / close[:-k] - 1
                    cols.append(r)
                lr = np.diff(np.log(np.maximum(close, 1e-12)), prepend=np.nan)
                for w in (96, 672):
                    c1 = np.cumsum(np.nan_to_num(lr)); c2 = np.cumsum(np.nan_to_num(lr) ** 2)
                    v = np.full(len(close), np.nan)
                    v[w:] = np.sqrt(np.maximum((c2[w:] - c2[:-w]) / w - ((c1[w:] - c1[:-w]) / w) ** 2, 0))
                    cols.append(v)
                return np.stack(cols, axis=1)

            btc_m = mtf(btc_c)
            raw = {}
            for s, d in self.per.items():
                i = np.clip(np.searchsorted(self.btc_ns, d["ns"], side="right") - 1, 0, None)
                ts = d["ns"].astype("datetime64[ns]")
                raw[s] = np.concatenate([mtf(d["close"]), btc_m[i], ref.matrix_for(ts)], axis=1)
            early = np.concatenate([raw[s][(d["year"] <= 2020)] for s, d in self.per.items()])
            mu, sd = np.nanmean(early, axis=0), np.nanstd(early, axis=0) + 1e-8
            self._full = {s: np.concatenate(
                [self.x[s], np.nan_to_num(np.clip((raw[s] - mu) / sd, -5, 5), nan=0.0).astype(np.float32)],
                axis=1) for s in self.per}
        return self._full

    def feats(self, cfg: dict) -> dict:
        return self.full() if cfg.get("features") == "full" else self.x

    def regime_up(self, ma) -> dict:
        """Per symbol per bar: is BTC above its `ma`-day average (causal, BTC's own closes)?"""
        if ma not in self._regime:
            if ma is None:
                self._regime[ma] = {s: np.ones(len(d["X"]), dtype=bool) for s, d in self.per.items()}
            else:
                w = int(ma) * 96
                c = np.cumsum(np.r_[0.0, self.btc_close])
                sma = np.full(len(self.btc_close), np.nan)
                sma[w - 1:] = (c[w:] - c[:-w]) / w
                up_btc = self.btc_close > sma
                out = {}
                for s, d in self.per.items():
                    i = np.clip(np.searchsorted(self.btc_ns, d["ns"], side="right") - 1, 0, None)
                    out[s] = up_btc[i] & np.isfinite(sma[i])
                self._regime[ma] = out
        return self._regime[ma]

    def outcomes(self, horizon: int) -> dict:
        if horizon not in self._out:
            res = {}
            for s, d in self.per.items():
                idx = np.flatnonzero(self.valid[s])
                net, mae = B.outcomes(d["close"], idx, self.stop, self.trail, horizon=horizon)
                end = d["year"][np.minimum(idx + horizon, len(d["year"]) - 1)]
                res[s] = {"idx": idx, "net": net, "mae": mae, "end_year": end}
            self._out[horizon] = res
        return self._out[horizon]

    def fwd(self, k: int) -> dict:
        """Per symbol per bar: the return of the next `k` bars, and the year that window ends in."""
        key = ("fwd", k)
        if key not in self._out:
            res = {}
            for sym, d in self.per.items():
                c = d["close"]
                f = np.full(len(c), np.nan)
                f[:-k] = c[k:] / c[:-k] - 1
                end = d["year"][np.minimum(np.arange(len(c)) + k, len(c) - 1)]
                res[sym] = {"fwd": f, "end_year": end}
            self._out[key] = res
        return self._out[key]

    def vol96(self) -> tuple[dict, float]:
        """Each coin's realised volatility over the last 96 bars (one day), and the median of
        it over years <= 2020 - the reference volatility targeting divides by."""
        if getattr(self, "_vol", None) is None:
            vol = {}
            for s, d in self.per.items():
                lr = np.diff(np.log(np.maximum(d["close"], 1e-12)), prepend=np.nan)
                lr = np.nan_to_num(lr)
                c1, c2 = np.cumsum(lr), np.cumsum(lr ** 2)
                v = np.full(len(lr), np.nan)
                v[96:] = np.sqrt(np.maximum((c2[96:] - c2[:-96]) / 96 - ((c1[96:] - c1[:-96]) / 96) ** 2, 0))
                vol[s] = np.where(np.isfinite(v), v, np.nanmedian(v))
            early = np.concatenate([vol[s][d["year"] <= 2020] for s, d in self.per.items()])
            self._vol = (vol, float(np.nanmedian(early)))
        return self._vol

    def book(self, masks: dict, year: int, horizon: int, size: dict | None = None,
             keep: dict | None = None, keep_min_hold: int = 0, **mm) -> dict:
        C = self.C
        per = self.per
        if getattr(self, "member", None) is not None:
            # PIT union: the book (and its momentum rank) sees only the coins of `year`'s list
            per = {s: d for s, d in per.items() if self.member[s][d["year"] == year].any()}
        old = C.HORIZON
        C.HORIZON = horizon
        try:
            r = C.book_year(per, masks, year, self.band, self.risk, keep=keep, size=size,
                             keep_min_hold=keep_min_hold, **mm)
        finally:
            C.HORIZON = old
        return r


# ------------------------------------------------------------------ one trial

def gate(world: World, cfg: dict) -> tuple[dict, dict]:
    up = world.regime_up(cfg["regime_ma"])
    g, regime = {}, {}
    for s, d in world.per.items():
        need = np.where(up[s], cfg["b_up"], cfg["b_down"])
        g[s] = world.valid[s] & (d["breadth"] >= need)
        regime[s] = up[s]
    return g, regime


def sizing(world: World, cfg: dict) -> dict | None:
    """Stake per bar: a full slot in the rising regime, `size_down` of one in the falling one.

    Added 2026-10-01 after the first eligible trials: a gate open enough for the
    availability rule keeps the book fully exposed through a bear year, and 2022 cost every
    one of them 70-80%. Trading smaller when BTC is below its average keeps the option to
    trade without paying a bear market in full.
    """
    down = float(cfg.get("size_down", 1.0))
    k = cfg.get("vol_target")
    if down >= 1.0 and not k:
        return None
    up = world.regime_up(cfg["regime_ma"])
    out = {s: np.where(up[s], 1.0, down) for s in world.per}
    if k:
        # Volatility targeting (catalogue A5, 2026-10-10): a stake shrinks when its coin's
        # last-day volatility is above k x the reference (the median over years <= 2020,
        # so causal for every test year); never above a full slot, never below a quarter.
        vol, ref = world.vol96()
        out = {s: out[s] * np.clip(k * ref / np.maximum(vol[s], 1e-6), 0.25, 1.0) for s in world.per}
    return out


def availability(world: World, g: dict) -> dict:
    out = {}
    for y in range(2019, FORWARD):
        days_all, days_on = set(), set()
        for s, d in world.per.items():
            sel = d["year"] == y
            day = d["ns"][sel] // 86_400_000_000_000
            days_all.update(np.unique(day).tolist())
            days_on.update(np.unique(day[g[s][sel]]).tolist())
        if not days_all:
            continue
        ordered = sorted(days_all)
        gap = run = 0
        for dd in ordered:
            run = 0 if dd in days_on else run + 1
            gap = max(gap, run)
        out[y] = {"day_share": round(len(days_on) / len(days_all), 4), "longest_gap_days": gap}
    ok = all(v["day_share"] >= DAY_SHARE_MIN and v["longest_gap_days"] <= GAP_MAX for v in out.values())
    return {"per_year": out, "passes": ok}


def selector_masks(world: World, cfg: dict, g: dict, regime: dict, fit_last: int,
                   choose_year: int, device: str) -> tuple[float, callable]:
    """Fit per-regime scorers on years <= fit_last; return (share chosen on choose_year, masks_for)."""
    out = world.outcomes(cfg["horizon"])
    votes_by_seed = []
    for seed in SEEDS:
        scores = {s: np.full(len(world.per[s]["X"]), np.nan, dtype=np.float32) for s in world.per}
        for up_flag in (True, False):
            if cfg["regime_ma"] is None and not up_flag:
                continue
            xs, ys = [], []
            for s, d in world.per.items():
                o = out[s]
                yr = d["year"][o["idx"]]
                keep = (g[s][o["idx"]] & (regime[s][o["idx"]] == up_flag) & (yr <= fit_last)
                        & (o["end_year"] <= fit_last) & np.isfinite(o["net"]))
                xs.append(world.feats(cfg)[s][o["idx"][keep]])
                ys.append((o["net"] - o["mae"])[keep])
            X, Y = np.concatenate(xs), np.concatenate(ys)
            if len(X) < 1000:
                continue
            if len(X) > MAX_FIT_ROWS:
                pick = np.random.default_rng(seed).choice(len(X), MAX_FIT_ROWS, replace=False)
                X, Y = X[pick], Y[pick]
            model = B.fit(X, Y, seed, device, epochs=6)
            for s in world.per:
                m = g[s] & (regime[s] == up_flag)
                if m.any():
                    scores[s][m] = B.score(model, world.feats(cfg)[s][m], device)
        votes_by_seed.append(scores)

    def masks_for(share: float, bar_year: int) -> dict:
        """Take where >= 3 of 4 seeds score above their own bar (that bar set on bar_year)."""
        count = {s: np.zeros(len(world.per[s]["X"]), dtype=np.int8) for s in world.per}
        for scores in votes_by_seed:
            pool = np.concatenate([scores[s][(world.per[s]["year"] == bar_year) & g[s]] for s in world.per])
            pool = pool[np.isfinite(pool)]
            if not len(pool):
                continue
            bar = float(np.quantile(pool, 1 - share))
            for s in world.per:
                count[s] += np.nan_to_num(scores[s], nan=-np.inf) >= bar
        need = max(1, int(np.ceil(0.75 * len(votes_by_seed))))
        return {s: g[s] & (count[s] >= need) for s in world.per}

    if cfg.get("take_bar") in ("pooled", "regime"):
        return _take_bar(world, cfg, g, regime, fit_last, choose_year, masks_for, votes_by_seed, device)
    best_share, best_key = SHARES[0], None
    for share in SHARES:
        r = world.book(masks_for(share, choose_year), choose_year, cfg["horizon"], sizing(world, cfg))
        key = (r["trades"] >= MIN_TRADES, r["q"])
        if best_key is None or key > best_key:
            best_share, best_key = share, key
    return best_share, masks_for


# Take-bar choice (review round 2, consultant's design change). Default (cfg without
# "take_bar"): the share is chosen on the single year N-1, so it flips 0.1 <-> 0.5 with that
# year's regime (PIT.md: 2021's 10% bar admitted nothing in 2022). "pooled": chosen on every
# choose-year from TAKE_BAR_FROM to N-1, each read by its own fold's scorers (fitted <= Y-1, so
# every year is out of sample for the scorers that read it); key = (years with >= MIN_TRADES,
# mean q). "regime": the same per BTC regime - a share and a bar for the rising bars, another
# for the falling ones (= "pooled" when regime_ma is None). Drawn only by the PIT search.
TAKE_BAR_STEPS = (None, "pooled", "regime")
TAKE_BAR_FROM = 2020
DRAW_TAKE_BAR = False          # True only in a PIT search process (pit_search.bind)
_SHARE_KEYS: dict = {}


def pick_share(tables: list[dict], flag) -> float:
    """The share with the best pooled key over per-year tables {(flag, share): (trades, q)}."""
    best, best_key = SHARES[0], None
    for share in SHARES:
        rows = [t[(flag, share)] for t in tables]
        key = (sum(int(n) >= MIN_TRADES for n, _ in rows), float(np.mean([float(q) for _, q in rows])))
        if best_key is None or key > best_key:
            best, best_key = share, key
    return best


def _take_bar(world, cfg: dict, g: dict, regime: dict, fit_last: int, choose_year: int,
              masks_for, votes_by_seed: list, device: str):
    by_reg = cfg["take_bar"] == "regime" and cfg["regime_ma"] is not None

    def masks_regime(sh: dict, bar_year: int) -> dict:
        """As masks_for, with each seed's bar set per regime on that regime's bars of bar_year."""
        count = {s: np.zeros(len(world.per[s]["X"]), dtype=np.int8) for s in world.per}
        for scores in votes_by_seed:
            for flag, share in ((True, sh["up"]), (False, sh["down"])):
                sel = {s: (world.per[s]["year"] == bar_year) & g[s] & (regime[s] == flag) for s in world.per}
                pool = np.concatenate([scores[s][sel[s]] for s in world.per])
                pool = pool[np.isfinite(pool)]
                if not len(pool):     # no bar of this regime that year: the all-regime bar
                    pool = np.concatenate([scores[s][(world.per[s]["year"] == bar_year) & g[s]] for s in world.per])
                    pool = pool[np.isfinite(pool)]
                if not len(pool):
                    continue
                bar = float(np.quantile(pool, 1 - share))
                for s in world.per:
                    count[s] += (regime[s] == flag) & (np.nan_to_num(scores[s], nan=-np.inf) >= bar)
        need = max(1, int(np.ceil(0.75 * len(votes_by_seed))))
        return {s: g[s] & (count[s] >= need) for s in world.per}

    sk = (cfg_id({k: v for k, v in cfg.items() if k not in MM_KEYS and k != "take_bar"}), SEEDS, by_reg)
    size = sizing(world, cfg)
    table = {}
    for share in SHARES:
        if by_reg:
            m = masks_regime({"up": share, "down": share}, choose_year)
            for flag in (True, False):
                r = world.book({s: m[s] & (regime[s] == flag) for s in m}, choose_year, cfg["horizon"], size)
                table[(flag, share)] = (r["trades"], r["q"])
        else:
            r = world.book(masks_for(share, choose_year), choose_year, cfg["horizon"], size)
            table[(None, share)] = (r["trades"], r["q"])
    if len(_SHARE_KEYS) >= 256:
        _SHARE_KEYS.pop(next(iter(_SHARE_KEYS)))
    _SHARE_KEYS[(sk, choose_year)] = table
    first = min(TAKE_BAR_FROM, choose_year)
    for y in range(first, choose_year):             # earlier folds, oldest first, each once
        if (sk, y) not in _SHARE_KEYS:
            selector_masks(world, cfg, g, regime, y - 1, y, device)
    tables = [_SHARE_KEYS[(sk, y)] for y in range(first, choose_year + 1) if (sk, y) in _SHARE_KEYS]
    if by_reg:
        sh = {"up": pick_share(tables, True), "down": pick_share(tables, False)}
        return sh, lambda share, bar_year: masks_regime(share, bar_year)
    return pick_share(tables, None), masks_for


EXIT_K = 96           # the learned exit predicts the next day's return (96 bars of 15 minutes)
EXIT_ROWS = 1_000_000
EXIT_BAND = 0.003      # act only past the round trip: exit below -0.3%, enter above +0.3%
EXIT_MIN_HOLD = 16     # bars (4 h) before the learned exit may close a position


def exit_keep(world: World, cfg: dict, fit_last: int, device: str) -> dict:
    """The learned exit (operator, 2026-10-06: change the approach - the money is lost in the exit).

    A small regressor per seed, trained on every bar of years <= `fit_last` whose window
    also ends by then, predicts the next day's return from the 44 market columns, the
    regime bit and breadth. An open position is KEPT while the four seeds' average
    prediction is above zero and closed the bar it is not; the stop and the trail stay
    on as the book's safety net, and `horizon` caps the hold. Causal: only past years
    train it, and it reads only what the bar could see.
    """
    up = world.regime_up(cfg["regime_ma"])
    target = world.fwd(EXIT_K)

    def feats(s, sel=slice(None)):
        d = world.per[s]
        extra = np.stack([up[s][sel].astype(np.float32) * 2 - 1,
                          (d["breadth"][sel] * 2 - 1).astype(np.float32)], axis=1)
        return np.concatenate([world.feats(cfg)[s][sel], extra], axis=1)

    xs, ys = [], []
    for s, d in world.per.items():
        tg = target[s]
        ok = (world.valid[s] & (d["year"] <= fit_last) & (tg["end_year"] <= fit_last)
              & np.isfinite(tg["fwd"]))
        idx = np.flatnonzero(ok)
        if len(idx):
            xs.append(feats(s, idx)); ys.append(np.clip(tg["fwd"][idx], -0.3, 0.3))
    X, Y = np.concatenate(xs), np.concatenate(ys)
    pred = {s: np.zeros(len(d["X"]), dtype=np.float32) for s, d in world.per.items()}
    for seed in SEEDS:
        pick = np.random.default_rng(seed).choice(len(X), min(EXIT_ROWS, len(X)), replace=False)
        model = B.fit(X[pick], Y[pick].astype(np.float32), seed, device, epochs=4)
        for s in world.per:
            pred[s] += B.score(model, feats(s), device) / len(SEEDS)
    # First run (2026-10-06): "keep while > 0" exited and re-entered bar after bar -
    # 4,982 trades in 2024 at a 10% win rate, -99%. The model now acts only when its
    # forecast clears the cost of acting: keep unless clearly negative, and the same
    # forecast vetoes entries it expects to lose.
    return {"keep": {s: pred[s] > -EXIT_BAND for s in world.per},
            "enter": {s: pred[s] > EXIT_BAND for s in world.per},
            "pred": pred}


_SIGNALS: dict = {}


def signals(world: World, cfg: dict, N: int, g: dict, regime: dict, device: str):
    """Entry masks and exit for test year N. They do not depend on the money-management
    keys, so trials that differ only in those reuse them (the book alone is re-run)."""
    key = (cfg_id({k: v for k, v in cfg.items() if k not in MM_KEYS}), N, SEEDS)
    if key not in _SIGNALS:
        if cfg["selector"]:
            share, masks_for = selector_masks(world, cfg, g, regime, N - 2, N - 1, device)
            masks = masks_for(share, N - 1)
        else:
            share, masks = None, g
        keep = pred = None
        if cfg.get("exit") == "learned":
            ex = exit_keep(world, cfg, N - 1, device)
            keep, pred = ex["keep"], ex["pred"]
            masks = {sym: masks[sym] & ex["enter"][sym] for sym in masks}
        if len(_SIGNALS) >= 32:
            _SIGNALS.pop(next(iter(_SIGNALS)))
        _SIGNALS[key] = (share, masks, keep, pred)
    return _SIGNALS[key][:3]


def strength(world: World, cfg: dict, N: int, g: dict, regime: dict, device: str) -> dict | None:
    """The signal model's continuous forecast for year N (None without a learned exit)."""
    signals(world, cfg, N, g, regime, device)
    key = (cfg_id({k: v for k, v in cfg.items() if k not in MM_KEYS}), N, SEEDS)
    return _SIGNALS[key][3]


VETO_MIN_TRADES = 20
VETO_FIRST_YEAR = 2020


def pareto_veto(world: World, cfg: dict, N: int, g: dict, regime: dict, device: str) -> tuple[dict, dict]:
    """Where this configuration loses, learned from its own past trades (operator,
    2026-10-08: "detect the conditions in which we fail consistently and do not trade them").

    The same configuration is booked on the up-to-three years before N (each with its own
    walk-forward signals, so nothing from N or later). Its trades are bucketed two ways -
    by coin, and by condition: regime (up/down) x volatility tercile x breadth band. A
    bucket with at least VETO_MIN_TRADES trades and a negative mean return is vetoed in N.
    """
    feats = world.full()
    up = world.regime_up(cfg["regime_ma"])
    rows = []
    for M in range(max(VETO_FIRST_YEAR, N - 3), N):
        _, m_masks, m_keep = signals(world, cfg, M, g, regime, device)
        r = world.book(m_masks, M, cfg["horizon"], sizing(world, cfg), m_keep, EXIT_MIN_HOLD, **mm_kwargs(cfg))
        for sym, bar, ret in r["trade_log"]:
            rows.append((sym, bool(up[sym][bar]), float(feats[sym][bar, 48]),
                         float(world.per[sym]["breadth"][bar]), ret))
    if len(rows) < VETO_MIN_TRADES:
        return {}, {"trades": len(rows)}
    vols = np.array([x[2] for x in rows])
    edges = np.quantile(vols, [1 / 3, 2 / 3])
    band = lambda b: 0 if b < 0.3 else (1 if b < 0.6 else 2)  # noqa: E731

    def cond(rg, v, b):
        return (int(rg), int(np.searchsorted(edges, v)), band(b))

    by_coin, by_cond = {}, {}
    for sym, rg, v, b, ret in rows:
        by_coin.setdefault(sym, []).append(ret)
        by_cond.setdefault(cond(rg, v, b), []).append(ret)
    bad_coin = {k for k, v in by_coin.items() if len(v) >= VETO_MIN_TRADES and np.mean(v) < 0}
    bad_cond = {k for k, v in by_cond.items() if len(v) >= VETO_MIN_TRADES and np.mean(v) < 0}
    veto = {}
    for sym, d in world.per.items():
        if sym in bad_coin:
            veto[sym] = np.ones(len(d["X"]), dtype=bool)
            continue
        vb = np.searchsorted(edges, feats[sym][:, 48])
        bb = np.where(d["breadth"] < 0.3, 0, np.where(d["breadth"] < 0.6, 1, 2))
        rg = up[sym].astype(int)
        v = np.zeros(len(d["X"]), dtype=bool)
        for c in bad_cond:
            v |= (rg == c[0]) & (vb == c[1]) & (bb == c[2])
        veto[sym] = v
    info = {"trades": len(rows), "coins": sorted(bad_coin), "conditions": sorted(map(list, bad_cond))}
    return veto, info


def evaluate(world: World, cfg: dict, device: str) -> dict:
    t0 = time.time()
    g, regime = gate(world, cfg)
    avail = availability(world, g)
    years = {}
    for N in TEST_YEARS:
        share, masks, keep = signals(world, cfg, N, g, regime, device)
        st = strength(world, cfg, N, g, regime, device) if (cfg.get("size_signal") or cfg.get("scale_in")) else None
        veto_info = None
        if cfg.get("veto") == "pareto":
            veto, veto_info = pareto_veto(world, cfg, N, g, regime, device)
            if veto:
                masks = {sym: masks[sym] & ~veto[sym] for sym in masks}
        r = world.book(masks, N, cfg["horizon"], sizing(world, cfg), keep, EXIT_MIN_HOLD,
                       strength=st, **mm_kwargs(cfg))
        months = monthly(world, N, r.pop("daily"))
        r.pop("trade_log", None)
        if months is not None:
            r["monthly"] = months
        if veto_info is not None:
            r["veto"] = veto_info
        years[N] = {**r, "share": share}
    rets = [years[y]["return"] for y in TEST_YEARS]
    worst = min(rets)
    cagr = float(np.prod([1 + r for r in rets]) ** (1 / len(rets)) - 1)
    active = all(years[y]["trades"] >= MIN_TRADES for y in TEST_YEARS)
    return {"id": cfg_id(cfg), "cfg": cfg, "at": _now(), "book_v": BOOK_V,
            "score": law(years, max(years[y]["max_dd"] for y in TEST_YEARS)), "worst_year": round(worst, 4),
            "cagr": round(cagr, 4), "worst_q": round(min(years[y]["q"] for y in TEST_YEARS), 4),
            "max_dd": round(max(years[y]["max_dd"] for y in TEST_YEARS), 4),
            "eligible": bool(avail["passes"] and active and guarded(cfg)
                             and max(years[y]["max_dd"] for y in TEST_YEARS) <= DD_CAP),
            "availability": avail,
            "years": years, "minutes": round((time.time() - t0) / 60, 2)}


def monthly(world: World, year: int, daily: list) -> list | None:
    """The book's daily returns compounded per calendar month (12 numbers), kept on the trial
    row so overfit.py's PBO can use months instead of years. None if the days do not line up."""
    ns = np.concatenate([d["ns"][d["year"] == year] for d in world.per.values()])
    days = np.unique(ns.astype("datetime64[ns]").astype("datetime64[D]"))
    if len(days) != len(daily) or not len(days):
        return None
    m = days.astype("datetime64[M]").astype(int) % 12
    g = np.log1p(np.asarray(daily, dtype=float))
    out = [round(float(np.expm1(g[m == k].sum())), 5) for k in range(12)]
    return out if len(np.unique(m)) == 12 else None


# ------------------------------------------------------------------ the search policy

def ledger() -> list[dict]:
    if not TRIALS.is_file():
        return []
    rows = [json.loads(x) for x in TRIALS.read_text(encoding="utf-8").splitlines() if x.strip()]
    # A worker still on pre-lever code books a lever cfg WITHOUT the lever; such rows are
    # dropped so the configuration is tried again by a worker that knows it.
    rows = [r for r in rows if r.get("book_v") or not any(k in r["cfg"] for k in LEVER_KEYS)]
    for r in rows:  # trials logged before the drawdown cap are judged by it too
        r["eligible"] = bool(r["eligible"] and r["max_dd"] <= DD_CAP and guarded(r["cfg"]))
        # every row is judged by today's law, a confirmed one by the weaker of its two seed sets
        if not r.get("years"):
            continue
        r["score"] = law(r["years"], max(float(v["max_dd"]) for v in r["years"].values()))
        c = r.get("confirm") or {}
        if c.get("years"):
            r["score"] = min(r["score"], law(c["years"], max(float(v["max_dd"]) for v in c["years"].values())))
    return rows


def neighbours(cfg: dict) -> list[dict]:
    out = []

    def step(seq, v, k):
        i = seq.index(v) if v in seq else 0
        return [seq[j] for j in (i - k, i + k) if 0 <= j < len(seq)]

    for v in step(MA_STEPS, cfg["regime_ma"], 1):
        out.append({**cfg, "regime_ma": v})
    for key in ("b_up", "b_down"):
        for v in step(B_STEPS, cfg[key], 1):
            out.append({**cfg, key: v})
    for v in step(H_STEPS, cfg["horizon"], 1):
        out.append({**cfg, "horizon": v})
    out.append({**cfg, "selector": not cfg["selector"]})
    out.append({**cfg, "exit": "fixed" if cfg.get("exit") == "learned" else "learned"})
    out.append({**cfg, "features": "price" if cfg.get("features") == "full" else "full"})
    out.append({**cfg, "veto": None if cfg.get("veto") == "pareto" else "pareto"})
    for v in step(VOL_STEPS, cfg.get("vol_target"), 1):
        out.append({**cfg, "vol_target": v})
    if cfg.get("exit") == "learned":
        for v in step(SIZE_SIGNAL_STEPS, cfg.get("size_signal"), 1):
            out.append({**cfg, "size_signal": v})
        out.append({**cfg, "scale_in": not cfg.get("scale_in", False)})
    # book levers (2026-10-14); companion keys only move while their lever is on
    for key, seq in (("mom_rank", MOM_STEPS), ("corr_cap", CORR_STEPS), ("eq_filter", EQ_STEPS),
                     ("take_profit", TP_STEPS), ("breakeven", BE_STEPS)):
        for v in step(seq, cfg.get(key), 1):
            out.append(_lever(cfg, key, v))
    if cfg.get("mom_rank"):
        for key, seq, default in (("mom_days", MOM_DAYS_STEPS, 60), ("mom_in", MOM_IN_STEPS, 2.0)):
            for v in step(seq, cfg.get(key, default), 1):
                out.append(_lever(cfg, key, v if v != default else None))
    if cfg.get("size_signal"):
        for v in step(EDGE_STEPS, cfg.get("min_edge"), 1):
            out.append(_lever(cfg, "min_edge", v))
    if cfg["regime_ma"] is not None:
        for v in step(SIZE_STEPS, cfg.get("size_down", 1.0), 1):
            out.append({**cfg, "size_down": v})
    if DRAW_TAKE_BAR and cfg["selector"]:      # PIT search only (review round 2)
        for v in TAKE_BAR_STEPS:
            if v != cfg.get("take_bar"):
                out.append(_lever(cfg, "take_bar", v))
    for key, seq, default in (("book_stop", BOOK_STOP_STEPS, None), ("stop", STOP_STEPS, None),
                              ("slots", SLOT_STEPS, 3), ("dd_scale", DD_SCALE_STEPS, None)):
        for v in step(seq, cfg.get(key, default), 1):
            out.append({**cfg, key: v})
    return out


def _lever(cfg: dict, key: str, v) -> dict:
    """cfg with lever `key` set to v; None removes it (and, for mom_rank, its companions),
    so a lever switched off is the very configuration it came from."""
    out = {k: x for k, x in cfg.items() if k != key}
    if v is not None:
        out[key] = v
    elif key == "mom_rank":
        out = {k: x for k, x in out.items() if k not in ("mom_days", "mom_in", "mom_out")}
    return out


def shortfall(r: dict) -> float:
    """How far a trial is from the availability rule: 0 when it passes."""
    yrs = r["availability"]["per_year"].values()
    return sum(max(0.0, DAY_SHARE_MIN - v["day_share"]) + max(0, v["longest_gap_days"] - GAP_MAX) / 100
               for v in yrs)


def rank_key(r: dict) -> float:
    """Eligible trials by score; the rest by score minus a heavy price for missing the rule.

    The first version ranked ineligible trials by score alone and climbed, 43 trials in a
    row, the scores of gates that required half the market to be rising - which leaves
    27% of 2022's days tradeable. The price steers the walk toward the feasible region
    first, and the score decides inside it.
    """
    return r["score"] if r["eligible"] else r["score"] - 2.0 * shortfall(r) - 1.0 - 2.0 * dd_excess(r)


def dd_excess(r: dict) -> float:
    """How far the worst test year's drawdown is above the cap: 0 when it is under."""
    return max(0.0, r["max_dd"] - DD_CAP)


def random_config(rng) -> dict:
    """A configuration drawn from the whole space - the daily strategy's answer to a stall."""
    cfg = {"regime_ma": rng.choice(MA_STEPS[1:]).item(), "b_up": float(rng.choice(B_STEPS[:-1])),
           "b_down": float(rng.choice(B_STEPS[:4])), "selector": bool(rng.random() < 0.8),
           "horizon": int(rng.choice(H_STEPS)), "size_down": float(rng.choice(SIZE_STEPS)),
           "exit": "learned", "features": str(rng.choice(["price", "full"])),
           "slots": int(rng.choice(SLOT_STEPS))}
    for key, steps in (("dd_scale", DD_SCALE_STEPS), ("size_signal", SIZE_SIGNAL_STEPS), ("vol_target", VOL_STEPS)):
        v = steps[int(rng.integers(len(steps)))]
        if v is not None:
            cfg[key] = v
    # book levers (2026-10-14), each on with a small probability so the space around the
    # release keeps most of the draws
    for key, steps in (("mom_rank", MOM_STEPS), ("corr_cap", CORR_STEPS), ("eq_filter", EQ_STEPS),
                       ("take_profit", TP_STEPS), ("breakeven", BE_STEPS)):
        if rng.random() < LEVER_P:
            cfg[key] = steps[1 + int(rng.integers(len(steps) - 1))]
    if cfg.get("mom_rank"):
        days, boost = int(rng.choice(MOM_DAYS_STEPS)), float(rng.choice(MOM_IN_STEPS))
        if days != 60:          # defaults stay implicit, so one setting has one id
            cfg["mom_days"] = days
        if boost != 2.0:
            cfg["mom_in"] = boost
    if cfg.get("size_signal") and rng.random() < LEVER_P:
        cfg["min_edge"] = EDGE_STEPS[1 + int(rng.integers(len(EDGE_STEPS) - 1))]
    if DRAW_TAKE_BAR and cfg["selector"] and rng.random() < LEVER_P:   # PIT search only
        cfg["take_bar"] = TAKE_BAR_STEPS[1 + int(rng.integers(len(TAKE_BAR_STEPS) - 1))]
    return cfg


def next_config(done: list[dict], skip: set | None = None) -> dict | None:
    seen = {r["id"] for r in done} | set(skip or ())
    for cfg in SEED_CONFIGS:
        if cfg_id(cfg) not in seen:
            return cfg
    # research/system10/EXPLORE (set by the daily strategy review after a stall): a third
    # of the trials jump anywhere in the space instead of walking the neighbourhood.
    if (OUT / "EXPLORE").exists():
        rng = np.random.default_rng()
        if rng.random() < 1 / 3:
            for _ in range(50):
                cfg = random_config(rng)
                if cfg_id(cfg) not in seen:
                    return cfg
    ranked = sorted(done, key=lambda r: -rank_key(r))
    legal = lambda c: not (c["regime_ma"] is None and c["b_up"] != c["b_down"])  # noqa: E731
    # Money management (2026-10-08) is tried first on the best signal sets by the old rule
    # (availability + activity, ignoring the new cap): only the book re-runs, so it is cheap.
    strong = sorted([r for r in done if r["availability"]["passes"] and operates(r)
                     and all(v["trades"] >= MIN_TRADES for v in r["years"].values())],
                    key=lambda r: -r["score"])[:15]
    for r in strong:
        base = {k: v for k, v in r["cfg"].items() if k not in MM_KEYS}
        # first probe (2026-10-08, release 20's signals): the account stop did not bound the
        # year (legs add up); 8 slots took the worst year from -2% to +2% and DD 51% -> 44%
        extras = [{"slots": 8}]
        for L in DD_SCALE_STEPS[1:]:
            extras += [{"dd_scale": L}, {"dd_scale": L, "slots": 8}, {"dd_scale": L, "slots": 5}]
        extras += [{"book_stop": bs, "slots": 8} for bs in BOOK_STOP_STEPS[1:]]
        for extra in extras:
            cfg = {**base, **extra}
            if cfg_id(cfg) not in seen:
                return cfg
    # The signal-strength trader (2026-10-10) first, on the best qualifying configs with a
    # learned exit (the forecast is the strength); then volatility targeting, then the veto.
    for r in [r for r in ranked if r["eligible"] and operates(r) and r["cfg"].get("exit") == "learned"][:10]:
        # Probe on release 27 (2026-10-10): stake by strength halved the drawdown at the same
        # return (2024 +42%/DD 23% -> +42%/DD 11%; 2025 +0.1%/25% -> +5.9%/15%); scaling in
        # hurt (2025 -9%). So: strength sizing, then spend the freed drawdown on exposure.
        base = {k: v for k, v in r["cfg"].items() if k not in ("scale_in",)}
        for extra in ({"size_signal": 0.01}, {"size_signal": 0.02},
                      {"size_signal": 0.01, "slots": 3}, {"size_signal": 0.02, "slots": 3},
                      {"size_signal": 0.01, "dd_scale": None}, {"size_signal": 0.02, "dd_scale": None},
                      {"size_signal": 0.01, "slots": 3, "dd_scale": None},
                      {"size_signal": 0.02, "slots": 3, "dd_scale": None},
                      {"size_signal": 0.01, "size_down": 0.5}, {"size_signal": 0.02, "size_down": 0.5}):
            cfg = {k: v for k, v in {**base, **extra}.items() if v is not None or k not in ("dd_scale",)}
            if cfg_id(cfg) not in seen:
                return cfg
    for r in [r for r in ranked if r["eligible"] and operates(r)][:10]:
        for extra in ({"vol_target": 1.0}, {"vol_target": 0.75}, {"vol_target": 1.5}):
            cfg = {**r["cfg"], **extra}
            if cfg_id(cfg) not in seen:
                return cfg
    for r in [r for r in ranked if r["eligible"] and operates(r)][:10]:
        cfg = {**r["cfg"], "veto": "pareto"}
        if cfg_id(cfg) not in seen:
            return cfg
    # Book levers (2026-10-14): the study's chosen momentum boosts on the best qualifying
    # configurations, before the neighbourhood walk. Book-only, so the signals are reused.
    for r in [r for r in ranked if r["eligible"] and operates(r)][:5]:
        for extra in LEVER_PROBES:
            cfg = {**r["cfg"], **extra}
            if cfg_id(cfg) not in seen:
                return cfg
    # The learned exit (2026-10-06) is tried first on the best condition sets found so far.
    for r in [r for r in ranked if r["eligible"] and operates(r)][:12]:
        for extra in ({"exit": "learned", "features": "full"}, {"exit": "learned"}, {"features": "full"}):
            cfg = {**r["cfg"], **extra}
            if cfg_id(cfg) not in seen:
                return cfg
    for width in (3, 10, len(ranked)):
        for r in ranked[:width]:
            for cfg in neighbours(r["cfg"]):
                if cfg_id(cfg) not in seen and legal(cfg):
                    return cfg
    # Every one-step neighbour of every trial is spent: take two steps from the best.
    for r in ranked[:5]:
        for a in neighbours(r["cfg"]):
            for cfg in neighbours(a):
                if cfg_id(cfg) not in seen and legal(cfg):
                    return cfg
    return None


def operates(r: dict) -> bool:
    """A zero stake in the falling regime is not trading there.

    Release 5 (2026-10-05) set `size_down` to 0: its gate stayed open in the bear regime,
    so the availability check passed, but the book put nothing on - a system that sits
    out every bear market, which is exactly what the operator's availability rule forbids.
    Such trials stay on the ledger and are never champions.
    """
    return float(r["cfg"].get("size_down", 1.0)) > 0


def guarded(cfg: dict) -> bool:
    """Audit 2026-10-15: release 43 won without the 12% stop and the drawdown-scaled stakes
    the decision log credits with keeping DD <= 25%; its cap held in-sample only. A champion
    must carry both money-management guards."""
    return bool(cfg.get("dd_scale")) and bool(cfg.get("stop"))


def confirmed(r: dict) -> bool:
    return bool(r.get("confirm", {}).get("eligible"))


def reconfirm(done: list[dict], busy: set) -> dict | None:
    """A trial that beats the champion under today's law but was never confirmed (it was booked
    under an older law) is re-run first, so the second seed set can confirm or sink it. Each id
    gets one re-run: rows seen twice are left alone."""
    champ = _champion_raw(done)
    seen: dict = {}
    for r in done:
        seen[r["id"]] = seen.get(r["id"], 0) + 1
    pend = [r for r in done if r["eligible"] and operates(r) and not r.get("confirm")
            and seen[r["id"]] == 1 and r["id"] not in busy
            and (champ is None or r["score"] > champ["score"])]
    return max(pend, key=lambda r: r["score"])["cfg"] if pend else None


def _champion_raw(done: list[dict]) -> dict | None:
    """The max-over-trials champion: eligible on both seed sets, best (score, worst q)."""
    pool = [r for r in done if r["eligible"] and operates(r) and confirmed(r)]
    return max(pool, key=lambda r: (r["score"], r["worst_q"])) if pool else None


def champion(done: list[dict]) -> dict | None:
    """The champion. With ENABLE_NESTED_ELIGIBILITY (review round 2, R2) only while the
    nested reading passes (nested_refusal); otherwise there is none, so nothing advances."""
    best = _champion_raw(done)
    if best is not None and NESTED_FLAG.is_file() and nested_refusal(done):
        return None
    return best


# Review round 2, R2: eligibility read on the nested curve. Absent (default): unchanged.
NESTED_FLAG = OUT / "ENABLE_NESTED_ELIGIBILITY"


def nested_refusal(done: list[dict]) -> str | None:
    """Why the nested (chosen-on-the-past) reading fails the eligibility rules, or None.

    A fixed configuration has no nested result of its own - its years are already out of
    sample for its models; what is in sample is the CHOICE of it among the trials. So the
    rule is read on the selection: overfit.py's nested curves (main seeds, and chosen on the
    weaker of both seed sets read on the confirm set) must each have a pick for 2023, 2024
    and 2025, and every pick's year must meet DD <= DD_CAP, trades >= MIN_TRADES and the
    availability rule (overfit.nested_failures). Reads the cached rnd/overfit.json (8-hourly);
    missing, unreadable or older than OVERFIT_MAX_AGE_H refuses - this is a restriction."""
    from . import overfit as O
    try:
        doc = json.loads(OVERFIT.read_text(encoding="utf-8"))
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(doc["at"])).total_seconds() / 3600
    except (OSError, ValueError, KeyError, TypeError):
        return "no nested reading (overfit.json missing or unreadable)"
    if age_h > OVERFIT_MAX_AGE_H:
        return f"nested reading stale ({age_h:.0f} h)"
    fails = O.nested_failures(doc, done)
    return "; ".join(fails[:4]) if fails else None


# ------------------------------------------------------------------ the monitor's inputs

def gpu_snapshot() -> dict:
    """The card's live state, from nvidia-smi. Never fails the search."""
    import subprocess
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,"
             "temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        name, util, used, total, temp, power = [x.strip() for x in out.split(",")]
        num = lambda v: float(v) if v.replace(".", "", 1).isdigit() else None  # noqa: E731
        return {"name": name, "util_pct": num(util), "mem_used_mb": num(used),
                "mem_total_mb": num(total), "temp_c": num(temp), "power_w": num(power),
                "at": _now()}
    except Exception:  # noqa: BLE001
        return {"at": _now(), "error": "nvidia-smi unavailable"}


def add_event(kind: str, text: str) -> None:
    with EVENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": _now(), "kind": kind, "text": text}) + "\n")


def pooled(years: dict) -> dict:
    """Winning-trade share and totals over the unseen test years, trade-weighted."""
    trades = sum(int(v["trades"]) for v in years.values())
    wins = sum(float(v.get("win_rate") or 0) * int(v["trades"]) for v in years.values())
    return {"trades": trades, "win_rate": round(wins / trades, 4) if trades else None,
            "worst_year": round(min(float(v["return"]) for v in years.values()), 4)}


def cfg_label(cfg: dict) -> str:
    ma = f"BTC vs its {cfg['regime_ma']}-day average" if cfg["regime_ma"] else "one regime"
    sel = "AI selector" if cfg["selector"] else "no selector"
    size = (f", {cfg['size_down']:g}x size when falling" if cfg.get("size_down", 1.0) < 1.0 else "")
    ex = (f"AI exit (max {cfg['horizon']} bars)" if cfg.get("exit") == "learned"
          else f"exit {cfg['horizon']} bars")
    full = ", full market picture" if cfg.get("features") == "full" else ""
    if cfg.get("size_signal") or cfg.get("scale_in"):
        full += ", signal-strength trader"
    if cfg.get("forecast") == "ensemble":
        full += ", GPU forecast ensemble"
    if cfg.get("take_bar"):
        full += f", take-bar chosen {cfg['take_bar']}"
    if cfg.get("mom_rank"):
        full += (f", {cfg.get('mom_in', 2.0):g}x stake on the top {cfg['mom_rank']} coins by "
                 f"{cfg.get('mom_days', 60)}-day return")
    for key, text in (("corr_cap", "correlation cap {}"), ("eq_filter", "equity filter {}d"),
                      ("min_edge", "min edge {}"), ("take_profit", "take profit {}"),
                      ("breakeven", "breakeven after {}")):
        if cfg.get(key) is not None:
            full += ", " + text.format(f"{cfg[key]:g}")
    return f"{ma}, breadth up {cfg['b_up']:g} / down {cfg['b_down']:g}, {sel}, {ex}{size}{full}"


# ------------------------------------------------------------------ the 2026 reading

def forward_reading(world: World, champ: dict, device: str, hours: float, trials: int) -> dict:
    # The same path as evaluate(): signals, Pareto veto, and the money management. Until
    # 2026-10-10 this booked the release WITHOUT its money-management keys (slots, drawdown-
    # scaled stakes), so release 27 read +54.2% here against +27.3% in its real form.
    cfg = champ["cfg"]
    g, regime = gate(world, cfg)
    share, masks, keep = signals(world, cfg, FORWARD, g, regime, device)
    st = strength(world, cfg, FORWARD, g, regime, device) if (cfg.get("size_signal") or cfg.get("scale_in")) else None
    if cfg.get("veto") == "pareto":
        veto, _ = pareto_veto(world, cfg, FORWARD, g, regime, device)
        if veto:
            masks = {sym: masks[sym] & ~veto[sym] for sym in masks}
    r = world.book(masks, FORWARD, cfg["horizon"], sizing(world, cfg), keep, EXIT_MIN_HOLD,
                   strength=st, **mm_kwargs(cfg))
    r.pop("trade_log", None)
    daily = r.pop("daily")
    eq = list(np.round(np.cumprod(1 + np.asarray(daily)) * 100_000.0, 2))
    prior = ledger_rows(LOG)
    row = {"at": _now(), "lineage": "champion", "cycle": len(prior) + 1,
           "train_hours": round(hours, 2), "updates": trials, "env_steps": trials,
           "champion": champ["id"], "cfg": cfg, "share": share,
           "in_sample_2025": champ["years"][2025] if 2025 in champ["years"] else champ["years"]["2025"],
           "forward_2026": r, "forward_equity": eq[::3]}
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


def timeline_reading(world: World, champ: dict | None, device: str, hours: float, trials: int,
                     cache: dict) -> dict:
    """One point on the operator's success chart. The 2026 part is recomputed only when the
    champion changes or the bars are fresh; between those an unchanged point is the truth."""
    row = {"at": _now(), "trials": trials, "search_hours": round(hours, 2), "gpu": gpu_snapshot()}
    if champ:
        if cache.get("id") != champ["id"]:
            fwd = forward_reading(world, champ, device, hours, trials)
            cache.update({"id": champ["id"], "fwd": fwd["forward_2026"]})
        f = cache["fwd"]
        yrs = {int(k): v for k, v in champ["years"].items()}
        row.update({"champion": champ["id"], "champion_label": cfg_label(champ["cfg"]),
                    "unseen": pooled(yrs), "score": champ["score"],
                    "forward_2026": {k: f.get(k) for k in
                                     ("return", "max_dd", "q", "trades", "win_rate", "mean_trade")}})
    with TIMELINE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


def trial_series(done: list[dict]) -> list[dict]:
    """Every trial as one small point, plus the best eligible trial so far at that moment -
    the curve that says whether the search is improving."""
    out, best = [], None
    for r in done:
        p = pooled({int(k): v for k, v in r["years"].items()})
        if r["eligible"] and (best is None or (r["score"], r["worst_q"]) > (best["score"], best["worst_q"])):
            best = r
        bp = pooled({int(k): v for k, v in best["years"].items()}) if best else None
        out.append({"at": r["at"], "n": len(out) + 1, "score": r["score"], "eligible": r["eligible"],
                    "win_rate": p["win_rate"], "worst_year": p["worst_year"],
                    "best_win_rate": bp["win_rate"] if bp else None,
                    "best_score": best["score"] if best else None})
    return out


def ledger_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_card(hours: float | None = None) -> None:
    """Rebuild the card from the ledgers on disk.

    Trainer workers and the release evaluator all call this; it reads only files, so
    whichever process writes last writes the same truth, and an atomic replace means the
    publisher never reads half a card.
    """
    done = ledger()
    champ = champion(done)
    rows = ledger_rows(LOG)
    rel = releases()
    if hours is None:
        hours = sum(r.get("minutes", 0) for r in done) / 60
    card = {
        "system": "system10", "family": "system10-condition-search", "system_type": "ai-model",
        "status": "condition search (continuous) - trainers and release evaluator run apart",
        "updated_at": _now(),
        "walk_forward": {"trained_through": 2025, "test_years": list(TEST_YEARS),
                         "forward_window": "2026-01-01 to today",
                         "note": "2026 is observed every reading, never used to choose anything"},
        "search": {"trials": len(done), "eligible": sum(r["eligible"] for r in done),
                   "hours": round(hours, 2),
                   "workers": sorted({r.get("worker", "w1") for r in done}),
                   "top": [{k: r[k] for k in ("id", "cfg", "score", "worst_year", "cagr", "worst_q",
                                               "max_dd", "eligible")}
                           for r in sorted(done, key=lambda r: -r["score"])[:10]]},
        "champion": ({k: champ[k] for k in ("id", "cfg", "score", "worst_year", "cagr", "worst_q",
                                             "max_dd", "years")} if champ else None),
        "releases": [{k: r.get(k) for k in ("n", "at", "id", "label", "score", "unseen", "trials")}
                     for r in rel][-100:],
        "region": {"rules": [cfg_label(champ["cfg"])] if champ else [],
                   "note": "the condition set is the champion trial's configuration"},
        "forward_history": [{k: r.get(k) for k in ("at", "lineage", "cycle", "train_hours", "updates",
                                                    "env_steps", "in_sample_2025", "forward_2026")}
                            for r in rows],
        "lineages": {"champion": {"cycle": len(rows), "trials": len(done),
                                  "last_forward": rows[-1]["forward_2026"] if rows else None}},
        "monitor": {
            "gpu": gpu_snapshot(),
            "counters": {
                "trials": len(done), "eligible": sum(r["eligible"] for r in done),
                "search_hours": round(hours, 2), "seeds_per_model": len(SEEDS),
                "walk_forward_folds": len(TEST_YEARS), "releases": len(rel),
                "models_fitted": sum(len(SEEDS) * len(TEST_YEARS)
                                     * (1 if r["cfg"]["regime_ma"] is None else 2)
                                     for r in done if r["cfg"]["selector"])},
            "last_trial": ({"at": done[-1]["at"], "label": cfg_label(done[-1]["cfg"]),
                            "score": done[-1]["score"], "eligible": done[-1]["eligible"],
                            "unseen": pooled({int(k): v for k, v in done[-1]["years"].items()})}
                           if done else None),
            "champion_label": cfg_label(champ["cfg"]) if champ else None,
        },
        "timeline": ledger_rows(TIMELINE)[-2000:],
        "trial_series": trial_series(done),
        "events": ledger_rows(EVENTS)[-200:],
    }
    tmp = CARD.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(card, indent=1, default=str), encoding="utf-8")
    # Windows refuses the replace while another process (status, the Worker pusher) has the card
    # open; 2026-10-16 w1 died on it at the end of its run. Retry briefly, then keep the old card.
    for attempt in range(20):
        try:
            os.replace(tmp, CARD)
            return
        except PermissionError:
            time.sleep(0.5)
    tmp.unlink(missing_ok=True)
    print(f"[{_now()}] model card not replaced (file busy); the previous card stays", flush=True)


# ------------------------------------------------------------------ releases and claims

RELEASES = OUT / "releases"
CLAIMS = OUT / "rnd/search_claims.jsonl"
CLAIM_TTL_S = 1800


def releases() -> list[dict]:
    if not RELEASES.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RELEASES.glob("release_*.json"))]


OVERFIT = OUT / "rnd/overfit.json"
OVERFIT_MAX_AGE_H = 36       # overfit.py runs every 8 h (review.py); older = stale, never blocks
PBO_MAX = 0.5


def overfit_refusal() -> str | None:
    """Audit 2026-10-15 (2.2): no new release while the search's PBO is above 0.5. Reads the
    cached rnd/overfit.json only; missing, unreadable or stale never blocks."""
    try:
        doc = json.loads(OVERFIT.read_text(encoding="utf-8"))
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(doc["at"])).total_seconds() / 3600
        pbo = doc.get("pbo")
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if pbo is None or age_h > OVERFIT_MAX_AGE_H or float(pbo) <= PBO_MAX:
        return None
    return f"PBO {float(pbo):.2f} > {PBO_MAX} ({doc.get('pbo_basis')}, {doc['at']})"


def current_release(worker: str) -> dict | None:
    """The release of the champion under today's law - what the evaluator reads and the
    paper book trades. Published here if the champion has none yet (a law change can crown a
    trial that was never released). While overfit_refusal() holds, the champion does not
    advance: the newest existing release stays current."""
    champ = champion(ledger())
    if champ is None:
        return None
    if overfit_refusal():
        rel = releases()
        return rel[-1] if rel else None
    for r in reversed(releases()):
        if r["id"] == champ["id"]:
            return r
    return release(champ, worker)


def release(champ: dict, worker: str) -> dict | None:
    """Publish the champion as a numbered release: the frozen condition set the evaluator
    backtests and forward-tests while the trainers carry on."""
    RELEASES.mkdir(parents=True, exist_ok=True)
    done = releases()
    if done and done[-1]["id"] == champ["id"]:
        return done[-1]
    why = overfit_refusal()
    if why:
        add_event("release", f"release refused for {champ['id']}: {why}")
        return None
    n = len(done) + 1
    row = {"n": n, "at": _now(), "id": champ["id"], "cfg": champ["cfg"],
           "label": cfg_label(champ["cfg"]), "score": champ["score"],
           "worst_year": champ["worst_year"], "cagr": champ["cagr"],
           "unseen": pooled({int(k): v for k, v in champ["years"].items()}),
           "years": champ["years"], "trials": len(ledger()), "released_by": worker}
    path = RELEASES / f"release_{n:04d}.json"
    path.write_text(json.dumps(row, indent=1, default=str), encoding="utf-8")
    win = row["unseen"]["win_rate"] or 0
    add_event("release", f"release {n}: {row['label']} - unseen years {win:.0%} winning trades, "
                         f"worst year {row['worst_year']:+.1%}")
    return row


def claimed() -> set:
    """Configs another worker is evaluating now, so two workers never run the same one."""
    now = time.time()
    return {r["id"] for r in ledger_rows(CLAIMS) if now - r["t"] < CLAIM_TTL_S}


def claim(cfg: dict, worker: str) -> None:
    with CLAIMS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": cfg_id(cfg), "worker": worker, "t": time.time(),
                             "label": cfg_label(cfg)}) + "\n")


# ------------------------------------------------------------------ the trainer worker

def main() -> int:
    ap = argparse.ArgumentParser(description="S10 condition-search trainer worker (never reads 2026)")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--worker", default="w1")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--threads", type=int, default=4,
                    help="CPU threads; the box has 12 and the GPU trainer must keep enough to feed the card")
    args = ap.parse_args()
    device = args.device
    torch.set_num_threads(args.threads)
    from . import pit_search
    if pit_search.enabled(args.worker):    # review round 2 (R6): ENABLE_PIT_SEARCH, read once here
        return pit_search.run(args.worker, args.hours, device)
    started = time.time()
    print(f"[{_now()}] worker {args.worker}: loading bars", flush=True)
    world = World()
    print(f"[{_now()}] worker {args.worker}: {len(ledger())} trials on the ledger", flush=True)
    while time.time() - started < args.hours * 3600 and not STOP.exists():
        done = ledger()
        cfg = reconfirm(done, claimed()) or next_config(done, skip=claimed())
        if cfg is None:
            print(f"[{_now()}] worker {args.worker}: nothing left to try, waiting", flush=True)
            time.sleep(300)
            continue
        claim(cfg, args.worker)
        before = champion(done)
        before_raw = _champion_raw(done)
        r = evaluate(world, cfg, device)
        r["worker"] = args.worker
        if r["eligible"] and operates(r) and (before_raw is None or r["score"] > before_raw["score"]):
            global SEEDS
            main_seeds, SEEDS = SEEDS, CONFIRM_SEEDS
            try:
                c = evaluate(world, cfg, device)
            finally:
                SEEDS = main_seeds
            r["confirm"] = {k: c[k] for k in ("score", "worst_year", "cagr", "max_dd", "eligible", "years")}
            r["score_first"] = r["score"]
            r["score"] = min(r["score"], c["score"])
            r["worst_year"] = min(r["worst_year"], c["worst_year"])
            r["max_dd"] = max(r["max_dd"], c["max_dd"])
        with TRIALS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r, default=str) + "\n")
        champ = champion(ledger())
        is_new = bool(champ and champ["id"] == r["id"] and (not before or before["id"] != r["id"]))
        tag = ""
        if is_new:
            rel = release(champ, args.worker)
            tag = f"  <- CHAMPION, RELEASE {rel['n']}" if rel else "  <- CHAMPION, release refused (overfit)"
        verdict = "ELIGIBLE" if r["eligible"] else "ineligible"
        print(f"[{_now()}] {args.worker} trial {r['id']} {json.dumps(cfg)} -> score {r['score']:+.4f} "
              f"worst {r['worst_year']:+.1%} cagr {r['cagr']:+.1%} dd {r['max_dd']:.0%} "
              f"{verdict} [{r['minutes']:.1f}m]{tag}", flush=True)
        write_card()
    return 0


if __name__ == "__main__":
    sys.exit(main())
