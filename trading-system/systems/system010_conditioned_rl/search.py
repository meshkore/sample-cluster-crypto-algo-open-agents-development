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
laboratory's consistency law: score = worst year + 0.10 x CAGR, Q of the worst year beside
it. The operator's availability rule is a hard filter: the gate must leave >= 70% of days
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
    def __init__(self, include_sealed: bool = False):
        """Trainers load research bars only (<= 2025) and so cannot see 2026 even by
        accident; only the release evaluator passes include_sealed=True."""
        C = _tools()
        self.C = C
        data = C.load(C.ENGINE, include_sealed=include_sealed)
        self.per, self.band, self.risk = data["per"], data["band"], data["risk"]
        self.stop = float(self.risk.get("stop_loss") or 0)
        self.trail = float(self.risk.get("trail_stop") or 0)
        btc = self.per["BTCUSDT"]
        self.btc_ns, self.btc_close = btc["ns"], btc["close"]
        self.valid = {s: np.isfinite(d["X"]).all(axis=1) for s, d in self.per.items()}
        # Standardise on years <= 2020: before every fold's training cut, so causal for all.
        early = np.concatenate([d["X"][(d["year"] <= 2020) & self.valid[s]] for s, d in self.per.items()])
        self.mean, self.std = early.mean(axis=0), early.std(axis=0) + 1e-8
        del early
        self.x = {s: np.nan_to_num(np.clip((d["X"] - self.mean) / self.std, -5, 5), nan=0.0).astype(np.float32)
                  for s, d in self.per.items()}
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

    def book(self, masks: dict, year: int, horizon: int, size: dict | None = None,
             keep: dict | None = None, keep_min_hold: int = 0) -> dict:
        C = self.C
        old = C.HORIZON
        C.HORIZON = horizon
        try:
            r = C.book_year(self.per, masks, year, self.band, self.risk, keep=keep, size=size,
                             keep_min_hold=keep_min_hold)
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
    if down >= 1.0:
        return None
    up = world.regime_up(cfg["regime_ma"])
    return {s: np.where(up[s], 1.0, down) for s in world.per}


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

    best_share, best_key = SHARES[0], None
    for share in SHARES:
        r = world.book(masks_for(share, choose_year), choose_year, cfg["horizon"], sizing(world, cfg))
        key = (r["trades"] >= MIN_TRADES, r["q"])
        if best_key is None or key > best_key:
            best_share, best_key = share, key
    return best_share, masks_for


EXIT_K = 96            # the learned exit predicts the next day's return (96 bars of 15 minutes)
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
            "enter": {s: pred[s] > EXIT_BAND for s in world.per}}


def evaluate(world: World, cfg: dict, device: str) -> dict:
    t0 = time.time()
    g, regime = gate(world, cfg)
    avail = availability(world, g)
    years = {}
    for N in TEST_YEARS:
        if cfg["selector"]:
            share, masks_for = selector_masks(world, cfg, g, regime, N - 2, N - 1, device)
            masks = masks_for(share, N - 1)
        else:
            share, masks = None, g
        keep = None
        if cfg.get("exit") == "learned":
            ex = exit_keep(world, cfg, N - 1, device)
            keep = ex["keep"]
            masks = {sym: masks[sym] & ex["enter"][sym] for sym in masks}
        r = world.book(masks, N, cfg["horizon"], sizing(world, cfg), keep, EXIT_MIN_HOLD)
        r.pop("daily")
        years[N] = {**r, "share": share}
    rets = [years[y]["return"] for y in TEST_YEARS]
    worst = min(rets)
    cagr = float(np.prod([1 + r for r in rets]) ** (1 / len(rets)) - 1)
    active = all(years[y]["trades"] >= MIN_TRADES for y in TEST_YEARS)
    return {"id": cfg_id(cfg), "cfg": cfg, "at": _now(),
            "score": round(worst + 0.10 * cagr, 4), "worst_year": round(worst, 4),
            "cagr": round(cagr, 4), "worst_q": round(min(years[y]["q"] for y in TEST_YEARS), 4),
            "max_dd": round(max(years[y]["max_dd"] for y in TEST_YEARS), 4),
            "eligible": bool(avail["passes"] and active), "availability": avail,
            "years": years, "minutes": round((time.time() - t0) / 60, 2)}


# ------------------------------------------------------------------ the search policy

def ledger() -> list[dict]:
    if not TRIALS.is_file():
        return []
    return [json.loads(x) for x in TRIALS.read_text(encoding="utf-8").splitlines() if x.strip()]


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
    if cfg["regime_ma"] is not None:
        for v in step(SIZE_STEPS, cfg.get("size_down", 1.0), 1):
            out.append({**cfg, "size_down": v})
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
    return r["score"] if r["eligible"] else r["score"] - 2.0 * shortfall(r) - 1.0


