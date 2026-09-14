# System 08 — where it stands and what is next

*Rewritten whenever the answer changes. If this file disagrees with anything else in the
repository, this file is wrong and should be fixed — it is a summary, never a source.*

Last updated: **2026-09-14**

---

## What the system is, in one paragraph

A beta-neutral residual momentum book on crypto perpetuals. Each day, every name's return is
regressed on a market factor over a rolling window that ends strictly before that day; what
is left over is its residual. Names are ranked cross-sectionally on the residual's recent
momentum, the top quarter is bought and the bottom quarter sold, each sized inversely to its
own residual volatility, and whatever net factor loading remains is hedged with BTC.
Execution is charged realistically. Research runs to the end of 2025; 2026 is sealed and has
been read six times, deliberately.

## The one-line status

**It works out of sample in every year we can test — and it loses money in 2026. We do not
yet know why, and that question is the whole project right now.**

## The numbers that matter

Best configuration, realistic execution, USD 100,000 book, 32-name universe:

| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | **2026 (sealed)** |
|---|---|---|---|---|---|---|---|---|
| +8.2% | +14.9% | +13.4% | +94.3% | +23.0% | +61.5% | +40.6% | +42.5% | **−26.1%** |

Research total +990%, Sharpe 1.153, raw t 3.32, drawdown 34.5%. The deflated Sharpe
**refuses** it, correctly: 1,400+ declared trials against one sample.

**Walk-forward** — pick the configuration using only prior years, then read the held-out
year: **6 of 6 positive**, mean +47.4%, worst +0.4%, and optimism **−10.1%** (held-out years
came in *better* than the years that selected them). The selection process is clean. This
refuted the author's own written verdict that the system was overfitted.

**2026 decomposes as** signal −11.0%, hedge −7.4%, costs −8.8%.

## Against the operator's mandate

- Target is **+30% every calendar year**. Currently met in 4 of 8 research years (2021,
  2023, 2024, 2025) and missed in 2018, 2019, 2020, 2022. Not met in 2026 at all.
- Capacity ceiling measured: the book returns 12.3x at USD 100k, 4.6x at USD 1M, and
  **loses** at USD 10M. It is a small-book strategy as it stands.

## What has been measured and killed — do not re-propose

| Idea | Verdict |
|---|---|
| Funding as an edge | Noise: ±0.4% of equity in eight of nine years |
| Partial adjustment (Gârleanu–Pedersen) | Cost falls proportionally, return falls **faster** |
| Large-cap liquidity screen | Destroys the edge monotonically; breadth beats size |
| Volatility targeting (Barroso–Santa-Clara) | Our best year has our highest vol; failure is **directional** |
| Minimum listing seasoning | Fixes the backtest's composition, does nothing to 2026 |
| Stacking single-sweep winners | Worse than either pair |
| The BTC hedge as culprit | Every hedge scale from 0 to 2 still gives 8/8 research years |

Each verdict has its numbers in `experiments/` and in the commit history.

## Live machinery

| Thing | Where | State |
|---|---|---|
| Experiment loop | `research/system08/loop.py` + `program.jsonl` | running, paced at one experiment per 15 min |
| Proposer | `research/system08/propose.py` | proposes its own hypotheses; stops after 12 values per knob |
| Wall listener | `research/system06/preview/wall_listener.py` | running, restarts at log-on |
| Live page | Lab tab, `#/live/lab` | renders every experiment and arm, with the deflated verdict |

Both daemons relaunch from the per-user Startup folder. Scheduled Task registration is
refused without elevation on this machine.

---

## THE NEXT TASK

**Find out what changed in the crypto cross-section in 2026.** Not a parameter — the market.
Every code-side explanation has been measured and eliminated. Four candidates, posted to the
cluster and unanswered so far:

1. **Crowding.** Residual momentum is published; large systematic flow entered crypto perps
   in 2024–25.
2. **Correlation structure changed**, so residuals stopped being idiosyncratic.
3. **The counterparty changed.** The design named leveraged retail as the other side; ETF
   and institutional flow may mean that is no longer who we trade against.
4. **One bad stretch.** 2026 is eight and a half months.

(2) is measurable here without anyone's help — compare the cross-sectional correlation
structure and the residual share of variance in 2026 against each research year — and that
is the next thing to build.

### Queued behind it, from the operator, 2026-09-14

- **Daily adaptation.** The book must detect that its environment moved and change its own
  criteria, rather than waiting for a human to diagnose a regime. Blocked on a design
  decision: regime detection, online reweighting, or an ensemble. Asked the cluster which,
  and why it would not just be a slower form of the overfitting already avoided.
- **LLM trade validator.** At each rebalance, send a frontier model a photograph of the
  world and ask it to validate or veto. `llm_router.py` is built and enforces the rule that
  makes it honest: a model is only eligible for dates it cannot have been trained on, with a
  three-month safety buffer, and an unverified cutoff is never used. **Today only two of
  2026's nine months are coverable** by a verified model, so the useful next step is
  verifying cutoffs for older models — not building prompt plumbing.

## What is deliberately NOT being done

- No further sealed 2026 reads until something survives a new, non-parameter hypothesis.
- No live-order, wallet or exchange-credential capability, ever. Research only.
- No adoption by any daemon. Promotion is the operator's decision.
