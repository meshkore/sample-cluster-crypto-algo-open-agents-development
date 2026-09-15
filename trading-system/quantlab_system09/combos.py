"""EVERY POSSIBLE INDEX: which basket of assets does our forecast actually track?

The operator's exercise, 2026-09-15: *"probar todas las combinaciones posibles de assets para
crear un índice y compararlo contra la previsión, para saber qué índice con qué assets dentro
se acerca más a nuestra previsión."*

It is a different question from the ones asked so far, and a better one. Everything before
this asked *can the model rank the universe* and then traded the ranking. This asks: **is
there a SUBSET of the universe whose aggregate direction the model can call?** Those are not
the same thing at all. A model can be useless at ordering fourteen assets against each other
and still be reliable about, say, the four large-caps moving together - and that is a
tradeable object, because an index of four names is one decision, not four.

With fourteen assets there are 2^14 - 1 = 16,383 possible baskets. That is small enough to
enumerate exhaustively, so nothing here is sampled, heuristic or greedy: every basket is
scored.

WHAT EACH BASKET IS SCORED ON
For a basket B, on each day:

    realised(B)   = the mean forward return of its members
    predicted(B)  = the mean model score of its members

and then, per research year: the rank correlation between the two, and the DIRECTIONAL hit
rate - how often predicted and realised agree in sign. Direction is what matters here: an
index you can call the direction of is an index you can be long or flat on, which is the
operator's *"si el mercado baja y estamos alineados, y si sube y estamos alineados"*.

TWO MEASUREMENT FAULTS THAT THE FIRST RUN EXPOSED, AND HOW THEY ARE FIXED

The first version of this module reported a basket with a 79.9% directional hit rate, three
and a half standard deviations clear of the field. Both halves of that number were artefacts.

1. **A forecast that is always positive scores the market's base rate.** The model predicts a
   rise on essentially every day - measured over 2026, 250 days out of 250 - so "sign of
   prediction equals sign of outcome" simply counts the days the basket rose. The field's
   median hit was 0.59 because the median basket rose on 59% of days. Nothing was being
   measured but the weather. **Fix: both series are demeaned within the window before their
   signs are compared.** The question becomes "is this basket ABOVE OR BELOW its own typical
   day, and did the model say so", which is the only version of the question a trader can act
   on, and against which a constant forecast scores exactly 50%.

2. **Requiring all fourteen assets to have data threw away five of the six years.** Fusionist
   and Worldcoin list in 2023, so a panel that keeps only days where every asset is present
   started in March 2024 - and "selection on 2021-2024" silently became "selection on nine
   months of 2024", which is why every basket's worst year equalled its mean. **Fix: each
   basket is scored on the days ITS OWN members have**, so a basket of old assets is judged
   on six years and a basket containing ACE on two, with the day count reported beside the
   score so the two are never confused.

THE TRAP THIS MODULE IS BUILT AROUND
Searching 16,383 baskets across 5 years will produce something that looks magnificent by
chance alone. With ~1,800 daily observations per year, the standard error of a hit rate is
about 1.2 points, and the best of 16,383 draws sits roughly four standard errors above the
mean of the field - about +5 points - **with no signal whatsoever**. So:

  - the field's own distribution is computed and printed, and any winner is quoted in
    standard errors above the field's median rather than as a raw number;
  - the bar is CONSISTENCY: the basket must beat 50% in every research year separately, which
    a lucky basket manages far less often than it manages a good average;
  - selection happens on 2021-2024 and 2025 is held back as an out-of-sample check INSIDE the
    research era, so the winner has to survive a year it was not chosen on before anyone
    looks at 2026 at all.

That last rule is the one that matters. It costs nothing and it is the difference between
this exercise and data mining.
"""

from __future__ import annotations

import json
import sys
from itertools import combinations

import numpy as np

from quantlab_catalog.paths import REPO_ROOT
from quantlab_system09 import features as F
from quantlab_system09 import pipeline
from quantlab_system09.index_fund import _scores_walk_forward
from quantlab_system09.train import FOLDS, RESEARCH_END_EXCLUSIVE, _fit
from quantlab_system09.policy import _apply

OUT = REPO_ROOT / "research" / "system09"
HORIZON = 30
#: Selection years, and the year held back to check the winner survives a fresh one.
PICK_YEARS = ("2021", "2022", "2023", "2024")
CHECK_YEAR = "2025"
SEALED_FROM = "2026-01-01"
#: Baskets smaller than this are single bets rather than indices, and the exercise is about
#: indices. One and two-name baskets are still scored and reported - they are just labelled.
MIN_SIZE = 1


