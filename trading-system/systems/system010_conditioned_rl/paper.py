"""System 10 paper trading: the best release, on live prices, from a fixed start, with a fixed stake.

The operator, 2026-10-13: *"start trading in real time from today with the best model we
have ... the September 17 book ran a model we no longer use, so that data is useless. Start
it today with $50,000."*

Paper only. Research only: no venue, no key, no order ever leaves this machine. The fills
are the backtest's own (the 15-minute close, 0.15% a side), so the book is exactly what
the backtest would have booked on the same bars - which is the point: it is the release's
forward test with the clock running.

How it stays honest while it re-reads the market every cycle:
  * The release is PINNED at the start (config.json). Its money management (slots,
    drawdown scaling, stops) defines the book; changing it mid-way would rewrite history.
  * Every bar's decision inputs (entry allowed, keep, signal strength, stake scale) are
    FROZEN the first cycle that bar is seen, in signals.npz. Later cycles retrain the
    walk-forward models on the same <= 2025 data and could differ in the last decimal; a
    frozen bar never changes, so the past of the book never changes either.
  * The book is re-run from the start over the frozen inputs each cycle; with fixed inputs
    and closed candles it is deterministic.

Data: the bars come from the shared candle cache, which the system 06 live process keeps
current every 15 minutes (it also refreshes the breadth channel this release reads). That
process keeps running as the data feed; its own book is no longer published.

Writes research/system10/paper/{config.json, signals.npz, paper_state.json}.
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

from . import search as S

DIR = S.OUT / "paper"
CONFIG = DIR / "config.json"
FROZEN = DIR / "signals.npz"
STATE = DIR / "paper_state.json"
CAPITAL = 50_000.0
CYCLE_S = 15 * 60
BAR_NS = 15 * 60 * 10**9
SWAP_BAND = 0.02     # law score a new champion must gain over the incumbent to take over


def iso(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, timezone.utc).isoformat(timespec="seconds")


def config() -> dict:
    """The run's fixed terms, written once: start, capital, release."""
    if CONFIG.is_file():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    rel = S.releases()[-1]
    now = datetime.now(timezone.utc)
    start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    cfg = {"start": start.isoformat(timespec="seconds"),
           "start_ns": int(start.timestamp() * 1e9), "capital": CAPITAL,
           "release": rel["n"], "release_id": rel["id"], "release_label": rel["label"], "cfg": rel["cfg"],
           "release_unseen": {k: rel[k] for k in ("worst_year", "cagr") if k in rel},
           "mode": "paper", "created_at": now.isoformat(timespec="seconds")}
    DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return cfg


def load_frozen() -> dict:
    if not FROZEN.is_file():
        return {}
    z = np.load(FROZEN)
    out: dict = {}
    for k in z.files:
        sym, field = k.split("|")
        out.setdefault(sym, {})[field] = z[k]
    return out


def save_frozen(fr: dict) -> None:
    tmp = FROZEN.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **{f"{s}|{k}": v for s, d in fr.items() for k, v in d.items()})
    os.replace(tmp, FROZEN)


def channel_last() -> dict[str, int]:
    """Per symbol, the newest bar the 06 channel cache (trend -> breadth) already covers.

    Found 2026-10-15: the 06 process writes the channel ~30-45 min after a bar closes, while
    the candles arrive at once. A bar read before its channel has breadth 0, so the gate is
    shut - and freezing that bar froze "no entry" for good: no trade for the first 36 hours.
    A bar is now decided (and frozen) only once its channel exists.
    """
    import conditions as C  # noqa: WPS433 - on the path once search is imported
    z = np.load(C.REPO / "live-trading/state/engine_cache" / C.ENGINE / "signals.npz")
    return {k.split("__")[0]: int(z[k][-1]) for k in z.files if k.endswith("__epoch_ns")}


