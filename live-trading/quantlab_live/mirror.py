"""Mirror the System 10 paper book onto a venue account - shadow by default, real money only when armed.

The decisions are NOT made here. The paper trader (system010_conditioned_rl.paper) runs the
pinned release and publishes its book every cycle; this process reads that book's
position weights and makes the venue account hold the same weights of its own capital.
Mirroring weights instead of replaying orders heals itself: a restart, a partial fill or a
skipped cycle is corrected on the next pass, and nothing here re-implements the strategy.

Three brakes, any one of which stops every order to the venue:

1. **The switch** on the public Trading tab (PIN-protected, stored by the Worker at
   /api/control). Anything but a fresh, explicit "on" is OFF - unreachable counts as off.
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
        return {"trading": "on" if doc.get("trading") == "on" else "off", "at": doc.get("at"),
                "by": doc.get("by"), "read_at": iso(), "reachable": True}
    except Exception as e:  # noqa: BLE001 - unreachable is a state, not a crash
        return {"trading": "off", "reachable": False, "error": type(e).__name__, "read_at": iso()}


def health() -> dict:
    h = read_json(HEALTH)
    if not h:
        return {"recommendation": "trade", "known": False, "note": "no health monitor yet"}
    stale = age_s(h.get("at")) > HEALTH_STALE_S
    return {"recommendation": "trade" if stale else h.get("recommendation", "trade"), "known": not stale,
            "score": h.get("score"), "level": h.get("level"), "at": h.get("at"),
            "note": "health reading stale - ignored" if stale else ""}


def brakes(switch: dict, hl: dict, live: bool = True) -> dict:
    """What may happen this pass: buys, sells, or flatten.

    The switch and HALT guard the venue, so they bind the live book only; the shadow book
    keeps following the paper (it sends nothing) and just records that live would be stopped.
    """
    reasons = []
    if switch["trading"] != "on":
        reasons.append("switch off" if switch.get("reachable") else "switch unreachable")
    if HALT.exists():
        reasons.append("local HALT: " + HALT.read_text(encoding="utf-8", errors="replace").strip()[:120])
    stopped = bool(reasons) and live
    if reasons and not live:
        reasons = [r + " (live would not send)" for r in reasons]
    rec = hl.get("recommendation", "trade")
    if not stopped and rec == "halt":
        reasons.append("market health: halt")
    elif not stopped and rec == "block_entries":
        reasons.append("market health: entries blocked")
    return {"orders": not stopped, "buys": not stopped and rec == "trade",
            "flatten": not stopped and rec == "halt", "reasons": reasons}


# -- mode ----------------------------------------------------------------------


def decide_mode(venue: BingX) -> tuple[str, str, dict]:
    """('live' | 'shadow', why, arm). Live only when every condition holds."""
    arm = read_json(ARM) or {}
    if not arm:
        return "shadow", "not armed (no arming file)", {}
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
    can = brakes(switch, hl, live=mode == "live")
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
        can = brakes(switch, hl, live=True)
        notes.append("drawdown breaker tripped - HALT written")
    orders = plan(book, targets(paper) if paper else {}, quotes, filters, can) if can["orders"] else []
    for i, o in enumerate(orders):
        if not execute:
            break
        if mode == "live":   # re-read the switch before EVERY real order
            sw = remote_switch()
            if sw["trading"] != "on" or HALT.exists():
                notes.append(f"switch went off - {len(orders) - i} orders not sent")
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
    mode, why, arm = decide_mode(venue)
    log(f"mode {mode} ({why})")
    end = time.time() + args.hours * 3600
    last_paper_at, last_cycle, last_mode_check = None, 0.0, time.time()
    while time.time() < end:
        switch, hl, paper = remote_switch(), health(), read_json(PAPER)
        if time.time() - last_mode_check > 600:   # arming or disarming takes effect within 10 min
            new = decide_mode(venue)
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
        if args.once:
            break
        time.sleep(TICK_S)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
