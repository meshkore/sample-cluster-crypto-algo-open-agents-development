"""System 12 shadow paper book (operator go 2026-10-21): $50,000 from the first run, side by side with System 11.

Pre-registered, frozen on the first run in paper/selection.json:
    the 20 configurations System 12's long/short search chose on 2019-2025 (out_ls/results.json "final"),
    averaged: long BTC+ETH while the BTC trend rules agree, half short BTC/BTC+ETH when they turn bearish,
    40% volatility target, exposure in steps of 25%.
Book: USD-M perpetuals, decide at a bar's close and fill at the next 4h bar, 0.10%/side + impact, funding charged.
The rules are deterministic and causal, so each run recomputes the book from the start on closed bars only.
Every run appends the current target to paper/decisions.jsonl (the audit trail) and writes paper/state.json.
Never trades real money.

    python research/system12/paper12.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

import system12_ls as L

OUT = L.S.HERE / "paper"
BOOK = 50_000.0


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fs = OUT / "selection.json"
    if not fs.exists():
        res = json.loads((L.OUT / "results.json").read_text(encoding="utf-8"))
        start = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "h")
        start = start - (start.astype(int) % 4)                     # the 4h bar that is open now; trading starts after it
        fs.write_text(json.dumps({"frozen_at": now(), "start": str(start), "book_usd": BOOK, "chosen_on": res["final"]["chosen_on"],
                                  "members": res["final"]["members"], "source": "research/system12/out_ls/results.json"}, indent=1),
                      encoding="utf-8")
    sel = json.loads(fs.read_text(encoding="utf-8"))
    eng, regs = L.setup()
    W = 0
    for r, b, v, s in sel["members"]:
        short = None if s == "None" else eval(s)                     # noqa: S307 - our own frozen tuple text
        W = W + eng.weights_ls(regs[r], b, float(v), short)
    W = W / len(sel["members"])
    w = eng.w
    grid = w.P4["grid"]
    t0 = np.datetime64(sel["start"], "ns").astype(np.int64)
    rows = np.flatnonzero(grid > t0)
    coins = [c.replace("USDT", "") for c in w.P4["coins"]]
    state = {"updated": now(), "start": sel["start"], "book_usd": BOOK, "bars": int(len(rows))}
    if len(rows):
        Wp = np.zeros_like(W)
        Wp[rows] = W[rows]
        r, _ = L.H.bar_returns(w, Wp, L.LV.PERP_HALF, w.fund4)
        eq = np.cumprod(1 + r[rows])
        state.update(ret=round(float(eq[-1] - 1), 5), equity_usd=round(BOOK * float(eq[-1]), 2),
                     max_dd=round(float((1 - eq / np.maximum.accumulate(eq)).max()), 5),
                     curve=[[str(grid[i].astype("datetime64[ns]"))[:16], round(float(e), 5)] for i, e in zip(rows, eq)])
    last = W[-1]
    pos = {coins[j]: round(float(last[j]), 4) for j in np.flatnonzero(np.abs(last) > 1e-6)}
    state["target"] = pos
    state["net_exposure"] = round(float(last.sum()), 4)
    state["as_of_bar"] = str(grid[-1].astype("datetime64[ns]"))[:16]
    (OUT / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
    with (OUT / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now(), "bar": state["as_of_bar"], "target": pos}) + "\n")
    print(f"[{now()}] System 12 paper: {state.get('ret', 0):+.2%} since {sel['start']} · target {pos}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
