"""Does blending funding carry into the ranking stabilise the book's raw material?

`signal_zoo.py` produced one interesting number out of four candidates: the cross-section of
funding rates delivers a positive mean spread and correlates only 0.176 with residual
momentum's. Low correlation is the property worth chasing - it is what would make a blend
survive a regime that kills one leg - so this measures the blend directly.

Rank-space blending, so the two scores are comparable without standardising anything (a
standardisation choice is another knob). One knob only: the weight on carry.

THE RESULT, on the 149 cycles where both signals exist:

    carry weight   0.0    0.2    0.3    0.4    0.5    0.7    1.0
    mean spread   4.29%  3.81%  4.44%  3.93%  3.75%  2.75%  2.46%
    worst year    1.40%  0.97%  0.14%  0.90%  0.79% -1.61% -2.87%

Pure momentum has the best worst year of any blend and is within 0.15pp of the best mean.
Carry adds nothing to the research record. It is genuinely uncorrelated, so a blend would
in principle hold up better if momentum inverted - but that is the same unprovable claim
`adaptive_exposure.py` was refused for, and it is refused here too. Recorded as negative.
"""
import json, sys
sys.path.insert(0,"trading-system"); sys.path.insert(0,"research/system08/experiments")
import numpy as np
from collections import defaultdict
import quantlab_catalog as cat
from quantlab_catalog.paths import universe_file
from quantlab_system08 import residual as R, signal as S
from signal_zoo import (compounded, daily_funding_rate, trailing_mean,
                        WINDOW, LOOKBACK, SKIP, HOLD, SIDE, MIN_HISTORY, CARRY_DAYS)

meta = json.loads(universe_file("universe_wide.json").read_text(encoding="utf-8"))
bars = {s: b for s, b in cat.research([str(x) for x in meta["symbols"]]).items() if b}
rets = {s: R.simple_returns(R.daily_closes(b)) for s, b in bars.items()}
rets = {s: v for s, v in rets.items() if v}
factors = R.market_ex_self(sorted(rets))
loads = R.residuals(rets, factors=factors, window=WINDOW)
eps = R.residual_series(rets, loads, factors=factors)
funding = {}
for s in rets:
    try: rows = cat.funding(s)
    except Exception: continue
    if rows: funding[s] = daily_funding_rate(rows)
days = sorted({d for v in rets.values() for d in v}); idx = {d:i for i,d in enumerate(days)}
first = min(min(p) for p in loads.values()); reb = days[idx.get(first,0)::HOLD]

def ranks(d):
    """Percentile rank in [0,1]; ties averaged. Rank-space so the two scores are
    comparable without standardising anything, which would be another knob."""
    o = sorted(d, key=lambda s: d[s]); n = len(o)
    return {s: (i+0.5)/n for i, s in enumerate(o)}

WEIGHTS = (0.0, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0)
cyc = defaultdict(dict)
for day in reb:
    i = idx[day]
    if i + 2*HOLD >= len(days): continue
    seas = S.seasoned_names(rets, day, MIN_HISTORY)
    vols = {s: loads[s][day].resid_vol for s in seas if s in loads and day in loads[s]}
    if len(vols) < 8: continue
    mom, car = {}, {}
    for s in vols:
        v = S.residual_momentum(eps.get(s,{}), day, lookback=LOOKBACK, skip=SKIP)
        if v is not None and np.isfinite(v): mom[s] = v
        f = funding.get(s)
        if f:
            m = trailing_mean(f, day, CARRY_DAYS)
            if m is not None: car[s] = -m
    both = set(mom) & set(car)
    if len(both) < 8: continue
    rm, rc = ranks({s: mom[s] for s in both}), ranks({s: car[s] for s in both})
    fw = {s: compounded(rets.get(s,{}), days, i+HOLD, HOLD) for s in both}
    for w in WEIGHTS:
        sc = {s: (1-w)*rm[s] + w*rc[s] for s in both}
        o = sorted(sc, key=lambda s: sc[s], reverse=True); k = max(2, int(len(o)*SIDE))
        t = [fw[s] for s in o[:k] if fw.get(s) is not None]
        b = [fw[s] for s in o[-k:] if fw.get(s) is not None]
        if len(t) >= 2 and len(b) >= 2: cyc[day][w] = float(np.mean(t))-float(np.mean(b))

ys = sorted({d[:4] for d in cyc})
print(f"{len(cyc)} cycles on names with BOTH signals\n")
print(f"{'carry wt':<10}" + "".join(f"{y[2:]:>8}" for y in ys) + f"{'mean':>9}{'worst':>9}{'yrs+':>7}")
for w in WEIGHTS:
    row = {y: float(np.mean([c[w] for d,c in cyc.items() if d[:4]==y and w in c]))
           for y in ys if any(d[:4]==y and w in c for d,c in cyc.items())}
    v = list(row.values())
    print(f"{w:<10.1f}" + "".join(f"{row.get(y,float('nan'))*100:>8.2f}" for y in ys)
          + f"{np.mean(v)*100:>9.2f}{min(v)*100:>9.2f}{sum(1 for x in v if x>0):>4}/{len(v)}")
print("\n(percent per 14-day cycle. wt 0.0 = pure momentum, 1.0 = pure carry.)")
