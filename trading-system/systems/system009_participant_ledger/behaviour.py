"""L2 - LEARNING WHAT EACH GROUP DOES, instead of asserting it.

This is the first piece of the generative simulator. v1 answers the inverse question: the
tape is given, so who must have traded? That model cannot be run forward, because the tape is
its input. v2 has to answer the forward question - *what will each group do tomorrow* - and
this module is where that is measured for the first time.

WHAT IS PREDICTED
For every day, every cohort and every asset, the reconstruction already knows the realised net
flow: how many units that group ended up holding against how many it held the day before. That
is the target. The features are the group's own condition on the day - how much of the float it
holds, how much dry powder it has left, how far underwater it is, what it did yesterday - plus
the market's condition.

WHY FLOW AND NOT PRICE
A flow model can be wrong in a way a return model cannot hide. If long-term holders are
predicted to sell while they actually accumulate, the simulation is not a model of this market
whatever its P&L says. And unlike a return forecast, flow is not a zero-sum contest against
everyone else's forecast: participants are far more persistent than prices, which is precisely
why an agent-based simulation is worth building at all.

WHAT A GOOD SCORE LOOKS LIKE
Per cohort, walk-forward, research years only:

  IC          rank correlation of predicted against realised flow
  sign        how often the direction of the flow is right
  persistence THE BAR. Yesterday's flow, used as today's forecast. A model that cannot beat
              the group's own inertia has learned nothing about the group - it has learned
              that cohorts are sticky, which we already knew.

Everything here is measured before 2026 and the sealed window is never loaded into a fit.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from quantlab_catalog.paths import REPO_ROOT
from system009_participant_ledger import cohorts as C
from system009_participant_ledger import pipeline
from system009_participant_ledger.train import DEVICE, RESEARCH_END_EXCLUSIVE, _fit

#: The cohorts worth scoring: the ones that hold and trade on an opinion. Boundary operators
#: (issuers, venues) move because the boundary moved, and predicting them is predicting the
#: observed series that drives them, which would flatter the result.
TRADERS = (C.LTH, C.MOMENTUM, C.DIP, C.LEVERED, C.INSTITUTIONAL, C.BASIS, C.MAKER)

#: How far ahead the flow is predicted. One day is the finest the ledger records; the horizon
#: study says this system's signal lives in weeks, so the same question is asked of behaviour.
AHEAD = (1, 7, 30)

OUT = REPO_ROOT / "research" / "system09"
FOLDS = ("2021", "2022", "2023", "2024", "2025")


def build(traj, ahead: int = 7) -> dict:
    """Rows of (day, cohort, symbol) -> features, and the flow that followed.

    Flow is normalised by the cohort's holding of that asset, so a 1% move by a small cohort
    and a 1% move by a large one are the same number. An absolute flow would make this a
    model of cohort size, which is not in question.
    """
    days, state, prices = traj.days, traj.state, traj.prices
    rows_x, rows_y, rows_day, rows_cohort, rows_sym, rows_prev = [], [], [], [], [], []
    for i in range(1, len(days) - ahead):
        today, yday, ahead_state = state[i], state[i - 1], state[i + ahead]
        px, px_prev = prices[i], prices[i - 1]
        for cohort in TRADERS:
            cur = today.get(cohort)
            old = yday.get(cohort)
            nxt = ahead_state.get(cohort)
            if not (cur and old and nxt):
                continue
            cash, value = cur["cash"], cur["value"]
            wealth = cash + value
            if wealth <= 0:
                continue
            unreal = cur["unrealized"] / value if value > 0 else 0.0
            dry = cash / wealth
            for sym, units in cur["coins"].items():
                if units <= 0 or sym not in px or sym not in px_prev:
                    continue
                before = old["coins"].get(sym, 0.0)
                after = nxt["coins"].get(sym, 0.0)
                prev_flow = (units - before) / units if units else 0.0
                flow = (after - units) / units
                if not np.isfinite(flow) or abs(flow) > 2.0:
                    continue
                held_share = units * px[sym] / value if value > 0 else 0.0
                ret1 = px[sym] / px_prev[sym] - 1.0
                rows_x.append([dry, unreal, held_share, prev_flow, ret1,
                               np.log1p(max(units * px[sym], 1.0)),
                               np.log1p(max(cash, 1.0))])
                rows_y.append(flow)
                rows_day.append(days[i])
                rows_cohort.append(cohort)
                rows_sym.append(sym)
                rows_prev.append(prev_flow)
    return {"x": np.array(rows_x, dtype=np.float32), "y": np.array(rows_y, dtype=np.float32),
            "day": np.array(rows_day), "cohort": np.array(rows_cohort),
            "symbol": np.array(rows_sym), "prev": np.array(rows_prev, dtype=np.float32)}


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30:
        return float("nan")
    ra = np.argsort(np.argsort(a[m])).astype(float)
    rb = np.argsort(np.argsort(b[m])).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


def score(data: dict, ahead: int) -> list[dict]:
    """Walk-forward, per cohort, against the cohort's own persistence."""
    x, y, day = data["x"], data["y"], data["day"]
    rows = []
    pred = np.full(len(y), np.nan)
    for year in FOLDS:
        stop = str(int(year) - 1)
        tr = day < f"{stop}-01-01"
        st = (day >= f"{stop}-01-01") & (day < f"{year}-01-01")
        va = (day >= f"{year}-01-01") & (day < f"{int(year) + 1}-01-01") & \
             (day < RESEARCH_END_EXCLUSIVE)
        if tr.sum() < 2000 or st.sum() < 200 or va.sum() < 200:
            continue
        model, blob, _, _ = _fit(x[tr], y[tr], x[st], y[st])
        import torch
        model.eval()
        with torch.no_grad():
            t = torch.tensor((x[va] - blob["mu"]) / blob["sd"], dtype=torch.float32,
                             device=DEVICE)
            pred[va] = model(t).cpu().numpy().ravel()
    scored = np.isfinite(pred)
    for cohort in TRADERS:
        m = scored & (data["cohort"] == cohort)
        if m.sum() < 200:
            continue
        ic = _spearman(pred[m], y[m])
        base = _spearman(data["prev"][m], y[m])
        sign = float(((pred[m] > 0) == (y[m] > 0)).mean())
        sign_base = float(((data["prev"][m] > 0) == (y[m] > 0)).mean())
        rows.append({"ahead": ahead, "cohort": cohort, "rows": int(m.sum()),
                     "ic": ic, "persistence_ic": base, "gain": ic - base,
                     "sign": sign, "persistence_sign": sign_base,
                     "beats_persistence": bool(ic > base)})
    return rows


