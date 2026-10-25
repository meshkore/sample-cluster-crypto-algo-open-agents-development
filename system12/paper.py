"""The System 12 paper book: $50,000 from selection.json's start, never real money.

Every run recomputes the book from the start on closed bars only (the rules are causal and deterministic), appends the
current target to decisions.jsonl (the audit trail) and writes state.json. Decide at a 4h close, fill at the next bar.

    python -m system12.paper
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from . import data
from . import strategy as S

STATE_DIR = data.DATA_DIR.parent / "paper"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stamp(ns) -> str:
    return str(np.int64(ns).astype("datetime64[ns]"))[:16]


def run(w=None) -> dict:
    w = w or S.world()
    W = S.weights(w)
    grid = w.p4["grid"]
    paper = S.SELECTION["paper"]
    book = float(paper["book_usd"])
    rows = np.flatnonzero(grid > np.datetime64(paper["start"], "ns").astype(np.int64))
    state = {
        "updated": now(),
        "version": S.SELECTION["version"],
        "start": paper["start"],
        "book_usd": book,
        "bars": int(len(rows)),
    }
    if len(rows):
        Wp = np.zeros_like(W)
        Wp[rows] = W[rows]
        eq = np.cumprod(1 + S.bar_returns(w, Wp)[rows])
        state.update(
            ret=round(float(eq[-1] - 1), 5),
            equity_usd=round(book * float(eq[-1]), 2),
            max_dd=round(float((1 - eq / np.maximum.accumulate(eq)).max()), 5),
            curve=[[stamp(grid[i]), round(float(e), 5)] for i, e in zip(rows, eq)],
        )
    last = W[-1]
    state.update(
        target={c: round(float(last[j]), 4) for j, c in enumerate(w.coins) if abs(last[j]) > 1e-6},
        net_exposure=round(float(last.sum()), 4),
        as_of_bar=stamp(grid[-1]),
        btc=round(float(w.p4["close"][-1, 0]), 2),
    )
    return state


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = run()
    (STATE_DIR / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
    with (STATE_DIR / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": state["updated"], "bar": state["as_of_bar"], "target": state["target"]}) + "\n")
    print(
        f"[{state['updated']}] System 12 paper: {state.get('ret', 0):+.2%} since {state['start']} - target {state['target']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
