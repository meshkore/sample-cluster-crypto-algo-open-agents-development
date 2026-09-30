"""S10-6c: is the oracle's region available often enough to trade?

The operator's rule, 2026-09-30: the conditions come from the per-year maximum-profit study
(where 80% of the oracle's most profitable trades concentrate), and training and execution
happen only inside them - BUT the system must have the option to trade at least ~70% of the
time. A pause of three weeks or forty days is acceptable; six months idle because the market
trends one way or goes sideways is not.

So, walk-forward (region fitted on years < N, read on N), for each coverage target:

    day_share      share of calendar days with at least one in-region bar on any symbol
    time_share     share of 15-minute stamps where at least one symbol is in the region
    longest_gap    the longest run of days with no in-region bar anywhere

A coverage passes when every out-of-sample year has day_share >= 70% and longest_gap <= 40.
The smallest passing coverage is the region system 10 trains and trades inside.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import conditions as C  # noqa: E402

from system010_conditioned_rl import region as R  # noqa: E402

COVERAGES = (0.8, 0.85, 0.9, 0.95)
QUANTILE = 0.2
DAY_SHARE_MIN = 0.70
GAP_MAX_DAYS = 40


def fold_inputs(per: dict, N: int):
    nets = np.concatenate([d["swings"][d["year"][d["swings"][:, 0].astype(int)] < N, 2]
                           for d in per.values() if len(d["swings"])])
    floor = float(np.quantile(nets, 1 - QUANTILE))
    Xs, zones, ids, off = [], [], [], 0
    for d in per.values():
        sw = d["swings"]
        sy = d["year"][sw[:, 0].astype(int)] if len(sw) else np.zeros(0, int)
        best = sw[(sy < N) & (sw[:, 2] >= floor)]
        tr = d["year"] < N
        if not tr.any():
            continue
        zone = R.entry_zone_mask(len(d["X"]), best)
        sid = np.full(len(d["X"]), -1, dtype=np.int64)
        for k, (a, b, _) in enumerate(best):
            sid[int(a):min(int(a) + R.ENTRY_ZONE, int(b))] = off + k
        off += len(best)
        Xs.append(d["X"][tr]); zones.append(zone[tr]); ids.append(sid[tr])
    return np.concatenate(Xs), np.concatenate(zones), np.concatenate(ids), off, floor


def availability(per: dict, masks: dict, year: int) -> dict:
    stamps = np.unique(np.concatenate([per[s]["ns"][per[s]["year"] == year] for s in per]))
    hot = np.unique(np.concatenate([per[s]["ns"][(per[s]["year"] == year) & masks[s]] for s in per]))
    days_all = np.unique(stamps.astype("datetime64[ns]").astype("datetime64[D]"))
    days_hot = np.unique(hot.astype("datetime64[ns]").astype("datetime64[D]"))
    have = np.isin(days_all, days_hot)
    gap = run = 0
    for h in have:
        run = 0 if h else run + 1
        gap = max(gap, run)
    return {"day_share": round(float(have.mean()), 4),
            "time_share": round(len(hot) / max(len(stamps), 1), 4),
            "longest_gap_days": int(gap)}


def main() -> int:
    data = C.load(C.ENGINE)
    per = data["per"]
    out: dict = {c: {} for c in COVERAGES}
    for N in C.BOOT_YEARS:
        X, zone, sid, n_best, floor = fold_inputs(per, N)
        for c in COVERAGES:
            reg = R.fit(X, zone, sid, n_best, coverage=c, fitted_on=range(2017, N),
                        quantile=QUANTILE, net_floor=floor)
            masks = {s: reg.holds(d["X"]) for s, d in per.items()}
            a = availability(per, masks, N)
            a["train_swing_coverage"] = round(reg.train_swing_coverage, 4)
            a["bar_share"] = round(sum(int(masks[s][per[s]["year"] == N].sum()) for s in per)
                                   / sum(int((per[s]["year"] == N).sum()) for s in per), 4)
            out[c][N] = a
            print(f"{N} cov {c:.0%}: days {a['day_share']:.0%}  time {a['time_share']:.0%}  "
                  f"gap {a['longest_gap_days']}d  bars {a['bar_share']:.0%}", flush=True)
    verdict = {}
    for c in COVERAGES:
        rows = out[c].values()
        verdict[c] = all(r["day_share"] >= DAY_SHARE_MIN and r["longest_gap_days"] <= GAP_MAX_DAYS
                         for r in rows)
    chosen = next((c for c in COVERAGES if verdict[c]), None)
    payload = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "rule": {"day_share_min": DAY_SHARE_MIN, "longest_gap_max_days": GAP_MAX_DAYS},
               "quantile": QUANTILE, "per_coverage": {str(c): v for c, v in out.items()},
               "passes": {str(c): v for c, v in verdict.items()}, "chosen_coverage": chosen}
    path = C.REPO / f"research/system10/rnd/availability_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\npasses: {verdict}\nchosen coverage: {chosen}\nwritten {path.relative_to(C.REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