def next_config(done: list[dict], skip: set | None = None) -> dict | None:
    seen = {r["id"] for r in done} | set(skip or ())
    for cfg in SEED_CONFIGS:
        if cfg_id(cfg) not in seen:
            return cfg
    ranked = sorted(done, key=lambda r: -rank_key(r))
    legal = lambda c: not (c["regime_ma"] is None and c["b_up"] != c["b_down"])  # noqa: E731
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


def champion(done: list[dict]) -> dict | None:
    pool = [r for r in done if r["eligible"] and operates(r)]
    return max(pool, key=lambda r: (r["score"], r["worst_q"])) if pool else None


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
    return f"{ma}, breadth up {cfg['b_up']:g} / down {cfg['b_down']:g}, {sel}, {ex}{size}{full}"


# ------------------------------------------------------------------ the 2026 reading

def forward_reading(world: World, champ: dict, device: str, hours: float, trials: int) -> dict:
    cfg = champ["cfg"]
    g, regime = gate(world, cfg)
    if cfg["selector"]:
        share, masks_for = selector_masks(world, cfg, g, regime, FORWARD - 2, FORWARD - 1, device)
        masks = masks_for(share, FORWARD - 1)
    else:
        share, masks = None, g
    keep = None
    if cfg.get("exit") == "learned":
        ex = exit_keep(world, cfg, FORWARD - 1, device)
        keep = ex["keep"]
        masks = {sym: masks[sym] & ex["enter"][sym] for sym in masks}
    r = world.book(masks, FORWARD, cfg["horizon"], sizing(world, cfg), keep, EXIT_MIN_HOLD)
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
        "system": "system10", "family": "system10-conditioned-rl", "system_type": "ai-model",
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
        "rl": {"timeline": ledger_rows(OUT / "rnd/rl_timeline.jsonl")[-500:],
               "note": "PPO trained 24/7 on 2017-2025, deciding every 4 h inside the champion's "
                       "conditions; a release every 2 h by the clock, read on 2025 and 2026"},
    }
    tmp = CARD.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(card, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, CARD)


# ------------------------------------------------------------------ releases and claims

RELEASES = OUT / "releases"
CLAIMS = OUT / "rnd/search_claims.jsonl"
CLAIM_TTL_S = 1800


def releases() -> list[dict]:
    if not RELEASES.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RELEASES.glob("release_*.json"))]


def release(champ: dict, worker: str) -> dict:
    """Publish the champion as a numbered release: the frozen condition set the evaluator
    backtests and forward-tests while the trainers carry on."""
    RELEASES.mkdir(parents=True, exist_ok=True)
    done = releases()
    if done and done[-1]["id"] == champ["id"]:
        return done[-1]
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
        fh.write(json.dumps({"id": cfg_id(cfg), "worker": worker, "t": time.time()}) + "\n")


# ------------------------------------------------------------------ the trainer worker

def main() -> int:
    ap = argparse.ArgumentParser(description="S10 condition-search trainer worker (never reads 2026)")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--worker", default="w1")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()
    device = args.device
    started = time.time()
    print(f"[{_now()}] worker {args.worker}: loading bars", flush=True)
    world = World()
    print(f"[{_now()}] worker {args.worker}: {len(ledger())} trials on the ledger", flush=True)
    while time.time() - started < args.hours * 3600 and not STOP.exists():
        done = ledger()
        cfg = next_config(done, skip=claimed())
        if cfg is None:
            print(f"[{_now()}] worker {args.worker}: nothing left to try, waiting", flush=True)
            time.sleep(300)
            continue
        claim(cfg, args.worker)
        before = champion(done)
        r = evaluate(world, cfg, device)
        r["worker"] = args.worker
        with TRIALS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r, default=str) + "\n")
        champ = champion(ledger())
        is_new = bool(champ and champ["id"] == r["id"] and (not before or before["id"] != r["id"]))
        tag = ""
        if is_new:
            rel = release(champ, args.worker)
            tag = f"  <- CHAMPION, RELEASE {rel['n']}"
        verdict = "ELIGIBLE" if r["eligible"] else "ineligible"
        print(f"[{_now()}] {args.worker} trial {r['id']} {json.dumps(cfg)} -> score {r['score']:+.4f} "
              f"worst {r['worst_year']:+.1%} cagr {r['cagr']:+.1%} dd {r['max_dd']:.0%} "
              f"{verdict} [{r['minutes']:.1f}m]{tag}", flush=True)
        write_card()
    return 0


if __name__ == "__main__":
    sys.exit(main())