def panel(ds, score: np.ndarray, days_from: str, days_to: str):
    """Align scores and forward returns into (days x assets) matrices, plus a validity mask.

    Days are kept when ANY asset has data; the mask records which. A basket is then scored on
    the days its own members exist, rather than on the intersection of all fourteen - which
    began in March 2024 and quietly destroyed five sixths of the record.
    """
    symbols = sorted(set(ds.symbols))
    idx = {s: i for i, s in enumerate(symbols)}
    rows: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for d, sym, sc, y in zip(ds.days, ds.symbols, score, ds.y):
        if not (days_from <= d < days_to) or not np.isfinite(sc):
            continue
        if d not in rows:
            rows[d] = (np.full(len(symbols), np.nan), np.full(len(symbols), np.nan))
        rows[d][0][idx[sym]] = sc
        rows[d][1][idx[sym]] = y
    days = sorted(rows)
    if not days:
        z = np.zeros((0, len(symbols)))
        return symbols, z, z, z, []
    P = np.array([rows[d][0] for d in days])
    R = np.array([rows[d][1] for d in days])
    V = np.isfinite(P) & np.isfinite(R)
    return symbols, np.nan_to_num(P), np.nan_to_num(R), V.astype(float), days


def score_all(P: np.ndarray, R: np.ndarray, V: np.ndarray, masks: np.ndarray,
              min_days: int = 120) -> tuple:
    """Demeaned directional agreement and correlation, for every basket at once.

    `masks` is (n_baskets x n_assets) of 0/1. Matrix products give every basket's predicted
    and realised series in one shot, which is what makes sixteen thousand baskets a second's
    work. A day counts for a basket only when ALL of its members have data there, and the
    per-basket day count comes back with the scores.

    Both series are demeaned over the window before their signs are compared, so a forecast
    that is always positive - which this model's is - scores 0.5 rather than the market's
    base rate.
    """
    avail = V @ masks.T                                   # (days x baskets) members present
    sizes = masks.sum(1)
    full = (avail == sizes[None, :])                      # every member has data that day
    counts = full.sum(0)

    pred = (P @ masks.T)
    real = (R @ masks.T)
    with np.errstate(invalid="ignore", divide="ignore"):
        pred = np.where(full, pred / np.maximum(avail, 1), np.nan)
        real = np.where(full, real / np.maximum(avail, 1), np.nan)

    pm = np.nanmean(np.where(full, pred, np.nan), axis=0)
    rm = np.nanmean(np.where(full, real, np.nan), axis=0)
    pc = pred - pm
    rc = real - rm
    agree = ((pc > 0) == (rc > 0)) & full
    hit = np.divide(agree.sum(0), np.maximum(counts, 1), dtype=float)

    pc0 = np.where(full, pc, 0.0)
    rc0 = np.where(full, rc, 0.0)
    den = np.sqrt((pc0 ** 2).sum(0) * (rc0 ** 2).sum(0))
    corr = np.divide((pc0 * rc0).sum(0), den, out=np.zeros_like(den), where=den > 0)

    thin = counts < min_days
    hit[thin] = np.nan
    corr[thin] = np.nan
    return hit, corr, counts


