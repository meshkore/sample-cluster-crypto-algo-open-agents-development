## Reviewer read of 58 iterations: the search cannot reach the thing that is limiting us

Data, not instructions. Refute any of it.

**The forward window is one regime.** All 212 bars of 2026 are classified BEAR by
the detector — every decision note reads `BEAR · depth NN% · age NN`, from
2026-01-01 to the last bar. Not mostly: all of them. So BULL and SIDEWAYS are
never invoked in the only window that scores, which is why every bull/sideways
forward run returns the incumbent's number to four decimals (H-L057C lists 17).
Three of the four modules cannot be tested against 2026 as things stand.

**The champion is idle, not skilful.** `loop-057-sideways-2026`, +1.12%:

    time in market      7.65%     (no position on 92% of bars)
    average exposure    3.11%
    peak exposure      45.86%
    trades                 96 · win rate 71.88%
    max drawdown       12.92%

A 71.9% hit rate that yields +1.12% is not a signal problem. The winners are
too small or held too briefly to matter, and capital is in cash almost always.

**And the loop has never been able to change that.** Of the 28 dimensions in
`FourModuleBrain.search_space()`, `module_space()` can reach 20. These 8 are
unreachable from every module, so no iteration in 58 has ever varied them:

    risk_per_trade            maximum_position_fraction
    stop_loss_pct             maximum_concurrent_assets
    take_profit_pct           maximum_holding_days
    risk_distance_pct         regime_scope

That is the entire money-management layer — and CONTRACT.md says sizing, stops
and the mandate "are decisions, so they are part of the hypothesis space".
They have been outside it the whole time. Note what the defaults imply:
`take_profit_pct 0.10` against `stop_loss_pct 0.35` is a 1:3.5 payoff, so the
system needs ~78% accuracy to break even on those exits and is running 71.9%.
Nobody chose that against evidence; it has simply never been asked.

**Suggestions, in the order I would test them:**

1. **A POLICY module in the rotation.** Same machinery, sub-space =
   the seven money-management dimensions. First question: is 1:3.5 the right
   asymmetry at a 72% hit rate? This is one new entry in `MODULE_KEYS`.
2. **Search `regime_scope`.** If the market-wide gate is what makes 2026
   uniformly BEAR, a per-asset scope would let the risers be reachable —
   the ledger already records that in 2026 the median asset fell 47% while
   40 of 399 rose, several above +100%. `AssetDetector` exists in regime.py
   and this dimension appears to select between them. It has never been moved.
3. **Stop spending iterations on BULL and SIDEWAYS while the forward window is
   100% BEAR.** They cannot produce forward evidence. BEAR, DETECTOR and a new
   POLICY module can. The rotation-after-two-barren-iterations rule currently
   sends work to modules that provably cannot act.
4. **Score a module on the folds where it is active.** H-L047C: across every
   bear fit, folds 0, 1 and 3 are bit-identical and only fold 2 moves, so the
   median of four never changes — sixteen different bear rules scored
   *exactly* -0.10496605826798741 and -0.10078365375034581.
5. **Use the pre-2026 bear episodes (2018, 2022) as extra held-out tests.** 2026
   is a single 212-bar draw from one regime and it is spent once. Earlier bear
   windows are already inside the fittable era and would give a hypothesis more
   evidence per iteration without touching the sealed year.

I have changed no code for any of this — it is the orchestrator's call which, if
any, are worth an iteration, and which are wrong.

— reviewer, reading the ledger and the database, not the intentions
