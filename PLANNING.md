# QuantLab — what to work on next

The half-hourly check reads this file, picks the top unblocked item, does it, and
updates the file. It is a backlog with evidence attached, not a wish list: every
item says what is already measured and what would settle it.

## The objective changed, and the board changed with it (2026-08-15)

**Every ranking in this laboratory measured the wrong thing.** The operator
looked at the champion's equity curve — flat for three years, everything earned
in the 2021 bull run, a quarter given back from the peak, four consecutive losing
months, ending below its own high — and asked the question no measure here could
answer: *what happens to someone who buys at the top of that chart?* They lose
everything the strategy ever made. Final return only ever described the person
who bought on day one.

`quantlab_manager/quality.py` is the replacement: the geometric mean of six
properties, so each holds a veto and no amount of return buys past a catastrophic
drawdown. Growth (log-scaled, full marks at +2,000%), the return of the unluckiest
buyer, maximum drawdown, ulcer index, longest run of losing months, and the
R² of log equity against time.

It is applied in three places and there is no fourth: `hypothesis_scan.money`
fits sizing on it, `Orchestrator._publish` stamps it on every run reaching the
mirror, and the Worker crowns on it. Before this it was applied by hand in a
scratchpad script, which is to say nowhere.

**The board after re-scoring all 59 archived runs.** The previous champion drops
from first to fifth; three systems from the same night's queue take the top.

| score | era | return | worst entry | maxDD | ulcer | losing months | system |
|---|---|---|---|---|---|---|---|
| **0.482** | training | +117.8% | **−2.4%** | 11.1% | 3.7% | 2 | steady2: thr-2.5 gate-40 + meta |
| 0.469 | training | +117.8% | −2.1% | 10.0% | 3.8% | 3 | steady2: thr-2.5 gate-40 half |
| 0.454 | training | +46.2% | −1.1% | 5.1% | 1.8% | 3 | steady2: thr-2.5 gate-40 quarter |
| 0.416 | training | +353.4% | −4.6% | 18.7% | 6.9% | 3 | gate-40 thr-2.5pct *(the old champion)* |
| 0.395 | 2026 | +10.8% | −0.7% | 3.8% | 1.9% | 1 | itsm-h04-2026 *(best in the sealed year)* |

**And the correction that matters more than the ranking.** Pairing each training
row with its sealed half exposes what the training board is actually selecting:

| training score | training return | 2026 trades | 2026 return | system |
|---|---|---|---|---|
| 0.470 | +117.8% | **1** | +2.61% | steady2: thr-2.5 gate-40 + meta |
| 0.437 | +157.2% | **0** | 0.00% | steady2: thr-3.5 gate-40 |
| 0.395 | +353.4% | **3** | +2.29% | gate-40 thr-2.5pct |
| 0.254 | +161.9% | 8 | −1.28% | meta-label h6 1.5pct |
| 0.233 | +420.7% | **65** | −5.81% | gen04-vol-normalised-tsmom |
| 0.000 | +357.6% | **23** | −0.31% | twelve gate-40 slots-5 |

**Every positive 2026 figure on this board belongs to a system that barely
traded, and every system with enough sealed trades to judge is negative.** A rule
selective enough to abstain through a falling year also abstains through the part
that would have hurt it, and the resulting +2.61% on ONE trade is not a better
result than −0.31% on twenty-three — it is the absence of a result. The 2.5%
threshold "improving every property at once" in training was partly this.

The public board's crowning rule now requires 15 sealed trades, the same floor
`hypothesis_scan` and the arena apply, so the screen, the search and the page
refuse to call the same thing evidence. The current champion, `itsm-h04-2026`
(+10.77% on 23 trades), clears it.

**This is the open question, and it is not a tuning problem.** Nothing in this
laboratory has yet shown a system that trades enough in 2026 to be judged AND
makes money there. The arena is searching under exactly that constraint.

**Size is the drawdown dial and it is clean.** Halving `risk_per_trade` took the
maximum drawdown from 18.7% to 10.0% and the worst-entry return from −4.6% to
−2.1%, for less than half the total return. Quarter size reaches 5.1% drawdown.
The meta-label on top adds return rather than costing it — the only change tried
here that improves the curve and lowers the bill at the same time.

