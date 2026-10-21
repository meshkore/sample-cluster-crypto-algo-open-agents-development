"""The Live view's System 12 documents, from the FROZEN system (step 2, research/system12/out_ls/results.json):
    out_ls/history_doc.json   year by year: each year traded with the 20 configurations chosen on the years before it
    lab/trades.json + lab/trades_detail.json   its 2026 trades (the 20 chosen on 2019-2025 = the paper book)
Run by the paper task every 4 h, after paper12.py.

    python research/system12/system12_doc.py
"""

from __future__ import annotations

import json

import numpy as np

import lab12
import system12 as S
import system12_ls as L
import trades12


def parse(m: list) -> tuple:
    r, b, v, s = m
    return r, b, float(v), None if s == "None" else eval(s)          # noqa: S307 - our own frozen tuple text


def main() -> int:
    res = json.loads((L.OUT / "results.json").read_text(encoding="utf-8"))
    eng, regs = L.setup()
    dy = eng.dy
    chain = np.zeros(len(dy))
    expo = {}
    for N, f in res["folds"].items():
        N = int(N)
        mem = [eng.weights_ls(regs[r], b, v, s) for r, b, v, s in map(parse, f["ensemble"]["members"])]
        W = sum(mem) / len(mem)
        d = eng.daily_ls(W)
        chain[dy == N] = d[dy == N]
        expo[N] = round(float(np.abs(W[eng.w.P4["year"] == N]).sum(axis=1).mean()), 3)
        if N == S.FOLDS[-1]:
            names = [" / ".join(map(str, m)) for m in f["ensemble"]["members"]]
            trades12.write(eng, None, W, mem, names, lab12.LAB, L.LV.PERP_HALF)
    lab12.LAB.mkdir(parents=True, exist_ok=True)
    lab12.write_doc(eng, chain, res["folds"], expo)
    src = lab12.LAB / "history_doc.json"
    doc = json.loads(src.read_text(encoding="utf-8"))
    doc["current_book"] = [" / ".join(map(str, m)) for m in res["final"]["members"]]
    (L.OUT / "history_doc.json").write_text(json.dumps(doc), encoding="utf-8")
    src.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
