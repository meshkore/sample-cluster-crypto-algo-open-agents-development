"""Operator idea (2026-10-20, from the Trades tab): sell a coin when it closes below its EMA 50 (or EMA 20).

An exit-only overlay on the current System 11 book: the model's bag decides what to hold exactly as in
history_v2 (models fitted on years < N, configurations chosen on earlier out-of-sample years, scaled to the
18% DD budget); on top, a held coin is sold - and not re-bought - while its price is below the moving average.
Read on 2020-2025 (research years: the honest test) AND on 2026 (the forward test - but the idea came from
looking at 2026 charts, so 2026 alone would flatter it). Costs of the extra trading are charged.

Variants: daily close vs daily EMA 20 / 50, and the 4h close vs the daily EMA 20 / 50 (faster).
Each decision uses only bars closed before it. Both seed sets; the worse counts.

    python research/plan_v2/ema_exit_test.py      -> lab/ema_exit_test.json, lab/EMA_EXIT_TEST.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from itertools import product

import numpy as np
import pandas as pd

import history_v2 as H
import lab_v2 as LV
import phase3_select as P3

SPEC = json.loads((H.HERE / "paper_v2" / "selection.json").read_text())["spec"]
OUT = H.HERE / "lab" / "ema_exit_test.json"
MD = H.HERE / "lab" / "EMA_EXIT_TEST.md"


class Quiet:
    """history_v2.preds wants a progress object; this run must not overwrite the page's progress file."""
    d: dict = {}

    def step(self, *a, **k):
        pass


def book_weights(w, spec, seeds) -> np.ndarray:
    """The scaled bag weights (4h x coins) for 2020..2026, exactly as history_v2.run_spec builds them."""
    models = LV.FAMILY_MODELS[spec["family"]]
    cfgs = [dict(tf=a, h_days=b, k=c, model=d) for a, b, c, d in product(LV.INNER["tf"], LV.INNER["h_days"], LV.INNER["k"], models)]
    half = P3.HALF_COST if spec["venue"] == "spot_long" else LV.PERP_HALF
    fund = w.fund4 if spec["venue"] != "spot_long" else None
    cache, runs = {}, []
    for cfg in cfgs:
        pr = H.preds(w, cfg["tf"], cfg["h_days"], cfg["model"], seeds, spec, cache, Quiet())
        r, Wx = H.bar_returns(w, H.book(w, spec, cfg, pr), half, fund)
        runs.append({"Wx": Wx, "d": H.to_daily(w, r)[0]})
    dy = H.to_daily(w, np.zeros(len(w.P4["grid"])))[1]
    Wall = np.zeros_like(w.P4["close"])
    for N in H.BOOK_YEARS:
        past = np.isin(dy, [y for y in H.MODEL_YEARS if y < N])
        scored = sorted(((P3.boot_sharpe_p5(x["d"][past]), i) for i, x in enumerate(runs)), reverse=True)[:H.BAG]
        Wb = np.mean([runs[i]["Wx"] for _, i in scored], axis=0)
        db = H.to_daily(w, H.bar_returns(w, Wb, half, fund)[0])[0]
        eq = np.cumprod(1 + db[past])
        dd = float((1 - eq / np.maximum.accumulate(eq)).max()) if past.any() else 1.0
        scale = min(1.0, H.DD_BUDGET / dd) if dd > 0 else 1.0
        inN = w.P4["year"] == N
        Wall[inN] = Wb[inN] * scale
    return Wall


def ema_mask(w, span: int, fast: bool) -> np.ndarray:
    """allowed[i, j]: at the close before 4h row i, was coin j at or above its daily EMA(span)?"""
    P1, P4 = w.P["1d"], w.P4
    ema = pd.DataFrame(P1["close"]).ewm(span=span, adjust=False, min_periods=span // 2).mean().values
    prev = np.r_[P4["grid"][0], P4["grid"][:-1]]                     # the decision is taken at the previous bar's close
    dk = np.searchsorted(P1["grid"], prev, side="right") - 1          # last daily bar closed by then
    e = np.where(dk[:, None] >= 0, ema[np.clip(dk, 0, None)], np.nan)
    px = np.r_[P4["close"][:1], P4["close"][:-1]] if fast else np.where(dk[:, None] >= 0, P1["close"][np.clip(dk, 0, None)], np.nan)
    with np.errstate(invalid="ignore"):
        return ~(px < e)                                             # NaN (no EMA yet) never blocks


def stats_for(w, W, half, fund) -> dict:
    r, Wx = H.bar_returns(w, W, half, fund)
    d, dy, dates = H.to_daily(w, r)
    out = {"years": {int(y): H.stats(d[dy == y]) for y in H.BOOK_YEARS},
           "research": H.stats(d[np.isin(dy, H.RESEARCH_YEARS)]), "forward": H.stats(d[dy == H.FORWARD_YEAR])}
    last = dates >= dates[-1] - 100 * P3.D1
    out["last100"] = H.stats(d[last])
    out["turnover_per_year"] = round(float(np.abs(np.diff(Wx, axis=0)).sum() / (len(H.BOOK_YEARS) - 0.2)), 1)
    out["exposure"] = round(float(Wx[np.isin(w.P4["year"], H.BOOK_YEARS)].sum(axis=1).mean()), 3)
    return out


def main() -> int:
    cut = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns").astype("int64")
    w = H.world(SPEC["cap"], int(cut))
    half = P3.HALF_COST if SPEC["venue"] == "spot_long" else LV.PERP_HALF
    fund = w.fund4 if SPEC["venue"] != "spot_long" else None
    variants = {"model only (today)": None, "daily close < EMA 20": (20, False), "daily close < EMA 50": (50, False),
                "4h close < daily EMA 20": (20, True), "4h close < daily EMA 50": (50, True)}
    res = {}
    for ss in ("s1", "s2"):
        Wall = book_weights(w, SPEC, P3.SEED_SETS[ss])
        for name, v in variants.items():
            W = Wall if v is None else Wall * ema_mask(w, *v)
            res.setdefault(name, {})[ss] = stats_for(w, W, half, fund)
            print(f"{ss} {name}: research {res[name][ss]['research']} forward {res[name][ss]['forward']}", flush=True)
    doc = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "spec": LV.spec_id(SPEC), "results": res}
    OUT.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    worse = lambda r: min(r.values(), key=lambda x: x["research"]["sharpe"])  # noqa: E731
    L = ["# EMA exit overlay test (operator idea, 2026-10-20)", "",
         f"System 11 current book ({LV.spec_id(SPEC)}); exit-only overlay; costs charged; worse of two seed sets.", "",
         "| rule | 2020-25 per year | max DD | Sharpe | " + " | ".join(str(y) for y in H.BOOK_YEARS) + " | last 100 d | trading/yr |",
         "|---|---|---|---|" + "---|" * len(H.BOOK_YEARS) + "---|---|"]
    for name, r in res.items():
        x = worse(r)
        L.append(f"| {name} | {x['research']['ann']:+.1%} | {x['research']['max_dd']:.0%} | {x['research']['sharpe']:+.2f} | "
                 + " | ".join(f"{x['years'][y].get('return', 0):+.1%}" for y in H.BOOK_YEARS)
                 + f" | {x['last100'].get('return', 0):+.1%} | {x['turnover_per_year']} |")
    MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
