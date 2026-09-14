"""PHASE 1 - the whole record, reconstructed: `python -m quantlab_system09.phase1`.

The operator's instruction, 2026-09-14: start from the first day there are records, bring
each asset in as it appears, manage the liquidity and the players through time, run to
2025-12-31 and set the balances there.

That is what this does. It opens on **2017-08-17**, the first day Binance has a tape at all,
with an empty population and an empty ledger - nothing is handed out by a constructor.
Assets arrive on the day they first trade, each bringing its float. Dollars arrive only
through the boundary. Players are born and retired against observed activity. It closes on
**2025-12-31** and freezes the books, which become the opening state for phase 2.

THREE THINGS THIS RUN IS NOT. It does not clear a market - prices are taken from the tape,
never produced by the model. It does not simulate anything forward; that is phase 3, and
2026 is the laboratory's sealed window, so opening it is a decision with a cost rather than
a command-line flag. And it does not trade.

IT RUNS TWICE, and the second run is why the first is worth anything:

  ANCHORED   ETF creations and redemptions are fed in as cash arriving at the institutional
             cohort. This is the reconstruction whose balances we keep.
  HELD OUT   the ETF series is withheld entirely, so the institutional cohort acts on its
             rule alone and what it ends up holding is a PREDICTION of a published series it
             never saw. That is V2, and it is the only test here that can embarrass us.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone

import quantlab_catalog as cat
from quantlab_catalog.paths import REPO_ROOT

from . import buckets, cohorts as C
from .boundary import Boundary, day_range
from .reconstruct import Reconstruction, baseline_desire
from .validate import accounting, anchor_recovery

#: The first day of the record and the day the books are closed, both as the operator set
#: them. The end is INCLUSIVE and sits strictly inside the research era; 2026 is sealed.
START = "2017-08-17"
END = "2025-12-31"
ANCHOR_SYMBOL = "BTCUSDT"
SCORE_FROM = "2024-01-11"          # the ETFs began trading; V2 has no anchor before it
BUCKETS_PER_DAY = 6
OUT = REPO_ROOT / "research" / "system09"


def _tapes() -> dict[str, list]:
    """Every symbol in the laboratory's universe, compressed to dollar-volume buckets."""
    syms = cat.load_universe()
    raw = cat.research(syms)
    out = {}
    for sym in syms:
        bars = buckets.window(raw[sym], START, _exclusive_end(END))
        if not bars:
            continue
        out[sym] = buckets.build(bars, buckets.sizing(bars, BUCKETS_PER_DAY))
    return out


def _exclusive_end(day: str) -> str:
    """`buckets.window` is half-open and the operator's end date is inclusive."""
    d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _etf_by_day() -> dict[str, float]:
    """Published ETF net flow in dollars, keyed by UTC date. Farside publishes millions."""
    return {datetime.fromtimestamp(r["t_s"], timezone.utc).strftime("%Y-%m-%d"):
            r["value"] * 1e6 for r in cat.etf_flows()}


def _run(tapes: dict[str, list], *, use_etf: bool, label: str):
    days = day_range(START, END)
    listings = {s: bk[0].day for s, bk in tapes.items()}
    bnd = Boundary(days, listings, use_etf=use_etf)
    funding = {}
    for sym in tapes:
        try:
            funding[sym] = cat.funding(sym)
        except FileNotFoundError:
            pass
    t0 = time.time()
    rec = Reconstruction(tapes, boundary=bnd, funding=funding, check_daily=True)
    traj = rec.run(until=END)
    print(f"  {label:9s} {traj.buckets:,} buckets  {len(traj.days):,} days  "
          f"{time.time() - t0:6.1f}s  fill {traj.overall_fill:.4f}")
    return rec, traj


def _balances(traj, title: str) -> str:
    st, prices, day = traj.state[-1], traj.prices[-1], traj.days[-1]
    rows = [f"{title}  ({day})",
            f"  {'cohort':<22s} {'agents':>7s} {'holdings $bn':>13s} {'cash $bn':>10s} "
            f"{'unrealised $bn':>15s} {'realised $bn':>13s}"]
    tv = sum(v["value"] for v in st.values())
    tc = sum(v["cash"] for v in st.values())
    for k, v in sorted(st.items(), key=lambda kv: -kv[1]["value"]):
        rows.append(f"  {k:<22s} {v['headcount']:7d} {v['value']/1e9:13,.1f} "
                    f"{v['cash']/1e9:10,.1f} {v['unrealized']/1e9:15,.1f} "
                    f"{v['realized_pnl']/1e9:13,.1f}")
    rows.append(f"  {'TOTAL':<22s} {sum(v['headcount'] for v in st.values()):7d} "
                f"{tv/1e9:13,.1f} {tc/1e9:10,.1f}")
    rows.append("")
    rows.append(f"  dry powder as a share of holdings: {tc / tv:.1%}" if tv else "")
    rows.append(f"  {'asset':<10s} {'price':>12s} {'float held':>16s} {'value $bn':>12s}")
    floats: dict[str, float] = {}
    for v in st.values():
        for s, q in v["coins"].items():
            floats[s] = floats.get(s, 0.0) + q
    for s, q in sorted(floats.items(), key=lambda kv: -kv[1] * prices.get(kv[0], 0)):
        rows.append(f"  {s:<10s} {prices.get(s, 0):12,.2f} {q:16,.0f} "
                    f"{q * prices.get(s, 0) / 1e9:12,.1f}")
    return "\n".join(rows)


