"""Local system06 monitor — backed by the REAL artifacts the autonomous loop writes.

Serves a purpose-built real-time dashboard (`dashboard.html`) plus a small JSON API
built from what the loop actually produces:

  - research/system06/live.json      — the loop's heartbeat: what it is doing NOW
  - research/system06/ledger.jsonl   — every iteration (the history), one JSON per line
  - research/system06/best.json      — the current champion
  - research/system06/champion_curves.json — the champion's per-year equity curves

Every file is re-read on each request, so the page reflects the loop within one poll.
Nothing here is fabricated: if a number is missing it is shown as missing. This is the
LOCAL view — the production monitor is monitor/public/index.html, deployed separately.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[3]
S6 = ROOT / "research" / "system06"
DASH = Path(__file__).resolve().parent / "dashboard.html"
ITER_PAGE = Path(__file__).resolve().parent / "iterations.html"

LIVE = S6 / "live.json"
LEDGER = S6 / "ledger.jsonl"
BEST = S6 / "best.json"
CURVES = S6 / "champion_curves.json"
KNOW = S6 / "knowledge"
VARIANTS = S6 / "variants.json"      # the labelled decision-stack backtests (same model)
RND = S6 / "rnd"                     # the autonomous R&D harness: agenda + diary
ROLLING = S6 / "rolling.json"        # rolling one-year-hold stats per card {id: {...}}

STALE_AFTER_S = 45   # heartbeat thread bumps every ~6s; older than this = process died
INCUMBENT_2026 = 0.0505


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _ledger() -> list[dict]:
    return _jsonl(LEDGER)


def _knowledge() -> dict:
    ideas = _jsonl(KNOW / "ideas.jsonl")
    sources = _jsonl(KNOW / "sources.jsonl")
    order = {"testing": 0, "applied": 1, "proposed": 2, "rejected": 3}
    prio = {"high": 0, "medium": 1, "low": 2}
    ideas.sort(key=lambda i: (order.get(i.get("status"), 9), prio.get(i.get("priority"), 9)))
    dates = sorted([s.get("date") for s in sources if s.get("date")], reverse=True)
    counts: dict[str, int] = {}
    for i in ideas:
        counts[i.get("status", "?")] = counts.get(i.get("status", "?"), 0) + 1
    return {"ideas": ideas, "sources_count": len(sources),
            "latest_source": dates[0] if dates else None, "counts": counts}


def _hyp(config: dict | None) -> str:
    c = config or {}
    span = int(c.get("trend_span", 2880))
    days = max(1, span // 96)
    win = c.get("window", "?")
    thr = c.get("threshold", "?")
    ep = c.get("epochs", "?")
    return f"TCN · window {win} · threshold {thr} · epochs {ep} · trend {days}d"


def _card_hyp(rec: dict) -> str:
    """Card headline: lead with the TECHNIQUE this attempt tested (the rationale focus),
    then the config detail — so the operator reads what each iteration tried, not just knobs."""
    focus = (rec.get("rationale") or {}).get("focus")
    base = _hyp(rec.get("config"))
    return f"{focus} · {base}" if focus else base


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds()
    except ValueError:
        return None


def _consistency_from(annual: dict, stored: dict) -> dict:
    """DERIVE the consistency badge from the years the card is actually showing.

    A stored `consistency` block is a derived value living next to the numbers it is
    derived from, and only the LOOP updates it - so every hand-adoption desynchronised
    it. On 2026-09-03 the champion card was showing "positive every year" and "worst
    year +5.1%" from a block computed before market impact turned 2025 negative, while
    the table printed right beside it said -2.96%.

    best.json is repaired (tools/resync_consistency.py), but deriving here as well means
    no future adoption can put the badge and the table back into disagreement. Falls
    back to the stored block only when there are no research years to derive from.
    Mirrors autoloop._consistency; 2026 is sealed and never counted.
    """
    rets = [float(v) for y, v in (annual or {}).items()
            if v is not None and str(y).isdigit() and int(y) < 2026]
    if not rets:
        return {"min_year": stored.get("min_year"), "cagr": stored.get("cagr"),
                "all_positive": stored.get("all_positive")}
    growth = 1.0
    for r in rets:
        growth *= (1.0 + r)
    return {"min_year": min(rets),
            "cagr": growth ** (1.0 / len(rets)) - 1.0,
            # `stopped` is not on the card, so honour it from the stored block if set.
            "all_positive": min(rets) > 0 and not stored.get("stopped", False)}


def _card_from_record(rec: dict) -> dict:
    """A history card from one ledger iteration."""
    cons = rec.get("consistency") or {}
    annual = rec.get("annual") or {}
    portfolio = (rec.get("portfolio") or {}).get("annual") or {}
    # Every iteration carries its own sealed-2026 readout since 2026-08-29 (operator:
    # the forward year is the only untrained evidence, so no published card may omit
    # it). Promoted rows also have it inside `portfolio`; prefer whichever exists.
    fw = rec.get("forward_2026") or (portfolio.get("2026")
                                     if isinstance(portfolio, dict) else None)
    if isinstance(fw, dict) and fw.get("error"):
        fw = None
    has_2026 = "2026" in annual or bool(fw)
    if fw and fw.get("return_pct") is not None and "2026" not in annual:
        annual = {**annual, "2026": round(float(fw["return_pct"]), 4)}
    _cons = _consistency_from(annual, cons)
    return {
        "id": f"iter-{rec.get('iteration')}",
        "kind": "iter",
        "iteration": rec.get("iteration"),
        "at": rec.get("at"),
        "hypothesis": _card_hyp(rec),
        "rationale": rec.get("rationale"),
        "score": rec.get("score"),
        "min_year": _cons["min_year"],
        "cagr": _cons["cagr"],
        "all_positive": _cons["all_positive"],
        "annual": annual,
        "has_2026": has_2026,
        "forward_2026": fw,
        "error": rec.get("error"),
        "seconds": rec.get("seconds"),
    }


def _best_card(best: dict | None) -> dict | None:
    if not best:
        return None
    cons = best.get("consistency") or {}
    annual = best.get("annual_returns") or {}
    fw = best.get("forward_2026") or {}
    # The champion keeps its sealed readout in `forward_2026`, not inside
    # `annual_returns` - so the card that matters most was the one card showing no
    # 2026 figure at all, while every iteration card had one. The operator spotted it
    # on the page. Merge it here exactly as `_card_from_record` does for iterations.
    if fw.get("return_pct") is not None and "2026" not in annual:
        annual = {**annual, "2026": round(float(fw["return_pct"]), 4)}
    _cons = _consistency_from(annual, cons)
    return {
        "id": "best",
        "kind": "best",
        "iteration": best.get("iteration"),
        "at": best.get("at"),
        "hypothesis": _card_hyp(best),
        "rationale": best.get("rationale"),
        "score": best.get("score"),
        "min_year": _cons["min_year"],
        "cagr": _cons["cagr"],
        "all_positive": _cons["all_positive"],
        "annual": annual,
        "has_2026": "2026" in annual,
        "forward_2026": fw,
        "note": best.get("note"),
        "seconds": None,
    }


def _variants() -> list[dict]:
    """The labelled decision-stack backtests (same model, different stack), if built."""
    data = _load(VARIANTS)
    return data if isinstance(data, list) else []


def _rolling() -> dict:
    """Rolling one-year-hold stats keyed by card id ('best', 'var-1', ...)."""
    data = _load(ROLLING)
    return data if isinstance(data, dict) else {}


def _variant_card(v: dict) -> dict:
    """A rail card for one variant — same shape the rail expects for iterations/best."""
    return {
        "id": v.get("id"), "kind": "variant", "name": v.get("name"),
        "hypothesis": v.get("name"), "note": v.get("note"), "at": v.get("at"),
        "score": v.get("score"), "min_year": v.get("min_year"), "cagr": v.get("cagr"),
        "all_positive": v.get("all_positive"), "annual": v.get("annual") or {},
        "has_2026": "2026" in (v.get("annual") or {}),
    }


def _architectures() -> list:
    """The architecture registry index, with each entry's measurement count."""
    rows = _jsonl(S6 / "registry" / "architectures.jsonl")
    out = []
    for r in rows:
        folder = S6 / "registry" / str(r.get("id"))
        bt = _jsonl(folder / "backtests.jsonl")
        sealed = [b.get("sealed_2026") for b in bt if b.get("sealed_2026") is not None]
        out.append({**r, "backtest_count": len(bt),
                    "sealed_2026": sorted(sealed)[len(sealed) // 2] if sealed else None,
                    "explain": (folder / "explain.md").read_text(encoding="utf-8")
                               if (folder / "explain.md").is_file() else "",
                    "diagram": (folder / "diagram.mmd").read_text(encoding="utf-8")
                               if (folder / "diagram.mmd").is_file() else "",
                    "backtests": bt})
    return out


def _rnd() -> dict:
    """The autonomous R&D harness state: the agenda (backlog + graveyard) and the diary
    tail (recent decisions). Read straight from rnd/*.jsonl so the panel is never stale."""
    agenda = _jsonl(RND / "agenda.jsonl")
    diary = _jsonl(RND / "diary.jsonl")
    # The MACHINE's own hourly trace (pulse.py), so the public page never has an
    # hour-shaped hole even when the agent is asleep. Newest first, last day.
    pulse = _jsonl(RND / "pulse.jsonl")[-24:][::-1]
    counts: dict[str, int] = {}
    for a in agenda:
        counts[a.get("status", "?")] = counts.get(a.get("status", "?"), 0) + 1
    order = {"running": 0, "queued": 1, "win": 2, "proposed": 3, "loss": 4, "shelved": 5}
    agenda.sort(key=lambda a: order.get(a.get("status"), 9))
    return {
        "agenda": agenda,
        "diary": diary[-12:][::-1],   # newest first, last dozen
        "pulse": pulse,
        "last_pulse": pulse[0] if pulse else None,
        "counts": counts,
        "last_tick": diary[-1] if diary else None,
        # The plain-language research strategy (diagnosis, direction, workstreams) so a
        # visitor can read WHY the loop is doing what it is doing, not just what it ran.
        "strategy": _load(RND / "strategy.json") or {},
        # The architecture registry (operator, 2026-08-30): one ID per STRUCTURE,
        # each with its code, explanation, diagram and every backtest attached.
        "architectures": _architectures(),
        "active": bool(agenda),
    }


def _ceiling() -> dict | None:
    """The perfect-hindsight ceiling per year (tools/ceiling.py), under the SAME cost
    model the champion trades under, plus how much of it we actually took.

    TWO capture numbers, because the obvious one is badly behaved (operator, 2026-09-03:
    "captura 700 trades de 1800... eso es prácticamente un 50%, o sea, algo no está bien
    calculado"). He was right, and the inconsistency he spotted is real:

      capture_wealth = (1+ours) / (1+oracle)      2021 -> 5.9%
      capture_log    = ln(1+ours) / ln(1+oracle)  2021 -> 63.9%
      share of the oracle's trades we took        2021 -> 42.9%

    Terminal wealth is EXPONENTIAL in the number of good decisions, so taking 43% of the
    decisions does not leave you with 43% of the money - it leaves you with e^(0.43·k)
    out of e^k. The wealth ratio therefore understates skill, and understates it harder
    the bigger the year, which is exactly why 5.9% sat next to 42.9% and looked broken.

    The log ratio is the honest headline: it is linear in compounding decisions, it
    agrees with the trade share, and it separates years the wealth ratio flattens
    together - 2022 (+8.7%) and 2025 (-3.0%) both read as "0.4%" of wealth, while the
    log ratio correctly gives +1.5% and -0.6% (negative: we went backwards in a year
    that offered +22,000%). Both are published; the page leads with the log ratio and
    labels each for what it is.
    """
    files = sorted(RND.glob("ceiling_*.json"))
    if not files:
        return None
    data = _load(files[-1])
    if not isinstance(data, dict):
        return None
    years = data.get("years") or {}
    out = {}
    for y, v in years.items():
        oracle_mult = 1.0 + float(v.get("oracle_return", 0.0))
        ach_mult = 1.0 + float(v.get("achieved", 0.0))
        wealth = ach_mult / oracle_mult if oracle_mult > 0 else None
        log_cap = None
        if oracle_mult > 1.0 and ach_mult > 0:
            log_cap = math.log(ach_mult) / math.log(oracle_mult)
        out[y] = {"oracle_return": v.get("oracle_return"), "achieved": v.get("achieved"),
                  "capture": log_cap,          # the headline: share of compounded growth
                  "capture_wealth": wealth,    # share of the final money
                  "oracle_trades": v.get("oracle_trades"),
                  "legs_available": v.get("legs_available")}
    return {"at": data.get("at"), "model": data.get("model"), "years": out}


def _market() -> dict | None:
    """The PLAYING FIELD, precomputed once by tools/market_base.py: how many assets
    existed each year, how much money changed hands, how many opportunities the market
    offered and what one perfect trade was worth. Pure description of the ground — it
    carries no result of ours, by the operator's instruction (2026-09-03)."""
    data = _load(RND / "market_base.json")
    return data if isinstance(data, dict) else None


def _running() -> dict:
    live = _load(LIVE) or {}
    age = _age_seconds(live.get("heartbeat"))
    running = bool(live.get("running"))
    stale = running and (age is not None and age > STALE_AFTER_S)
    if stale:
        running = False
    return {**live, "running": running, "stale": stale, "heartbeat_age_s": age}


# The home rail shows only the freshest iterations (operator, 2026-09-02: dozens of
# old cards are noise on every load - the last ten tell the story, the rest belong on
# their own page). The FULL list still ships, once, via _iterations()/api/iterations.
HOME_HISTORY = 10


def _state() -> dict:
    records = _ledger()
    best = _best_card(_load(BEST))
    history = [_card_from_record(r) for r in reversed(records)][:HOME_HISTORY]
    proms = 0
    seen = None
    # count score improvements as promotions: each ledger crossing of the running best
    for r in records:
        s = r.get("score")
        if s is None:
            continue
        if seen is None or s > seen + 0.02:
            proms += 1
            seen = s
    return {
        "best": best,
        "running": _running(),
        "history": history,
        "variants": [_variant_card(v) for v in _variants()],
        "rnd": _rnd(),
        "ceiling": _ceiling(),
        "market": _market(),
        "counts": {"iterations": len(records), "promotions": proms,
                   "shown": len(history)},
        "incumbent_2026": INCUMBENT_2026,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


def _iterations() -> dict:
    """EVERY iteration as a compact table row, newest first - the /iterations page.

    Deliberately the same card shape the rail uses: the row already carries the
    annual percentages and the hypothesis, so the page can show a detail without a
    per-id fetch against a details map that only covers the home rail.
    """
    records = _ledger()
    # No timestamp in this payload on purpose: the pusher gates it by content hash,
    # and a clock field would turn "one push per new iteration" into one per cycle.
    return {"rows": [_card_from_record(r) for r in reversed(records)],
            "count": len(records)}


def _detail(cid: str) -> dict | None:
    if cid == "best":
        best = _load(BEST)
        card = _best_card(best)
        if not card:
            return None
        card["annual_detail"] = (best or {}).get("annual_detail") or {}
        card["band"] = (best or {}).get("band")
        card["risk"] = (best or {}).get("risk")
        card["net_val"] = (best or {}).get("net_val")
        card["config"] = (best or {}).get("config")
        card["curves"] = _load(CURVES) or {}
        card["rolling"] = _rolling().get("best")
        return card
    if cid.startswith("var-"):
        roll = _rolling()
        for v in _variants():
            if v.get("id") == cid:
                # already carries annual / annual_detail / curves / risk / config / band
                return {**v, "kind": "variant", "rolling": roll.get(cid)}
        return None
    if cid.startswith("iter-"):
        try:
            n = int(cid.split("-", 1)[1])
        except ValueError:
            return None
        for r in _ledger():
            if r.get("iteration") == n:
                card = _card_from_record(r)
                card["annual_detail"] = r.get("annual_detail") or {}
                card["band"] = r.get("band")
                card["risk"] = r.get("risk")
                card["net_val"] = r.get("net_val")
                card["config"] = r.get("config")
                # the champion's curves belong only to the champion iteration
                best = _load(BEST) or {}
                is_champ = best.get("iteration") == n
                card["curves"] = (_load(CURVES) or {}) if is_champ else {}
                card["rolling"] = _rolling().get("best") if is_champ else _rolling().get(cid)
                return card
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html", "/dashboard.html"):
            try:
                return self._send(DASH.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            except OSError:
                return self._send("dashboard.html missing", "text/plain", 404)
        if path == "/api/state":
            return self._send(json.dumps(_state(), default=str))
        if path == "/api/iterations":
            return self._send(json.dumps(_iterations(), default=str))
        if path == "/iterations":
            try:
                return self._send(ITER_PAGE.read_text(encoding="utf-8"),
                                  "text/html; charset=utf-8")
            except OSError:
                return self._send("iterations.html missing", "text/plain", 404)
        if path == "/api/knowledge":
            return self._send(json.dumps(_knowledge(), default=str))
        if path == "/api/detail":
            cid = (parse_qs(parsed.query).get("id") or [""])[0]
            d = _detail(cid)
            if d is None:
                return self._send(json.dumps({"error": "not found"}), code=404)
            return self._send(json.dumps(d, default=str))
        return self._send(json.dumps({"error": "unknown route"}), code=404)


def main(argv=None):
    import sys
    port = int((argv or sys.argv[1:] or [8799])[0])
    host = "0.0.0.0"
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"real system06 monitor on http://{host}:{port}  (open http://127.0.0.1:{port})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
