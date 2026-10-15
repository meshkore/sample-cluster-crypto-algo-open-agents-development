"""Book-only lab on frozen signals (book audit 2026-10-15, phases 0-2).

The signal layer of a release is read from book_inputs (cached walk-forward signals); only
`conditions.book_year` runs, ~2.5 s per book-year. Every book run on 2020-2025 is one row of
rnd/book_trials.jsonl (the book ledger: no 2026 in it, ever).

    baseline   releases 31, 43, 43 + stop 0.12 / dd_scale 0.35, and the champion; checks the
               ledger rows to the 4th decimal -> rnd/book_baseline.json
    grid       the book grid (GRID) on the champion's signals -> ledger
    nested     for N in 2022-2025 the book chosen on years < N by search.law, read on N
               -> rnd/book_nested.json
    ab LEVER   phase 2 A/B of one lever on the nested incumbent -> rnd/book_ab.json
    forward    the one 2026 read of the adopted book (never used to choose)

    R=$(pwd -W); PYTHONPATH="$R/trading-system;$R/trading-system/systems;$R/research/system10/tools" \
        python research/system10/tools/book_lab.py baseline
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for sub in ("trading-system", "trading-system/systems", "research/system10/tools"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

import book_inputs as BI  # noqa: E402

RND = REPO / "research/system10/rnd"
LEDGER = RND / "book_trials.jsonl"
YEARS = (2020, 2021, 2022, 2023, 2024, 2025)
READ_YEARS = (2022, 2023, 2024, 2025)
DD_CAP, MIN_TRADES = 0.25, 50
TARGET = 0.20
BLOCK, DRAWS = 21, 5000
WIN_P = 0.90          # a year is won when the paired bootstrap puts B above A in >= 90% of draws

# The book levers search.py draws (book-only part of MM_KEYS), on a grid that holds every
# release book of 2026-10-15 (31, 34, 43, 43 restored).
GRID = {"slots": (3, 5, 8), "stop": (None, 0.12), "dd_scale": (None, 0.25, 0.35),
        "size_signal": (0.01, 0.02), "scale_in": (False, True),
        "mom": (None, (5, 90), (7, 90)), "take_profit": (None, 0.2)}
# veto and vol_target are in search.MM_KEYS but act on the cached masks / sizes: signal side here.
BOOK_KEYS = ("slots", "stop", "dd_scale", "size_signal", "scale_in", "book_stop",
             "corr_cap", "corr_rho", "eq_filter", "eq_cut", "min_edge", "take_profit", "breakeven",
             "mom_rank", "mom_days", "mom_in", "mom_out", "add_above", "trim_below", "port_vol",
             "size_kelly", "atr_trail", "meta")

# Phase 2, in the audit's order. Each: values B may take (chosen on years < N among them).
AB = {
    "port_vol": [{"port_vol": v} for v in (0.20, 0.25, 0.30, 0.40)],
    "size_kelly": [{"size_kelly": v} for v in (0.25, 0.35, 0.5)],
    "thresholds": [{"scale_in": True, "add_above": a, "trim_below": b}
                   for a in (0.003, 0.006, 0.01) for b in (-0.003, 0.0, 0.003)],
    "atr_trail": [{"atr_trail": k} for k in (2.0, 3.0, 4.0)],
    "meta": [{"meta": c} for c in ((0.5, 1.5), (0.25, 2.0))],
    "corr_cap": [{"corr_cap": n, "corr_rho": r} for n, r in ((3, 0.9), (2, 0.9), (3, 0.8), (2, 0.8), (1, 0.8))],
}
AB_ORDER = tuple(AB)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def book_of(cfg: dict) -> dict:
    """The book part of a cfg, None/False/defaults dropped so one book has one id."""
    out = {k: cfg[k] for k in BOOK_KEYS if k in cfg and cfg[k] is not None}
    if out.get("scale_in") is False:
        out.pop("scale_in")
    return out


def book_id(book: dict) -> str:
    from system010_conditioned_rl import search as S
    return S.cfg_id(book_of(book))


def grid_books() -> list[dict]:
    keys = list(GRID)
    out = []
    for vals in itertools.product(*(GRID[k] for k in keys)):
        b = dict(zip(keys, vals))
        mom = b.pop("mom")
        if mom:
            b["mom_rank"], b["mom_days"] = mom
        out.append(book_of(b))
    return out


# ---------------------------------------------------------------------------- the lab

class Lab:
    def __init__(self, release="current"):
        self.per, self.meta, self.rel = BI.load(release)
        self.sid = self.meta["signal_id"]
        self.signal_cfg = {k: v for k, v in self.meta["cfg"].items() if k not in BOOK_KEYS}
        self.pN = {s: {k: d[k] for k in ("ns", "close", "prob", "year")} for s, d in self.per.items()}
        self._days: dict = {}
        self._meta_scale: dict = {}

    def cfg(self, book: dict) -> dict:
        return {**self.signal_cfg, **book_of(book)}

    def book(self, N: int, book: dict, detail: bool = False, **extra) -> dict:
        import conditions as C
        from system010_conditioned_rl import search as S
        cfg = self.cfg(book)
        per = self.per
        pick = lambda f: {s: d[f"{f}{N}"] for s, d in per.items()}  # noqa: E731
        size = ({s: d["size"] for s, d in per.items()}
                if (cfg.get("size_down", 1.0) < 1.0 or cfg.get("vol_target")) else None)
        keep = pick("keep") if (self.meta.get("has_keep", cfg.get("exit") == "learned")) else None
        if cfg.get("meta"):
            extra = {**extra, "meta_scale": self.meta_scale(N, tuple(cfg["meta"]))}
        old = C.HORIZON
        C.HORIZON = cfg["horizon"]
        try:
            return C.book_year(self.pN, pick("enter"), N, self.meta["band"], self.meta["risk"], keep=keep,
                               size=size, keep_min_hold=self.meta["exit_min_hold"], strength=pick("strength"),
                               detail=detail, **S.mm_kwargs(cfg), **extra)
        finally:
            C.HORIZON = old

    def days(self, N: int) -> np.ndarray:
        if N not in self._days:
            ns = np.concatenate([d["ns"][d["year"] == N] for d in self.per.values()])
            self._days[N] = np.unique(ns.astype("datetime64[ns]").astype("datetime64[D]"))
        return self._days[N]

    def monthly(self, N: int, daily: list) -> list | None:
        days = self.days(N)
        if len(days) != len(daily):
            return None
        m = days.astype("datetime64[M]").astype(int) % 12
        g = np.log1p(np.asarray(daily, dtype=float))
        return [round(float(np.expm1(g[m == k].sum())), 5) for k in range(12)]

    def row(self, N: int, book: dict) -> dict:
        r = self.book(N, book)
        return {"return": r["return"], "max_dd": r["max_dd"], "trades": r["trades"],
                "win_rate": r["win_rate"], "q": r["q"], "monthly": self.monthly(N, r["daily"])}

    def run(self, book: dict, years=YEARS, source: str = "grid", ledger: dict | None = None) -> dict:
        """Per-year rows for a book; read from / appended to the ledger (2020-2025 only)."""
        bid = book_id(book)
        have = (ledger or {}).get((self.sid, bid), {})
        miss = [N for N in years if str(N) not in have]
        if miss:
            new = {str(N): self.row(N, book) for N in miss}
            have = {**have, **new}
            if all(int(N) <= 2025 for N in miss):
                append({"at": now(), "signal_id": self.sid, "release": self.rel["n"], "id": bid,
                        "book": book_of(book), "source": source, "years": new})
            if ledger is not None:
                ledger[(self.sid, bid)] = have
        return {int(k): v for k, v in have.items()}

    # ------------------------------------------------------------- meta-labelling sizer
    def meta_scale(self, N: int, clip: tuple) -> dict:
        key = (N, clip)
        if key not in self._meta_scale:
            from book_meta import scale_for_year
            self._meta_scale[key] = scale_for_year(self, N, clip)
        return self._meta_scale[key]


def append(row: dict) -> None:
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=float) + "\n")


def load_ledger() -> dict:
    """{(signal_id, book id): {year: row}}, rows merged (later rows add years)."""
    out: dict = {}
    if LEDGER.is_file():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out.setdefault((r["signal_id"], r["id"]), {}).update(r["years"])
    return out


def ledger_books() -> dict:
    out: dict = {}
    if LEDGER.is_file():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[(r["signal_id"], r["id"])] = r["book"]
    return out


# ---------------------------------------------------------------------------- statistics

def law(rows: dict) -> float:
    from system010_conditioned_rl import search as S
    return S.law({str(k): v for k, v in rows.items()}, max(float(v["max_dd"]) for v in rows.values()))


def summary(rows: dict, years=READ_YEARS) -> dict:
    rows = {y: rows[y] for y in years if y in rows}
    rets = [float(rows[y]["return"]) for y in rows]
    cagr = float(np.prod([1 + r for r in rets]) ** (1 / len(rets)) - 1)
    return {"years": {str(y): [round(float(rows[y]["return"]), 4), round(float(rows[y]["max_dd"]), 4),
                               int(rows[y]["trades"])] for y in rows},
            "law": law(rows), "cagr": round(cagr, 4), "worst_year": round(min(rets), 4),
            "max_dd": round(max(float(v["max_dd"]) for v in rows.values()), 4)}


def _paths(n: int, days: int = 365, draws: int = DRAWS, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    blocks = -(-days // BLOCK)
    starts = rng.integers(0, n - BLOCK, size=(draws, blocks))
    return (starts[..., None] + np.arange(BLOCK)).reshape(draws, -1)[:, :days]


def _ret_dd(paths: np.ndarray):
    eq = np.cumprod(1 + paths, axis=1)
    eq = np.concatenate([np.ones((len(eq), 1)), eq], axis=1)
    dd = (1 - eq / np.maximum.accumulate(eq, axis=1)).max(axis=1)
    return eq[:, -1] - 1, dd


def boot(daily, target: float = TARGET) -> dict:
    """21-day block bootstrap of 365-day years from the daily returns."""
    d = np.asarray(daily, dtype=float)
    r, dd = _ret_dd(d[_paths(len(d))])
    return {f"p_year_ge_{int(target * 100)}": round(float((r >= target).mean()), 4),
            "p05": round(float(np.percentile(r, 5)), 4), "median": round(float(np.median(r)), 4),
            "p95_dd": round(float(np.percentile(dd, 95)), 4)}


def paired(da, db) -> dict:
    """Paired block bootstrap of one year: the single-year law of B minus A on the same days."""
    a, b = np.asarray(da, dtype=float), np.asarray(db, dtype=float)
    idx = _paths(len(a))
    ra, ddA = _ret_dd(a[idx])
    rb, ddB = _ret_dd(b[idx])
    law1 = lambda r, dd: 0.5 * r + 0.5 * np.minimum(r, 0.5) - 0.25 * dd  # noqa: E731  (search.law, one year)
    diff = law1(rb, ddB) - law1(ra, ddA)
    return {"p_better": round(float((diff > 0).mean()), 4), "p10": round(float(np.percentile(diff, 10)), 4),
            "median": round(float(np.median(diff)), 4)}


# ---------------------------------------------------------------------------- nested choice

def eligible(rows: dict, years) -> bool:
    return all(float(rows[y]["max_dd"]) <= DD_CAP and int(rows[y]["trades"]) >= MIN_TRADES for y in years)


def choose(cands: dict, N: int) -> tuple[str, dict]:
    """cands: {id: {year: row}}. The law on years < N among those eligible there (DD cap,
    trades); if none is, the law alone (recorded as cap_met False)."""
    past = [y for y in YEARS if y < N]
    have = {k: v for k, v in cands.items() if all(y in v for y in past)}
    pool = {k: v for k, v in have.items() if eligible(v, past)}
    use = pool or have
    key = lambda k: (law({y: use[k][y] for y in past}), -max(float(use[k][y]["max_dd"]) for y in past), k)  # noqa: E731
    best = max(use, key=key)
    return best, {"past_law": key(best)[0], "cap_met": bool(pool), "candidates": len(use)}


def nested_curve(picks: dict) -> dict:
    """picks: {N: {"rows": {year: row}}} -> summary of the read years."""
    rows = {N: p["rows"][N] for N, p in picks.items()}
    return summary(rows, sorted(rows))


# ---------------------------------------------------------------------------- stages

def baselines(lab: Lab) -> dict:
    from system010_conditioned_rl import search as S
    rels = {r["n"]: r for r in S.releases()}
    out = {"release 31": rels[31]["cfg"], "release 43": rels[43]["cfg"],
           "release 43 + stop 0.12 + dd_scale 0.35": {**rels[43]["cfg"], "stop": 0.12, "dd_scale": 0.35},
           f"champion (release {lab.rel['n']})": lab.rel["cfg"]}
    return {k: book_of(v) for k, v in out.items()}


def stage_baseline(lab: Lab) -> dict:
    from system010_conditioned_rl import search as S
    led = load_ledger()
    trials = {r["id"]: r for r in S.ledger()}
    rels = {r["id"]: r for r in S.releases()}
    doc = {"at": now(), "signal_id": lab.sid, "books": {}}
    for name, book in baselines(lab).items():
        cfg = lab.cfg(book)
        rows = lab.run(book, source="baseline", ledger=led)
        daily = []
        for N in READ_YEARS:
            daily += lab.book(N, book)["daily"]
        cid = S.cfg_id(cfg)
        ref = (rels.get(cid) or trials.get(cid) or {}).get("years")
        check = None
        if ref:
            check = all(abs(float(ref[str(N)]["return"]) - rows[N]["return"]) < 5e-5
                        and abs(float(ref[str(N)]["max_dd"]) - rows[N]["max_dd"]) < 5e-5
                        and int(ref[str(N)]["trades"]) == rows[N]["trades"] for N in READ_YEARS)
        doc["books"][name] = {"cfg_id": cid, "book": book, "ledger_row": bool(ref), "reproduces": check,
                              "2022_2025": summary(rows), "2020_2025": summary(rows, YEARS),
                              "bootstrap_2022_2025": boot(daily)}
        s = doc["books"][name]["2022_2025"]
        print(f"{name:<42} law {s['law']:+.4f} cagr {s['cagr']:+.1%} worst {s['worst_year']:+.1%} "
              f"dd {s['max_dd']:.1%} | 2020-25 dd {doc['books'][name]['2020_2025']['max_dd']:.1%} "
              f"| reproduces ledger: {check}", flush=True)
    (RND / "book_baseline.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


def _grid_job(book):
    lab = _W["lab"]
    return book, {str(N): lab.row(N, book) for N in YEARS}


_W: dict = {}


def _init(release):
    _W["lab"] = Lab(release)


def stage_grid(lab: Lab, workers: int) -> None:
    led = load_ledger()
    todo = [b for b in grid_books() if (lab.sid, book_id(b)) not in led
            or not all(str(N) in led[(lab.sid, book_id(b))] for N in YEARS)]
    print(f"grid: {len(todo)} of {len(grid_books())} books to run", flush=True)
    t0 = time.time()
    if workers <= 1:
        it = map(lambda b: (b, {str(N): lab.row(N, b) for N in YEARS}), todo)
        pool = None
    else:
        from multiprocessing import Pool
        pool = Pool(workers, initializer=_init, initargs=(lab.rel["n"],))
        it = pool.imap_unordered(_grid_job, todo)
    for i, (b, years) in enumerate(it, 1):
        append({"at": now(), "signal_id": lab.sid, "release": lab.rel["n"], "id": book_id(b),
                "book": book_of(b), "source": "grid", "years": years})
        if i % 10 == 0:
            print(f"  {i}/{len(todo)} [{(time.time() - t0) / 60:.1f} min]", flush=True)
    if pool:
        pool.close()


def nested_from(cands: dict) -> dict:
    picks = {}
    for N in READ_YEARS:
        k, info = choose(cands, N)
        picks[N] = {"id": k, **info, "rows": cands[k]}
    return picks


def stage_nested(lab: Lab) -> dict:
    led = load_ledger()
    books = ledger_books()
    grid_ids = {book_id(b) for b in grid_books()}
    cands = {bid: {int(y): v for y, v in rows.items()} for (sid, bid), rows in led.items()
             if sid == lab.sid and bid in grid_ids}
    picks = nested_from(cands)
    full = {k: v for k, v in cands.items() if all(y in v for y in READ_YEARS)}
    jm = max(full, key=lambda k: law({y: full[k][y] for y in READ_YEARS}))
    base = json.loads((RND / "book_baseline.json").read_text(encoding="utf-8"))
    doc = {"at": now(), "signal_id": lab.sid, "signal_release": lab.rel["n"],
           "note": "signals frozen; releases 31/34/43 share them, so one nested curve serves all",
           "grid": {k: [list(x) if isinstance(x, tuple) else x for x in v] for k, v in GRID.items()},
           "books_in_grid": len(cands),
           "picks": {str(N): {"book": books[(lab.sid, p["id"])], "id": p["id"], "past_law": p["past_law"],
                              "cap_met": p["cap_met"], "candidates": p["candidates"],
                              "read": [p["rows"][N]["return"], p["rows"][N]["max_dd"], p["rows"][N]["trades"]]}
                     for N, p in picks.items()},
           "nested": nested_curve(picks),
           "joint_max_diagnostic": {"book": books[(lab.sid, jm)], **summary(full[jm])},
           "baselines": {k: v["2022_2025"] for k, v in base["books"].items()}}
    (RND / "book_nested.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    n = doc["nested"]
    print(f"nested: {n['years']} law {n['law']:+.4f} cagr {n['cagr']:+.1%} worst {n['worst_year']:+.1%} dd {n['max_dd']:.1%}")
    for N, p in doc["picks"].items():
        print(f"  {N}: {p['book']} (past law {p['past_law']:+.4f}, cap met {p['cap_met']})")
    j = doc["joint_max_diagnostic"]
    print(f"joint max: law {j['law']:+.4f} cagr {j['cagr']:+.1%} worst {j['worst_year']:+.1%} dd {j['max_dd']:.1%} {j['book']}")
    return doc


AB_FILE = RND / "book_ab.json"


def stage_ab(lab: Lab, lever: str) -> dict:
    """B = the incumbent's book for N plus the lever, its value chosen on years < N among
    AB[lever]; A = the incumbent. Adopt iff B wins >= 3 of 4 read years beyond the paired
    bootstrap band and B's max yearly DD over the read years is not above A's."""
    nest = json.loads((RND / "book_nested.json").read_text(encoding="utf-8"))
    state = json.loads(AB_FILE.read_text(encoding="utf-8")) if AB_FILE.is_file() else {}
    inc = state.get("incumbent") or {N: p["book"] for N, p in nest["picks"].items()}
    led = load_ledger()
    res = {"at": now(), "values": AB[lever], "years": {}}
    a_rows, b_rows, b_books = {}, {}, {}
    for N in READ_YEARS:
        a_book = inc[str(N)]
        a = lab.run(a_book, source="ab", ledger=led)
        cands = {}
        for v in AB[lever]:
            b = book_of({**a_book, **v})
            cands[book_id(b)] = (b, lab.run(b, source=f"ab:{lever}", ledger=led))
        k, info = choose({i: r for i, (b, r) in cands.items()}, N)
        b_book, b = cands[k]
        da, db = lab.book(N, a_book)["daily"], lab.book(N, b_book)["daily"]
        pb = paired(da, db)
        win = pb["p_better"] >= WIN_P
        a_rows[N], b_rows[N], b_books[str(N)] = a[N], b[N], b_book
        res["years"][str(N)] = {"A": [a[N]["return"], a[N]["max_dd"]], "B": [b[N]["return"], b[N]["max_dd"]],
                                "B_book": b_book, "chosen_on_past": info, "paired": pb, "win": win}
        print(f"  {lever} {N}: A {a[N]['return']:+.1%}/{a[N]['max_dd']:.1%}  B {b[N]['return']:+.1%}/"
              f"{b[N]['max_dd']:.1%}  P(B>A) {pb['p_better']:.2f}  {'WIN' if win else '-'}  {b_book}", flush=True)
    sa, sb = summary(a_rows), summary(b_rows)
    wins = sum(v["win"] for v in res["years"].values())
    adopt = wins >= 3 and sb["max_dd"] <= sa["max_dd"]
    res.update({"A": sa, "B": sb, "wins": wins, "adopted": adopt})
    print(f"{lever}: A law {sa['law']:+.4f} cagr {sa['cagr']:+.1%} dd {sa['max_dd']:.1%} | B law {sb['law']:+.4f} "
          f"cagr {sb['cagr']:+.1%} dd {sb['max_dd']:.1%} | wins {wins}/4 -> {'ADOPTED' if adopt else 'closed'}")
    state.setdefault("levers", {})[lever] = res
    if adopt:
        state["incumbent"] = b_books
        state.setdefault("adopted", []).append(lever)
    else:
        state["incumbent"] = inc
    AB_FILE.write_text(json.dumps(state, indent=1, default=float), encoding="utf-8")
    return res


def stage_forward(lab: Lab, book: dict, base: dict) -> dict:
    """The one 2026 read: the adopted book against the book it replaced. Never feeds back."""
    out = {}
    for name, b in (("before", base), ("adopted", book)):
        r = lab.book(2026, b)
        out[name] = {"return": r["return"], "max_dd": r["max_dd"], "trades": r["trades"], "book": book_of(b)}
        print(f"2026 {name:<8} {r['return']:+.2%} dd {r['max_dd']:.1%} trades {r['trades']}  {book_of(b)}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=("baseline", "grid", "nested", "ab", "forward"))
    ap.add_argument("lever", nargs="?")
    ap.add_argument("--release", default="current")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--book", default=None, help="forward: JSON book")
    ap.add_argument("--base", default=None, help="forward: JSON book it replaced")
    a = ap.parse_args()
    lab = Lab(a.release)
    if a.stage == "baseline":
        stage_baseline(lab)
    elif a.stage == "grid":
        stage_grid(lab, a.workers)
    elif a.stage == "nested":
        stage_nested(lab)
    elif a.stage == "ab":
        for lv in ([a.lever] if a.lever else AB_ORDER):
            stage_ab(lab, lv)
    else:
        stage_forward(lab, json.loads(a.book), json.loads(a.base))
