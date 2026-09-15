"""THE SECOND HEAD: where does the MARKET go? One row per day, not per asset.

The ablation forced this module into existence, and the reason is structural rather than
empirical. Macro, liquidity, rates, and the crowd's sentiment are the SAME NUMBER for all
fourteen assets on any given day. A cross-sectional model - one that predicts which asset
beats which - cannot use them even in principle: a column that is constant across the
alternatives being compared carries no information about the comparison, so all it can do is
give the optimiser more places to overfit. That is exactly what the measurement showed:
adding the world block took the held-back year from +0.111 to -0.066.

So the architecture splits in two, and each half is asked only what it can answer:

    CROSS-SECTIONAL   per-asset features -> the asset's return RELATIVE to the universe
                      "which of these is better", and the evidence says chart features alone
                      are what survive out of sample here.

    MARKET DIRECTION  market-wide features -> the universe's OWN forward return
                      "is this a market to be in at all", which is where inflation, the Fed,
                      the dollar, credit spreads, the yield curve and fear-and-greed live.
                      This module.

The two compose: the market head decides how much to hold, the cross-sectional head decides
what to hold. A book is then long when the market head is positive and flat or hedged when it
is not, tilted towards whatever the cross-sectional head prefers.

WHAT MAKES THIS HARD, SAID PLAINLY
There are ~3,000 days in the record and the horizon is 30 days, so there are roughly 100
independent observations of "where the market went next". A hundred observations against a
dozen macro features is a setting in which almost anything can be made to look predictive on
the selection years, which is why this module reports the held-back year first and the
selection years second, and why the null - always long - is printed on the same screen.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from quantlab_catalog.paths import REPO_ROOT
from quantlab_system09 import features as F
from quantlab_system09 import pipeline
from quantlab_system09 import world as W
from quantlab_system09.train import DEVICE, _fit

OUT = REPO_ROOT / "research" / "system09"
HORIZON = 30
PICK = ("2021", "2022", "2023", "2024")
CHECK = "2025"


def daily(traj, ds) -> tuple[list[str], np.ndarray, np.ndarray]:
    """One row per day: the market's condition, and where the market went next.

    The market's own forward return is already computed by the feature builder as `y_market`
    - the cross-sectional mean of the forward returns - so the two heads are guaranteed to be
    describing the same universe on the same days.
    """
    seen: dict[str, tuple[int, float]] = {}
    for k, (d, ym) in enumerate(zip(ds.days, ds.y_market)):
        seen.setdefault(d, (k, float(ym)))
    days = sorted(seen)

    idx = {d: i for i, d in enumerate(traj.days)}
    greed = F._greed_daily()
    world = W.block(days)
    # The regional block: currencies, local rates and local equity, each of them daily and
    # current. This is where "an investor in Shanghai and one in Frankfurt face different
    # decisions" becomes a column rather than a sentence - and the market head is the only
    # head that can use it, because these numbers are identical across assets within a day.
    region = W.regional(days)

    rows, ys = [], []
    for n, d in enumerate(days):
        i = idx.get(d)
        if i is None or i < 200:
            continue
        cap = traj.market_cap
        ret = lambda k: (cap[i] / cap[i - k] - 1.0) if (i - k) >= 0 and cap[i - k] > 0 else 0.0
        win = [cap[t] / cap[t - 1] - 1.0 for t in range(i - 29, i + 1) if cap[t - 1] > 0]
        vol = float(np.std(win)) if len(win) > 5 else 0.0
        ath = max(cap[:i + 1]) or cap[i]
        dd_days = 0
        t = i
        while t > 0 and cap[t] < ath:
            dd_days += 1
            t -= 1
        ma200 = float(np.mean(cap[max(0, i - 199):i + 1]))
        g = greed.get(d)
        g30 = greed.get(traj.days[max(0, i - 30)])
        seg = traj.segments[i]
        seg30 = traj.segments[max(0, i - 30)]
        cash = sum(v["cash"] for v in seg.values())
        assets = sum(v["assets"] for v in seg.values())
        cash30 = sum(v["cash"] for v in seg30.values())
        assets30 = sum(v["assets"] for v in seg30.values())
        dry = cash / (cash + assets) if (cash + assets) > 0 else 0.0
        dry30 = cash30 / (cash30 + assets30) if (cash30 + assets30) > 0 else dry

        rows.append([
            ret(7), ret(30), ret(90), ret(180),
            cap[i] / ath - 1.0,
            min(dd_days, 900) / 900.0,
            vol,
            (cap[i] / ma200 - 1.0) if ma200 > 0 else 0.0,
            (g if g is not None else 50.0) / 100.0,
            ((g - g30) / 100.0) if (g is not None and g30 is not None) else 0.0,
            dry, dry - dry30,
            *world[n], *region[n],
        ])
        ys.append(seen[d][1])
    return ([d for d in days if idx.get(d, 0) >= 200][:len(rows)],
            np.asarray(rows, dtype=np.float32), np.asarray(ys, dtype=np.float32))


def _predict(model, blob, x):
    import torch
    model.eval()
    with torch.no_grad():
        t = torch.tensor((x - blob["mu"]) / blob["sd"], dtype=torch.float32, device=DEVICE)
        return model(t).cpu().numpy().ravel()


def evaluate(days, x, y) -> dict:
    d = np.array(days)
    out, preds = {}, np.full(len(y), np.nan)
    for year in (*PICK, CHECK):
        stop = str(int(year) - 1)
        tr = d < f"{stop}-01-01"
        st = (d >= f"{stop}-01-01") & (d < f"{year}-01-01")
        va = (d >= f"{year}-01-01") & (d < f"{int(year) + 1}-01-01")
        if tr.sum() < 300 or st.sum() < 60 or va.sum() < 60:
            continue
        model, blob, _, _ = _fit(x[tr], y[tr], x[st], y[st])
        p = _predict(model, blob, x[va])
        preds[va] = p
        # The comparison that matters is not "was the forecast accurate" but "would acting on
        # it have beaten simply being long", which is the null this market has always beaten.
        long_always = float(np.mean(y[va]))
        timed = float(np.mean(y[va][p > 0])) if (p > 0).any() else 0.0
        out[year] = {"hit": float(((p > 0) == (y[va] > 0)).mean()),
                     "in_market_pct": float((p > 0).mean()),
                     "mean_when_long": timed, "always_long": long_always,
                     "edge": timed - long_always}
    return out


#: The market head's feature blocks, in the order `daily()` writes them. They are priced
#: separately because "the bundle moved" is not an answer to "which of these should survive".
#: Adding the regional block moved the held-back year from +10.71% to +5.65% while making the
#: worst selection year less bad (-12.54% to -5.27%), and with ~94 independent observations in
#: the entire record neither of those movements is separable from noise. So each arm is
#: measured on its own and the reader is told the sample size on the same screen.
_N_CRYPTO = 12          # the twelve columns `daily()` writes before the world blocks
BLOCKS = {
    "crypto": (0, _N_CRYPTO),
    "liquidity": (_N_CRYPTO, _N_CRYPTO + len(W.NAMES)),
    "regional": (_N_CRYPTO + len(W.NAMES), _N_CRYPTO + len(W.NAMES) + len(W.REGIONAL_NAMES)),
}

ARMS = {
    "crypto only": ("crypto",),
    "crypto+liquidity": ("crypto", "liquidity"),
    "crypto+regional": ("crypto", "regional"),
    "everything": ("crypto", "liquidity", "regional"),
    "world only": ("liquidity", "regional"),
}


def arm_columns(x: np.ndarray, blocks) -> np.ndarray:
    return np.hstack([x[:, BLOCKS[b][0]:BLOCKS[b][1]] for b in blocks])


def ablate(days, x, y) -> dict:
    """What each block is worth to the MARKET head, on a year nobody selected on."""
    out = {}
    for name, blocks in ARMS.items():
        res = evaluate(days, arm_columns(x, blocks), y)
        picks = [r["edge"] for yr, r in res.items() if yr in PICK]
        out[name] = {"per_year": res,
                     "pick_mean_edge": float(np.mean(picks)) if picks else float("nan"),
                     "pick_worst_edge": float(np.min(picks)) if picks else float("nan"),
                     "check_edge": res.get(CHECK, {}).get("edge", float("nan")),
                     "check_hit": res.get(CHECK, {}).get("hit", float("nan")),
                     "check_in_market": res.get(CHECK, {}).get("in_market_pct", float("nan"))}
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    print("SYSTEM 09 - MARKET DIRECTION: is this a market to be in at all?")
    print(f"  one row per day, {HORIZON}-day horizon. Macro, liquidity, rates, sentiment -")
    print("  the features a cross-sectional model cannot use because they are the same for "
          "every asset.\n")
    ctx, traj = pipeline.reconstruct(end="2025-12-31", sealed=False, quiet=True, cache=True)
    ds = F.build(traj, ctx.funding(), horizon=HORIZON, target="relative")
    days, x, y = daily(traj, ds)
    print(f"  {len(days):,} days, {x.shape[1]} market-wide features, "
          f"~{len(days) // HORIZON} independent observations\n")

    res = evaluate(days, x, y)
    print(f"  {'year':<7s}{'hit':>8s}{'in market':>11s}{'when long':>12s}"
          f"{'always long':>13s}{'edge':>9s}")
    for year, r in res.items():
        flag = "  <- held back" if year == CHECK else ""
        print(f"  {year:<7s}{r['hit']:>8.3f}{r['in_market_pct']:>11.1%}"
              f"{r['mean_when_long']:>+12.2%}{r['always_long']:>+13.2%}"
              f"{r['edge']:>+9.2%}{flag}")

    if "--arms" in argv:
        print()
        print("  WHAT EACH BLOCK IS WORTH TO THE MARKET HEAD")
        print(f"    {'arm':<20s}{'pick mean':>11s}{'pick worst':>12s}"
              f"{'held-back ' + CHECK:>16s}{'in market':>11s}")
        table = ablate(days, x, y)
        for name, r in table.items():
            print(f"    {name:<20s}{r['pick_mean_edge']:>+11.2%}"
                  f"{r['pick_worst_edge']:>+12.2%}{r['check_edge']:>+16.2%}"
                  f"{r['check_in_market']:>11.1%}")
        print()
        print("    ~94 independent 30-day windows in the whole record. A gap of a few")
        print("    points between these arms is not evidence; a sign flip in the worst")
        print("    selection year is.")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "market_arms_report.json").write_text(
            json.dumps({"horizon": HORIZON, "blocks": BLOCKS, "arms": table}, indent=1),
            encoding="utf-8")

    check = res.get(CHECK, {})
    picks = [r["edge"] for yr, r in res.items() if yr in PICK]
    print(f"\n  selection years: mean edge {np.mean(picks):+.2%}, "
          f"worst {np.min(picks):+.2%}" if picks else "")
    print(f"  held-back {CHECK}: edge {check.get('edge', float('nan')):+.2%}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "market_model_report.json").write_text(
        json.dumps({"horizon": HORIZON, "features": x.shape[1], "days": len(days),
                    "per_year": res}, indent=1), encoding="utf-8")
    print(f"  written  {OUT / 'market_model_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
