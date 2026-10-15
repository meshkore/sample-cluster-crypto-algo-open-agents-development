"""The book worker (book audit 2026-10-15, phase 4): book levers chosen on their own ledger.

Signals are frozen to the current signal release (tools/book_inputs.py). Each pass books the
proposals not yet on rnd/book_trials.jsonl (the book grid, then each phase-2 lever grafted on
the current choice), chooses the book on years <= 2025 by search.law (tools/book_lab.choose:
DD cap and trades first), and publishes book_releases/book_NNNN.json only when the choice
beats the incumbent book (the newest book release on these signals, else the release's own)
  * by >= GAIN_MIN of law on 2022-2025,
  * with the paired 21-day-block bootstrap P(better) >= book_lab.WIN_P,
  * without a higher max yearly drawdown on 2022-2025,
  * and the book ledger's PBO (CSCV, monthly) <= PBO_MAX.
A book release changes only the book keys (search.mm_kwargs); paper.py applies it as a new
hot-swap segment only while research/system10/ENABLE_BOOK_RELEASES exists.

NOT launched by the watchdog (operator, 2026-10-15: inert until reviewed).
    python -m system010_conditioned_rl.book_worker --hours 6
    python -m system010_conditioned_rl.book_worker --pbo        # write rnd/book_overfit.json only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np

from . import search as S

BOOK_RELEASES = S.OUT / "book_releases"
BOOK_OVERFIT = S.OUT / "rnd/book_overfit.json"
GAIN_MIN = 0.02            # paper.SWAP_BAND: the top of the search sits within ~0.02 of law
PBO_MAX = 0.5
BATCH = 24                 # books per pass before the choice is re-read


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _lab_mod():
    S._tools()
    import book_lab as L   # noqa: WPS433 - research/system10/tools, on the path after _tools()
    return L


def book_releases() -> list[dict]:
    if not BOOK_RELEASES.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(BOOK_RELEASES.glob("book_*.json"))]


def book_pbo(sid: str | None = None) -> dict:
    """CSCV PBO (overfit.cscv_pbo, 16 blocks of monthly returns 2020-2025) over the book
    ledger's distinct books on one signal set (default: the newest rows' set)."""
    from . import overfit as O
    L = _lab_mod()
    led, books = L.load_ledger(), L.ledger_books()
    if sid is None:
        rows = [json.loads(x) for x in L.LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()] \
            if L.LEDGER.is_file() else []
        sid = rows[-1]["signal_id"] if rows else None
    M = []
    for (s, bid), ys in led.items():
        if s != sid or "meta" in books[(s, bid)]:
            continue
        m = [ys.get(str(y), {}).get("monthly") for y in L.YEARS]
        if all(x and len(x) == 12 for x in m):
            M.append([v for x in m for v in x])
    doc = {"at": _now(), "signal_id": sid, "books": len(M), "pbo": None, "pbo_max": PBO_MAX}
    if len(M) >= 10:
        r = O.cscv_pbo(np.array(M).T, 16)
        doc.update({"pbo": r["pbo"], "cscv": r, "basis": "monthly Sharpe, 16 blocks, 2020-2025"})
    doc["refuses"] = bool(doc["pbo"] is not None and doc["pbo"] > PBO_MAX)
    tmp = BOOK_OVERFIT.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.replace(tmp, BOOK_OVERFIT)
    return doc


def incumbent(L, lab) -> tuple[dict, int | None]:
    """The book in force on these signals: newest book release for them, else the release's own."""
    for r in reversed(book_releases()):
        if r["signal_id"] == lab.sid:
            return r["book"], r["n"]
    return L.book_of(lab.rel["cfg"]), None


def proposals(L, current: dict) -> list[dict]:
    out = list(L.grid_books())
    for lever in L.AB_ORDER:
        if lever == "meta":            # paper cannot run the meta sizer: never a book release
            continue
        out += [L.book_of({**current, **v}) for v in L.AB[lever]]
    return out


