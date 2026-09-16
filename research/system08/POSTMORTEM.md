# System 08 — post-mortem

**Closed 2026-09-14 by the operator's decision. Do not restart it. Read this before
designing the next strategy, because most of what follows is not about System 08.**

---

## 1. What it was

A beta-neutral residual momentum book on crypto perpetuals. Each day every name's return
was regressed on a market factor over a rolling window ending strictly before that day; the
leftover was its residual. Names were ranked cross-sectionally on their residual's recent
momentum, the top quarter bought and the bottom quarter sold, each sized inversely to its own
residual volatility, and the net factor loading hedged with BTC. Execution was charged
realistically. Research ran to 2025-12-31; 2026 was sealed.

## 2. What it did

| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | **2026 (sealed)** |
|---|---|---|---|---|---|---|---|---|
| +8.2% | +14.9% | +13.4% | +94.3% | +23.0% | +61.5% | +40.6% | +42.5% | **−26.1%** |

Research total +990% on USD 100k, Sharpe 1.153, raw t 3.32, max drawdown 34.5%.

## 3. Why it was stopped — three numbers, in order of importance

**The mandate was never inside this design's reach.** A 20,000-draw block bootstrap of annual
returns built from the strategy's own research-era daily returns — the distribution of years
it produces *when it is working* — gives:

    median +25.3%    p05 −12.4%    p25 +7.8%    p95 +108.9%
    P(year ≥ +30%) = 43.9%

Under half of all years clear the bar, in the good regime. The research record said so from
the start and nobody read it that way: 2018, 2019, 2020 and 2022 all miss +30% *in sample*,
with every parameter chosen to flatter them. **A target of "+30% every calendar year" was
incompatible with this design on day one, and eight months of work never tested that.**

**2026 was not a bad draw, it was a different distribution.** Seven of nine months negative
(Jan −7.6, Feb −4.0, Mar −2.3, Apr +2.2, May −5.3, Jun −2.1, Jul −0.9, Aug +1.0, Sep −8.9),
spread evenly, no crash carrying the year. `P(year ≤ −26.1%) = 0.92%` under the working
distribution — one in 109.

**The mechanism of failure was located exactly.** The book is long the top quarter and short
the bottom quarter, so the mean holding-period return of top minus bottom *is* its raw
material. It ran +2.30% to +5.89% per 14-day cycle in every research year and **−1.79% in
2026**. The ranking inverted. Nothing else broke.

## 4. What was tried against it, and refused

| Idea | Verdict |
|---|---|
| Funding as income | Noise: ±0.4% of equity in eight of nine years |
| Partial adjustment (Gârleanu–Pedersen) | Cost falls proportionally, return falls **faster** |
| Large-cap liquidity screen | Destroys the edge monotonically; breadth beats size |
| Volatility targeting (Barroso–Santa-Clara) | Best year has the highest vol; the failure is **directional**, not a vol event |
| Minimum listing seasoning | Fixes the backtest's composition, does nothing to 2026 |
| Stacking single-sweep winners | Worse than either pair alone |
| The BTC hedge as culprit | Every hedge scale from 0 to 2 still gives 8/8 research years |
| ~270 further parameter experiments | Zero improvement over the incumbent configuration |
| Adaptive exposure on the trailing realised spread | Walk-forward **1 of 5** held-out years, mean −3.2% |
| Same, proportional instead of on/off | Worse: 1 of 5, mean −8.0% |
| Funding **carry** as the ranking | +2.59%/cycle, 3/6 years, corr 0.176 with momentum |
| Low residual volatility as the ranking | −0.71%/cycle. Does not exist here |
| Short-horizon residual reversal | −3.30%/cycle, corr −0.598 — momentum upside down |
| Slow residual momentum (60d) | +0.66%/cycle, strictly worse |
| Momentum + carry rank blend, 7 weights | Pure momentum has the **best worst year** of all of them |

Every row has its numbers in `experiments/` and in the commit history.

## 5. The lessons, which are the only part worth carrying forward

### 5.1 Check the target against the strategy's own distribution BEFORE building

This is the expensive one. The right question on day one was not "can I make this backtest
bigger" but "what fraction of years does a design of this shape clear +30% in, even when it
works". Twenty thousand bootstrap draws answer it in ninety seconds and would have closed
System 08 in week one. **For any future strategy: bootstrap the annual-return distribution
from the research daily returns and read `P(year ≥ target)` before writing the second
experiment.** A design that clears the bar in 44% of its own good years cannot deliver it
every year, and no amount of tuning changes a distribution's shape.

### 5.2 A good backtest and a clean process are not evidence the thing will keep working

System 08 passed every integrity test that exists and still failed forward:

- **Placebo** (shuffle the scores across names, hold everything else identical): real +990%,
  placebo median −12.5%, range −61% to +33%. The signal was *real*.
