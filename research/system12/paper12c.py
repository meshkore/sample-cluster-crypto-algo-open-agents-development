"""System 12 CHAMPION paper book (operator go 2026-10-22): $50,000, side by side with the frozen book (paper12.py).

Pre-registered, frozen on the first run in paper_champion/selection.json: the hypothesis loop's champion at that moment -
the frozen book's 20 configurations (chosen on 2019-2025) plus every adopted overlay with the parameter it chose on
2019-2025 (hyp/champion.json, fold 2026). Later adoptions do NOT change this book; a new champion would need a new book.
Same execution as paper12.py: decide at a 4h close, fill at the next bar, perp costs + funding. Never real money.

    python research/system12/paper12c.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

import hyp12
import system12_ls as L

OUT = L.S.HERE / "paper_champion"
BOOK = 50_000.0


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fs = OUT / "selection.json"
    if not fs.exists():
        champ = hyp12.load_champ()
        start = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "h")
        start = start - (start.astype(int) % 4)
        fs.write_text(json.dumps({"frozen_at": now(), "start": str(start), "book_usd": BOOK,
                                  "overlays": [{"id": c["id"], "param": c["params"]["2026"]} for c in champ],
                                  "base": "research/system12/out_ls/results.json folds[2026] (= paper/selection.json members)"},
                                 indent=1, default=str), encoding="utf-8")
    sel = json.loads(fs.read_text(encoding="utf-8"))
    import gen12
    import hypotheses12
    reg = {h.id: h for h in hypotheses12.ALL + gen12.load()}
    lab = hyp12.Lab()
    W = lab.base[2026]
    for o in sel["overlays"]:
        W = lab.apply(reg[o["id"]], W, o["param"])
    w = lab.eng.w
    grid = w.P4["grid"]
    rows = np.flatnonzero(grid > np.datetime64(sel["start"], "ns").astype(np.int64))
    coins = [c.replace("USDT", "") for c in w.P4["coins"]]
    state = {"updated": now(), "start": sel["start"], "book_usd": BOOK, "bars": int(len(rows)),
             "overlays": [o["id"] for o in sel["overlays"]]}
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
    state.update(target=pos, net_exposure=round(float(last.sum()), 4), as_of_bar=str(grid[-1].astype("datetime64[ns]"))[:16])
    (OUT / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
    with (OUT / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now(), "bar": state["as_of_bar"], "target": pos}) + "\n")
    print(f"[{now()}] System 12 champion paper: {state.get('ret', 0):+.2%} since {sel['start']} · target {pos}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