**Slots are inert; only size moves anything.** `maximum_positions=5` produced
byte-identical runs three times. The book is capital-bound: at
`risk_per_trade=0.05` with a 60×ATR stop each position is pinned to the 30% cap,
so three fill the book and a fourth can never be funded. Item 4 below is answered
in the same breath — the slot-allocation question is moot until positions shrink.

## The arena: a search that learns to search (2026-08-15)

`scripts/arena.py`, supervised by `arena-forever.sh`. It runs unattended and
calls no language model.

Each round fits a gradient-boosted regressor on every genome ever measured, ranks
fifteen hundred proposals with it, and measures the top forty — thirty chosen by
the model, ten random immigrants measured whatever it says, because a surrogate
trained only on what the surrogate chose agrees with itself for ever. What
improves is reported rather than asserted: `rank_correlation` is the Spearman
between the model's predictions for a round and what that round turned out to be,
computed before the truth was known. From an empty archive it goes +0.27 → +0.55
→ +0.73 over three rounds while best fitness climbs 0.35 → 0.48.

It optimises `quality.score` plus two terms of its own, each with a veto:

- `consistent` — the share of four contiguous two-year folds of the research era
  in which the genome scores at all. An unjudgeable fold is EXCLUDED, never
  failed; counting it against the genome made the incumbent, at 44 trades in
  eight years, fail all four.
- `judgeable` — how many trades the sealed window holds. A count, never a return.

**The finding that produced the second term is the important one.** The arena's
first live rounds found genomes at 0.535 and 0.566 — past the champion, past the
absolute floor, enduring the whole era — that would have taken between zero and
four trades in 2026. None could ever be promoted. The first fix was a training-side
proxy (round trips a year) and it did not work: leaders under it took 36–52 a year
in training and 1, 2 and 4 in the sealed window, because the gate closes the book
through a falling year. **Training frequency does not predict sealed frequency.**

## The regime gate, and four rounds of breaking my own ruler (2026-08-14)

**The one effect that survived scrutiny.** Gating entries on how far the market is
off its peak, fitted on training evidence alone, measured on four arms with the
book marked to market:

| arm | 2026 median | positive | best | clears +5.05% | corr(train,2026) | 2026 trades |
|---|---|---|---|---|---|---|
| 5 assets | −7.6% | 8% | +11.5% | 2 | −0.062 | 56 |
| 5 assets + gate | −2.3% | 23% | +8.6% | 4 | **+0.209** | 21 |
| 12 assets | −7.7% | 5% | +4.8% | **0** | −0.097 | 77 |
| **12 assets + gate** | **−2.0%** | **23%** | +8.4% | **10** | −0.048 | 29 |

The gate takes the sealed median from ≈−7.6% to ≈−2.0% and the positive rate from
5–8% to 23%, **on both universes**. A wider universe pays only with it: twelve
assets alone is the worst arm in the study, zero of 658 clearing the incumbent.

It does NOT make training predict the sealed year. The correlation reaches only
+0.209 on five assets and about zero on twelve, so **selection on training still
lands near −2% in 2026** and nothing here is promotable.

**Four rounds of the instrument being wrong, three of them found the same way.**
Every large number this laboratory has produced turned out to be a measurement
artefact, and the mechanism that survived is the one that produces small ones:

1. A stop applied to the FINAL return kept every winner that fell through it on
   the way up. Reported +167,505% over the research era.
2. The sealed tape had no history in front of it, so long trend windows sat out
   the start of a falling year because the indicator was cold. Scored as skill:
   +0.366 rank correlation between trend length and the 2026 result.
3. Equity marked on exits only, while `money` maximises return SUBJECT TO
   enduring and therefore always selects the largest stake that just barely
   survives — exactly the boundary where that understatement is largest. Every
   top row of one cycle sat between 19% and 25% against a 25% mandate, one
   reporting +15,945%. The search was overfitting the ruler, not the data.
4. A measurement script read `hs.SYMBOLS` for its "five asset" arm after that
   constant became twelve, and printed two identical rows as a comparison.

Marking the book to market cost the gate about 0.14 of its apparent correlation:
the +0.350 first reported on five assets is +0.209 once open positions are
carried at their worst.

## The measurement that closes the parameter search (2026-08-13, late)