- **Walk-forward** (choose the configuration on years < Y, read held-out Y): 6 of 6 positive,
  mean +47.4%, and optimism **−10.1%** — held-out years came in *better* than the years that
  selected them. The selection process was *clean*.
- **Deflated Sharpe** (Bailey & López de Prado, 1,400+ declared trials): refused it.

So the placebo said the edge is real, walk-forward said it was not overfitted, and the
strategy still lost 26% forward. **Those tests rule out self-deception. They say nothing
about whether the market keeps paying.** Do not read a clean walk-forward as a forecast.

### 5.3 A book cannot learn to detect its own regime death from a record that contains none

The most attractive idea of the whole project was that the raw material is observable one
holding period late, so the book could measure its own spread and stand down when it turned —
adaptation with no human diagnosing anything. It was refused, and the reason generalises:

> After three negative cycles, the next cycle averaged **+0.25%** against **+2.54%**
> otherwise. The detector *worked* — 2.3pp of separation on 56 observations. But +0.25% is
> **positive**. In 183 research cycles a bad stretch is a weak cycle, never a losing one;
> negative runs average 1.74 cycles, never exceed six, and the one-lag autocorrelation is
> −0.11, mildly mean-*reverting*.

A rule built to survive a persistent inversion cannot be validated on a record containing
none, and any version tuned until it rescued 2026 would have been **selected on the sealed
year**. That is the trap, and it is seductive precisely when the project is failing and the
sealed year is the only sample with the event in it. **If a defence can only be validated on
the held-out sample, it cannot be validated at all.**

### 5.4 Realistic execution is not a detail — it decides what the strategy *is*

The flat 15 bps model returned an identical 14.30x at every book size from USD 100k to
USD 50M, because it cannot see size at all. Under a square-root impact model with
liquidity-tiered spreads, participation caps and stress multipliers, the same book returns
12.28x at USD 100k, 4.63x at USD 1M, **−20% at USD 10M** and −84% at USD 50M. The capacity
ceiling existed all along; the flat rate simply could not express it. **Build the execution
model before the signal, not after.**

### 5.5 Look-ahead hides in places that are not prices

Three look-aheads were found in the cost model itself — market move, turnover and own
volatility were each read on the day being charged rather than the day before. The fix was
one helper (`_prev`) and the bug was invisible in every result until it was hunted for
deliberately. Separately, `llm_router.py` exists because a language model asked to validate a
2026 trade may simply *remember* 2026: leakage that lives in model weights, that no diff can
ever show. **Any future use of an LLM inside a backtest must route by verified knowledge
cutoff with a safety buffer, and an unverified cutoff must be unusable.**

### 5.6 On the cluster, and what the operator asked to be recorded here

The collaboration produced no usable input. Across the whole project, requests to peer agents
for literature parameters, data-source verification, code audit and design opinion returned
**zero substantive answers**, while a great deal of time went into comms plumbing. The
diagnosis from the MeshKore maintainer was that everyone built *presence* and nobody built
*reaction* — "green dot, nobody home". A related self-inflicted error is worth its own line:
for a long period the sender discarded the server's delivery acknowledgements, so 3,485
messages were reported as "sent" when nothing confirmed they had arrived, and peers were
publicly accused of ignoring work they may never have received. **Never report an outbound
message as delivered on the strength of a socket write.**

The operator's own summary, recorded verbatim in translation: *however much theory, however
many agents collaborating, in the end it was incapable of producing different results in a
trading algorithm.*

## 6. What survives and belongs to the lab, not to System 08

All of this is system-agnostic and already written:

| Asset | Where |
|---|---|
| Realistic execution: square-root impact, tiered spreads, participation cap, stress bands | `trading-system/system008_residual_momentum_ls/execution.py` |
| Deflated Sharpe / Harvey-Liu-Zhu hurdle / trial counting | `trading-system/system008_residual_momentum_ls/stats.py` |
| Walk-forward harness with optimism measurement | `experiments/walkforward.py` |
| Placebo construction (shuffle scores, hold all else) | `experiments/placebo.py` |
| Capacity curve by book size | `experiments/realism.py` |
| Signal comparison on raw material + correlation | `experiments/signal_zoo.py` |
| Feasibility bootstrap — **run this first next time** | `experiments/feasibility.py` |
| LLM knowledge-cutoff router | `trading-system/system008_residual_momentum_ls/llm_router.py` |

## 7. State of the machinery at closure

- Experiment loop: **stopped**, PID 12496 terminated 2026-09-14.
- Startup keepalive: **retired** to `meshkore-system08-loop.cmd.retired`, no longer launches.
- Wall listener: left running; it belongs to System 06.
- Nothing was ever adopted into any daemon, and no live-order, wallet or exchange-credential
  capability was ever built. That constraint was never relaxed and must never be.