def _per_year(traj, bnd) -> str:
    years: dict[str, list[int]] = {}
    for i, d in enumerate(traj.days):
        years.setdefault(d[:4], []).append(i)
    ramp = bnd.ramp_summary()
    rows = ["PER YEAR",
            f"  {'year':<6s} {'days':>5s} {'fill':>8s} {'worst':>8s} {'players':>8s} "
            f"{'assets':>7s} {'fiat ramped $bn':>16s}"]
    for y, idx in sorted(years.items()):
        f = [traj.fill_ratio[i] for i in idx]
        rows.append(f"  {y:<6s} {len(idx):5d} {sum(f)/len(f):8.4f} {min(f):8.4f} "
                    f"{traj.headcount[idx[-1]]:8d} {traj.listed[idx[-1]]:7d} "
                    f"{ramp.get(y, 0.0)/1e9:16,.1f}")
    return "\n".join(rows)


def main() -> int:
    print("SYSTEM 09 - THE LEDGER   PHASE 1: the whole record, reconstructed")
    print(f"  window [{START} .. {END}]   universe {len(cat.load_universe())} assets   "
          f"buckets/day {BUCKETS_PER_DAY}\n")
    tapes = _tapes()
    for s, bk in sorted(tapes.items(), key=lambda kv: kv[1][0].day):
        print(f"    {s:10s} lists {bk[0].day}  {len(bk):6,} buckets")
    print()

    rec_a, traj_a = _run(tapes, use_etf=True, label="anchored")
    rec_h, traj_h = _run(tapes, use_etf=False, label="held-out")
    print()

    v0 = accounting(rec_a.ledger, traj_a)
    print(v0.render(), "\n")

    v2 = anchor_recovery(traj_h, _etf_by_day(),
                         baseline_desire(rec_h, C.INSTITUTIONAL, ANCHOR_SYMBOL),
                         symbol=ANCHOR_SYMBOL, start=SCORE_FROM)
    print(v2.render(), "\n")
    print(_per_year(traj_a, rec_a.boundary), "\n")
    print(_balances(traj_a, "BALANCES AT THE CLOSE OF THE RECORD"), "\n")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase1_state.json").write_text(json.dumps([
        {"day": d, "prices": p, "fill": f, "players": h, "assets": n,
         "cohorts": {k: {"value": v["value"], "cash": v["cash"],
                         "unrealized": v["unrealized"], "coins": v["coins"],
                         "headcount": v["headcount"]} for k, v in s.items()}}
        for d, p, f, h, n, s in zip(traj_a.days, traj_a.prices, traj_a.fill_ratio,
                                    traj_a.headcount, traj_a.listed, traj_a.state)]),
        encoding="utf-8")
    (OUT / "phase1_report.json").write_text(json.dumps({
        "window": [START, END], "universe": sorted(tapes), "buckets": traj_a.buckets,
        "agents_final": traj_a.headcount[-1], "buckets_per_day": BUCKETS_PER_DAY,
        "v0": {"passed": v0.passed, "coin_drift": v0.coin_drift,
               "cash_drift": v0.cash_drift, "mean_fill": v0.mean_fill,
               "min_fill": v0.min_fill, "shortfall_events": v0.shortfall_events},
        "v2": {"days": v2.days, "beats_baseline": v2.beats_baseline, "margin": v2.margin,
               "wins": v2.wins, "scored": v2.scored, "daily": v2.daily,
               "weekly": v2.weekly, "cumulative": v2.cumulative},
        "fiat_ramped_by_year": rec_a.boundary.ramp_summary(),
        "final_day": traj_a.days[-1], "final_prices": traj_a.prices[-1],
        "final_state": traj_a.state[-1],
    }, indent=2), encoding="utf-8")
    print(f"written  {OUT / 'phase1_state.json'}\n         {OUT / 'phase1_report.json'}")
    return 0 if v0.passed else 1


if __name__ == "__main__":
    sys.exit(main())