def main() -> int:
    print("SYSTEM 09 - L2 BEHAVIOUR: can we predict what each group does?")
    print("  walk-forward, research years only. The bar is the cohort's own persistence.\n")
    _, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    out = []
    for ahead in AHEAD:
        data = build(traj, ahead=ahead)
        print(f"  {ahead}-day flow   {len(data['y']):,} rows")
        print(f"    {'cohort':<22s}{'IC':>9s}{'persistence':>13s}{'gain':>9s}"
              f"{'sign':>8s}{'base':>8s}")
        for r in score(data, ahead):
            out.append(r)
            flag = "" if r["beats_persistence"] else "  <- no better than inertia"
            print(f"    {r['cohort']:<22s}{r['ic']:>+9.4f}{r['persistence_ic']:>+13.4f}"
                  f"{r['gain']:>+9.4f}{r['sign']:>8.3f}{r['persistence_sign']:>8.3f}{flag}")
        print()
    if out:
        beat = sum(1 for r in out if r["beats_persistence"])
        print(f"  {beat} of {len(out)} cohort-horizons beat the group's own inertia")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "behaviour_report.json").write_text(
            json.dumps({"rows": out, "beat": beat, "total": len(out)}, indent=1),
            encoding="utf-8")
        print(f"  written  {OUT / 'behaviour_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
