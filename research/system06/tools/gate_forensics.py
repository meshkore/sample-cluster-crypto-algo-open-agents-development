"""Why a year goes quiet: the entry funnel of the shipping champion, year by year.

    PYTHONPATH=trading-system python research/system06/tools/gate_forensics.py

The question this exists to answer (operator, 2026-09-04): 2025 returns -2.96% while
every other research year pays, and no amount of staring at the trades explains it,
because the trades are FINE. The ledger already said so on 2026-09-02:

    year   trades   hit rate   return
    2021      797      48.1%   +14554%
    2022       47      42.4%      +8.7%
    2024      324      40.1%    +155.7%
    2025       75      45.5%      -3.0%

2025 has the best hit rate in the table and the second-fewest trades. It is not a year
the book lost in. It is a year the book did not SHOW UP for. So the thing to measure is
the refusals, not the fills - and specifically, which gate made them.

Every entry the model wanted lands in exactly one bucket:

    above_bar    the model's conviction cleared `enter`
      -> veto:<module>   a gate refused it, by name (regime, fractal, crowd, meta, ...)
      -> no_consensus    not enough modules independently backed it
      -> book_full       nobody objected; there was no slot free
      -> eligible        it became a trade

plus `deploy` - the average fraction of equity the regime allowed on the table, which
separates "we refused the trades" from "we took them at a size that could not matter".

This is a MEASUREMENT, not a proposal. It cannot adopt anything, and it does not open the
sealed year at all - see the note beside the year loop for why a "readout" that informs
the next experiment is not a readout. What comes out is a ranked list of which gate to
interrogate first, which is the difference between the next experiment being aimed and
being a guess.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
DATA = "trading-system/backtester/data"


def _pct(n, d):
    return (100.0 * n / d) if d else 0.0


def main() -> int:
    from system006_oracle_net_15m import autoloop, launch, universe
    from system006_oracle_net_15m.dataset import Dataset

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, band, risk = dict(best["config"]), dict(best["band"]), dict(best["risk"])
    sig = str(ROOT / "signals.npz")
    if not Path(sig).exists():
        print(f"no signals at {sig} - the champion's own export is required", file=sys.stderr)
        return 2

    brain = {"enter": float(band["enter"]), "exit_": float(band["exit_"]),
             "min_hold": int(band["min_hold"]), **risk}
    if band.get("meta_signals"):
        brain["meta_signals"] = band["meta_signals"]
    if float(risk.get("money_model") or 0) > 0 and (ROOT / "moneymodel.npz").exists():
        brain["size_signals"] = str(ROOT / "moneymodel.npz")

    symbols = universe.load()
    if not isinstance(symbols, list) or len(symbols) < 5:
        raise SystemExit(f"degenerate universe: {symbols!r} - run from the repo root "
                         f"with PYTHONPATH=trading-system")
    print(f"gate forensics: champion band {brain['enter']}/{brain['exit_']} on "
          f"{len(symbols)} symbols", flush=True)

    t0 = time.time()
    dataset = Dataset(data_root=DATA, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})
    py = launch.per_year(rbars, rstamps, autoloop.RESEARCH_YEARS, sig,
                         brain_kwargs=brain, keep_funnel=True)

    # 2026 is deliberately ABSENT. The seal permits a readout, and an early draft of this
    # tool took that permission - the sealed year's funnel would have sat in the table
    # "just for shape". But this tool exists to point at the next experiment, and a
    # number you look at while choosing what to try next is an input whatever the header
    # calls it. The diagnosis is about 2025, which is a research year, and it needs
    # nothing from 2026 to be complete.
    years: dict[str, dict] = {}
    for y in sorted(py):
        r = py[y] or {}
        if r.get("return_pct") is not None:
            years[str(y)] = r

    # Every veto label seen anywhere, so the table has one column per gate and a year
    # that never fired a gate shows a zero rather than a hole.
    gates = sorted({k for r in years.values() for k in (r.get("funnel") or {})
                    if k.startswith("veto:")})

    rows = {}
    for y, r in years.items():
        f = r.get("funnel") or {}
        above = f.get("above_bar", 0)
        rows[y] = {
            "return_pct": r.get("return_pct"),
            "trades": r.get("trades"),
            "max_drawdown": r.get("max_drawdown"),
            "bars": f.get("bars", 0),
            "above_bar": above,
            "vetoed": f.get("vetoed", 0),
            "no_consensus": f.get("no_consensus", 0),
            "eligible": f.get("eligible", 0),
            "book_full": f.get("book_full", 0),
            "avg_deploy": (f.get("deploy_sum", 0.0) / f["bars"]) if f.get("bars") else None,
            "gates": {g[5:]: f.get(g, 0) for g in gates},
            "refused_pct": _pct(above - f.get("eligible", 0), above),
        }

    # Reconciliation, before anything is printed or written. The first run of this tool
    # reported "0 signals cleared the bar" beside "512 trades" for the same year and
    # saved it to disk without complaint - per_year() filters the summary down to a
    # fixed key list and had silently dropped the funnel. A diagnostic that can print a
    # self-contradiction is worse than no diagnostic: it looks like a finding.
    broken = [y for y, r in rows.items()
              if (r["trades"] or 0) > 0 and r["above_bar"] == 0]
    if broken:
        print(f"\nREFUSING TO REPORT: {', '.join(sorted(broken))} traded but recorded no "
              f"signal above the bar. The funnel is not reaching this tool - check that "
              f"launch.per_year was called with keep_funnel=True.", file=sys.stderr)
        return 3

    print("\nENTRY FUNNEL - of every signal that cleared the model's bar, what happened")
    head = (f"{'year':>5} {'return':>10} {'trades':>7} {'above bar':>10} {'refused':>9} "
            f"{'consensus':>10} {'full book':>10} {'eligible':>9} {'deploy':>7}")
    print(head)
    print("-" * len(head))
    for y in sorted(rows):
        r = rows[y]
        dep = "-" if r["avg_deploy"] is None else format(r["avg_deploy"], ".1%")
        print(f"{y:>5} {r['return_pct']:>+9.2%} {r['trades']:>7} {r['above_bar']:>10,} "
              f"{r['refused_pct']:>8.1f}% {r['no_consensus']:>10,} {r['book_full']:>10,} "
              f"{r['eligible']:>9,} {dep:>7}")

    if gates:
        print("\nWHO REFUSED - vetoes per gate, as a share of the signals that cleared the bar")
        head = f"{'year':>5} " + " ".join(f"{g[5:]:>13}" for g in gates)
        print(head)
        print("-" * len(head))
        for y in sorted(rows):
            r = rows[y]
            cells = " ".join(f"{_pct(r['gates'][g[5:]], r['above_bar']):>12.1f}%" for g in gates)
            print(f"{y:>5} {cells}")

    # The comparison the whole run is for: the weak years against the years that paid.
    # 0.30 is the operator's own mandate: a year below it is a year the system failed.
    weak = [y for y in rows if (rows[y]["return_pct"] or 0) < 0.30]
    strong = [y for y in rows if (rows[y]["return_pct"] or 0) >= 0.30]
    def _avg(ys, f):
        vals = [f(rows[y]) for y in ys if f(rows[y]) is not None]
        return sum(vals) / len(vals) if vals else None
    contrast = {}
    if weak and strong:
        print(f"\nWEAK YEARS {weak} vs YEARS THAT PAID {strong}")
        for label, fn in (("signals above the bar", lambda r: r["above_bar"]),
                          ("refused %", lambda r: r["refused_pct"]),
                          ("eligible", lambda r: r["eligible"]),
                          ("avg deployment", lambda r: r["avg_deploy"]),
                          ("trades", lambda r: r["trades"])):
            w, s = _avg(weak, fn), _avg(strong, fn)
            contrast[label] = {"weak": w, "strong": s}
            if w is not None and s is not None:
                print(f"  {label:<24} weak {w:>12,.2f}   paid {s:>12,.2f}   "
                      f"ratio {(w / s if s else float('nan')):.2f}x")
        for g in gates:
            w, s = _avg(weak, lambda r, g=g: _pct(r["gates"][g[5:]], r["above_bar"])), \
                   _avg(strong, lambda r, g=g: _pct(r["gates"][g[5:]], r["above_bar"]))
            contrast[g] = {"weak": w, "strong": s}
            if w is not None and s is not None:
                print(f"  veto {g[5:]:<19} weak {w:>11.1f}%   paid {s:>11.1f}%   "
                      f"gap {w - s:>+7.1f} points")

    out = ROOT / "rnd" / f"gate_forensics_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    out.write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(),
        "band": {k: brain[k] for k in ("enter", "exit_", "min_hold")},
        "risk": risk, "years": rows, "weak": weak, "strong": strong, "contrast": contrast,
        "note": "Diagnostic only. 2026 is present so its SHAPE sits beside the research "
                "years; nothing here selects on it.",
    }, indent=1), encoding="utf-8")
    print(f"\nwritten -> {out}   ({(time.time() - t0) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
