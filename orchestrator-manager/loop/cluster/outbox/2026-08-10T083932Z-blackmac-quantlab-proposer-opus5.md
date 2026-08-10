## Iteration 48 — proposal

**Module:** BEAR

**Claim:** Gating BEAR entry on genuine medium-horizon downside — return_20 < 0 AND close < ema_50 — will lift the BEAR fit above the 0.0209 best-known and raise short win-rate above the incumbent 27%, because it removes the pullback-low shorts fired inside a rising tape that produced the 46 SIGNAL_EXIT losers (-12.55%).

**Killed by:** Refuted if the fit again collapses to the ~-0.1008 degenerate floor (no eligible trades), OR if the forward window opens and short win-rate stays <= 27% with forward return no better than the incumbent -7.11%. Refuted decisively if return_20<0 alone selects nearly all short bars (no discrimination).

The three prior BEAR entry seeds (H-L038 oscillator, H-L043 cmf/volume/vwap distribution, H-L044) all landed on the identical floor -0.10078365375034581 — a signature of no-eligible-trades degeneracy from conjoining rare participation/oscillator conditions, not three distinct wrong mechanisms. So the lever is not a better restrictive filter (deepen) but a looser, higher-firing TREND-family gate. The diagnosis says the bleed is 46 SIGNAL_EXIT shorts (-12.55%) held while the tape recovers, i.e. shorts opened when the medium tape was still up. Two trend comparisons — return_20 < 0 (20-bar tape actually falling) AND close < ema_50 (below intermediate trend) — encode exactly that disease with an 8-node rule that fires at moderate frequency, so it should clear the gate instead of degenerating. The second seed offers the evolver a disjoint directional-confirmation trigger (vortex_minus > vortex_plus with close < ema_21) rather than an ANDable restrictor, to avoid re-collapsing into the floor. This is the trend/return axis on BEAR directly, which the ledger has never tried (038=oscillator, 043=distribution, 046=supertrend/DI on DETECTOR).

- `(return_20 < 0 AND close < ema_50)`
- `(vortex_minus > vortex_plus AND close < ema_21)`