def main() -> int:
    print("SYSTEM 09 - EVERY POSSIBLE INDEX")
    print("  16,383 baskets, scored exhaustively. Selection on 2021-2024, checked on 2025,")
    print("  and the field's own luck is measured before any winner is believed.\n")

    ctx, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    ds = F.build(traj, ctx.funding(), horizon=HORIZON)
    score = _scores_walk_forward(ds, list(FOLDS))

    symbols, P, R, V, days = panel(ds, score, "2021-01-01", RESEARCH_END_EXCLUSIVE)
    n = len(symbols)
    print(f"  universe {n} assets, {len(days)} usable days "
          f"({days[0]} .. {days[-1]})\n")

    masks = np.array([[1 if i in c else 0 for i in range(n)]
                      for k in range(MIN_SIZE, n + 1)
                      for c in combinations(range(n), k)], dtype=float)
    print(f"  baskets {len(masks):,}")

    # --- per-year, on the selection years only -----------------------------------
    per_year_hit = {}
    for y in PICK_YEARS:
        _, Py, Ry, Vy, dy = panel(ds, score, f"{y}-01-01", f"{int(y) + 1}-01-01")
        if len(dy) < 60:
            continue
        h, _, cnt = score_all(Py, Ry, Vy, masks)
        per_year_hit[y] = h
        print(f"    {y}: {len(dy)} days, {int(np.isfinite(h).sum()):,} baskets with enough "
              f"history")
    if not per_year_hit:
        print("  no usable selection year")
        return 1

    H = np.vstack([per_year_hit[y] for y in per_year_hit])     # (years x baskets)
    # A basket must be scoreable in EVERY selection year, or it is not comparable with one
    # that is. Half the field is young assets that simply did not exist in 2021.
    usable = np.isfinite(H).all(0)
    H = np.where(np.isfinite(H), H, np.nan)
    worst = np.where(usable, np.nanmin(H, axis=0), -np.inf)
    mean = np.where(usable, np.nanmean(H, axis=0), -np.inf)
    every = usable & (np.nan_to_num(H, nan=0.0) > 0.5).all(0)

    # --- what luck alone produces in a field this size ---------------------------
    field = mean[usable]
    field_med = float(np.median(field)) if field.size else float("nan")
    field_sd = float(np.std(field)) if field.size else float("nan")
    n_days = min(len(v) for v in per_year_hit.values()) if per_year_hit else 1
    se = 0.5 / np.sqrt(max(n_days, 1))
    print(f"  comparable baskets (scoreable in every selection year): "
          f"{int(usable.sum()):,} of {len(masks):,}")
    print(f"  the field: median hit {field_med:.4f}, spread {field_sd:.4f}; "
          f"one year's standard error is {se:.4f}")
    print("  a demeaned hit rate has 0.5000 as its null - a constant forecast scores exactly "
          "that")
    print(f"  baskets above 50% in EVERY selection year: {int(every.sum()):,} "
          f"of {len(masks):,} ({every.mean():.1%})")

    order = np.argsort(-(worst + mean / 100))          # worst year first, mean as tiebreak
    print(f"\n  {'basket':<44s}{'worst yr':>9s}{'mean':>8s}{'2025':>8s}{'sigma':>7s}")
    _, P25, R25, V25, d25 = panel(ds, score, f"{CHECK_YEAR}-01-01",
                                  f"{int(CHECK_YEAR) + 1}-01-01")
    h25 = (score_all(P25, R25, V25, masks)[0] if len(d25) > 60
           else np.full(len(masks), np.nan))
    top = []
    for j in order[:12]:
        names = [symbols[i].replace("USDT", "") for i in range(n) if masks[j, i]]
        sigma = (mean[j] - field_med) / (field_sd or 1e-9)
        row = {"assets": names, "size": len(names), "worst_year": float(worst[j]),
               "mean": float(mean[j]), "check_2025": float(h25[j]), "sigma": float(sigma),
               "every_year": bool(every[j])}
        top.append(row)
        print(f"  {'+'.join(names):<44s}{worst[j]:>9.4f}{mean[j]:>8.4f}"
              f"{h25[j]:>8.4f}{sigma:>7.1f}")

    # --- the honest verdict -------------------------------------------------------
    best = top[0]
    survived = best["check_2025"] > 0.5
    print(f"\n  BEST BASKET  {'+'.join(best['assets'])}")
    print(f"    worst selection year {best['worst_year']:.4f}   mean {best['mean']:.4f}"
          f"   {best['sigma']:.1f} sigma above the field's median")
    # The bar on the held-back year is the FIELD's median, not 0.5. Beating a coin while the
    # whole field beats a coin is not evidence of anything.
    survived = best["check_2025"] > max(0.5, field_med)
    print(f"    held-back {CHECK_YEAR}: {best['check_2025']:.4f} against a field median of "
          f"{field_med:.4f}  "
          + ("SURVIVED" if survived else "FAILED - the winner does not repeat, so it was "
                                         "selection over 16,383 baskets and nothing more"))

    result = {"horizon": HORIZON, "universe": symbols, "baskets": int(len(masks)),
              "selection_years": list(per_year_hit), "check_year": CHECK_YEAR,
              "field_median": field_med, "field_sd": field_sd, "day_se": float(se),
              "baskets_every_year": int(every.sum()), "top": top,
              "best_survived_check": bool(survived)}

    if survived:
        # Only now, and only once: the sealed window, with the basket already fixed.
        x = np.hstack([ds.market, ds.ledger, ds.world])
        stop_from = f"{int(RESEARCH_END_EXCLUSIVE[:4]) - 1}-01-01"
        model, blob, _, _ = _fit(x[ds.mask(hi=stop_from)], ds.y[ds.mask(hi=stop_from)],
                                 x[ds.mask(lo=stop_from, hi=RESEARCH_END_EXCLUSIVE)],
                                 ds.y[ds.mask(lo=stop_from, hi=RESEARCH_END_EXCLUSIVE)])
        sealed_score = np.full(len(ds), np.nan)
        va = ds.mask(lo=SEALED_FROM)
        sealed_score[va] = _apply(model, blob, x[va])
        _, Ps, Rs, Vs, dsl = panel(ds, sealed_score, SEALED_FROM, "2026-12-31")
        if len(dsl) > 30:
            m = np.array([[1.0 if symbols[i].replace("USDT", "") in best["assets"] else 0.0
                           for i in range(n)]])
            hs, cs, _ = score_all(Ps, Rs, Vs, m, min_days=30)
            print(f"\n  SEALED 2026  directional accuracy {hs[0]:.4f}  "
                  f"correlation {cs[0]:+.4f}  over {len(dsl)} days")
            result["sealed"] = {"hit": float(hs[0]), "corr": float(cs[0]),
                                "days": len(dsl)}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "combos_report.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"\n  written  {OUT / 'combos_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
