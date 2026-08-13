# QuantLab — what to work on next

The half-hourly check reads this file, picks the top unblocked item, does it, and
updates the file. It is a backlog with evidence attached, not a wish list: every
item says what is already measured and what would settle it.

## Where we stand (2026-08-13)

| | training | sealed 2026 |
|---|---|---|
| incumbent `itsm-h06` | +168.19%, **aborted 25.04%** 2022-04-08 | **+5.05%**, 24 trades, t +0.74 |
| candidate `itsm-h08` | +78.66%, aborted 25.05% 2022-07-08 | +6.07%, 32 trades, t +1.40 |
| `itsm-h05` (neighbour) | +29.92%, aborted | −1.54%, 31 trades |
| generation 5 (meta-label) | +149.29%, **completed**, DD 22.65% | −1.03%, 7 trades |
| buy & hold | — | −35.58% |

**The signal is real.** Buying a +1.5% intraday move while price is above its
30-day mean pays **+1.38% net per trade over 3,273 observations at t = 6.00**
across twelve assets and eight years. That is not the problem.

**The portfolio is the problem.** Hours 5 and 8 score +0.556% and +0.573% per
trade raw — statistically identical — and produce −1.54% and +6.07% through the
book. When equal signals give opposite portfolio results, the result is about
which trades got one of the three slots, not about the signal.

**The toll is the other problem.** `itsm-h08` grossed +153.51% and netted
+78.66%: costs ate half. 824 trades at 0.30% is 74.9% of capital.

## Backlog, most valuable first

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

### 4. Money management
`risk_per_trade=0.05` with a 60×ATR stop pins every position to the 30% cap, so
sizing is effectively flat and the "risk budget" does nothing. Either size by
something real (inverse volatility, signal strength, meta-label confidence) or
say plainly that it is flat. The de-leverage ramp has also never been measured
against a flat book.

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
