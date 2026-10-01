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
]
MA_STEPS = (None, 50, 80, 100, 111, 123, 150, 200, 250, 300, 350)
B_STEPS = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.1)
H_STEPS = (96, 192, 384, 768)


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
    def __init__(self):
        C = _tools()
        self.C = C
        data = C.load(C.ENGINE, include_sealed=True)
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

    def book(self, masks: dict, year: int, horizon: int) -> dict:
        C = self.C
        old = C.HORIZON
        C.HORIZON = horizon
        try:
            r = C.book_year(self.per, masks, year, self.band, self.risk)
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
                xs.append(world.x[s][o["idx"][keep]])
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
                    scores[s][m] = B.score(model, world.x[s][m], device)
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
        r = world.book(masks_for(share, choose_year), choose_year, cfg["horizon"])
        key = (r["trades"] >= MIN_TRADES, r["q"])
        if best_key is None or key > best_key:
            best_share, best_key = share, key
    return best_share, masks_for


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
        r = world.book(masks, N, cfg["horizon"])
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


def next_config(done: list[dict]) -> dict | None:
    seen = {r["id"] for r in done}
    for cfg in SEED_CONFIGS:
        if cfg_id(cfg) not in seen:
            return cfg
    ranked = sorted(done, key=lambda r: -rank_key(r))
    legal = lambda c: not (c["regime_ma"] is None and c["b_up"] != c["b_down"])  # noqa: E731
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


def champion(done: list[dict]) -> dict | None:
    pool = [r for r in done if r["eligible"]]
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
    return (f"{ma}, breadth up {cfg['b_up']:g} / down {cfg['b_down']:g}, {sel}, "
            f"exit {cfg['horizon']} bars")


# ------------------------------------------------------------------ the 2026 reading

def forward_reading(world: World, champ: dict, device: str, hours: float, trials: int) -> dict:
    cfg = champ["cfg"]
    g, regime = gate(world, cfg)
    if cfg["selector"]:
        share, masks_for = selector_masks(world, cfg, g, regime, FORWARD - 2, FORWARD - 1, device)
        masks = masks_for(share, FORWARD - 1)
    else:
        share, masks = None, g
    r = world.book(masks, FORWARD, cfg["horizon"])
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


def write_card(done: list[dict], champ: dict | None, hours: float) -> None:
    rows = ledger_rows(LOG)
    card = {
        "system": "system10", "family": "system10-conditioned-rl", "system_type": "ai-model",
        "status": "condition search (continuous)", "updated_at": _now(),
        "walk_forward": {"trained_through": 2025, "test_years": list(TEST_YEARS),
                         "forward_window": "2026-01-01 to today",
                         "note": "2026 is observed every reading, never used to choose anything"},
        "search": {"trials": len(done), "eligible": sum(r["eligible"] for r in done),
                   "hours": round(hours, 2),
                   "top": [{k: r[k] for k in ("id", "cfg", "score", "worst_year", "cagr", "worst_q",
                                               "max_dd", "eligible")}
                           for r in sorted(done, key=lambda r: -r["score"])[:10]]},
        "champion": ({k: champ[k] for k in ("id", "cfg", "score", "worst_year", "cagr", "worst_q",
                                             "max_dd", "years")} if champ else None),
        "region": {"rules": [json.dumps(champ["cfg"])] if champ else [],
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
                "walk_forward_folds": len(TEST_YEARS),
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
    CARD.write_text(json.dumps(card, indent=1, default=str), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 continuous condition search")
    ap.add_argument("--hours", type=float, default=24.0)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    started = time.time()
    print(f"[{_now()}] loading 2017 to today; 2026 is read only by the forward reading", flush=True)
    world = World()
    done = ledger()
    prior_hours = sum(r.get("minutes", 0) for r in done) / 60
    through = datetime.fromtimestamp(int(world.btc_ns[-1]) // 1_000_000_000, timezone.utc)
    add_event("data", f"search restarted with fresh bars through {through:%Y-%m-%d %H:%M} UTC")
    print(f"[{_now()}] {len(done)} trials on the ledger ({prior_hours:.1f} h of search)", flush=True)

    def hours() -> float:
        return prior_hours + (time.time() - started) / 3600

    cache: dict = {}
    champ = champion(done)
    timeline_reading(world, champ, device, hours(), len(done), cache)
    write_card(done, champ, hours())
    last_read = time.time()
    while time.time() - started < args.hours * 3600 and not STOP.exists():
        cfg = next_config(done)
        if cfg is None:
            print(f"[{_now()}] neighbourhood exhausted", flush=True)
            break
        r = evaluate(world, cfg, device)
        done.append(r)
        with TRIALS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r, default=str) + "\n")
        new = champion(done)
        is_new = bool(new and (not champ or new["id"] != champ["id"]))
        if is_new:
            p = pooled({int(k): v for k, v in new["years"].items()})
            add_event("champion", f"new champion: {cfg_label(new['cfg'])} - unseen years "
                                  f"{(p['win_rate'] or 0):.0%} winning trades, worst year {p['worst_year']:+.1%}")
        champ = new
        print(f"[{_now()}] trial {len(done)} {r['id']} {json.dumps(cfg)} -> score {r['score']:+.4f} "
              f"worst {r['worst_year']:+.1%} cagr {r['cagr']:+.1%} dd {r['max_dd']:.0%} "
              f"{'ELIGIBLE' if r['eligible'] else 'ineligible'} [{r['minutes']:.1f}m]"
              f"{'  <- CHAMPION' if is_new else ''}", flush=True)
        if is_new or time.time() - last_read >= READ_EVERY_S:
            row = timeline_reading(world, champ, device, hours(), len(done), cache)
            last_read = time.time()
            if "forward_2026" in row:
                f = row["forward_2026"]
                print(f"[{_now()}] reading: unseen win {(row['unseen']['win_rate'] or 0):.0%} | 2026 "
                      f"{f['return']:+.1%} dd {f['max_dd']:.0%} win {(f['win_rate'] or 0):.0%} "
                      f"{f['trades']} trades", flush=True)
        write_card(done, champ, hours())
    timeline_reading(world, champ, device, hours(), len(done), cache)
    write_card(ledger(), champ, hours())
    return 0


if __name__ == "__main__":
    sys.exit(main())
