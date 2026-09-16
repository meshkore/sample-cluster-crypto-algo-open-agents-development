"""Build the trade ledger for the SHIPPING champion and print it, 2026 first.

Run from the repository root:

    PYTHONPATH=trading-system python research/system06/tools/attribution_run.py

Three things happen, in this order, because the order is the honesty:

1. **Reproduction.** The sealed 2026 year is re-run from the champion's own artefacts
   and checked against the number on record (+2.08%, 61 trades). A ledger that cannot
   reproduce the book it claims to describe is describing something else, and every
   conclusion drawn from it would be about a phantom.
2. **The ledger.** Every year is re-run with per-trade detail and reconciled against
   the opportunity set - the same zigzag legs the labeller trains on, charged the real
   round trip. Four kinds of row, no leftovers: won, lost, unforced, missed.
3. **The rules.** Two shallow trees fitted on RESEARCH YEARS ONLY: one separating the
   trades that won from the trades that lost, one separating the legs we caught from
   the legs we let go. 2026 rows sit in the table and never in the fit.

The output is a diagnosis, not an adoption. Anything it suggests goes through the
ordinary paired A/B with reseeds like every other idea in this project.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from system006_oracle_net_15m import attribution, launch, universe
from system006_oracle_net_15m.dataset import Dataset

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"
YEARS = list(range(2018, 2027))
SEALED = 2026


def _artifacts() -> tuple[dict, dict]:
    """The champion's band and risk, wired to the champion's OWN overlay files.

    best.json's band carries whatever overlay path the last experiment wrote, which is
    a scratch directory that no longer exists. The shipping book is the one whose
    numbers are published, so its overlays are pinned here explicitly and the
    reproduction check in step 1 is what proves the pinning right.
    """
    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    band = dict(best["band"])
    band["meta_signals"] = str(ROOT / "meta.npz")
    risk = dict(best["risk"])
    if float(risk.get("money_model") or 0) > 0:
        risk["size_signals"] = str(ROOT / "moneymodel.npz")
    return {**band, **risk}, best


def main() -> int:
    brain_kwargs, best = _artifacts()
    signals = str(ROOT / "signals.npz")
    symbols = universe.load()
    print(f"universe {len(symbols)} symbols | signals {signals}")

    ds = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    # combined(), not research(): the sealed year has to be IN the table, and the
    # research years are sliced out of it identically either way.
    rbars = ds.combined()
    stamps = sorted({b.timestamp for series in rbars.values() for b in series})

    # ---- 1. reproduction -----------------------------------------------------------
    # The sealed number on record came from launch.forward(), whose window is the lock
    # plus its own warmup - not the calendar-year account the research years use. The
    # reproduction has to use the same window or it is comparing two different things,
    # so forward()'s geometry is replicated here with per-trade detail switched on.
    on_record = best.get("forward_2026") or {}
    before = [s for s in stamps if s < ds.lock]
    after = [s for s in stamps if s >= ds.lock]
    sealed = launch.run_window(rbars, before[-launch.FORWARD_WARMUP_BARS], ds.lock.isoformat(),
                               after[-1], signals, "forward", brain_kwargs=brain_kwargs,
                               with_trades=True)
    got = float(sealed["return_pct"])
    want = float(on_record.get("return_pct") or 0.0)
    ok = abs(got - want) < 0.005
    print(f"\nREPRODUCTION of sealed {SEALED}: {got:+.2%} vs {want:+.2%} on record "
          f"({sealed['trades']} trades vs {on_record.get('trades')}) -> "
          f"{'MATCH' if ok else 'MISMATCH'}")
    if not ok:
        print("  The ledger below describes THIS run, which is not the published book.")

    # ---- 2. the ledger -------------------------------------------------------------
    opps: list[attribution.Opportunity] = []
    for symbol, series in rbars.items():
        opps.extend(attribution.opportunities(
            series, threshold=float(best["config"]["threshold"]), symbol=symbol))
    print(f"opportunity set: {len(opps)} harvestable long legs after costs")

    trips: list[dict] = []
    per_year_return: dict[int, float] = {}
    for year in YEARS:
        res = sealed if year == SEALED else launch.year_window(
            rbars, stamps, year, signals, brain_kwargs=brain_kwargs, with_trades=True)
        if not res:
            continue
        per_year_return[year] = float(res["return_pct"])
        trips.extend(res.get("trades_detail") or [])
        print(f"  {year}: {res['return_pct']:+7.2%}  {res['trades']:>4} trades")

    rows = attribution.reconcile(opps, trips)
    table = attribution.yearly(rows)

    print("\n" + "=" * 104)
    print("THE LEDGER - every trade that was possible, and what the book did about it")
    print("=" * 104)
    head = (f"{'year':>6} {'return':>9} {'opps':>6} {'caught':>7} {'capture':>8} "
            f"{'won':>5} {'lost':>5} {'unforced':>9} {'hit':>6} {'left on table':>14}")
    print(head)
    order = [SEALED] + [y for y in sorted(table) if y != SEALED]
    for y in order:
        r = table.get(y)
        if not r:
            continue
        mark = "  <-- SEALED, never trained or selected on" if y == SEALED else ""
        print(f"{y:>6} {per_year_return.get(y, 0.0):>+8.2%} {r['opportunities']:>6} "
              f"{r['won'] + r['lost']:>7} {r['capture_rate']:>7.1%} {r['won']:>5} "
              f"{r['lost']:>5} {r['unforced']:>9} {r['hit_rate']:>5.1%} "
              f"{r['left_on_table_pp']:>13.0f}pp{mark}")

    # ---- 3. the rules --------------------------------------------------------------
    feats: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for symbol, series in rbars.items():
        mine = [r.at_ns for r in rows if r.symbol == symbol]
        if mine:
            feats[symbol] = attribution.features_at(series, mine)

    def matrix(kinds: set[str], positive: set[str]):
        X, y = [], []
        for symbol in feats:
            mine = [r for r in rows if r.symbol == symbol]
            Xs, ok = feats[symbol]
            for i, r in enumerate(mine):
                if r.kind in kinds and ok[i] and r.year != SEALED:
                    X.append(Xs[i])
                    y.append(1 if r.kind in positive else 0)
        return (np.array(X, dtype=np.float32), np.array(y, dtype=np.int64)) if X else \
            (np.zeros((0, len(attribution.tree.FEATURES)), np.float32), np.zeros(0, np.int64))

    findings = {}
    for name, kinds, positive, question in (
        ("losing_trades", {"won", "lost"}, {"won"},
         "which indicator at entry separated the trades that WON from the ones that LOST?"),
        ("unforced", {"won", "lost", "unforced"}, {"won", "lost"},
         "which indicator separated entries with real material from UNFORCED ones?"),
        ("missed", {"won", "lost", "missed"}, {"won", "lost"},
         "which indicator separated the legs we CAUGHT from the ones we MISSED?"),
    ):
        X, y = matrix(kinds, positive)
        rules = attribution.explain(X, y) if len(y) else []
        findings[name] = {"question": question, "rows": int(len(y)),
                          "base_rate": round(float(np.mean(y)), 4) if len(y) else None,
                          "rules": rules}
        print(f"\n--- {question}")
        print(f"    {len(y)} research rows, base rate "
              f"{(np.mean(y) if len(y) else 0):.1%}")
        for r in sorted(rules, key=lambda r: r["lift"])[:3]:
            print(f"    WORST  {r['rate']:6.1%} ({r['support']:>5} rows, "
                  f"{r['lift']:+.1%} vs base)  {r['rule']}")
        for r in sorted(rules, key=lambda r: -r["lift"])[:3]:
            print(f"    BEST   {r['rate']:6.1%} ({r['support']:>5} rows, "
                  f"{r['lift']:+.1%} vs base)  {r['rule']}")

    # ---- A73 stage 1: response curves over the trades that resolved ----------------
    # Research rows only, and only won-vs-lost: the question is "given that we entered
    # where material existed, which indicator VALUE separated winning from losing?".
    Xwl, ywl = matrix({"won", "lost"}, {"won"})
    curves = attribution.response_curves(Xwl, ywl.astype(float)) if len(ywl) else {}
    seps = {k: c for k, c in curves.items() if c["separated"]}
    print(f"\n--- A73 response curves: {len(curves)} computable, {len(seps)} separated")
    for name, c in sorted(seps.items(), key=lambda kv: -(kv[1]["optimum_rate"] - kv[1]["worst_rate"])):
        print(f"    {name:>14}: optimum near {c['optimum']:+.4f} ({c['optimum_rate']:.1%}) "
              f"vs worst {c['worst']:+.4f} ({c['worst_rate']:.1%}), base {c['base_rate']:.1%}")

    attribution.dump(rows, str(ROOT / "rnd" / "attribution_rows.json"))
    out = ROOT / "rnd" / f"attribution_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    payload = attribution.report(rows, sealed_year=SEALED)
    payload["response_curves"] = curves
    payload["reproduction"] = {"sealed_year": SEALED, "got": got, "on_record": want,
                               "match": bool(ok)}
    payload["returns"] = {str(y): round(v, 6) for y, v in per_year_return.items()}
    payload["findings"] = findings
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
