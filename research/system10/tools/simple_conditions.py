"""S10-6b: the simplest conditions that pay, before any learning.

S10-6 found that the conditions holding 80% of the best swings are a volatility detector,
and that the worst swings live there too. The operator, 2026-09-30: *"a minimum list of
conditions, of parameters... as simple as possible... I don't want a complex trading system,
because that did not work in any of the previous cases."*

So this screens a handful of one-line conditions, every threshold a round number fixed
BEFORE the run (nothing is fitted), through the same model-free book as `conditions.py`:
three slots, a third each, enter where the condition holds, leave by 06's stop + trail or
after 384 bars, costs charged, a fresh $100,000 each year.

    T  slow trend up         06's causal uptrend bit (price only, no model)
    B  breadth >= 50%        at least half the universe is in an uptrend
    P  pull-back             price at least 3% below its 55-bar high
    V  enough movement       14-bar normalised ATR above 1%, so a swing can clear costs

Eight trials, declared here, counted in the trial ledger. The winner is chosen on
2019-2023 only and then read on 2024-2025, which it has not been chosen on.
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

from system010_conditioned_rl.features import MARKET  # noqa: E402

CHOOSE = tuple(range(2019, 2024))
CONFIRM = (2024, 2025)
COL = {name: i for i, name in enumerate(MARKET)}


def predicates(d: dict) -> dict[str, np.ndarray]:
    X = d["X"]
    ok = np.isfinite(X).all(axis=1)
    return {
        "T": ok & (d["trend"] > 0),
        "B": ok & (d["breadth"] >= 0.5),
        "P": ok & (X[:, COL["pct_below_high_55"]] <= -0.03),
        "V": ok & (X[:, COL["natr_14"]] > 0.01),
    }


TRIALS = ("T", "T&B", "T&P", "T&V", "T&B&P", "T&B&V", "B", "B&P")


def main() -> int:
    data = C.load(C.ENGINE)
    per, band, risk = data["per"], data["band"], data["risk"]
    preds = {s: predicates(d) for s, d in per.items()}
    out: dict[str, dict] = {}
    for trial in ("everywhere",) + TRIALS:
        masks = {}
        for s in per:
            m = np.isfinite(per[s]["X"]).all(axis=1)
            if trial != "everywhere":
                for part in trial.split("&"):
                    m = m & preds[s][part]
            masks[s] = m
        rows = {y: C.book_year(per, masks, y, band, risk) for y in C.BOOT_YEARS}
        share = float(np.mean([masks[s].mean() for s in per]))

        def block(years):
            daily = [v for y in years for v in rows[y]["daily"]]
            worst = min(rows[y]["return"] for y in years)
            return {"worst_year": worst, "max_dd": max(rows[y]["max_dd"] for y in years),
                    "worst_q": min(rows[y]["q"] for y in years),
                    "bootstrap": C.bootstrap(daily, worst)}

        out[trial] = {"bar_share": round(share, 4), "choose": block(CHOOSE),
                      "confirm": block(CONFIRM),
                      "annual": {y: {k: rows[y][k] for k in ("return", "max_dd", "q", "trades")}
                                 for y in rows}}
        c, f = out[trial]["choose"], out[trial]["confirm"]
        print(f"{trial:<11} bars {share:5.1%} | 2019-23 worst {c['worst_year']:+.1%} dd {c['max_dd']:.0%} "
              f"P20 {c['bootstrap']['p_year_ge_20']:.0%} | 2024-25 "
              + " ".join(f"{y}:{rows[y]['return']:+.1%}/{rows[y]['max_dd']:.0%}" for y in CONFIRM),
              flush=True)
    best = max(TRIALS, key=lambda k: (out[k]["choose"]["bootstrap"]["p_year_ge_20"],
                                      out[k]["choose"]["worst_q"]))
    payload = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "trials_declared": len(TRIALS), "choose_years": CHOOSE, "confirm_years": CONFIRM,
               "chosen_on_2019_2023": best, "result": out,
               "book": "3 slots x 1/3, stop + trail from v3-exit-010, 384-bar horizon, no model"}
    for y in out.values():
        for r in y["annual"].values():
            r.pop("daily", None)
    path = C.REPO / f"research/system10/rnd/simple_conditions_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"\nchosen on 2019-2023: {best}\nwritten {path.relative_to(C.REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