def stitch(world, start_ns: int, fresh: dict, fr: dict, ready: dict | None = None) -> tuple[dict, int]:
    """Per symbol, the decision inputs for every bar: frozen where the bar was already seen,
    fresh (and now frozen) where it is new and complete. A bar whose channel has not arrived
    (`ready`) is neither frozen nor acted on: no entry, keep held. Returns the stitched arrays
    and how many bars were frozen this cycle."""
    out, added = {k: {} for k in fresh}, 0
    for s, d in world.per.items():
        ns = d["ns"]
        late = ns > (ready or {}).get(s, np.iinfo(np.int64).max)
        live = (ns >= start_ns) & ~late
        old = fr.get(s, {"ns": np.zeros(0, dtype=np.int64)})
        if len(old["ns"]):
            pos = np.clip(np.searchsorted(old["ns"], ns), 0, len(old["ns"]) - 1)
            hit = live & (old["ns"][pos] == ns)
        else:
            pos, hit = np.zeros(len(ns), dtype=np.int64), np.zeros(len(ns), dtype=bool)
        for k, arrs in fresh.items():
            a = np.array(arrs[s], copy=True)
            if hit.any():
                a[hit] = old[k][pos[hit]]
            if late.any() and k in ("enter", "keep"):
                a[late] = (k == "keep")
            out[k][s] = a
        new = live & ~hit
        if new.any():
            added += int(new.sum())
            keep_ns = np.r_[old["ns"], ns[new]]
            order = np.argsort(keep_ns, kind="stable")
            fr[s] = {"ns": keep_ns[order]}
            for k in fresh:
                prev = old.get(k, np.zeros(0, dtype=out[k][s].dtype))
                fr[s][k] = np.r_[prev, out[k][s][new]][order]
    return out, added


# ------------------------------------------------------------------ a fast reload
# A full World takes ~25 min on the busy box: 4.4 min reading eight years of candles and
# ~2 min per coin rebuilding the indicator panel. Neither changes for a closed bar, so:
#   * the pre-2026 candles are read once per process; each cycle reads only 2026
#   * each coin's feature rows are kept, and only the newest bars are recomputed, from a
#     tail of TAIL bars (~200 days: every window in the panel is <= 252 bars, and the
#     exponential ones have decayed to nothing long before)
# The first cycle of every process builds the full matrix AND the tail version and checks
# that their last rows agree; if they ever do not, the tail path is switched off.
TAIL = 20_000
_FAST: dict = {"research": None, "X": {}, "ok": True, "checked": False}


def _fast_candles(orig_candles):
    import importlib
    Q = importlib.import_module("quantlab_catalog.candles")   # the module (the package exports a function of the same name)

    def candles(symbols, interval="15m", *, include_sealed=False, end=None, data_root=None):
        if not include_sealed:
            return orig_candles(symbols, interval, include_sealed=False, data_root=data_root)
        first = _FAST["research"] is None
        if first:
            _FAST["research"] = Q.research(symbols, interval, data_root)
        fwd = Q.forward(symbols, interval, end, data_root)
        out = {s: _FAST["research"].get(s, []) + fwd.get(s, []) for s in symbols}
        if first:   # once per process: the splice must equal the loader's own combined read
            ref = orig_candles(symbols, interval, include_sealed=True, end=end, data_root=data_root)
            bad = [s for s in symbols if [b.timestamp for b in ref.get(s, [])] != [b.timestamp for b in out[s]]
                   or [b.close for b in ref.get(s, [])] != [b.close for b in out[s]]]
            print(f"[{S._now()}] paper: candle splice check: {'OK' if not bad else 'MISMATCH ' + ','.join(bad)}", flush=True)
            if bad:
                _FAST["research"] = None
                return ref
        return out
    return candles


