## Iteration 82 — proposal

**Module:** POLICY

**Claim:** Lowering take_profit_pct from 0.308 to ~0.08 -- a target reachable inside the fixed 4-day maximum_holding_days -- while holding H-L070's confirmed exposure caps (maximum_concurrent_assets=5, maximum_position_fraction~0.10, risk_per_trade~0.005), stop_loss_pct=0.093, and maximum_holding_days=4 all fixed, raises forward return above the incumbent +0.20% and lifts the take-profit-hit rate from ~0 toward a materially nonzero share of exits, by banking the confirmed deviation-plus-volume bounce (H-L0

**Killed by:** Refuted if forward return is <= +0.20%, or the take-profit-hit rate stays ~0 (TP still never binds within 4 days, so the lever did nothing), or maximum drawdown exceeds the 30% mandate.

POLICY takes no trades and has no rule trees, so the only lever is exit geometry. With maximum_holding_days=4, take_profit_pct=0.308 is inert -- a 30.8% move almost never prints in four bars, so nearly every winner exits on the time-stop and gives back the mean-reversion gain that H-L078B confirmed (+48.3% at 24.7% wdd for deviation+volume). Reversion pays on the snap back to bb_mid, not a 30% extension, so a target near the typical bounce banks it. Distinct from the two dead POLICY directions: H-L076 also tightened TP but confounded it by lengthening holding 4->20 (forward -6.94%), and H-L077 was a blind multi-parameter sweep (forward -22.20%). Here every exposure and horizon parameter is pinned at incumbent values and only the profit target moves, so the run isolates whether the wide TP -- not exposure, not holding -- is what flattens returns. Exposure-increasing directions are abandoned, not deepened: every prior attempt to add size or trades lost money, so aggregate exposure stays fixed and only where winners exit changes.

