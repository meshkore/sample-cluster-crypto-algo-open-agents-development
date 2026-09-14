"""The Phase 3 MVP, end to end: `python -m quantlab_system09.mvp`.

What this run is, in the design document's terms: L0 and L1 on one pair, with V0 and V2.
It builds a conserved ledger of the Bitcoin float and the sector's cash, walks the whole
Binance BTCUSDT tape through it in dollar-volume buckets, and answers the operator's
question - who holds the coins and who holds the dry powder - as a time series rather than
as a snapshot.

It runs TWICE, and the second run is the reason the first one is worth anything:

  ANCHORED     ETF creations and redemptions are fed in as cash arriving at the
               institutional cohort. This is the reconstruction we would actually use.
  HELD OUT     the ETF series is withheld entirely. The institutional cohort acts on its
               behavioural rule alone, and what it ends up holding becomes a PREDICTION of
               a published series it was never shown. That is V2.

What this run is NOT: it does not clear a market, it does not simulate anything forward,
and it does not trade. L2 through L5 are later phases and no number here should be read as
evidence about them.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import quantlab_catalog as cat
from quantlab_catalog.paths import REPO_ROOT

from . import buckets, cohorts as C
from .boundary import Boundary, etf_flow
from .reconstruct import Reconstruction, baseline_desire
from .validate import accounting, anchor_recovery

SYMBOL = "BTCUSDT"
#: The window opens in 2020 because the cash side of the ledger is only observable in the
#: stablecoin era; see `boundary.py`. It closes before 2026 because that is the laboratory's
#: sealed forward window and the catalogue will not serve it here.
START = "2020-01-01"
END = "2026-01-01"
#: V2 is scored only where the anchor exists. The ETFs began trading 2024-01-11.
SCORE_FROM = "2024-01-11"
OUT = REPO_ROOT / "research" / "system09"


def _load() -> list:
    bars = buckets.window(cat.research([SYMBOL])[SYMBOL], START, END)
    if not bars:
        raise SystemExit(f"no {SYMBOL} bars in [{START}, {END})")
    return bars


def _run(bars: list, *, use_etf: bool, label: str) -> tuple:
    thr = buckets.sizing(bars, 8.0)
    bkts = buckets.build(bars, thr)
    t0 = time.time()
    rec = Reconstruction(bkts, boundary=Boundary(use_etf=use_etf, cash_share=True),
                         funding=cat.funding(SYMBOL), check_every=False)
    traj = rec.run()
    print(f"  {label:9s} {len(bkts):,} buckets  {len(traj.days):,} days  "
          f"{time.time() - t0:.1f}s  fill {traj.overall_fill:.4f}")
    return rec, traj


def _holdings_table(traj, title: str) -> str:
    st, px, day = traj.state[-1], traj.price[-1], traj.days[-1]
    rows = [f"{title}  ({day}, BTC at ${px:,.0f})",
            f"  {'cohort':<22s} {'coins':>13s} {'share':>7s} {'cash $bn':>10s} "
            f"{'avg basis':>11s} {'unreal $bn':>11s}"]
    total = sum(v["coins"] for v in st.values())
    for k, v in sorted(st.items(), key=lambda kv: -kv[1]["coins"]):
        rows.append(f"  {k:<22s} {v['coins']:13,.0f} {v['coins']/total:6.1%} "
                    f"{v['cash']/1e9:10,.1f} {v['avg_basis']:11,.0f} "
                    f"{v['unrealized']/1e9:11,.1f}")
    dry = sum(v["cash"] for v in st.values())
    rows.append(f"  {'TOTAL':<22s} {total:13,.0f} {1.0:6.1%} {dry/1e9:10,.1f}")
    return "\n".join(rows)


def _per_year(traj) -> str:
    """Per calendar year: how much of the tape the population could actually trade, and
    where the float moved. Split by year because this laboratory's standing rule is that a
    statistic without its era is a number that could mean either of two opposite things."""
    years: dict[str, list] = {}
    for i, d in enumerate(traj.days):
        years.setdefault(d[:4], []).append(i)
    rows = ["PER YEAR",
            f"  {'year':<6s} {'days':>5s} {'fill mean':>10s} {'fill worst':>11s} "
            f"{'LTH dcoins':>12s} {'inst dcoins':>12s} {'price end':>11s}"]
    for y, idx in sorted(years.items()):
        f = [traj.fill_ratio[i] for i in idx]
        a, b = traj.state[idx[0]], traj.state[idx[-1]]
        rows.append(f"  {y:<6s} {len(idx):5d} {sum(f)/len(f):10.4f} {min(f):11.4f} "
                    f"{b[C.LTH]['coins']-a[C.LTH]['coins']:12,.0f} "
                    f"{b[C.INSTITUTIONAL]['coins']-a[C.INSTITUTIONAL]['coins']:12,.0f} "
                    f"{traj.price[idx[-1]]:11,.0f}")
    return chr(10).join(rows)


def main() -> int:
    print(f"SYSTEM 09 - THE LEDGER   MVP (phase 3: L0 + L1, V0 + V2)")
    print(f"  symbol {SYMBOL}   window [{START}, {END})   population "
          f"{len(C.TRADING) * C.LADDER + C.LADDER * 2 + 2} agents\n")
    bars = _load()

    rec_a, traj_a = _run(bars, use_etf=True, label="anchored")
    rec_h, traj_h = _run(bars, use_etf=False, label="held-out")
    print()

    v0 = accounting(rec_a.ledger, traj_a)
    print(v0.render(), "\n")

    v2 = anchor_recovery(traj_h, etf_flow(),
                         baseline_desire(rec_h, C.INSTITUTIONAL),
                         start=SCORE_FROM)
    print(v2.render(), "\n")

    print(_holdings_table(traj_a, "WHO HOLDS WHAT - anchored reconstruction"), "\n")
    print(_per_year(traj_a), "\n")

    OUT.mkdir(parents=True, exist_ok=True)
    series = [{"day": d, "price": p, "fill": f,
               **{f"{c}_coins": s[c]["coins"] for c in s},
               **{f"{c}_cash": s[c]["cash"] for c in s},
               **{f"{c}_basis": s[c]["avg_basis"] for c in s}}
              for d, p, f, s in zip(traj_a.days, traj_a.price, traj_a.fill_ratio,
                                    traj_a.state)]
    (OUT / "cohort_state.json").write_text(json.dumps(series), encoding="utf-8")
    (OUT / "mvp_report.json").write_text(json.dumps({
        "symbol": SYMBOL, "window": [START, END], "score_from": SCORE_FROM,
        "agents": len(rec_a.agents), "buckets": traj_a.buckets,
        "v0": {"passed": v0.passed, "coin_drift": v0.coin_drift,
               "cash_drift": v0.cash_drift, "mean_fill": v0.mean_fill,
               "min_fill": v0.min_fill, "shortfall_events": v0.shortfall_events,
               "funding_unpaid": v0.funding_unpaid},
        "v2": {"days": v2.days, "beats_baseline": v2.beats_baseline,
               "margin": v2.margin, "wins": v2.wins, "scored": v2.scored, "daily": v2.daily, "weekly": v2.weekly,
               "cumulative": v2.cumulative},
        "final_state": traj_a.state[-1], "final_day": traj_a.days[-1],
        "final_price": traj_a.price[-1],
    }, indent=2), encoding="utf-8")
    print(f"written  {OUT / 'cohort_state.json'}\n         {OUT / 'mvp_report.json'}")
    return 0 if v0.passed else 1


if __name__ == "__main__":
    sys.exit(main())