def gate(L, lab, led: dict, cand: dict, inc: dict) -> dict:
    a, b = lab.run(inc, ledger=led, source="worker"), lab.run(cand, ledger=led, source="worker")
    sa, sb = L.summary(a), L.summary(b)
    da = [x for N in L.READ_YEARS for x in lab.book(N, inc)["daily"]]
    db = [x for N in L.READ_YEARS for x in lab.book(N, cand)["daily"]]
    pb = L.paired(da, db)
    pbo = book_pbo(lab.sid)
    checks = {"gain": round(sb["law"] - sa["law"], 4) >= GAIN_MIN, "bootstrap": pb["p_better"] >= L.WIN_P,
              "max_dd": sb["max_dd"] <= sa["max_dd"], "pbo": not pbo["refuses"]}
    return {"incumbent": sa, "candidate": sb, "gain": round(sb["law"] - sa["law"], 4), "paired": pb,
            "pbo": pbo["pbo"], "checks": checks, "passes": all(checks.values())}


def publish(lab, book: dict, g: dict, choice: dict) -> dict:
    BOOK_RELEASES.mkdir(parents=True, exist_ok=True)
    n = len(book_releases()) + 1
    L = _lab_mod()
    row = {"n": n, "name": f"book_{n:04d}", "at": _now(), "signal_release": lab.rel["n"],
           "signal_release_id": lab.rel["id"], "signal_id": lab.sid, "id": L.book_id(book), "book": book,
           "law_2022_2025": g["candidate"]["law"], "gain": g["gain"], "gate": g, "choice": choice}
    (BOOK_RELEASES / f"book_{n:04d}.json").write_text(json.dumps(row, indent=1, default=float), encoding="utf-8")
    S.add_event("release", f"book release {n} on signal release {lab.rel['n']}: {book} "
                           f"(law +{g['gain']:.4f} over the incumbent, P {g['paired']['p_better']:.2f})")
    return row


def one_pass(L, lab, log=print) -> tuple[dict | None, int]:
    """One batch of proposals, then the choice and the gate. -> (book release or None, books run)."""
    led = L.load_ledger()
    books = L.ledger_books()
    inc, inc_n = incumbent(L, lab)
    cands = {bid: {int(y): v for y, v in ys.items()} for (sid, bid), ys in led.items()
             if sid == lab.sid and "meta" not in books[(sid, bid)]}
    cur = books[(lab.sid, L.choose(cands, 2026)[0])] if cands else inc
    todo = [b for b in proposals(L, cur)
            if not all(str(N) in led.get((lab.sid, L.book_id(b)), {}) for N in L.YEARS)][:BATCH]
    for b in todo:
        lab.run(b, ledger=led, source="worker")
    books = {**L.ledger_books(), **{(lab.sid, L.book_id(b)): L.book_of(b) for b in todo}}
    cands = {bid: {int(y): v for y, v in ys.items()} for (sid, bid), ys in led.items()
             if sid == lab.sid and "meta" not in books[(sid, bid)]}
    pick, info = L.choose(cands, 2026)
    cand = books[(lab.sid, pick)]
    log(f"[{_now()}] book worker: {len(todo)} books run, {len(cands)} on the ledger; choice {cand} "
        f"(law <=2025 {info['past_law']:+.4f}); incumbent {'book ' + str(inc_n) if inc_n else 'release book'} {inc}")
    if L.book_id(cand) == L.book_id(inc):
        return None, len(todo)
    g = gate(L, lab, led, cand, inc)
    log(f"  gate: gain {g['gain']:+.4f}, P(better) {g['paired']['p_better']:.2f}, PBO {g['pbo']}, {g['checks']}")
    if not g["passes"]:
        return None, len(todo)
    return publish(lab, cand, g, {**info, "nested": {str(N): p["id"] for N, p in L.nested_from(cands).items()}}), len(todo)


def main() -> int:
    ap = argparse.ArgumentParser(description="S10 book worker (book levers on frozen signals)")
    ap.add_argument("--hours", type=float, default=6.0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--pbo", action="store_true", help="write rnd/book_overfit.json and exit")
    a = ap.parse_args()
    if a.pbo:
        print(json.dumps(book_pbo(), indent=1))
        return 0
    L = _lab_mod()
    import book_inputs as BI   # noqa: WPS433
    started = time.time()
    while time.time() - started < a.hours * 3600 and not S.STOP.exists():
        rel = BI.release("current")
        if BI.find(rel["cfg"]) is None:
            BI.dump(rel["n"], a.device)          # waits for free RAM itself
        lab = L.Lab(rel["n"])
        r, ran = one_pass(L, lab)
        if r:
            print(f"[{_now()}] BOOK RELEASE {r['n']}: {r['book']}", flush=True)
        if a.once:
            break
        if r is None and not ran:     # nothing left to book: wait for a new signal release
            time.sleep(600)
    return 0


if __name__ == "__main__":
    sys.exit(main())
