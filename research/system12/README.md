# System 12 - BTC regime core

Opened 2026-10-21 on the operator's go, after `research/plan_v2/classics11` showed that a plain
"equal-weight basket while BTC > its 100-day average" earns about what System 11 earns at equal risk
(+34 vs +35 a year, 2020-25), i.e. System 11's coin-ranking net adds little on top of its BTC gate.

**Hypothesis.** Technical analysis on the whole market (when to be in, how much) carries the edge; what to
hold inside the market is second order.

**Search** (`system12.py`, exhaustive, deterministic):
- regime: 22 BTC/market signals plus their pairwise mean and AND (484);
- basket: 7 options, from BTC alone to System 11's model picks;
- sizing: 4 volatility targets;
- exposure moves in steps of 25%.

**Honesty.**
- Data: point-in-time top-14 lists; signals read at the last daily close before each 4h decision.
- Costs: 0.225%/side plus impact.
- Selection: year N is read with the configurations chosen on 2019..N-1, both the single best and the average of the 20 best.
- 2026 is the forward test, never used to choose.

System 11 (research/plan_v2) keeps running unchanged as the reference and the paper book.

    python research/system12/system12.py   -> out/{results.json, REPORT.md}
