## Iteration 58 — proposal

**Module:** POLICY

**Claim:** The incumbent's +1.12% forward return comes entirely from 96 BEAR mean-reversion dip-buys whose residual 12.92% drawdown is dominated by 10 STOP_LOSS exits (-12.13%, per H-L054): in a bear tape the bounce is brief and decays to -0.20% by bar 20, so trades that are held to their stop round-trip a small early gain into a full loss. Cutting maximum_holding_days to ~5 and setting take_profit_pct tight (~3-4%) while leaving stop_loss_pct wider will harvest the snapback on a time/target exit before it

**Killed by:** Refuted if forward return is <= +1.12% on a comparable trade count (~80-110), OR if stop-loss-attributed drawdown does not fall below ~12%, OR if the shorter holding cap starves the book to 0 trades (the H-L054 failure mode: standing aside is not an improvement).

POLICY has never been touched in the ledger — the last four iterations re-read a stale run and H-L058R flags that 58 iterations optimized a layer the search cannot reach. This is genuinely fresh territory, not a deepening of a dead direction. I deliberately do NOT pull the 'system is in cash 92%' lever (maximum_concurrent_assets / maximum_position_fraction): H-L058R shows all 212 bars of 2026 route to BEAR, and the BEAR finding is that buying dips loses money, so deploying MORE capital into the only active branch scales up a losing bias, and position-fraction changes are near scale-invariant to portfolio return %. The lever that actually moves which trades win is the exit asymmetry, which POLICY owns. H-L054 already localized the damage to stop-losses on snapback entries; rather than change BEAR's entry (that path returned 0 trades), I keep the confirmed +1.12% entry and change only when it exits — force a fast time/target exit that captures the transient bounce before the bear trend reasserts and the stop fires. Falsifiable on both return and drawdown, so a scale-only artifact cannot pass it.

