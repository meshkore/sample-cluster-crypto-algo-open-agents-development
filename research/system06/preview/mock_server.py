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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[3]
S6 = ROOT / "research" / "system06"
DASH = Path(__file__).resolve().parent / "dashboard.html"

LIVE = S6 / "live.json"
LEDGER = S6 / "ledger.jsonl"
BEST = S6 / "best.json"
CURVES = S6 / "champion_curves.json"
KNOW = S6 / "knowledge"

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


def _card_from_record(rec: dict) -> dict:
    """A history card from one ledger iteration."""
    cons = rec.get("consistency") or {}
    annual = rec.get("annual") or {}
    portfolio = (rec.get("portfolio") or {}).get("annual") or {}
    fw = portfolio.get("2026") if isinstance(portfolio, dict) else None
    has_2026 = "2026" in annual or bool(fw)
    if fw and fw.get("return_pct") is not None and "2026" not in annual:
        annual = {**annual, "2026": round(float(fw["return_pct"]), 4)}
    return {
        "id": f"iter-{rec.get('iteration')}",
        "kind": "iter",
        "iteration": rec.get("iteration"),
        "at": rec.get("at"),
        "hypothesis": _card_hyp(rec),
        "rationale": rec.get("rationale"),
        "score": rec.get("score"),
        "min_year": cons.get("min_year"),
        "cagr": cons.get("cagr"),
        "all_positive": cons.get("all_positive"),
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
    return {
        "id": "best",
        "kind": "best",
        "iteration": best.get("iteration"),
        "at": best.get("at"),
        "hypothesis": _card_hyp(best),
        "rationale": best.get("rationale"),
        "score": best.get("score"),
        "min_year": cons.get("min_year"),
        "cagr": cons.get("cagr"),
        "all_positive": cons.get("all_positive"),
        "annual": annual,
        "has_2026": "2026" in annual,
        "forward_2026": fw,
        "note": best.get("note"),
        "seconds": None,
    }


def _running() -> dict:
    live = _load(LIVE) or {}
    age = _age_seconds(live.get("heartbeat"))
    running = bool(live.get("running"))
    stale = running and (age is not None and age > STALE_AFTER_S)
    if stale:
        running = False
    return {**live, "running": running, "stale": stale, "heartbeat_age_s": age}


def _state() -> dict:
    records = _ledger()
    best = _best_card(_load(BEST))
    history = [_card_from_record(r) for r in reversed(records)]  # newest first
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
        "counts": {"iterations": len(records), "promotions": proms},
        "incumbent_2026": INCUMBENT_2026,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


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
        return card
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
                card["curves"] = (_load(CURVES) or {}) if best.get("iteration") == n else {}
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
