## Iteration 77 — proposal

**Module:** DETECTOR

**Claim:** Flipping regime_scope from market to asset — so each symbol is routed by its own detector state instead of one aggregate breadth reading assigning all 386 assets to a single branch per bar — while holding every module rule tree, the detector's trend/slope/confirmation/breadth params, and the H-L070 exposure caps (maximum_concurrent_assets=5, maximum_position_fraction≈0.10, risk_per_trade≈0.005) fixed at incumbent, raises forward return above the incumbent +0.20% by letting individually-trending 

**Killed by:** Refuted if asset-scope forward return is ≤ incumbent (+0.20%), or if per-asset routing raises peak simultaneous deployed capital enough to breach the drawdown mandate that H-L070 attributed to aggregate correlated long exposure (i.e. the routing gain is eaten by the exposure it opens).

The entire post-L068U ledger (L070-L076) moves only the BEAR rule tree and POLICY exposure levers; all land flat-to-negative forward, best +0.20%, and the diagnosis notes the last four iterations never touched DETECTOR. Routing itself is untested. The incumbent detector is market-scoped — bull_breadth/bear_breadth are breadth fractions, and with trend_period=284 and confirmation_bars=43 it reads one slow aggregate regime. Under that scope a correlated selloff routes the whole book to BEAR, whose confirmed finding (H-REGIME-001: RSI-30 dips return -0.20% in bear vs +2.26% in bull) is that holding there loses money. Asset-scope routes each symbol by its own trend, so a symbol in an individual uptrend is owned by BULL — capturing the confirmed bull-regime edge on the subset actually trending — rather than dragged through BEAR because the market aggregate is red. This is a mechanism, not a fit: it changes who owns the bar, not the entry conditions, and the H-L070 concurrent caps bound the one real failure mode (more simultaneous BULL positions inflating correlated exposure).