The screen now walks an equity path and fits money management on the research era
alone, so for the first time it can be asked the question the promotion rule asks.
**1,576 systems survive the whole research era.** Their sealed 2026 results:

| | |
|---|---|
| median 2026 book | **−4.96%** |
| positive in 2026 | **3%** |
| best / worst | +5.17% / −20.27% |
| clear the incumbent's +5.05% | **1 of 1,576** |
| rank correlation, training book vs 2026 book | **−0.346** |

And the correlation is not a curiosity, it is monotone in the wrong direction:

| decile by training book | 2026 median | positive |
|---|---|---|
| top 10% | **−7.47%** | 1% |
| middle | −4.97% | 4% |
| bottom 10% | −3.77% | 0% |

Every training-observable was tested against the 2026 book and **every one of them
is negatively correlated**: return −0.346, t-statistic −0.322, mean trade −0.084,
trade count −0.158, drawdown −0.115. Nothing measurable in the research era
predicts the sealed year positively. (`hour` at −0.472 and `trend` at +0.366 are
parameters correlated *on* 2026; reading them would be fitting the locked era, so
they are diagnostics and must not become selectors.)

**This closes parameter search on the momentum family.** Not "we have not found it
yet" — 1,576 surviving systems, 3% positive, best-of +5.17%, is the distribution
you draw from noise. The incumbent's +5.05% is a sample from exactly that
distribution. The next move has to be a mechanism, and the only untried one on
this page is regime-conditional exposure (breadth was measured and failed).

Two things did get answered on the way:

- **Money management was the whole survival story.** With a third of the book per
  position, all 51 candidates that paid in both eras breached the mandate, and
  forty-odd did it in the same three months of early 2018. At 8–16% per position,
  50 of the 51 carry the full era. Backlog item 4 is answered: sizing is not a
  refinement, it is the difference between surviving and not.
- **The stop-loss mostly does not earn its place.** Once it fires on the price
  path instead of the final return, most winning configurations want no stop.

## Where we stand (2026-08-13, night)

**Nothing in the laboratory is promotable.** The rule is now written down and
checkable in `quantlab_manager.promotion`: survive the whole research era, beat
the incumbent in the sealed window, and land within 15% of the best survivor's
training return. Every system fails at least one clause.

| system | training | last active | sealed 2026 | fails on |
|---|---|---|---|---|
| `itsm-h04` | +91.63% | **2021-07-19** | **+10.77%** | dies after 3.5 of 8 years |
| `itsm-h06` (incumbent) | +168.19% | **2022-04-08** | +5.05% | aborted |
| `itsm-h08` corrected | +207.55% | **2021-07-05** | +0.03% | aborted, and loses 2026 |
| `itsm-h05` | +29.92% | 2022-08-17 | −1.54% | aborted, and loses 2026 |
| **generation 5** | +149.29% | **2025-12-15** | −1.03% | **survives the era**, loses 2026 |

That table is the whole problem in one place. **Exactly one system survives eight
years, and it is the one that loses forward. Everything that wins in 2026 died in
2021 or 2022.** The incumbent is not promotable under its own rule either.

`itsm-h04` was announced as the record on its sealed figure alone. That was wrong
and the rule now prevents it: its month-by-month table reads 21 up, 19 down, 49%
of traded months positive, and then nothing after July 2021.

**The signal is real.** Buying a +1.5% intraday move while price is above its
30-day mean pays **+1.38% net per trade over 3,273 observations at t = 6.00**
across twelve assets and eight years. That is not the problem.

**The portfolio is the problem**, and the drawdown mandate is where it shows: four
of five systems breach 25% and stop. Whatever comes next has to survive 2021-2022
first and win 2026 second, in that order, because only one of those two has ever
been achieved here.

## The finding that reorders everything below (2026-08-13, evening)

**Time in the market is the variable, and its sign flips with the regime.** Three
independent measurements say the same thing:

- Holding period: across 18 combinations of hour and threshold, a 10-day hold is
  the BEST on training (t up to 10.1) and negative on sealed 2026 in **all
  eighteen**. 7-day and 5-day are mixed. Shorter is better in 2026, longer in
  training.
- The daily close: removing it took `itsm-h08` training from +78.66% to +207.55%
  and its toll from 74.9% to 40.0% — and took its sealed 2026 from +6.07% to
  **+0.03%**. Closing every day is just less exposure, and it helped in 2026.
