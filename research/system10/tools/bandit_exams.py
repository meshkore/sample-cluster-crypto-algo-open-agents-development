"""S10-8b exams: does choosing WHICH trades to take inside the region beat taking them all?

Two walk-forward exams, nothing seen twice:

    exam 2024: region + scorer fitted on <= 2022, the take-bar chosen on 2023, read on 2024
    exam 2025: region + scorer fitted on <= 2023, the take-bar chosen on 2024, read on 2025

Labels never cross into the selection year: an opportunity whose four-day trade would end
after its training year's last bar is dropped (the embargo). Two criteria - lambda 1 (the
operator's: net return minus the trade's worst excursion) and lambda 0 (maximum profit, the
control) - four seeds each. The take-bar is an absolute score, chosen on the selection year
as the best Q among bars that trade at least MIN_TRADES times, then applied unchanged.

Every number is the three-slot book of `conditions.book_year` with the fixed causal exit.
Baselines on the same years: take every opportunity in the region, and trade everywhere.

    PYTHONPATH="trading-system;trading-system/systems;backtester;live-trading" \
        python research/system10/tools/bandit_exams.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import conditions as C  # noqa: E402

from system010_conditioned_rl import bandit as B  # noqa: E402
from system010_conditioned_rl import train as T  # noqa: E402

SEEDS = (77101, 77102, 91002, 51015)
LAMBDAS = (1.0, 0.0)
EXAMS = ((2024, 2023), (2025, 2024))
TAKE_SHARES = (0.5, 0.3, 0.2, 0.1, 0.05, 0.02)
MIN_TRADES = 100
COVERAGE = 0.9
MARKET = "--market" in sys.argv   # add breadth + slow trend to the scorer's inputs


def main() -> int:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    t0 = time.time()
    data = C.load(C.ENGINE)
    per, band, risk = data["per"], data["band"], data["risk"]
    stop, trail = float(risk.get("stop_loss") or 0), float(risk.get("trail_stop") or 0)
    everywhere = {s: np.isfinite(d["X"]).all(axis=1) for s, d in per.items()}
    results: dict = {}

    for test_year, sel_year in EXAMS:
        last = sel_year - 1
        reg = T.fit_region(per, last, COVERAGE)
        inside = {s: reg.holds(d["X"]) & everywhere[s] for s, d in per.items()}
        tr_all = np.concatenate([d["X"][d["year"] <= last] for d in per.values()])
        mean, std = np.nanmean(tr_all, axis=0), np.nanstd(tr_all, axis=0) + 1e-8
        del tr_all

        opp = {}
        for s, d in per.items():
            idx = np.flatnonzero(inside[s])
            net, mae = B.outcomes(d["close"], idx, stop, trail)
            x = np.nan_to_num(np.clip((d["X"][idx] - mean) / std, -5, 5), nan=0.0).astype(np.float32)
            if MARKET:
                # The market's state, not the coin's: the share of the universe in an uptrend
                # and the coin's own slow trend bit - both price-only, causal, no model.
                mk = np.stack([d["breadth"][idx] * 2 - 1, (d["trend"][idx] > 0) * 2.0 - 1], axis=1)
                x = np.concatenate([x, mk.astype(np.float32)], axis=1)
            end_year = d["year"][np.minimum(idx + B.HORIZON, len(d["year"]) - 1)]
            opp[s] = {"idx": idx, "x": x, "net": net, "mae": mae, "year": d["year"][idx],
                      "end_year": end_year}
        train_rows = [o for o in opp.values()]
        keep = [(o["year"] <= last) & (o["end_year"] <= last) & np.isfinite(o["net"]) for o in train_rows]
        X_tr = np.concatenate([o["x"][k] for o, k in zip(train_rows, keep)])
        net_tr = np.concatenate([o["net"][k] for o, k in zip(train_rows, keep)])
        mae_tr = np.concatenate([o["mae"][k] for o, k in zip(train_rows, keep)])
        print(f"exam {test_year}: {len(X_tr):,} training opportunities (mean net {net_tr.mean():+.3%}) "
              f"[{(time.time() - t0) / 60:.1f}m]", flush=True)

        base = {}
        for name, masks in (("take all in region", inside), ("everywhere", everywhere)):
            base[name] = {y: {k: v for k, v in C.book_year(per, masks, y, band, risk).items() if k != "daily"}
                          for y in (sel_year, test_year)}
            b = base[name]
            print(f"  {name:<20} {sel_year} {b[sel_year]['return']:+.1%}/{b[sel_year]['max_dd']:.0%}  "
                  f"{test_year} {b[test_year]['return']:+.1%}/{b[test_year]['max_dd']:.0%}", flush=True)

        exam = {"baselines": base, "arms": {}}
        for lam in LAMBDAS:
            y_tr = net_tr - lam * mae_tr
            for seed in SEEDS:
                model = B.fit(X_tr, y_tr, seed, device)
                scores = {s: B.score(model, o["x"], device) for s, o in opp.items()}

                def masks_at(bar: float) -> dict:
                    m = {s: np.zeros(len(per[s]["X"]), dtype=bool) for s in per}
                    for s, o in opp.items():
                        m[s][o["idx"][scores[s] >= bar]] = True
                    return m

                sel_scores = np.concatenate([scores[s][opp[s]["year"] == sel_year] for s in opp])
                tried = []
                for share in TAKE_SHARES:
                    bar = float(np.quantile(sel_scores, 1 - share))
                    r = C.book_year(per, masks_at(bar), sel_year, band, risk)
                    r.pop("daily")
                    tried.append({"share": share, "bar": bar, **r})
                active = [t for t in tried if t["trades"] >= MIN_TRADES] or tried
                pick = max(active, key=lambda t: t["q"])
                test = C.book_year(per, masks_at(pick["bar"]), test_year, band, risk)
                test.pop("daily")
                arm = f"lambda {lam:g} seed {seed}"
                exam["arms"][arm] = {"lam": lam, "seed": seed, "chosen": pick, "tried": tried, "test": test}
                print(f"  {arm:<22} top {pick['share']:.0%} -> {sel_year} {pick['return']:+.1%}/"
                      f"{pick['max_dd']:.0%} ({pick['trades']} tr) | {test_year} {test['return']:+.1%}/"
                      f"{test['max_dd']:.0%} Q {test['q']:+.3f} ({test['trades']} tr) "
                      f"[{(time.time() - t0) / 60:.1f}m]", flush=True)
        results[test_year] = exam

    tag = "_market" if MARKET else ""
    path = C.REPO / f"research/system10/rnd/bandit_exams{tag}_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print(f"written {path.relative_to(C.REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