def _fast_matrix(orig):
    from system006_oracle_net_15m.features import FEATURE_COLUMNS
    dd_col = FEATURE_COLUMNS.index("drawdown_from_high")

    def tail_rows(bars, spec, symbol):
        """The panel on the last TAIL bars, with the one column whose memory is the whole
        history - drawdown from the all-time high (indicators.py: close / running max - 1)
        - recomputed on every close."""
        Xt, _ = orig(bars[-TAIL:], spec, None, symbol)
        close = np.array([b.close for b in bars], dtype=float)
        dd = close / np.maximum.accumulate(close) - 1
        Xt[:, dd_col] = dd[-len(Xt):]
        return Xt

    def build_matrix(bars, spec=None, store=None, symbol=None, market=None, reference=None):
        ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars])
        prev = _FAST["X"].get(symbol)
        if prev is None or not _FAST["ok"] or market is not None or reference is not None:
            X, ts = orig(bars, spec, store, symbol, market, reference)
            if not _FAST["checked"] and len(bars) > TAIL + 500:
                Xt = tail_rows(bars, spec, symbol)
                a, b = X[-500:], Xt[-500:]
                diff = float(np.nanmax(np.abs(np.where(np.isfinite(a) & np.isfinite(b), a - b, 0))))
                same_nan = bool((np.isfinite(a) == np.isfinite(b)).all())
                _FAST["ok"] = diff < 1e-6 and same_nan
                _FAST["checked"] = True
                print(f"[{S._now()}] paper: tail check on {symbol}: max diff {diff:.2e}, "
                      f"NaN pattern {'same' if same_nan else 'DIFFERENT'} -> tail path "
                      f"{'ON' if _FAST['ok'] else 'OFF'}", flush=True)
            _FAST["X"][symbol] = (ns, X)
            return X, ts
        pns, pX = prev
        keep = np.searchsorted(ns, pns[-1], side="right")           # rows already known
        if keep < len(ns) - TAIL // 2 or not np.array_equal(ns[:len(pns)], pns):
            X, ts = orig(bars, spec, store, symbol, market, reference)   # history changed: rebuild
        else:
            Xt = tail_rows(bars, spec, symbol)
            new = len(ns) - keep
            X = np.concatenate([pX[:keep], Xt[len(Xt) - new:]]) if new else pX[:keep]
            ts = np.array([b.timestamp for b in bars], dtype="datetime64[ns]")
        _FAST["X"][symbol] = (ns, X)
        return X, ts
    return build_matrix


def fast_world():
    import importlib
    Q = importlib.import_module("quantlab_catalog.candles")
    import system006_oracle_net_15m.features as F
    oc, om = Q.candles, F.build_matrix
    Q.candles, F.build_matrix = _fast_candles(oc), _fast_matrix(om)
    try:
        return S.World(include_sealed=True)
    finally:
        Q.candles, F.build_matrix = oc, om


