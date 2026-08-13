# Research notebook

The durable, human-readable account of what this laboratory has explored: what
worked, what looked promising and died, and why. Append-only.

`hypotheses.jsonl` is the ledger and holds the arithmetic — every hypothesis,
its verdict, its score. This file holds the judgement the arithmetic cannot
carry: that three variations failed for the same underlying reason, that a
direction is exhausted rather than mistuned, that nobody has looked somewhere.

Written by the evolve session every tenth iteration, which is the only
participant that sees every iteration at once. Never rewritten — a process that
can edit its own account of being wrong can delete the evidence, and the
deletion looks exactly like a tidy-up.

## Iteration 87 · seeded by hand, 2026-08-11

Where the loop stands as self-review begins.

**The record.** 122 ledger entries, 102 of them loop iterations: 88 refuted, 18
confirmed, 7 inconclusive. The best result in the sealed 2026 window is
`loop-067-sideways-2026` at +1.12% on 96 trades — and that number was selected
under the contaminated rule described below, so it is not independent evidence.

**Two defects fixed today, both structural rather than about any one strategy.**

1. *The sealed window was steering the search.* Selection compared 2026 forward
   returns, the incumbent moved on that comparison, and every population is
   seeded from the incumbent. So 2026 chose the genome that shaped the next
   search, 87 times. Raised in public by `blackmac-quantlab-critic-codex` on
   iteration 87 and verified in code. Selection is now the walk-forward fold
   score; the verdict is settled before the forward window opens. See
   `H-L087-NOTE`.

2. *The proposer could not remember.* The briefing carried the last ten ledger
   entries against 88 refutations, and was then told not to repeat itself. It
   now receives a digest of all of them.

**What the record says about where to look, now that it is visible at all.**
POLICY holds the three best fold scores ever recorded (0.176, 0.128, 0.125) on
ten attempts, against BEAR's 43 attempts and a best of 0.021. Every one of those
POLICY fits collapsed in 2026 — an overfit signature, and the most interesting
open question in the ledger. Under fold-based selection this is where the search
now has the most room and the least evidence.

**Known dead ground.** Buying RSI-30 dips inside a bear regime: −0.20% over the
next 20 bars against +2.26% in a bull regime; `H-REGIME-001` traded it and
returned −8.46%. The system is long only, so "BEAR" means what to hold while the
market falls, not what to short.


## 2026-08-13T09:23:43+00:00 · generation 4, by hand

**Generation 4, hand-written: the frequency diagnosis was right and it did not help.**

The incumbent `intraday-itsm-30d` (+5.05% sealed 2026, 3 trades) was diagnosed by
forensics: its fixed 3% opening-range bar was refused 319,662 times in 2026 while the
trend filter refused only ten. The conclusion drawn was that a fixed percentage bar is
regime-dependent and the fix was to express it in units of the asset's own volatility.

That fix WORKS, and the claim is now measured rather than argued:

- Training 2018 -> lock: **+495.35%** at 20.91% drawdown, 782 trades, mandate held.
- Trades per year: 27, 68, 74, 96, 103, 96, 116, 111, 91 -- stable through bull AND
  bear years, which is exactly what a regime-neutral bar should do.
- Sealed 2026: **65 trades**, against the incumbent's 3. The frequency collapse is gone.

And the return is **-5.81%**. The decomposition is the finding: 2026 gross was
**-0.87%** and the toll on 65 round trips was **4.9%**. So the mechanism has no edge in
the 2026 tape, and trading it twenty times more often simply pays the toll twenty times
more often.

**What this kills.** The theory that the incumbent's forward weakness was a FREQUENCY
problem. It was not. Its three trades happened to be good ones; the mechanism itself
does not generalise into 2026, and making it fire more does not manufacture an edge.
Anyone proposing to rescue a configuration by making it trade more often now owes an
answer to this result.

**Second data point for the anti-prediction.** +495% training is the best training
result this laboratory has ever recorded, and it produced a loss forward. The rule
holds: training score carries no information about 2026, and a large one is not
reassuring.
