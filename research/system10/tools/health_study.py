"""The market-health overlay on the pinned release, year by year (operator, 2026-10-14).

Two stages, so the expensive one runs once:

  dump   builds the World (bars through today), fits release 31's walk-forward signals
         for every year in YEARS exactly as `search.evaluate` / `forward_reading` do, and
         saves the book's inputs to research/system10/rnd/health_inputs.npz (gitignored).
  study  books the release from those inputs with and without the health guard
         (block-only, block+flatten) over a small grid of thresholds. Thresholds are
         chosen on years <= 2025 only; 2026 is read once, for the chosen settings.

Run from the repo root:
    R=$(pwd -W); PYTHONPATH="$R/trading-system;$R/trading-system/systems" \
        python research/system10/tools/health_study.py dump
    ... python research/system10/tools/health_study.py study
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for sub in ("trading-system", "trading-system/systems", "research/system10/tools"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

INPUTS = REPO / "research/system10/rnd/health_inputs.npz"
PAPER_CFG = REPO / "research/system10/paper/config.json"
YEARS = (2020, 2021, 2022, 2023, 2024, 2025, 2026)
CHOOSE_YEARS = (2020, 2021, 2022, 2023, 2024, 2025)


def release_cfg() -> dict:
    return json.loads(PAPER_CFG.read_text(encoding="utf-8"))["cfg"]


# ---------------------------------------------------------------------------- dump

def dump(device: str) -> None:
    from system010_conditioned_rl import search as S
    cfg = release_cfg()
    t0 = time.time()
    print("building the World (bars through today)...", flush=True)
    world = S.World(include_sealed=True)
    world.full()
    world.x = None                      # only the full picture is read from here on
    print(f"world ready in {(time.time() - t0) / 60:.1f} min", flush=True)
    g, regime = S.gate(world, cfg)
    size = S.sizing(world, cfg)
    out: dict = {}
    for s, d in world.per.items():
        out[f"{s}|ns"] = d["ns"]
        out[f"{s}|close"] = d["close"]
        out[f"{s}|prob"] = d["prob"]
        out[f"{s}|year"] = d["year"]
        out[f"{s}|size"] = size[s] if size is not None else np.ones(len(d["ns"]))
    for N in YEARS:
        t1 = time.time()
        share, masks, keep = S.signals(world, cfg, N, g, regime, device)
        st = S.strength(world, cfg, N, g, regime, device)
        for s in world.per:
            out[f"{s}|enter{N}"] = masks[s].astype(bool)
            out[f"{s}|keep{N}"] = keep[s].astype(bool)
            out[f"{s}|strength{N}"] = st[s]
        r = world.book(masks, N, cfg["horizon"], size, keep, S.EXIT_MIN_HOLD, strength=st, **S.mm_kwargs(cfg))
        print(f"{N}: share {share}  return {r['return']:+.2%}  dd {r['max_dd']:.1%}  trades {r['trades']}"
              f"  [{(time.time() - t1) / 60:.1f} min]", flush=True)
        S._SIGNALS.clear()
    meta = {"band": world.band, "risk": world.risk, "cfg": cfg, "years": list(YEARS),
            "symbols": list(world.per), "exit_min_hold": S.EXIT_MIN_HOLD}
    out["meta"] = np.array(json.dumps(meta, default=float))
    INPUTS.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(INPUTS, **out)
    print(f"written {INPUTS} in {(time.time() - t0) / 60:.1f} min", flush=True)


def load_inputs() -> tuple[dict, dict]:
    z = np.load(INPUTS)
    meta = json.loads(str(z["meta"]))
    per: dict = {}
    for k in z.files:
        if k == "meta":
            continue
        s, f = k.split("|")
        per.setdefault(s, {})[f] = z[k]
    return per, meta


# ---------------------------------------------------------------------------- study

EPISODES = {   # label: (first day, last day) - the drops the operator named, and the other big ones
    "2020-03 COVID": ("2020-03-08", "2020-03-20"),
    "2021-05 crash": ("2021-05-10", "2021-05-26"),
    "2022-05 LUNA": ("2022-05-05", "2022-05-15"),
    "2022-06 3AC/Celsius": ("2022-06-10", "2022-06-20"),
    "2022-11 FTX": ("2022-11-06", "2022-11-14"),
    "2023-06 SEC suits": ("2023-06-05", "2023-06-15"),
    "2023-08-17 flush": ("2023-08-14", "2023-08-22"),
    "2024-08-05 carry unwind": ("2024-08-01", "2024-08-09"),
    "2025-02-03 tariffs": ("2025-01-31", "2025-02-07"),
    "2025-10-10 liquidations": ("2025-10-08", "2025-10-15"),
}
EPISODES_2026: dict = {}     # filled only for the single 2026 read

_CTX: dict = {}


def _ctx() -> dict:
    if not _CTX:
        from system010_conditioned_rl import health as H
        per, meta = load_inputs()
        series = {s: (d["ns"], d["close"]) for s, d in per.items()}
        _CTX.update(per=per, meta=meta, hist=H.history(series), H=H)
    return _CTX


def book(N: int, setting: dict | None, detail: bool = False) -> dict:
    import conditions as C
    from system010_conditioned_rl import search as S
    c = _ctx()
    per, meta, H = c["per"], c["meta"], c["H"]
    cfg = meta["cfg"]
    pN = {s: {"ns": d["ns"], "close": d["close"], "prob": d["prob"], "year": d["year"]} for s, d in per.items()}
    pick = lambda f: {s: d[f"{f}{N}"] for s, d in per.items()}  # noqa: E731
    size = {s: d["size"] for s, d in per.items()} if cfg.get("size_down", 1.0) < 1.0 else None
    guard = H.Guard(c["hist"], **setting) if setting else None
    old = C.HORIZON
    C.HORIZON = cfg["horizon"]
    try:
        r = C.book_year(pN, pick("enter"), N, meta["band"], meta["risk"], keep=pick("keep"), size=size,
                        keep_min_hold=meta["exit_min_hold"], strength=pick("strength"),
                        **S.mm_kwargs(cfg), guard=guard, detail=detail)
    finally:
        C.HORIZON = old
    r.pop("daily", None)
    r.pop("trade_log", None)
    r["halts"] = len([x for x in guard.log if x[1] in ("halt", "block")]) if guard else 0
    r["guard_log"] = [(str(np.datetime64(int(t), "ns"))[:16], what, round(sc, 1)) for t, what, sc in guard.log] if guard else []
    return r


def _job(args):
    name, setting, N = args
    r = book(N, setting)
    return name, N, {k: r[k] for k in ("return", "max_dd", "trades", "win_rate", "halts")}


def settings() -> dict:
    out = {"baseline": None}
    for book_on in (False, True):
        for gap in (10.0, 20.0):
            for th in (10.0, 15.0, 20.0, 25.0, 30.0):
                tag = f"{th:g}/gap{gap:g}{'/book' if book_on else ''}"
                out[f"block<{tag}"] = {"block_below": th, "resume_gap": gap, "use_book": book_on}
                out[f"flatten<{tag}"] = {"halt_below": th, "resume_gap": gap, "use_book": book_on}
    # Round 2, after round 1 showed the release BUYS the crash bar (its best trades): guards
    # that let the first capitulation bar through and react only to a sustained turn.
    for th in (20.0, 30.0, 40.0, 50.0):
        for fam, extra in (("day", {"smooth": 96}), ("slow", {"smooth": 96, "exclude": ("crash", "vol")})):
            out[f"block<{th:g}/{fam}"] = {"block_below": th, "resume_gap": 10.0, **extra}
            out[f"flatten<{th:g}/{fam}"] = {"halt_below": th, "resume_gap": 10.0, **extra}
    # Round 3: the book's own losing streak (trades closed in the last BOOK_DAYS only).
    for th in (10.0, 25.0, 40.0, 50.0, 60.0, 70.0):
        for gap in (20.0, 10.0):
            tag = "" if gap == 20.0 else f"/gap{gap:g}"
            out[f"block<{th:g}/book-only{tag}"] = {"block_below": th, "resume_gap": gap, "book_only": True}
            out[f"flatten<{th:g}/book-only{tag}"] = {"halt_below": th, "resume_gap": gap, "book_only": True}
    return out


def summarise(rows: dict, years) -> dict:
    rets = [rows[y]["return"] for y in years]
    dd = max(rows[y]["max_dd"] for y in years)
    cagr = float(np.prod([1 + r for r in rets]) ** (1 / len(rets)) - 1)
    return {"cagr": round(cagr, 4), "worst_year": round(min(rets), 4), "max_dd": round(dd, 4),
            "q": round(float(np.sign(cagr) * cagr * cagr / max(dd, 0.02)), 4), "dd_ok": bool(dd <= 0.25)}


def study(workers: int) -> None:
    from multiprocessing import Pool
    out_path = REPO / "research/system10/rnd/health_study.json"
    sets = settings()
    jobs = [(k, v, N) for k, v in sets.items() for N in CHOOSE_YEARS]
    res: dict = {k: {} for k in sets}
    t0 = time.time()
    with Pool(workers) as pool:
        for i, (name, N, r) in enumerate(pool.imap_unordered(_job, jobs), 1):
            res[name][N] = r
            if i % 20 == 0:
                print(f"  {i}/{len(jobs)} books [{(time.time() - t0) / 60:.1f} min]", flush=True)
    summ = {k: summarise(v, CHOOSE_YEARS) for k, v in res.items()}
    ok = {k: s for k, s in summ.items() if s["dd_ok"]} or summ
    max_profit = max(ok, key=lambda k: ok[k]["cagr"])
    optimal = max(ok, key=lambda k: ok[k]["q"])
    # the release's own judged years, for reference
    summ4 = {k: summarise(v, (2022, 2023, 2024, 2025)) for k, v in res.items()}
    ok4 = {k: s for k, s in summ4.items() if s["dd_ok"]} or summ4
    mp4, op4 = max(ok4, key=lambda k: ok4[k]["cagr"]), max(ok4, key=lambda k: ok4[k]["q"])
    print(f"2022-2025 only: max profit {mp4} {summ4[mp4]}   optimal {op4} {summ4[op4]}")
    print(f"\n{'setting':<28}" + "".join(f"{y:>16}" for y in CHOOSE_YEARS) + "   cagr  maxdd     q")
    for k in sorted(summ, key=lambda k: -summ[k]["q"]):
        print(f"{k:<28}" + "".join(f"  {res[k][y]['return']:+7.1%}/{res[k][y]['max_dd']:4.1%}" for y in CHOOSE_YEARS)
              + f"  {summ[k]['cagr']:+.1%} {summ[k]['max_dd']:.1%} {summ[k]['q']:.3f}")
    print(f"\nmax profit: {max_profit}   optimal: {optimal}", flush=True)
    doc = {"years": list(CHOOSE_YEARS), "per_year": res, "summary": summ,
           "max_profit": max_profit, "optimal": optimal, "settings": sets,
           "summary_2022_2025": summ4, "max_profit_2022_2025": mp4, "optimal_2022_2025": op4}
    out_path.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    print(f"written {out_path}", flush=True)


def forward(names: list[str]) -> None:
    """The one 2026 read, for the settings already chosen on <= 2025."""
    sets = settings()
    for k in ["baseline"] + names:
        r = book(2026, sets[k])
        print(f"2026 {k:<28} {r['return']:+.2%}  dd {r['max_dd']:.1%}  trades {r['trades']}  halts {r['halts']}",
              flush=True)
        if r["guard_log"]:
            print("    " + ", ".join(f"{t} {w}" for t, w, _ in r["guard_log"]), flush=True)


def episodes(names: list[str], include_2026: bool = False) -> None:
    """Per crash: the score's low and when it first crossed 25 / 15, BTC's peak-to-trough,
    and the book's change over the window with and without each setting."""
    c = _ctx()
    h, per = c["hist"], c["per"]
    sets = settings()
    eps = dict(EPISODES)
    if include_2026:
        eps.update(EPISODES_2026)
    curves: dict = {}
    for k in ["baseline"] + names:
        for N in sorted({int(a[:4]) for a, _ in eps.values()}):
            r = book(N, sets[k], detail=True)
            ec = np.array(r["equity_curve"], dtype=float)
            curves[(k, N)] = (ec[:, 0].astype(np.int64), ec[:, 1])
    btc = per["BTCUSDT"]
    fmt = lambda t: str(np.datetime64(int(t), "ns"))[:16]  # noqa: E731
    for label, (a, b) in eps.items():
        lo = np.datetime64(a, "ns").astype(np.int64)
        hi = (np.datetime64(b, "ns") + np.timedelta64(1, "D")).astype(np.int64)
        m = (h["ns"] >= lo) & (h["ns"] < hi)
        sc, ns = h["score"][m], h["ns"][m]
        bm = (btc["ns"] >= lo) & (btc["ns"] < hi)
        bc, bns = btc["close"][bm], btc["ns"][bm]
        pk = int(np.argmax(bc))
        tr = pk + int(np.argmin(bc[pk:]))
        first = {th: (fmt(ns[np.argmax(sc < th)]) if (sc < th).any() else "-") for th in (25, 15)}
        print(f"{label:<26} score min {sc.min():4.0f} at {fmt(ns[np.argmin(sc)])}; first <25 {first[25]}, "
              f"<15 {first[15]}; BTC {bc[tr] / bc[pk] - 1:+.1%} {fmt(bns[pk])} -> {fmt(bns[tr])}")
        N = int(a[:4])
        for k in ["baseline"] + names:
            t, e = curves[(k, N)]
            w = (t >= lo) & (t < hi)
            if w.sum() < 2:
                continue
            ew = e[w]
            mdd = float((1 - ew / np.maximum.accumulate(ew)).max())
            print(f"    {k:<28} book {ew[-1] / ew[0] - 1:+6.2%} over the window, drawdown inside it {mdd:.1%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=("dump", "study", "forward", "episodes"))
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--settings", nargs="*", default=[])
    ap.add_argument("--with-2026", action="store_true")
    a = ap.parse_args()
    if a.stage == "dump":
        dump(a.device)
    elif a.stage == "study":
        study(a.workers)
    elif a.stage == "forward":
        forward(a.settings)
    else:
        episodes(a.settings, a.with_2026)