def adopt_champion(cfgx: dict, fr: dict) -> dict:
    """The paper book always trades the current champion (search.current_release). A new
    champion takes over at the first bar not yet decided, with the book's positions as they
    stand (operator, 2026-10-15: "replace the engines immediately when we have a better one")."""
    segs = cfgx.setdefault("segments", [{"from_ns": cfgx["start_ns"], "release": cfgx["release"],
                                         "release_id": cfgx["release_id"], "cfg": cfgx["cfg"]}])
    rel = S.current_release("paper")
    if rel is None or rel["id"] == segs[-1]["release_id"]:
        return cfgx
    # Hysteresis (audit 2026-10-15): the top 100 trials sit within ~0.02 of score and a seed
    # swap moves a year by 8-30 points, so a champion replaces the incumbent only when it
    # beats it by more than that band - or when the incumbent is no longer eligible.
    done = S.ledger()
    inc = [r for r in done if r["id"] == segs[-1]["release_id"]]
    new = [r for r in done if r["id"] == rel["id"]]
    inc_ok = any(r["eligible"] for r in inc)
    best = lambda rows: max((r["score"] for r in rows if r["eligible"]), default=float("-inf"))  # noqa: E731
    if inc_ok and best(new) < best(inc) + SWAP_BAND:
        return cfgx
    decided = max((int(v["ns"][-1]) for v in fr.values() if len(v["ns"])), default=cfgx["start_ns"] - BAR_NS)
    frm = max(decided + BAR_NS, cfgx["start_ns"])
    segs.append({"from_ns": frm, "release": rel["n"], "release_id": rel["id"], "cfg": rel["cfg"],
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    cfgx.setdefault("switches", []).append({"at": segs[-1]["at"], "from": cfgx["release"], "to": rel["n"],
                                            "from_bar": iso(frm), "why": "new champion (hot swap)"})
    cfgx.update({"release": rel["n"], "release_id": rel["id"], "release_label": rel["label"], "cfg": rel["cfg"],
                 "release_unseen": {k: rel[k] for k in ("worst_year", "cagr") if k in rel}})
    CONFIG.write_text(json.dumps(cfgx, indent=1), encoding="utf-8")
    print(f"[{S._now()}] paper: hot swap -> release {rel['n']} from {iso(frm)}", flush=True)
    return cfgx


BOOK_FLAG = S.OUT / "ENABLE_BOOK_RELEASES"     # absent (default): book releases are ignored
BOOK_DIR = S.OUT / "book_releases"


def adopt_book(cfgx: dict, fr: dict) -> dict:
    """Book audit 2026-10-15, phase 4: the newest book release (book_worker.py) for the signal
    release in force replaces only the book keys, as a new hot-swap segment. Off unless
    ENABLE_BOOK_RELEASES exists; a book carrying a lever paper cannot run ("meta") or gaining
    less than SWAP_BAND over its incumbent is ignored."""
    if not BOOK_FLAG.is_file() or not BOOK_DIR.is_dir():
        return cfgx
    segs = cfgx.get("segments") or []
    if not segs:
        return cfgx
    books = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(BOOK_DIR.glob("book_*.json"))]
    books = [b for b in books if b.get("signal_release_id") == segs[-1]["release_id"]]
    if not books:
        return cfgx
    b = books[-1]
    if (b["n"] == segs[-1].get("book") or "meta" in b["book"] or float(b.get("gain", 0)) < SWAP_BAND):
        return cfgx
    book_keys = set(S.MM_KEYS) - {"veto", "vol_target"}     # those two act on the signals
    rel_cfg = next((r["cfg"] for r in S.releases() if r["id"] == b["signal_release_id"]), segs[-1]["cfg"])
    cfg = {**{k: v for k, v in rel_cfg.items() if k not in book_keys}, **b["book"]}
    strong = lambda c: bool(c.get("size_signal") or c.get("scale_in"))  # noqa: E731
    if strong(cfg) != strong(rel_cfg):   # run_book would freeze (or drop) the forecast for every segment
        return cfgx
    decided = max((int(v["ns"][-1]) for v in fr.values() if len(v["ns"])), default=cfgx["start_ns"] - BAR_NS)
    frm = max(decided + BAR_NS, cfgx["start_ns"])
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    segs.append({"from_ns": frm, "release": segs[-1]["release"], "release_id": segs[-1]["release_id"],
                 "cfg": cfg, "book": b["n"], "at": at})
    cfgx.setdefault("switches", []).append({"at": at, "from": cfgx["release"], "to": cfgx["release"], "book": b["n"],
                                            "from_bar": iso(frm), "why": f"book release {b['n']} (hot swap)"})
    cfgx.update({"cfg": cfg, "book": b["n"]})
    CONFIG.write_text(json.dumps(cfgx, indent=1), encoding="utf-8")
    print(f"[{S._now()}] paper: book release {b['n']} on release {cfgx['release']} from {iso(frm)}", flush=True)
    return cfgx


def cycle(device: str) -> dict:
    cfgx = config()
    t0 = time.time()
    world = fast_world()
    fr = load_frozen()
    cfgx = adopt_champion(cfgx, fr)
    cfgx = adopt_book(cfgx, fr)
    r, added = run_book(world, cfgx["cfg"], cfgx["start_ns"], cfgx["capital"], fr, device,
                        cfgx.get("segments"))
    save_frozen(fr)
    publish(cfgx, r, world, added, time.time() - t0)
    return r


def book_segments(world, x: dict, segments: list, capital: float, sized: bool, kept: bool,
                  strong: bool) -> dict:
    """Hot swap (operator, 2026-10-15): each release books the same account from the bar it
    took over, carrying the previous release's cash, high water and OPEN positions, so a
    better engine replaces the old one at once and the past stays as it was booked."""
    last = max(int(d["ns"][-1]) for d in world.per.values())
    state, fills, curve, r = None, [], [], None
    for i, seg in enumerate(segments):
        end = segments[i + 1]["from_ns"] if i + 1 < len(segments) else None
        if seg["from_ns"] > last or (end is not None and end <= seg["from_ns"]):
            continue
        c = seg["cfg"]
        r = world.book(x["enter"], S.FORWARD, c["horizon"], x["size"] if sized else None,
                       x["keep"] if kept else None, S.EXIT_MIN_HOLD,
                       strength=x["strength"] if strong else None, **S.mm_kwargs(c),
                       start_ns=seg["from_ns"], capital=capital, detail=True, end_ns=end, init=state)
        state = r["state"]
        fills += r["fills"]
        curve += r["equity_curve"]
    hw, dd, out = 0.0, 0.0, []
    for t, e, _ in curve:
        hw = max(hw, e, capital if not out else 0.0)
        dd = max(dd, 1 - e / hw)
        out.append((t, e, hw))
    r.update({"fills": fills, "equity_curve": out, "max_dd": round(dd, 4)})
    return r


def run_book(world, cfg: dict, start_ns: int, capital: float, fr: dict, device: str,
             segments: list | None = None) -> tuple[dict, int]:
    """The release's 2026 signals, stitched onto the frozen ones, booked from start_ns."""
    g, regime = S.gate(world, cfg)
    _, masks, keep = S.signals(world, cfg, S.FORWARD, g, regime, device)
    st = S.strength(world, cfg, S.FORWARD, g, regime, device) if (cfg.get("size_signal") or cfg.get("scale_in")) else None
    if cfg.get("veto") == "pareto":
        veto, _ = S.pareto_veto(world, cfg, S.FORWARD, g, regime, device)
        if veto:
            masks = {s: masks[s] & ~veto[s] for s in masks}
    size = S.sizing(world, cfg)
    ones = {s: np.ones(len(d["ns"])) for s, d in world.per.items()}
    fresh = {"enter": {s: masks[s].astype(bool) for s in world.per},
             "keep": {s: (keep[s] if keep is not None else np.ones(len(d["ns"]), bool)).astype(bool)
                      for s, d in world.per.items()},
             "strength": {s: (st[s] if st is not None else np.zeros(len(d["ns"]))).astype(np.float64)
                          for s, d in world.per.items()},
             "size": {s: (size[s] if size is not None else ones[s]).astype(np.float64) for s in world.per}}
    ready = channel_last()
    x, added = stitch(world, start_ns, fresh, fr, ready)
    r = book_segments(world, x, segments or [{"from_ns": start_ns, "cfg": cfg}], capital,
                      size is not None, keep is not None, st is not None)
    # What the model read on the newest bar of every coin (operator, 2026-10-13: "a small
    # box that tells me in real time that we are working on it, and that there are no buy
    # or sell opportunities right now").
    held = {p["symbol"] for p in r["positions"]}
    coins = []
    for s, d in world.per.items():
        i = len(d["ns"]) - 1
        coins.append({"symbol": s, "bar": iso(int(d["ns"][i])), "price": float(d["close"][i]),
                      "forecast": float(x["strength"][s][i]), "entry": bool(x["enter"][s][i]),
                      "keep": bool(x["keep"][s][i]), "gate": bool(g[s][i]), "held": s in held})
    up = bool(regime["BTCUSDT"][len(world.per["BTCUSDT"]["ns"]) - 1])
    r["scan"] = {"coins": sorted(coins, key=lambda c: -c["forecast"]), "btc_above_ma": up,
                 "entry_threshold": S.EXIT_BAND, "exit_threshold": -S.EXIT_BAND,
                 "bars_read": int(sum(len(v["ns"]) for v in fr.values())), "trail": world.trail,
                 "decided_through": iso(min(ready.get(s, 0) for s in world.per))}
    return r, added


def publish(cfgx: dict, r: dict, world, added: int, secs: float) -> None:
    """paper_state.json in the shape the public Trading tab already reads."""
    cap = cfgx["capital"]
    closed = r["closed_returns"]
    invested = sum(p["value"] for p in r["positions"])
    eq = r["equity_curve"]
    step = max(1, len(eq) // 600)
    curve = [{"at": iso(t), "equity": round(e, 2), "dd": round(1 - e / pk, 5)} for t, e, pk in eq[::step]]
    if eq and (not curve or curve[-1]["at"] != iso(eq[-1][0])):
        t, e, pk = eq[-1]
        curve.append({"at": iso(t), "equity": round(e, 2), "dd": round(1 - e / pk, 5)})
    fees = sum(f["fee"] for f in r["fills"])
    c, sc = cfgx["cfg"], r.get("scan", {})
    pc = lambda v: f"{v * 100:g}%"  # noqa: E731
    # The book's rules, written from the same numbers the book runs on (conditions.book_year).
    rules = [
        ["Long only", "spot, no shorts, no leverage"],
        [f"Max {c.get('slots', 3)} positions", f"each stake is at most 1/{c.get('slots', 3)} of the account"],
        [f"Buy when forecast ≥ +{pc(S.EXIT_BAND)}", "the AI's forecast of the next day's return, after the AI selector and the market gate"],
        [f"Sell when forecast < −{pc(S.EXIT_BAND)}", f"once held at least {S.EXIT_MIN_HOLD // 4} h"],
        [f"Stop −{pc(c['stop'])}" if c.get("stop") else "Stop (06 default)", "per position, from its entry price"],
        [f"Trailing stop −{sc.get('trail', 0) * 100:.0f}%", "from the position's highest close"],
        [f"Max hold {c['horizon'] * 15 / 60 / 24:g} days", f"{c['horizon']} bars of 15 min"],
        [f"Stake by signal: forecast ÷ {pc(c['size_signal'])}" if c.get("size_signal") else "Full stakes",
         "a fraction of a slot between 25% and 100%"],
        ["Add ¼ slot every 4 h if forecast ≥ +0.6%, sell half if < 0" if c.get("scale_in") else "No scaling", "while a position is held"],
        [f"{c.get('size_down', 1):g}× stakes when BTC < its {c['regime_ma']}-day average", "the falling regime"],
        [f"Stakes shrink with drawdown, to 25% at −{pc(c['dd_scale'])}" if c.get("dd_scale") else "No drawdown brake",
         "new stakes × max(0.25, 1 − drawdown ÷ " + pc(c.get("dd_scale") or 1) + "); not a hard stop of the account"],
        [f"Breadth ≥ {c['b_up']:g} to buy when BTC is above its average", f"below it: breadth ≥ {c['b_down']:g}"],
    ]
    if c.get("mom_rank"):
        rules.insert(8, [f"{c.get('mom_in', 2.0):g}× stake for the top {c['mom_rank']} coins by {c.get('mom_days', 60)}-day return",
                         "cross-sectional momentum, ranked at entry"])
    doc = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": "paper",
        "system": "system010_conditioned_rl", "cutover": cfgx["start"], "trading_since": cfgx["start"],
        "engine": {"system": "system010_conditioned_rl", "version": f"release {cfgx['release']}",
                   "label": cfgx["release_label"], "cfg": cfgx["cfg"],
                   "provenance": "the best System 10 release when trading started, pinned; "
                                 "unseen 2022-2025 worst year "
                                 f"{cfgx['release_unseen'].get('worst_year', 0):+.1%}, CAGR "
                                 f"{cfgx['release_unseen'].get('cagr', 0):+.1%}"},
        "account": {"initial_capital": cap, "equity": round(r["equity"], 2), "cash": round(r["cash"], 2),
                    "invested": round(invested, 2), "exposure": round(invested / r["equity"], 4) if r["equity"] else 0,
                    "return_pct": round(r["equity"] / cap - 1, 6), "high_water": round(r["high_water"], 2),
                    "drawdown": round(1 - r["equity"] / r["high_water"], 5) if r["high_water"] else 0,
                    "max_drawdown": r["max_dd"], "fees_paid": round(fees, 2),
                    "realised": round(sum(f.get("realised", 0.0) for f in r["fills"]), 2),
                    "trades_closed": len(closed),
                    "win_rate": round(float(np.mean([c > 0 for c in closed])), 4) if closed else None},
        "positions": [{**{k: v for k, v in p.items() if k != "entry_ns"}, "entry_time": iso(p["entry_ns"])}
                      for p in r["positions"]],
        "orders": [{"kind": "FILL", "at": iso(f["t"]), **{k: v for k, v in f.items() if k != "t"}}
                   for f in r["fills"]][-200:][::-1],
        "equity_curve": curve,
        "last_bar": iso(r["last_ns"]),
        "last_note": f"holding {len(r['positions'])}",
        "cycle": {"seconds": round(secs, 1), "bars_frozen_now": added,
                  "next_at": datetime.fromtimestamp((int(time.time() // CYCLE_S) + 1) * CYCLE_S + 180,
                                                    timezone.utc).isoformat(timespec="seconds")},
        "scan": sc, "rules": rules,
        # per closed trade (returns net of costs) for the Trading tab's summary
        "stats": ({"best": max(closed), "worst": min(closed),
                   "avg_win": float(np.mean([c for c in closed if c > 0])) if any(c > 0 for c in closed) else None,
                   "avg_loss": float(np.mean([c for c in closed if c <= 0])) if any(c <= 0 for c in closed) else None}
                  if closed else {}),
        "halted": None,
    }
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, default=str), encoding="utf-8")
    for _ in range(10):   # the publisher may hold the file open for a moment (WinError 5)
        try:
            os.replace(tmp, STATE)
            break
        except PermissionError:
            time.sleep(0.5)
    print(f"[{S._now()}] paper: equity ${r['equity']:,.0f} ({r['equity'] / cap - 1:+.2%}), "
          f"{len(r['positions'])} open, {len(r['fills'])} fills, last bar {iso(r['last_ns'])}, "
          f"{added} new bars frozen, {secs / 60:.1f} min", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 paper trading of the pinned release")
    ap.add_argument("--hours", type=float, default=6.0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    started = time.time()
    c = config()
    print(f"[{S._now()}] paper: release {c['release']} from {c['start']} with ${c['capital']:,.0f}", flush=True)
    while not S.STOP.exists():
        t = time.time()
        try:
            cycle(args.device)
        except Exception as exc:  # noqa: BLE001 - one bad cycle must not end the clock
            print(f"[{S._now()}] paper: cycle failed: {type(exc).__name__}: {exc}", flush=True)
        if args.once or time.time() - started > args.hours * 3600:
            break
        # next cycle 3 minutes after the next quarter hour (the feed lands its candle by then)
        nxt = (int(time.time() // CYCLE_S) + 1) * CYCLE_S + 180
        while time.time() < nxt and not S.STOP.exists():
            time.sleep(5)
        S._SIGNALS.clear()
    return 0


if __name__ == "__main__":
    sys.exit(main())
