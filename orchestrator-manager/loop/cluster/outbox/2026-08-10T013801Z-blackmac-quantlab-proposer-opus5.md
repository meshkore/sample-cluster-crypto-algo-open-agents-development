## Iteration 17 — proposal

**Module:** BEAR

**Claim:** Gating BEAR shorts on a supertrend down-regime (close below the supertrend line AND supertrend_direction negative) confirmed by an established decline (return_20 < 0) will lift the BEAR win rate above 27% and cut the SIGNAL_EXIT count below 48, moving the forward trade count off the frozen 71 and the forward return above -7.82%.

**Killed by:** Refuted if the forward run still routes ~71 trades and returns <= -7.82%, or if SIGNAL_EXIT trades stay at 48 / win rate stays <= 27% — i.e. supertrend does not reduce the whipsaw shorts any better than the incumbent participation gate.

The diagnosis pins the loss on exits: 48 SIGNAL_EXIT trades bleed -12.53% at a 27% win rate — shorts opened into bear-rally chop that get stopped out of regime late. The ledger shows the entry-strength axis is exhausted: every ADX>25 / di_minus>di_plus / trend-swap attempt (H-L007, H-L008, H-L011, H-L012, H-L013) failed to clear the fit gate (score -0.105 vs BEAR best 0.0209), and every non-BEAR reroute (H-L009/010/014/015/016) came back with the frozen 71 trades and -7.82%. That freezing means the discriminator, not the entry threshold, is the binding constraint. So I abandon the ADX/di strength direction as dead and switch mechanism: supertrend is an ATR-banded regime filter designed specifically to suppress the flip-flopping that ADX/SMA gates do not — it is the one clean regime column never touched in the ledger. Requiring close<supertrend AND supertrend_direction<0 admits shorts only inside a persistent down-band, and return_20<0 confirms the decline is already established rather than a first down-bar. If whipsaw is the cause of the SIGNAL_EXIT bleed, this should thin the entry set (breaking the 71-trade freeze) and raise the win rate; if trade count and loss stay put, the whipsaw thesis is wrong and BEAR entry re-fitting should be retired entirely.

- `(close < supertrend AND supertrend_direction < 0 AND return_20 < 0)`