"""The two-book combine: trend book + capitulation sleeve on shared capital.

Measured design (A64 stages 1-3b, 2026-08-28): the trend book (system 06) manages
the account and by construction never deploys more than its ceiling; the
capitulation book (system 07) rides a sleeve of the cash the trend book leaves
idle. Rules, exactly as measured:

  - the sleeve is rebalanced at each MONTH boundary to `sleeve` x combined equity;
  - each month's capitulation contribution is scaled by that month's WORST
    available-cash ratio  r_m = clip((min(cash/equity) - margin) / sleeve, 0, 1)
    - a deliberately pessimistic cap: the real book can only do better;
  - contribution is additive: combined(t) = trend(t) + carry + sleeve * r_m *
    base_m * (capit(t)/capit(month_start) - 1), so the trend book's years -
    especially 2021 - are never diluted.

This module is measurement/aggregation code: it consumes equity curves the two
backtests produce and never places orders or touches the trend book's decision
path. Off unless explicitly invoked. Long-only, research-only.
"""

from __future__ import annotations

import numpy as np

SLEEVE = 0.30
MARGIN = 0.02


def _to_arrays(points) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ts = np.array([np.datetime64(p["timestamp"]).astype("datetime64[ns]") for p in points])
    eq = np.array([p["equity"] for p in points], dtype=float)
    cash = np.array([p.get("cash", np.nan) for p in points], dtype=float)
    order = np.argsort(ts)
    return ts[order], eq[order], cash[order]


def combine_curves(trend_points, capit_points, *, sleeve: float = SLEEVE,
                   margin: float = MARGIN) -> dict:
    """Combine one window's curves. Returns return/dd/avg_rm and the combined curve.

    `trend_points`: engine curve dicts with timestamp/equity/cash (cash required -
    the cap is the whole point). `capit_points`: capitulation curve dicts with
    timestamp/equity; must cover the trend window (values are sampled at or before
    each trend timestamp).
    """
    tts, teq, tcash = _to_arrays(trend_points)
    if np.isnan(tcash).all():
        raise ValueError("trend curve carries no cash column - cannot cap the sleeve")
    cts, ceq, _ = _to_arrays(capit_points)
    if teq[0] <= 0:
        raise ValueError("trend curve starts at non-positive equity")

    t_norm = teq / teq[0]
    idx = np.searchsorted(cts, tts, side="right") - 1
    if (idx < 0).all():
        raise ValueError("capitulation curve does not cover the trend window")
    c_at = ceq[np.clip(idx, 0, len(ceq) - 1)]

    months = tts.astype("datetime64[M]")
    comb = np.empty_like(t_norm)
    carry = 0.0
    rms: list[float] = []
    for m in np.unique(months):
        sel = np.where(months == m)[0]
        i0 = sel[0]
        cash_frac = np.where(teq[sel] > 0, tcash[sel] / teq[sel], 0.0)
        if sleeve <= 0:
            r_m = 0.0
        else:
            r_m = float(np.clip((np.nanmin(cash_frac) - margin) / sleeve, 0.0, 1.0))
        rms.append(r_m)
        c_month = c_at[sel] / c_at[i0]
        base = t_norm[i0] + carry
        comb[sel] = t_norm[sel] + carry + sleeve * r_m * base * (c_month - 1.0)
        carry += sleeve * r_m * base * (c_month[-1] - 1.0)

    run_peak = np.maximum.accumulate(comb)
    return {
        "return_pct": float(comb[-1] - 1.0),
        "max_drawdown": float(np.max((run_peak - comb) / run_peak)),
        "avg_sleeve_ratio": float(np.mean(rms)),
        "curve": [{"timestamp": t, "equity": float(e)} for t, e in zip(tts, comb)],
    }


def combined_per_year(rbars, rstamps, years, signals_path: str, brain_kwargs: dict,
                      capit, *, sleeve: float = SLEEVE, margin: float = MARGIN) -> dict:
    """Per-year table for the combine: trend book via the promotion path
    (launch.per_year, keep_equity), capitulation book via its own backtest with
    the full curve. `capit` is a configured CapitulationDip (keep_full_equity is
    forced on). Returns {year: {trend..., combined...}}."""
    from system006_oracle_net_15m import launch

    capit.keep_full_equity = True
    capit_res = capit.backtest(rbars)
    trend = launch.per_year(rbars, rstamps, years, signals_path,
                            brain_kwargs=brain_kwargs, keep_equity=True)
    out: dict[int, dict] = {}
    for y in years:
        r = trend.get(y) or {}
        if not r.get("equity"):
            continue
        c = combine_curves(r["equity"], capit_res["equity"], sleeve=sleeve, margin=margin)
        out[y] = {
            "trend_return": r["return_pct"], "trend_dd": r["max_drawdown"],
            "combined_return": c["return_pct"], "combined_dd": c["max_drawdown"],
            "avg_sleeve_ratio": c["avg_sleeve_ratio"],
        }
    return out
