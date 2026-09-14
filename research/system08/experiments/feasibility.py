"""Can this system reach the operator's mandate? The stop/go question, answered.

The mandate is +30% in EVERY calendar year. This asks two things that decide it, and it is
forensics on an already-read sealed year rather than selection - nothing here chooses a
configuration, and the answer cannot flatter the system because nothing is being fitted.

ONE. IS 2026 A SINGLE EVENT OR A DIFFERENT REGIME? Monthly, sealed year:

    Jan -7.6  Feb -4.0  Mar -2.3  Apr +2.2  May -5.3  Jun -2.1  Jul -0.9  Aug +1.0  Sep -8.9

Seven of nine months negative, losses spread across the whole year, no single crash carrying
it. This is not a drawdown the book happened to take. It is how the book now behaves.

TWO. IS -26% UNUSUAL, AND IS +30% NORMAL? A 20,000-draw block bootstrap (21-day blocks, to
keep autocorrelation) of annual returns built from the strategy's OWN research-era daily
returns - that is, the distribution of years this book produces when it is working:

    median +25.3%   p05 -12.4%   p25 +7.8%   p95 +108.9%
    P(year <= -26.1%) = 0.92%      1 in 109. 2026 is outside the working distribution.
    P(year >= +30%)   = 43.9%      FEWER THAN HALF THE YEARS.

The second number is the one that settles it. Even in the regime where this strategy works,
it clears +30% in under half of all years. The mandate is not a tuning problem or a bad
sealed year; it is outside this design's distribution and always was. The research record
agrees and always did - 2018 +8.2%, 2019 +14.9%, 2020 +13.4% and 2022 +23.0% all miss the
bar, in-sample, with every parameter chosen to flatter them.
"""
import json, sys
sys.path.insert(0,"trading-system"); sys.path.insert(0,"research/system08/experiments")
import numpy as np
from collections import defaultdict
import quantlab_catalog as cat
from quantlab_catalog.paths import universe_file
from quantlab_system08 import residual as R, signal as S
from quantlab_system08.system import Config, HEDGE_SYMBOL
from quantlab_system08.book import run_book, daily_funding
from adaptive_exposure import CONFIG, compounded

meta = json.loads(universe_file("universe_wide.json").read_text(encoding="utf-8"))
syms = [str(x) for x in meta["symbols"]]
bars = {s: b for s, b in cat.candles(syms, include_sealed=True).items() if b}
cfg = Config(**CONFIG)
rets = {s: R.simple_returns(R.daily_closes(b)) for s, b in bars.items()}
rets = {s: v for s, v in rets.items() if v}
turn = {s: R.daily_turnover(b) for s, b in bars.items() if b}
factors = R.market_ex_self(sorted(rets))
loads = R.residuals(rets, factors=factors, window=cfg.window)
eps = R.residual_series(rets, loads, factors=factors)
hl = R.residuals(rets, factors=R.BTC_ONLY, window=cfg.window)
days = sorted({d for v in rets.values() for d in v}); idx={d:i for i,d in enumerate(days)}
first = min(min(p) for p in loads.values()); reb = days[idx.get(first,0)::cfg.hold]
tg, hg = {}, {}
for day in reb:
    vols = {s: p[day].resid_vol for s,p in loads.items() if day in p}
    seas = S.seasoned_names(rets, day, cfg.min_history)
    vols = {s:v for s,v in vols.items() if s in seas}
    betas = {s: p[day].beta for s,p in hl.items() if day in p}
    if HEDGE_SYMBOL in rets: betas[HEDGE_SYMBOL]=1.0
    if not vols: continue
    t = S.targets_for_day(eps, vols, day, lookback=cfg.lookback, skip=cfg.skip,
                          side_fraction=cfg.side_fraction, gross_cap=cfg.gross_cap)
    tg[day] = t; hg[day] = (S.hedge_weight(t, betas)*cfg.hedge_scale) if t else 0.0
fund = {}
for s in list(rets)+[HEDGE_SYMBOL]:
    try: rows = cat.funding(s)
    except Exception: continue
    if rows: fund[s]=daily_funding(rows)
traded=[d for d in days if d>=reb[0]]
res = run_book(traded, rets, tg, hg, HEDGE_SYMBOL, funding=fund,
               initial_equity=cfg.initial_equity, gross_cap=cfg.gross_cap,
               turnover=turn, realistic_costs=cfg.realistic_costs)

# daily fractional return
dr=[]; prev=None
for d in res.days:
    base = prev if prev and prev>0 else d.equity
    dr.append((d.day, (d.asset_pnl+d.hedge_pnl+d.funding_pnl-d.cost)/base)); prev=d.equity

# 1) IS 2026 ONE EVENT OR THE WHOLE YEAR? monthly, sealed year.
by_m=defaultdict(float)
for day,v in dr:
    if day[:4]=="2026": by_m[day[:7]]+=v
print("2026 by month:", "  ".join(f"{m[5:]}:{v*100:+.1f}" for m,v in sorted(by_m.items())))
worst = min(by_m.values()); tot = sum(by_m.values())
print(f"2026 total {tot*100:+.1f}%   worst month {worst*100:+.1f}%   "
      f"months negative {sum(1 for v in by_m.values() if v<0)}/{len(by_m)}")

# 2) IS -26% UNUSUAL FOR THIS STRATEGY? block bootstrap of research daily returns.
res_d=[v for day,v in dr if day[:4]<"2026"]
rng=np.random.default_rng(7); B=20000; L=21; n=252
sims=[]
for _ in range(B):
    acc=1.0
    for _ in range(n//L):
        i=rng.integers(0,len(res_d)-L)
        for v in res_d[i:i+L]: acc*= (1+v)
    sims.append(acc-1)
sims=np.array(sims)
print(f"\nbootstrap of ANNUAL return from research days (20k draws, 21d blocks):")
print(f"  median {np.median(sims)*100:+.1f}%   p05 {np.percentile(sims,5)*100:+.1f}%   "
      f"p25 {np.percentile(sims,25)*100:+.1f}%   p95 {np.percentile(sims,95)*100:+.1f}%")
print(f"  P(year <= -26.1%) = {float((sims<=-0.261).mean())*100:.2f}%")
print(f"  P(year >= +30%)   = {float((sims>=0.30).mean())*100:.1f}%   <- the mandate")
