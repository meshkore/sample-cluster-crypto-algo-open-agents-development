## Iteration 58 — proposal

**Module:** BEAR

**Claim:** Sourcing BEAR shorts from failing rallies instead of fresh lows — entering on a cross_down of close through sma_20 inside a confirmed downtrend (close < sma_200 and di_minus > di_plus), and covering into oversold (rsi_14 < 30) or a new upcross of sma_20 — will cut the STOP_LOSS share below the incumbent's 10-of-96 and lift forward return above +1.12% while keeping a comparable trade count (>40 trades).

**Killed by:** Refuted if the fit stands aside (<20 forward trades, as H-L049 and H-L054 both did), OR forward return <= +1.12%, OR the STOP_LOSS exits are not fewer than the incumbent's 10 (-12.13%).

The whole 12.92% drawdown is the 10 STOP_LOSS shorts (-12.13%), which the ledger characterizes as shorts taken mid-range into snapback bounces (H-L049, H-L054) — entering near a local low that rallies into the stop. The two prior fixes both ADDED a rare-conjunction entry gate (RSI capitulation-exclusion H-L049; fresh-20-low + volume H-L054) and each returned 0 trades: restriction stands BEAR aside. So instead of restricting, this relocates entry to a frequent, better-priced event — a rally rolling over (close cross_down sma_20) inside a structurally confirmed downtrend (close < sma_200, di_minus > di_plus) — which enters into strength rather than into the snapback zone. The exit is moved AHEAD of the snapback: cover into oversold (rsi_14 < 30) or when a fresh rally starts (close cross_up sma_20), banking the down-move before the bounce can trigger the stop. Distinct from H-L053's generic evolve (now the incumbent) and from the two 0-trade restrictive gates. Entry = 10 nodes, exit = 7 nodes; both under the 24 cap, no self-comparisons, three/two joined comparisons each.

- `(close crosses below sma_20 AND close < sma_200 AND di_plus < di_minus)`
- `(rsi_14 < 30 OR close crosses above sma_20)`