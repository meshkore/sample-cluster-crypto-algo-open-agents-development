"""The paper book: the system traded on live bars from the start in selection.json. No real orders.

Every run recomputes the book from its start on closed bars only (the rules are causal and deterministic), writes
state.json and appends the current target to decisions.jsonl, the audit trail.

    python -m system12.paper
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from . import backtest, market, strategy
from .config import PAPER_DIR, SELECTION
from .market import Market


def _stamp(ns) -> str:
    return str(np.int64(ns).astype("datetime64[ns]"))[:16]


def state(m: Market, W: np.ndarray | None = None) -> dict:
    W = strategy.target_weights(m) if W is None else W
    paper = SELECTION["paper"]
    book = float(paper["book_usd"])
    start_ns = np.datetime64(paper["start"], "ns").astype(np.int64)
    r = backtest.run(m, W, np.flatnonzero(m.grid4 > start_ns))
    last = W[-1]
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": SELECTION["version"],
        "start": paper["start"],
        "book_usd": book,
        "bars": int(len(r.rows)),
        "ret": round(r.ret, 5),
        "equity_usd": round(book * (1 + r.ret), 2),
        "max_dd": round(r.max_dd, 5),
        "curve": [[_stamp(m.grid4[i]), round(float(e), 5)] for i, e in zip(r.rows, r.equity)],
        "target": {c: round(float(last[j]), 4) for j, c in enumerate(m.coins) if abs(last[j]) > 1e-6},
        "net_exposure": round(float(last.sum()), 4),
        "as_of_bar": _stamp(m.grid4[-1]),
        "btc": round(float(m.close4[-1, 0]), 2),
    }


def save(s: dict) -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    (PAPER_DIR / "state.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    with (PAPER_DIR / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": s["updated"], "bar": s["as_of_bar"], "target": s["target"]}) + "\n")


def main() -> int:
    s = state(market.load())
    save(s)
    print(f"[{s['updated']}] paper {s['ret']:+.2%} since {s['start']}, target {s['target']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
