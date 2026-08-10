## Iteration 77 — proposal

**Module:** POLICY

**Claim:** Holding every detector setting, module rule tree, and per-trade sizing lever at incumbent (risk_per_trade=0.00544, maximum_position_fraction=0.102, stop_loss_pct=0.093, take_profit_pct=0.308, maximum_holding_days=4) and moving ONLY maximum_concurrent_assets from 5 to 3 will reduce forward maximum drawdown by capping peak simultaneous deployed capital at ~30% of book instead of ~50% -- attacking the correlated-aggregate-exposure channel H-L070 confirmed -- while holding forward return at or above

**Killed by:** Refuted if forward return falls below 0% (the concurrency cut starves winning trades faster than it removes drawdown) OR forward maximum drawdown does not improve versus the incumbent (the binding exposure constraint is per-position sizing, already cut by H-L070, not the concurrency count).

H-L070 (CONFIRMED) established the drawdown is driven by aggregate correlated long exposure, not single-position tails. Both refuted POLICY hypotheses attacked the wrong side: H-L068 tightened the single-position stop (didn't clear the gate) and H-L076 lengthened holding days to 20 (-6.94%). The exposure channel has one untried direct lever: maximum_concurrent_assets. H-L070 cut only risk_per_trade and maximum_position_fraction; H-L076 explicitly pinned concurrency at 5. Cutting 5->3 reduces the correlated capital one market move can touch by 40% via the exact mechanism H-L070 confirmed, without repeating either refuted exit-side or per-position sizing hypothesis. This deepens the one confirmed direction rather than reopening a dead one.

