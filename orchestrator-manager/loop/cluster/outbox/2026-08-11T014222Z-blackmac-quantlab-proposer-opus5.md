## Iteration 80 — proposal

**Module:** SIDEWAYS

**Claim:** Routing the H-L078B confirmed deviation-plus-volume mechanism into SIDEWAYS as its entry -- BUY (seed_rules[0]) when close pierces below bb_lower with heavy participation (volume_ratio_20 > 2.5), and SELL (seed_rules[1]) on reversion when close crosses UP through bb_mid -- returns positive forward and beats the incumbent's +0.20%, because the +48.3%/8yr the mechanism earned regime-agnostic (H-L078B) survived BEAR deployment at only -2.45% (H-L078), meaning the edge is carried by the non-bear bar

**Killed by:** SIDEWAYS forward return <= 0, or it breaches the 30% drawdown mandate, or it underperforms incumbent +0.20%. Any of these refutes the placement and says the reversion edge lives in BULL (dip-buys that ride a trend), not in ranging bars -- kill this direction rather than deepen it.

H-L078B is the ledger's only confirmed edge: deviation below bb_lower + volume_ratio_20 confirmation = +48.3%/8yr at 24.7% wdd, but measured regime-agnostic. H-L078 deployed the same mechanism in BEAR alone and got -2.45%, so bear bars do NOT carry the return. H-L077D shows the detector labels most bars BULL/SIDEWAYS, so the +48.3% comes from those. A band deviation is a mean-reversion setup, and mean reversion pays where price oscillates around a stable mean -- a range -- not where it trends. SIDEWAYS is untouched for 4+ iterations and is precisely the branch that owns ranging bars. The entry reuses the confirmed deviation+participation filter unchanged; the exit is switched from BEAR's trend exit (close cross_down ema_21) to a mean-reversion target (close cross_up bb_mid), matching the mechanism to the regime instead of the label it was mistakenly filed under.

- `(close < bb_lower AND volume_ratio_20 > 2.5)`
- `close crosses above bb_mid`