"""Mirror the System 10 paper book onto a venue account - shadow by default, real money only when armed.

The decisions are NOT made here. The paper trader (system010_conditioned_rl.paper) runs the
pinned release and publishes its book every cycle; this process reads that book's
position weights and makes the venue account hold the same weights of its own capital.
Mirroring weights instead of replaying orders heals itself: a restart, a partial fill or a
skipped cycle is corrected on the next pass, and nothing here re-implements the strategy.

Three brakes, any one of which stops every order to the venue:

1. **The ON/OFF switch** on the public Trading tab (PIN-protected, stored by the Worker at
   /api/control). OFF stops the simulated book and the live one alike. Anything but a
   fresh, explicit "on" is OFF - unreachable counts as off. Its twin, **LIVE/SIMULATED**,
   picks the market: live is used only when it says live AND the account is armed.
2. **A local HALT file** in live-trading/state/ - works with no internet at all.
3. **The market-health monitor** (research/system10/paper/health_state.json): "block_entries"
   stops buys, "halt" sells the mirror's positions and buys nothing until it clears.
   And a hard breaker: the mirror's own drawdown past the armed limit writes HALT itself.

Modes. `shadow` (the default) touches no account: it prices every order on the venue's real
order book, charges the venue fee and keeps a simulated book, so the gap between paper and
venue execution is measured before a cent is at risk. `live` needs ALL of:
  * keys in ~/.quantlab_live_env (BINGX_API_KEY / BINGX_API_SECRET), outside every git tree;
  * the key's permissions: spot trading yes, transfer and withdrawal NO (refused otherwise);
  * an arming file ~/.quantlab_live_arm.json written by the operator, e.g.
      {"venue": "bingx", "capital": 1000, "max_order": 300, "max_drawdown": 0.30,
       "real_money": true}
There is deliberately no command-line flag that arms it.

    python -m quantlab_live.mirror            loop (default 24 h)
    python -m quantlab_live.mirror --once     one reconcile pass, then exit
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config as C
from .brokers.bingx import FORBIDDEN_PERMS, PERM_SPOT_TRADE, BingX, VenueError, base_asset, round_step, venue_symbol, walk_book

PAPER = C.REPO / "research" / "system10" / "paper" / "paper_state.json"
HEALTH = C.REPO / "research" / "system10" / "paper" / "health_state.json"
STATE = C.STATE_DIR / "mirror_state.json"
LEDGER = C.STATE_DIR / "mirror_orders.jsonl"
HALT = C.STATE_DIR / "HALT"
ARM = Path(os.environ.get("QUANTLAB_LIVE_ARM", str(Path.home() / ".quantlab_live_arm.json")))
CONTROL_URL = os.environ.get("QUANTLAB_CONTROL_URL", "https://quantlab-public-mirror.rjj.workers.dev/api/control")

VENUE = "bingx"
SHADOW_CAPITAL = 50_000.0     # same as the paper book, so the two read side by side
FEE = 0.001                   # BingX spot taker; live fills use the fee the venue reports
BAND = 0.005                  # trade only when a holding is off its target by > 0.5% of equity
PAPER_STALE_S = 40 * 60       # an older paper book is not a decision, it is a memory
HEALTH_STALE_S = 60 * 60
CONTROL_STALE_S = 60
TICK_S = 15
CYCLE_S = 15 * 60


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime | None = None) -> str:
    return (t or now()).isoformat(timespec="seconds")


def age_s(stamp: str | None) -> float:
    try:
        return (now() - datetime.fromisoformat(stamp)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(p: Path, doc: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, default=str), encoding="utf-8")
    for _ in range(10):   # the publisher may hold the file open for a moment
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.5)


def log(msg: str) -> None:
    print(f"[{iso()}] mirror: {msg}", flush=True)


# -- the brakes ----------------------------------------------------------------


def remote_switch() -> dict:
    """The panel's switch. Anything but a fresh, explicit 'on' reads as off."""
    try:
        req = urllib.request.Request(CONTROL_URL, headers={"User-Agent": "Mozilla/5.0 (quantlab-mirror)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            doc = json.loads(r.read().decode("utf-8"))
        return {"trading": "on" if doc.get("trading") == "on" else "off",
                "market": "live" if doc.get("market") == "live" else "sim", "at": doc.get("at"),
                "by": doc.get("by"), "read_at": iso(), "reachable": True}
    except Exception as e:  # noqa: BLE001 - unreachable is a state, not a crash
        return {"trading": "off", "market": "sim", "reachable": False, "error": type(e).__name__,
                "read_at": iso()}


def health() -> dict:
    h = read_json(HEALTH)
    if not h:
        return {"recommendation": "trade", "known": False, "note": "no health monitor yet"}
    stale = age_s(h.get("at")) > HEALTH_STALE_S
    # The guard only binds when the monitor says it is enforced: on 2026 its one profitable
    # rule halved return and drawdown alike (research/system10/HEALTH.md), so it ships advisory.
    enforced = bool((h.get("thresholds") or {}).get("enforced", True))
    rec = h.get("recommendation", "trade")
    note = "health reading stale - ignored" if stale else ("" if enforced else f"advisory only (says {rec})")
    return {"recommendation": rec if enforced and not stale else "trade", "known": not stale,
            "advice": rec, "enforced": enforced, "score": h.get("score"), "level": h.get("level"),
            "at": h.get("at"), "components": h.get("components"), "note": note}


def brakes(switch: dict, hl: dict) -> dict:
    """What may happen this pass: buys, sells, or flatten. OFF stops both books."""
    reasons = []
    if switch["trading"] != "on":
        reasons.append("switch off" if switch.get("reachable") else "switch unreachable")
    if HALT.exists():
        reasons.append("local HALT: " + HALT.read_text(encoding="utf-8", errors="replace").strip()[:120])
    stopped = bool(reasons)
    rec = hl.get("recommendation", "trade")
    if not stopped and rec == "halt":
        reasons.append("market health: halt")
    elif not stopped and rec == "block_entries":
        reasons.append("market health: entries blocked")
    return {"orders": not stopped, "buys": not stopped and rec == "trade",
            "flatten": not stopped and rec == "halt", "reasons": reasons}


# -- mode ----------------------------------------------------------------------


def decide_mode(venue: BingX, market: str = "sim") -> tuple[str, str, dict]:
    """('live' | 'shadow', why, arm). Live only when the panel says live AND every condition holds."""
    if market != "live":
        return "shadow", "simulated (panel)", {}
    arm = read_json(ARM) or {}
    if not arm:
        return "shadow", "LIVE asked but not armed (no arming file)", {}
    if arm.get("venue") != VENUE or not arm.get("real_money") or float(arm.get("capital", 0)) <= 0:
        return "shadow", "arming file incomplete (venue, capital, real_money)", {}
    if not venue.private:
        return "shadow", "armed but no venue keys", {}
    try:
        venue.sync_time()
        perms = set(venue.permissions().get("permissions", []))
    except VenueError as e:
        return "shadow", f"key check failed: {e}", {}
    if PERM_SPOT_TRADE not in perms:
        return "shadow", "key has no spot-trading permission", {}
    if perms & FORBIDDEN_PERMS:
        return "shadow", "key can transfer or withdraw - refused; make a trade-only key", {}
    return "live", "armed", arm


# -- the book ------------------------------------------------------------------


def book_path(mode: str) -> Path:
    return C.STATE_DIR / f"mirror_book_{mode}.json"


def load_book(mode: str, capital: float) -> dict:
    b = read_json(book_path(mode))
    if b and abs(b.get("capital", 0) - capital) < 1e-6:
        return b
    return {"mode": mode, "venue": VENUE, "capital": capital, "cash": capital, "holdings": {},
            "high_water": capital, "fees": 0.0, "started": iso(), "orders": 0}


def mark(book: dict, quotes: dict) -> float:
    return book["cash"] + sum(q * quotes[s][0] for s, q in book["holdings"].items() if s in quotes)


def targets(paper: dict) -> dict[str, float]:
    eq = paper["account"]["equity"] or 1.0
    return {p["symbol"]: p["value"] / eq for p in paper.get("positions", [])}


def plan(book: dict, weights: dict, quotes: dict, filters: dict, can: dict) -> list[dict]:
    """Sells first (they fund the buys), then buys; each above the band and the venue minimum."""
    equity = mark(book, quotes)
    band = BAND * equity
    out = []
    want = {} if can["flatten"] else weights
    for s, q in sorted(book["holdings"].items()):
        if s not in quotes or q <= 0:
            continue
        bid = quotes[s][0]
        f = filters.get(venue_symbol(s), {})
        target = want.get(s, 0.0) * equity
        gap = q * bid - target
        qty = q if target <= 0 else (gap / bid if gap > band else 0.0)
        qty = round_step(min(qty, q), float(f.get("stepSize", 0)))
        if qty > 0 and qty * bid >= float(f.get("minNotional", 1)):
            out.append({"symbol": s, "side": "SELL", "quantity": qty, "why": "exit" if target <= 0 else "trim"})
    if can["buys"]:
        cash = book["cash"]
        for s, w in sorted(want.items(), key=lambda kv: -kv[1]):
            if s not in quotes:
                continue
            f = filters.get(venue_symbol(s), {})
            if not f.get("apiStateBuy", True):
                continue
            have = book["holdings"].get(s, 0.0) * quotes[s][1]
            gap = w * equity - have
            notional = min(gap, cash * 0.995, book.get("max_order") or float("inf"))
            if gap > band and notional >= max(float(f.get("minNotional", 1)) * 1.5, 5.0):
                out.append({"symbol": s, "side": "BUY", "notional": round(notional, 2),
                            "why": "entry" if have <= 0 else "add"})
                cash -= notional
    return out


# -- execution -------------------------------------------------------------------


def shadow_fill(venue: BingX, o: dict) -> dict:
    bids, asks = venue.depth(o["symbol"])
    if o["side"] == "BUY":
        px, qty = walk_book(asks, notional=o["notional"])
        return {"price": px, "quantity": qty, "quote": o["notional"], "fee_usdt": o["notional"] * FEE,
                "mid": (bids[0][0] + asks[0][0]) / 2}
    px, qty = walk_book(bids, quantity=o["quantity"])
    return {"price": px, "quantity": qty, "quote": px * qty, "fee_usdt": px * qty * FEE,
            "mid": (bids[0][0] + asks[0][0]) / 2}


def live_fill(venue: BingX, o: dict, cid: str) -> dict:
    bid, ask = venue.book(o["symbol"])
    r = (venue.market_buy(o["symbol"], o["notional"], cid) if o["side"] == "BUY"
         else venue.market_sell(o["symbol"], o["quantity"], cid))
    d = r
    for _ in range(5):
        try:
            d = venue.query(o["symbol"], r["orderId"])
            if str(d.get("status")) in ("FILLED", "CANCELED", "FAILED"):
                break
        except VenueError:
            pass
        time.sleep(1)
    qty, quote = float(d.get("executedQty", 0)), float(d.get("cummulativeQuoteQty", 0))
    fee, fee_asset = abs(float(d.get("fee", 0) or 0)), d.get("feeAsset", "USDT")
    fee_usdt = fee if fee_asset == "USDT" else fee * (quote / qty if qty else 0)
    if o["side"] == "BUY" and fee_asset == base_asset(o["symbol"]):
        qty -= fee   # the fee came out of the coins received
    return {"price": quote / qty if qty else 0.0, "quantity": qty, "quote": quote, "fee_usdt": fee_usdt,
            "fee_in_coin": fee_asset != "USDT", "mid": (bid + ask) / 2, "order_id": r.get("orderId"),
            "status": d.get("status")}


def apply(book: dict, o: dict, f: dict) -> None:
    s = o["symbol"]
    h = book["holdings"]
    if o["side"] == "BUY":
        h[s] = h.get(s, 0.0) + f["quantity"]
        book["cash"] -= f["quote"] + (0.0 if f.get("fee_in_coin") else f["fee_usdt"])
    else:
        h[s] = max(0.0, h.get(s, 0.0) - f["quantity"])
        book["cash"] += f["quote"] - f["fee_usdt"]
        if h[s] * f["price"] < 1.0:
            h.pop(s)
    book["fees"] += f["fee_usdt"]
    book["orders"] += 1


def reconcile_live(venue: BingX, book: dict) -> list[str]:
    """Never believe our own book over the venue: clamp holdings and cash to real balances."""
    notes = []
    bal = venue.balances()
    for s, q in list(book["holdings"].items()):
        real = bal.get(base_asset(s), 0.0)
        if real < q * 0.999:
            notes.append(f"{s} held {q:g} but the account has {real:g} - book corrected")
            book["holdings"][s] = real
    usdt = bal.get("USDT", 0.0)
    if usdt < book["cash"]:
        notes.append(f"cash ${book['cash']:,.2f} but the account has ${usdt:,.2f} free - book corrected")
        book["cash"] = usdt
    return notes


# -- one pass ----------------------------------------------------------------------


def cycle(venue: BingX, mode: str, arm: dict, why_mode: str, paper: dict | None, switch: dict, hl: dict,
          execute: bool) -> dict:
    capital = float(arm.get("capital", SHADOW_CAPITAL)) if mode == "live" else SHADOW_CAPITAL
    book = load_book(mode, capital)
    book["max_order"] = float(arm.get("max_order", capital * 0.25)) if mode == "live" else None
    can = brakes(switch, hl)
    notes, sent = [], []
    if mode == "live":
        notes += reconcile_live(venue, book)
    if paper is None or age_s(paper.get("at")) > PAPER_STALE_S:
        can = {**can, "buys": False, "orders": can["orders"] and can["flatten"]}
        notes.append("paper book stale - holding")
    universe = set(targets(paper or {"account": {"equity": 1}}).keys()) | set(book["holdings"])
    quotes = {s: venue.book(s) for s in sorted(universe)}
    filters = venue.filters()
    equity = mark(book, quotes)
    book["high_water"] = max(book["high_water"], equity)
    max_dd = float(arm.get("max_drawdown", 0.30))
    if mode == "live" and equity < (1 - max_dd) * book["high_water"] and not HALT.exists():
        HALT.write_text(f"mirror drawdown past {max_dd:.0%} at {iso()}", encoding="utf-8")
        can = brakes(switch, hl)
        notes.append("drawdown breaker tripped - HALT written")
    orders = plan(book, targets(paper) if paper else {}, quotes, filters, can) if can["orders"] else []
    for i, o in enumerate(orders):
        if not execute:
            break
        if mode == "live":   # re-read the switch before EVERY real order
            sw = remote_switch()
            if sw["trading"] != "on" or sw["market"] != "live" or HALT.exists():
                notes.append(f"switch went off or to simulated - {len(orders) - i} orders not sent")
                switch = sw
                break
        cid = f"s10m{int(time.time())}{i}{o['side'][0]}"[:40]
        try:
            f = live_fill(venue, o, cid) if mode == "live" else shadow_fill(venue, o)
        except VenueError as e:
            notes.append(f"{o['side']} {o['symbol']} rejected: {e}")
            continue
        apply(book, o, f)
        paper_px = next((p["price"] for p in (paper or {}).get("positions", []) if p["symbol"] == o["symbol"]), None)
        rec = {"at": iso(), "mode": mode, "venue": VENUE, **o, **{k: v for k, v in f.items()},
               "slip_bps_vs_mid": round(1e4 * (f["price"] / f["mid"] - 1) * (1 if o["side"] == "BUY" else -1), 2)
               if f["mid"] and f["price"] else None,
               "paper_price": paper_px}
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        sent.append(rec)
        log(f"{mode} {o['side']} {o['symbol']} {f['quantity']:g} @ {f['price']:g} ({o['why']})")
    equity = mark(book, quotes)
    book["high_water"] = max(book["high_water"], equity)
    book["last_cycle"] = iso()
    write_json(book_path(mode), book)
    w = targets(paper) if paper else {}
    return {"book": book, "quotes": quotes, "equity": equity, "planned": orders, "sent": sent, "notes": notes,
            "can": can, "weights": w, "switch": switch}


# -- execution costs (book audit 2026-10-15, phase 3) ----------------------------------

COSTS = C.STATE_DIR / "exec_samples.jsonl"
COST_TABLE = C.REPO / "research" / "system10" / "rnd" / "exec_costs.json"
SAMPLE_S = 15 * 60


def sample_costs(venue: BingX, paper: dict) -> int:
    """Every 15 min, what a market order of one slot (and two) would cost on BingX for every
    coin the book reads, against the 15-minute close the backtest fills at. Sends nothing."""
    eq = float(paper["account"]["equity"])
    slot = eq / max(1, int((paper.get("engine") or {}).get("cfg", {}).get("slots", 5)))
    rows, now_iso = [], iso()
    for c in (paper.get("scan") or {}).get("coins", []):
        try:
            bids, asks = venue.depth(c["symbol"], limit=100)
        except (VenueError, OSError, KeyError, IndexError):
            continue
        if not bids or not asks:
            continue
        mid = (bids[0][0] + asks[0][0]) / 2
        row = {"at": now_iso, "symbol": c["symbol"], "mid": mid, "close": c.get("price"), "close_bar": c.get("bar"),
               "half_spread_bps": round(1e4 * (asks[0][0] - bids[0][0]) / 2 / mid, 3),
               "mid_vs_close_bps": round(1e4 * (mid / c["price"] - 1), 2) if c.get("price") else None,
               "depth_1pct_usd": round(sum(p * q for p, q in asks if p <= mid * 1.01), 0)}
        for k, n in (("1x", slot), ("2x", 2 * slot)):
            bp, _ = walk_book(asks, notional=n)
            sp, _ = walk_book(bids, quantity=n / mid)
            row[f"buy_{k}_bps"] = round(1e4 * (bp / mid - 1), 3)
            row[f"sell_{k}_bps"] = round(1e4 * (1 - sp / mid), 3)
        row["slot_usd"] = round(slot, 0)
        rows.append(row)
    with COSTS.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return len(rows)


def cost_table() -> None:
    """Per coin medians of the samples -> research/system10/rnd/exec_costs.json, the measured
    round trip (2 x taker fee + both half spreads incl. impact at one slot) next to the
    backtest's flat 0.30%."""
    if not COSTS.exists():
        return
    import statistics as st
    by: dict[str, list] = {}
    for line in COSTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            by.setdefault(r["symbol"], []).append(r)
    med = lambda rs, k: round(st.median([x[k] for x in rs if x.get(k) is not None]), 3) if any(x.get(k) is not None for x in rs) else None  # noqa: E731
    out = {}
    for s, rs in sorted(by.items()):
        b1, s1, b2, s2 = (med(rs, k) for k in ("buy_1x_bps", "sell_1x_bps", "buy_2x_bps", "sell_2x_bps"))
        out[s] = {"samples": len(rs), "half_spread_bps": med(rs, "half_spread_bps"), "buy_1x_bps": b1, "sell_1x_bps": s1,
                  "buy_2x_bps": b2, "sell_2x_bps": s2, "mid_vs_close_bps": med(rs, "mid_vs_close_bps"),
                  "depth_1pct_usd": med(rs, "depth_1pct_usd"),
                  "round_trip_1x_pct": round((2 * FEE * 1e4 + (b1 or 0) + (s1 or 0)) / 100, 3)}
    doc = {"at": iso(), "venue": VENUE, "fee_taker": FEE, "backtest_round_trip_pct": 0.30,
           "first": min(r["at"] for rs in by.values() for r in rs), "coins": out}
    write_json(COST_TABLE, doc)


def publish(mode: str, why_mode: str, r: dict | None, switch: dict, hl: dict, paper: dict | None) -> None:
    """mirror_state.json: what the Trading tab shows above the paper book."""
    doc = {"at": iso(), "venue": VENUE, "mode": mode, "why_mode": why_mode, "switch": switch,
           "local_halt": HALT.read_text(encoding="utf-8", errors="replace").strip()[:200] if HALT.exists() else None,
           "health": hl, "paper_at": (paper or {}).get("at"), "control_url": CONTROL_URL}
    prev = read_json(STATE) or {}
    if r is None:
        doc.update({k: prev[k] for k in ("account", "positions", "last_cycle", "orders") if k in prev})
    else:
        b, q, eq = r["book"], r["quotes"], r["equity"]
        doc["account"] = {"capital": b["capital"], "equity": round(eq, 2), "cash": round(b["cash"], 2),
                          "invested": round(eq - b["cash"], 2), "return_pct": round(eq / b["capital"] - 1, 6),
                          "drawdown": round(1 - eq / b["high_water"], 5) if b["high_water"] else 0,
                          "fees": round(b["fees"], 2), "orders": b["orders"], "started": b["started"]}
        doc["positions"] = [{"symbol": s, "quantity": qty, "value": round(qty * q[s][0], 2),
                             "weight": round(qty * q[s][0] / eq, 4) if eq else 0,
                             "paper_weight": round(r["weights"].get(s, 0.0), 4)}
                            for s, qty in sorted(b["holdings"].items()) if s in q]
        doc["last_cycle"] = {"at": iso(), "planned": len(r["planned"]), "sent": len(r["sent"]),
                             "brakes": r["can"]["reasons"], "notes": r["notes"]}
        tail = []
        if LEDGER.exists():
            tail = [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines()[-50:] if x.strip()]
        doc["orders"] = [o for o in tail if o.get("mode") == mode][::-1]
    write_json(STATE, doc)


def main() -> int:
    ap = argparse.ArgumentParser(description="mirror the S10 paper book onto BingX (shadow unless armed)")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry", action="store_true", help="plan only, send nothing even in shadow")
    args = ap.parse_args()
    C.ensure_state_dir()
    creds = C.credentials()
    venue = BingX(creds.get("BINGX_API_KEY"), creds.get("BINGX_API_SECRET"))
    del creds
    market = remote_switch()["market"]
    mode, why, arm = decide_mode(venue, market)
    log(f"mode {mode} ({why})")
    end = time.time() + args.hours * 3600
    last_paper_at, last_cycle, last_mode_check = None, 0.0, time.time()
    last_sample, last_table = 0.0, 0.0
    while time.time() < end:
        switch, hl, paper = remote_switch(), health(), read_json(PAPER)
        # the panel's LIVE/SIMULATED takes effect on the next tick; arming within 10 min
        if switch["market"] != market or time.time() - last_mode_check > 600:
            market = switch["market"]
            new = decide_mode(venue, market)
            if new[0] != mode:
                log(f"mode {mode} -> {new[0]} ({new[1]})")
            mode, why, arm = new
            last_mode_check = time.time()
        due = (paper or {}).get("at") != last_paper_at or time.time() - last_cycle > CYCLE_S
        r = None
        if due or args.once:
            try:
                r = cycle(venue, mode, arm, why, paper, switch, hl, execute=not args.dry)
                last_paper_at, last_cycle = (paper or {}).get("at"), time.time()
            except (VenueError, OSError, KeyError, ValueError, IndexError) as e:
                log(f"cycle failed: {type(e).__name__}: {e}")
        publish(mode, why, r, switch, hl, paper)
        if paper and time.time() - last_sample > SAMPLE_S:
            try:
                sample_costs(venue, paper)
            except Exception as e:  # noqa: BLE001 - measuring must never stop the mirror
                log(f"cost sample failed: {type(e).__name__}: {e}")
            last_sample = time.time()
            if time.time() - last_table > 6 * 3600:
                cost_table()
                last_table = time.time()
        if args.once:
            break
        time.sleep(TICK_S)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
