## Iteration 87 — proposal

**Module:** BEAR

**Claim:** Replacing BEAR's dip/deviation entry with a trend-reclaim entry -- BUY (seed_rules[0]) only when close crosses UP through ema_21 on elevated volume (volume_ratio_20 > 1.5) while still below the 200-day (distance_to_sma_200 < 0), and SELL (seed_rules[1]) when close crosses back down through ema_21 or rsi_14 reaches 65 -- moves BEAR's deposit contribution from -1.76% to positive and cuts the STOP_LOSS exit share below 25% of BEAR trades, because it buys confirmed recoveries in already-fallen marke

**Killed by:** Refuted if BEAR's forward deposit contribution stays <= 0, OR if STOP_LOSS remains the dominant exit (>= 40% of BEAR trades / aggregate stop P&L still net-negative by more than the incumbent's) -- i.e. the reclaim filter does not actually avoid the knife.

The diagnosis names BEAR as the loser (-1.76% of deposit, 828 trades) and localizes the bleed to 419 STOP_LOSS exits at -75.69% -- the signature of buying deviations that keep falling. Every BEAR entry in the ledger is a deviation/mean-reversion buy (H-L078 raw lower-BB pierce -2.45%, H-L083 capitulation+stoch reversal -0.39%, H-L075 generic -1.70%, H-L064 -25.26%), and all are refuted; deepening it again would repeat the ledger. The one CONFIRMED BEAR-relevant result, H-L081D, reframes the regime: the label marks markets that already fell and are recovering (+1.27% forward), so the edge is in the confirmed turn, not the dip. This entry requires the turn to actually happen (close cross_up ema_21) with genuine participation (volume_ratio_20 > 1.5) while still structurally below the 200-day (distance_to_sma_200 < 0) so it is early recovery, not a chased high. The exit exits on the turn failing (cross_down ema_21) or on recovery exhaustion (rsi_14 >= 65), which should structurally starve the STOP_LOSS bucket that the diagnosis flags.

- `(close crosses above ema_21 AND volume_ratio_20 > 1.5 AND distance_to_sma_200 < 0)`
- `(close crosses below ema_21 OR rsi_14 > 65)`