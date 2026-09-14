"""Can the book notice, on its own, that its raw material has turned?

WHAT THIS IS TRYING TO FIX

`quartile_spread.py` found the one number that separates 2026 from every research year.
The book is long the top quarter of the residual-momentum ranking and short the bottom
quarter, so the mean holding-period return of the top group minus the bottom group IS its
raw material:

    2020 +5.15%   2021 +5.89%   2022 +2.51%   2023 +5.30%   2024 +2.30%   2025 +5.47%
                                                                          2026 -1.79%

The ranking inverted. Every research year paid between +2.3% and +5.9% per cycle; the sealed
year paid -1.8%. Nothing about the parameters changed, and no parameter sweep can reach this.

THE ONE PROPERTY THAT MAKES THIS ACTIONABLE

That spread is OBSERVABLE WITH A LAG OF EXACTLY ONE HOLDING PERIOD. The targets chosen at
rebalance j are known at j; the returns they earned are known by the time rebalance j+1 comes
round. So at every rebalance the book can read its own realised spread on every cycle that
has already finished, without anyone diagnosing a regime and without reading a single price
from the future. The operator asked for a system that adapts day by day and is "totally
independent" of a human noticing. This is the honest version of that: the system measures the
thing it lives on and stands down when that thing stops paying.

THE RULE, DELIBERATELY THE SIMPLEST ONE THAT COULD WORK

    at rebalance D:  s = mean realised spread over the last K completed cycles
                     multiplier = 1.0 if s >= 0 else FLOOR
                     scale both legs and the hedge by the multiplier

Two knobs, K and FLOOR, and that is already expensive - the deflated Sharpe has to be
corrected for every one of them. No smoothing, no threshold above zero, no gradual ramp:
each of those is another knob, and the point of this test is to find out whether the IDEA
works, not to find the best-performing version of it on one sample.

WHY THE HEADLINE NUMBER HERE IS THE WALK-FORWARD ONE AND NOT THE RESEARCH TOTAL

A rule that cuts exposure after a bad stretch will always improve a backtest that contains a
bad stretch, because it was written by someone who had already seen it. That is not evidence.
The only question worth answering is whether choosing K and FLOOR using years BEFORE Y helps
in year Y, measured on years the choice could not see. If walk-forward says no, the rule is
hindsight wearing a formula and gets deleted - which is the expected outcome and the reason
this is written as an experiment rather than as a feature.

Research years only. 2026 is not read here and must not be, until this survives.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "trading-system")

import quantlab_catalog as cat                              # noqa: E402
from quantlab_catalog.paths import universe_file            # noqa: E402
from quantlab_system08 import residual as R                 # noqa: E402
from quantlab_system08 import signal as S                   # noqa: E402
from quantlab_system08.book import daily_funding, run_book  # noqa: E402
from quantlab_system08.system import HEDGE_SYMBOL, Config   # noqa: E402

# The configuration under study: the best one found in 564 trials, unchanged.
CONFIG = dict(factor="market_ex_self", window=35, lookback=18, skip=1, hold=14,
              side_fraction=0.25, min_history=365)

K_VALUES = (1, 2, 3, 4, 6)
FLOORS = (0.0, 0.5)


def compounded(series: dict[str, float], days: list[str], i: int, n: int) -> float | None:
    """Compounded return over the n days days[i-n:i]. None if the window is incomplete."""
    if i - n < 0 or i > len(days):
        return None
    acc = 1.0
    for d in days[i - n:i]:
        v = series.get(d)
        if v is None:
            return None
        acc *= (1.0 + v)
    return acc - 1.0


class Prepared:
    """Everything that does not depend on the adaptation rule, computed once.

    Built once and reused by every arm deliberately: the arms must differ in the rule and
    in nothing else, and recomputing residuals per arm is both slow and an opportunity for
    them to disagree.
    """

    def __init__(self, bars: dict, cfg: Config):
        self.cfg = cfg
        self.rets = {s: R.simple_returns(R.daily_closes(b)) for s, b in bars.items() if b}
        self.rets = {s: v for s, v in self.rets.items() if v}
        self.turnover = {s: R.daily_turnover(b) for s, b in bars.items() if b}

        factors = R.market_ex_self(sorted(self.rets))
        loads = R.residuals(self.rets, factors=factors, window=cfg.window)
        eps = R.residual_series(self.rets, loads, factors=factors)
        hedge_loads = R.residuals(self.rets, factors=R.BTC_ONLY, window=cfg.window)

        self.all_days = sorted({d for v in self.rets.values() for d in v})
        idx = {d: i for i, d in enumerate(self.all_days)}
        first = min(min(p) for p in loads.values())
        start = idx.get(first, 0)
        self.reb_days = self.all_days[start::cfg.hold]

        # The unadapted target vector and hedge at every rebalance.
        self.targets: dict[str, list] = {}
        self.hedge: dict[str, float] = {}
        for day in self.reb_days:
            vols = {s: p[day].resid_vol for s, p in loads.items() if day in p}
            if cfg.min_history:
                seasoned = S.seasoned_names(self.rets, day, cfg.min_history)
                vols = {s: v for s, v in vols.items() if s in seasoned}
            betas = {s: p[day].beta for s, p in hedge_loads.items() if day in p}
            if HEDGE_SYMBOL in self.rets:
                betas[HEDGE_SYMBOL] = 1.0
            if not vols:
                continue
            tg = S.targets_for_day(eps, vols, day, lookback=cfg.lookback, skip=cfg.skip,
                                   side_fraction=cfg.side_fraction,
                                   gross_cap=cfg.gross_cap)
            if not tg:
                self.targets[day], self.hedge[day] = [], 0.0
                continue
            self.targets[day] = tg
            self.hedge[day] = S.hedge_weight(tg, betas) * cfg.hedge_scale

        # THE OBSERVABLE. For each rebalance, the gross-weighted return its own target
        # vector actually earned over the holding period that followed it. This is the
        # book's raw material measured on the book's own positions rather than on an
        # idealised quartile, and it is UNLEVERED - a weighted average of realised
        # returns, independent of whatever exposure multiplier the rule later applies,
        # which is what stops the rule from feeding on its own output.
        self.spread: dict[str, float] = {}
        for day, tg in self.targets.items():
            if not tg:
                continue
            i = idx[day]
            num, den = 0.0, 0.0
            for t in tg:
                fwd = compounded(self.rets.get(t.symbol, {}), self.all_days,
                                 i + cfg.hold, cfg.hold)
                if fwd is None:
                    continue
                num += t.weight * fwd
                den += abs(t.weight)
            if den > 0:
                self.spread[day] = num / den

        # WHEN each spread becomes readable: the last day it consumed is i+hold-1, so it
        # is known at the rebalance that falls on index i+hold and not one day sooner.
        self.readable_on = {day: self.all_days[idx[day] + cfg.hold]
                            for day in self.spread
                            if idx[day] + cfg.hold < len(self.all_days)}

        self.funding = {}
        for s in list(self.rets) + [HEDGE_SYMBOL]:
            try:
                rows = cat.funding(s)
            except Exception:
                continue
            if rows:
                self.funding[s] = daily_funding(rows)

    def multipliers(self, k: int | None, floor: float) -> dict[str, float]:
        """The exposure multiplier at each rebalance. k=None means no adaptation.

        Only spreads whose `readable_on` day is at or before the rebalance are consulted,
        so this cannot see a return the book had not yet earned. Before k cycles have
        completed the multiplier is 1.0: a rule that stands aside for want of evidence
        would be measuring start-up, not adaptation.
        """
        if k is None:
            return {d: 1.0 for d in self.targets}
        ready = sorted(self.readable_on, key=lambda d: self.readable_on[d])
        out = {}
        for day in sorted(self.targets):
            done = [self.spread[d] for d in ready if self.readable_on[d] <= day]
            if len(done) < k:
                out[day] = 1.0
                continue
            out[day] = 1.0 if float(np.mean(done[-k:])) >= 0.0 else floor
        return out

    def run(self, k: int | None, floor: float):
        m = self.multipliers(k, floor)
        targets = {d: ([S.Target(t.symbol, t.weight * m[d], t.score, t.resid_vol)
                        for t in tg] if m[d] != 1.0 else tg)
                   for d, tg in self.targets.items()}
        hedge = {d: h * m.get(d, 1.0) for d, h in self.hedge.items()}
        traded = ([d for d in self.all_days if d >= self.reb_days[0]]
                  if self.reb_days else [])
        return run_book(traded, self.rets, targets, hedge, HEDGE_SYMBOL,
                        funding=self.funding, initial_equity=self.cfg.initial_equity,
                        gross_cap=self.cfg.gross_cap, turnover=self.turnover,
                        realistic_costs=self.cfg.realistic_costs)


def years_of(result) -> dict[str, float]:
    years, prev = defaultdict(float), None
    for d in result.days:
        base = prev if prev and prev > 0 else d.equity
        years[d.day[:4]] += (d.asset_pnl + d.hedge_pnl + d.funding_pnl - d.cost) / base
        prev = d.equity
    return {y: v for y, v in years.items() if abs(v) > 1e-9}


def rank_key(years: dict[str, float]) -> tuple:
    """Same lexicographic preference the loop uses: breadth first, then the worst year."""
    if not years:
        return (0, -9.0, -9.0)
    vals = list(years.values())
    return (sum(1 for v in vals if v > 0), round(min(vals), 3), float(np.mean(vals)))


def main(universe: str = "universe_wide.json") -> int:
    meta = json.loads(universe_file(universe).read_text(encoding="utf-8"))
    bars = {s: b for s, b in
            cat.research([str(x) for x in meta["symbols"]]).items() if b}
    prep = Prepared(bars, Config(**CONFIG))
    print(f"{universe}: {len(bars)} names, research only, "
          f"{len(prep.spread)} completed cycles measured\n")

    arms: dict[str, dict[str, float]] = {}
    order: list[tuple[str, int | None, float]] = [("baseline", None, 1.0)]
    for k in K_VALUES:
        for f in FLOORS:
            order.append((f"K={k} floor={f:g}", k, f))

    print(f"{'arm':<16}{'total':>9}{'yrs+':>7}{'worst':>9}   per year")
    for name, k, f in order:
        res = prep.run(k, f)
        ys = years_of(res)
        arms[name] = ys
        pos = sum(1 for v in ys.values() if v > 0)
        print(f"{name:<16}{res.total_return:>9.2f}{pos:>4}/{len(ys)}"
              f"{min(ys.values()):>9.3f}   "
              + " ".join(f"{y[2:]}:{v:+.2f}" for y, v in sorted(ys.items())))

    # ---- THE TEST THAT DECIDES. Choose the arm on years strictly before Y, read Y.
    print("\nWALK-FORWARD. The arm is chosen on prior years only, then the held-out year")
    print("is read. 'delta' is adapted minus baseline ON THAT YEAR - the only honest one.")
    print(f"\n{'year':<7}{'chosen arm':<16}{'adapted':>10}{'baseline':>10}{'delta':>9}")
    deltas = []
    all_years = sorted(arms["baseline"])
    for y in all_years:
        prior = [p for p in all_years if p < y]
        if len(prior) < 3:
            continue
        best = max((a for a in arms if a != "baseline"),
                   key=lambda a: rank_key({p: arms[a][p] for p in prior if p in arms[a]}))
        adapted = arms[best].get(y, 0.0)
        base = arms["baseline"].get(y, 0.0)
        deltas.append(adapted - base)
        print(f"{y:<7}{best:<16}{adapted:>10.3f}{base:>10.3f}{adapted - base:>+9.3f}")
    if deltas:
        won = sum(1 for d in deltas if d > 0)
        print(f"\nheld-out years improved: {won}/{len(deltas)}   "
              f"mean delta {float(np.mean(deltas)):+.3f}")
        print("A rule that only helps in the years that selected it is hindsight, not")
        print("adaptation. Positive here, on years the choice never saw, is the whole bar.")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
