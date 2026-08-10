## Iteration 68 — proposal

**Module:** POLICY

**Claim:** Holding every detector setting and module rule tree at incumbent and moving only the exit-discipline levers — stop_loss_pct tightened to ~0.06 and maximum_holding_days cut to ~10, with all sizing/exposure caps (risk_per_trade, maximum_position_fraction, maximum_concurrent_assets) left unchanged — the 2026 forward run returns at least the incumbent +1.12% while max_drawdown stays below 15%, because 2026 is a monolithic-bear tape where per-trade forward drift is negative within 20 bars (the BEAR f

**Killed by:** Refuted if forward return falls below the incumbent +1.12%, OR max_drawdown is not reduced versus incumbent (faster exits chop recoveries more than they avoid losses), OR the trade count is so low the two levers never bind (an untested null like H-L067's SIDEWAYS run, not a result).

H-L063 already tried the broad POLICY-optimization direction — 'move the parameters to improve the walk-forward score' — and it returned -20.02% on 53 trades and is recorded dead; I am NOT re-running that. This is its opposite: not a score-maximizing sweep but a single-mechanism risk-reduction isolated to exit timing. The ledger's dominant pattern is that in this long-only 2026 tape every high-activity forward run bled (H-L064 -25.26% / 116 trades, H-L065 -17.47% / 212 trades, H-L063 -20.02% / 53 trades) while the incumbent survives at +1.12% precisely by holding little for long. The drawdown mandate has already fired once (H-L063R: floor 82,303 breached at 31.98%), so the binding scarce resource is capital, not opportunity. Tightening the stop and shortening the hold attacks exactly the leak the BEAR finding names — negative per-trade drift over the next ~20 bars — without touching entries or exposure caps, keeping the change falsifiable on drawdown and return rather than on an unfilled fit gate.

