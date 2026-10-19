"""Artefact check on the phase 3 IC: is it the per-coin cost term?

The phase 3 target is gross forward return minus (0.45% + 2 x the pair's impact). The impact is a
per-coin-year constant that the features can read (illiquid coins), so part of the IC could be "the
model knows which coins are expensive". Here the same predictions are scored against the GROSS forward
return (close t+1 -> t+1+H, no cost), and against the cost term alone, per year 2021-2025.

    python research/plan_v2/ic_check.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import phase3_select as P3

HERE = Path(__file__).resolve().parent


def ic(pred, tgt, member, rows, step):
    vals = []
    for t in rows[::step]:
        ok = np.isfinite(pred[t]) & np.isfinite(tgt[t]) & member[t]
        if ok.sum() >= 5 and np.nanstd(tgt[t][ok]) > 0:
            vals.append(pd.Series(pred[t][ok]).corr(pd.Series(tgt[t][ok]), method="spearman"))
    v = np.array(vals)
    return round(float(np.nanmean(v)), 4), round(float(np.nanmean(v) / (np.nanstd(v) + 1e-12) * np.sqrt(np.isfinite(v).sum())), 2)


def main() -> int:
    st = P3.prepare()
    P, imp, preds = st["P"], st["imp"], st["preds"]
    out = {}
    for (tf, h, model, ss), pr in preds.items():
        if ss != "s1":
            continue
        n = P3.BARS_PER_DAY[tf]
        c = P[tf]["close"]
        H = h * n
        gross = np.full_like(c, np.nan)
        gross[: len(c) - 1 - H] = c[1 + H:] / c[1: len(c) - H] - 1
        cost = np.broadcast_to(2 * imp[tf][np.clip(P[tf]["year"] - 2020, 0, 6)], c.shape)
        cell = {}
        for y in P3.TEST_YEARS:
            rows = np.flatnonzero(P[tf]["year"] == y)
            net = gross - P3.HALF_COST * 2 - cost
            cell[y] = {"ic_net": ic(pr, net, P[tf]["member"], rows, n), "ic_gross": ic(pr, gross, P[tf]["member"], rows, n),
                       "ic_vs_minus_cost": ic(pr, -cost + 0 * gross, P[tf]["member"], rows, n)}
        out[f"{tf} H={h}d {model}"] = cell
        print(f"{tf} H={h}d {model}: " + " | ".join(f"{y} net {v['ic_net'][0]:+.3f} gross {v['ic_gross'][0]:+.3f} ({v['ic_gross'][1]:+.1f}) cost {v['ic_vs_minus_cost'][0]:+.3f}" for y, v in cell.items()), flush=True)
    (HERE / "ic_check_results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
