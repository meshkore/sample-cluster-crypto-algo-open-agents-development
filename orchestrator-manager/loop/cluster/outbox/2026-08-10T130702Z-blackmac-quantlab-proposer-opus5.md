## Iteration 59 — proposal

**Module:** BEAR

**Claim:** Replacing BEAR's evolved mean-reversion dip-buy entry with a confirmed trend-reclaim entry — close crossing UP through ema_21 while di_plus leads di_minus and volume exceeds its 20-bar average, exiting when close crosses back below ema_21 or di_minus retakes di_plus — yields a forward return above the incumbent +1.12% with residual drawdown below 12.92%, because reclaim entries buy nascent bear-market rallies that have momentum and participation rather than falling-knife dips that decay to -0.20

**Killed by:** Refuted if the forward return is <= +1.12% (no improvement on the incumbent), OR the residual drawdown is >= 12.92% (no cut to the stop-loss bleed), OR the configuration takes 0 trades and stands aside rather than performing (as H-L054 did).

The ledger has exhausted the weakness-buying family for BEAR: deviation dip-buys average -0.20% in bear (recorded finding), the incumbent's +1.12% is a thin dip-buy result whose 12.92% drawdown is 10 stop-losses held into snapbacks (H-L058), tightening that hold refuted at -13.87% (H-L058), buying breakdowns took 0 trades (H-L054), and rewriting the gate failed the fit gate (H-L055). I am abandoning the mean-reversion direction rather than deepening it. The untested family is trend-reclaim: the first seed BUYS only a confirmed reclaim (close crosses up through ema_21) with directional momentum already turned (di_plus > di_minus) and volume participation above its 20-bar mean, so it enters momentum-backed bear rallies instead of falling knives; the second seed SELLS the moment that reclaim fails (close crosses back below ema_21 or di_minus retakes di_plus), matching the finding that bear bounces are brief. Because H-L058R shows all 212 forward bars route to BEAR, this entry quality is the whole system's forward return, so the improvement (if real) is measured directly against the incumbent +1.12%.

- `(close crosses above ema_21 AND di_plus > di_minus AND volume > volume_sma_20)`
- `(close crosses below ema_21 OR di_minus > di_plus)`