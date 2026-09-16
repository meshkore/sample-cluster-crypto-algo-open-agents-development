"""Does a bad stretch of the book's raw material predict the next one?

`adaptive_exposure.py` proposed cutting exposure when the trailing realised spread turns
negative, and walk-forward refused it. This asks the prior question that explains why:
whether the spread carries any conditional information at all, and how long a bad stretch
lasts. It measures the mechanism rather than the P&L, so it cannot be gamed by a threshold.

The answer, on 183 completed cycles of research data:

    trailing K=3 negative  ->  next cycle +0.25%    (n=56)
    trailing K=3 positive  ->  next cycle +2.54%    (n=124)

So the detector IS real - it separates cycles that pay well from cycles that barely pay, by
2.3 percentage points, using nothing but information the book already had. What it does NOT
do is find losing cycles, because in the research years there are not enough of them: the
conditional mean stays POSITIVE even after three bad cycles in a row. Cutting exposure there
forfeits a small gain rather than avoiding a loss, which is exactly what the walk-forward
deltas showed.

Negative runs last 1.74 cycles on average and never exceed six. The one-lag autocorrelation
is -0.11, mildly MEAN-REVERTING. The research record simply contains no persistent inversion
of the kind 2026 shows, so a rule tuned to react to one cannot be validated here at all.

Research years only.
"""
import json, sys
sys.path.insert(0, "trading-system")
sys.path.insert(0, "research/system08/experiments")
import numpy as np
import quantlab_catalog as cat
from quantlab_catalog.paths import universe_file
from system008_residual_momentum_ls.system import Config
from adaptive_exposure import Prepared, CONFIG

meta = json.loads(universe_file("universe_wide.json").read_text(encoding="utf-8"))
bars = {s: b for s, b in cat.research([str(x) for x in meta["symbols"]]).items() if b}
p = Prepared(bars, Config(**CONFIG))
days = sorted(p.spread)
s = [p.spread[d] for d in days]
print(f"{len(s)} cycles  mean {np.mean(s):+.4f}  median {np.median(s):+.4f} "
      f"negative {sum(1 for v in s if v < 0)}/{len(s)}")

# DOES A NEGATIVE TRAILING SPREAD PREDICT THE NEXT ONE? The mechanism, measured.
print(f"\n{'K':<4}{'n neg':>7}{'next|neg':>11}{'next|pos':>11}{'gap':>10}")
for K in (1,2,3,4,6):
    neg, pos = [], []
    for i in range(K, len(s)):
        (neg if np.mean(s[i-K:i]) < 0 else pos).append(s[i])
    g = (np.mean(neg) if neg else float('nan')) - (np.mean(pos) if pos else float('nan'))
    print(f"{K:<4}{len(neg):>7}{(np.mean(neg) if neg else float('nan')):>11.4f}"
          f"{(np.mean(pos) if pos else float('nan')):>11.4f}{g:>10.4f}")

# How long do negative stretches last? A regime you can ride vs noise you chase.
runs, cur = [], 0
for v in s:
    if v < 0: cur += 1
    elif cur: runs.append(cur); cur = 0
if cur: runs.append(cur)
print(f"\nnegative runs: {len(runs)}  mean length {np.mean(runs):.2f} cycles  "
      f"max {max(runs)}  distribution {sorted(runs, reverse=True)[:12]}")
print(f"one-lag autocorrelation of the spread: {np.corrcoef(s[:-1], s[1:])[0,1]:+.4f}")