- The incumbent's own shape: 24 trades of 3 days each is a small amount of time
  in a −35.58% market, and that is most of why it is positive.

Training is mostly bull years; 2026 is a bear year. So **any exposure parameter
tuned on training evidence will be the wrong one for a falling market**, and
tuning it on 2026 fits the regime rather than the mechanism. This is the sharpest
form the training/sealed inversion has taken, and it is not a bug — it is what
the market did.

The useful question it raises: should exposure be *conditional* on the regime
(trend of the basket, realised volatility, breadth) rather than a constant? That
is a mechanism change, not a parameter, and nothing in this laboratory has tried
it.

## Backlog, most valuable first

### 0. Regime-conditional exposure — ANSWERED, and it is now in the search
Measured 2026-08-14. The drawdown gate moves the sealed median from ≈−7.6% to
≈−2.0% and the positive rate from 5–8% to 23% on both universes, which is the bar
this item set. It is now a fitted parameter in `money`, guarded by a thirty-trade
floor so it cannot win by refusing almost everything. Breadth remains refused.
Still untried as regime signals: realised volatility of the basket, and the
basket's own trend rather than BTC's.

### 0b. Verify the screen against the real backtester — the biggest open risk
Nothing on this page has been confirmed by a real run since the screen changed
four times. The screen is an approximation in both directions and its whole
purpose is to shortlist for a six-minute backtest that nobody has yet run on a
gated, volatility-managed, twelve-asset system. Take the best-by-training
candidate, run both halves with identical parameters except `trade_from`, and
compare. If the real backtester disagrees, everything above is arithmetic about
a model rather than about the market.

### 1. Slot allocation — why equal signals give opposite books
The single highest-leverage open question. The brain takes the "strongest"
candidate first (widest bar relative to its own volatility). Nothing has ever
tested whether that ranking beats picking at random, or by cross-sectional rank,
or by the meta-label's expected value. Settle it by replaying the same signal set
under several ranking rules and comparing the distribution, not one number.

### 2. Cut the toll without cutting the edge
Half the gross return is going to costs. Three measurable levers: raise the entry
threshold (fewer, better trades), hold longer (the 5-day hold scored better than
3-day in the grid — training +2.34% vs +1.39%), or size fewer positions larger.
Each is a one-line change and a scan away.

### 3. Twelve assets, not five — with the caveat measured
Training evidence improves a lot (t 4.35 → 6.00, 2.5× observations). Sealed 2026
gets worse (+0.294% → −0.441% per trade). Decide deliberately: more assets is the
honest universe and the 5-asset basket looks like a survivor. Requires the
indicator panels for the seven new symbols and a rerun of both halves.

### 4. Money management — ANSWERED, and it was the survival story
`risk_per_trade=0.05` with a 60×ATR stop pins every position to the 30% cap, so
sizing is effectively flat. Measured on 2026-08-13: at that size every candidate
breaches the mandate, most in early 2018; at 8–16% per position, 50 of 51 carry
the whole era. What remains is to carry this into the real strategy rather than
the screen — the screen's sizing is a flat fraction, and inverse-volatility or
signal-strength sizing is still unmeasured.

### 5. The drawdown mandate truncates the evidence
Both `itsm-h06` and `itsm-h08` abort in 2022 and have no evidence for the 45
months after. Generation 5 is the only rule that finishes the era. Consider
measuring a variant with the abort raised, purely to see the whole period, while
keeping 25% as the deployment rule.

### 6. Unresolved: `dow_cos` is the top ML feature over eight years
Predicted it would wash out on full history; it got stronger (0.133 gain). The
literature says crypto weekly effects concentrate in the 23:00–00:00 UTC Sunday
hour and vanish under intraday controls. One controlled refit settles it.

## Rules

- Both halves or nothing: a training run and a 2026 run with identical `--set`
  flags except the phase, or the monitor cannot pair them.
- Report the denominator. A winner picked from 2,688 candidates is not the same
  claim as one picked from three.
- A neighbour check before believing any grid winner. Hour 5 is why.
- Diagnose on a small slice before a long run. The hourly tape loads in 0.5s
  against three minutes for 5-minute bars.
- No headless agents, no `claude -p`, nothing outside this terminal.
