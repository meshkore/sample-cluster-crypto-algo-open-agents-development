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


def stitch(world, start_ns: int, fresh: dict, fr: dict) -> tuple[dict, int]:
    """Per symbol, the decision inputs for every bar: frozen where the bar was already seen,
    fresh (and now frozen) where it is new. Returns the stitched arrays and how many bars
    were frozen this cycle."""
    out, added = {k: {} for k in fresh}, 0
    for s, d in world.per.items():
        ns = d["ns"]
        live = ns >= start_ns
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
    from quantlab_catalog import candles as Q

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
    def build_matrix(bars, spec=None, store=None, symbol=None, market=None, reference=None):
        ns = np.array([np.datetime64(b.timestamp.replace(tzinfo=None), "ns").astype("int64") for b in bars])
        prev = _FAST["X"].get(symbol)
        if prev is None or not _FAST["ok"] or market is not None or reference is not None:
            X, ts = orig(bars, spec, store, symbol, market, reference)
            if not _FAST["checked"] and len(bars) > TAIL + 500:
                Xt, _ = orig(bars[-TAIL:], spec, None, symbol)
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
            Xt, _ = orig(bars[-TAIL:], spec, None, symbol)
            new = len(ns) - keep
            X = np.concatenate([pX[:keep], Xt[len(Xt) - new:]]) if new else pX[:keep]
            ts = np.array([b.timestamp for b in bars], dtype="datetime64[ns]")
        _FAST["X"][symbol] = (ns, X)
        return X, ts
    return build_matrix


def fast_world():
    import quantlab_catalog.candles as Q
    import system006_oracle_net_15m.features as F
    oc, om = Q.candles, F.build_matrix
    Q.candles, F.build_matrix = _fast_candles(oc), _fast_matrix(om)
    try:
        return S.World(include_sealed=True)
    finally:
        Q.candles, F.build_matrix = oc, om


def cycle(device: str) -> dict:
    cfgx = config()
    t0 = time.time()
    world = fast_world()
    fr = load_frozen()
    r, added = run_book(world, cfgx["cfg"], cfgx["start_ns"], cfgx["capital"], fr, device)
    save_frozen(fr)
    publish(cfgx, r, world, added, time.time() - t0)
    return r


def run_book(world, cfg: dict, start_ns: int, capital: float, fr: dict, device: str) -> tuple[dict, int]:
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
    x, added = stitch(world, start_ns, fresh, fr)
    r = world.book(x["enter"], S.FORWARD, cfg["horizon"], x["size"] if size is not None else None,
                   x["keep"] if keep is not None else None, S.EXIT_MIN_HOLD,
                   strength=x["strength"] if st is not None else None, **S.mm_kwargs(cfg),
                   start_ns=start_ns, capital=capital, detail=True)
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
        "cycle": {"seconds": round(secs, 1), "bars_frozen_now": added},
        "halted": None,
    }
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, default=str), encoding="utf-8")
    os.replace(tmp, STATE)
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
