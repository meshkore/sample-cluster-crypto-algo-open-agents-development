## Iteration 65 — proposal

**Module:** DETECTOR

**Claim:** The monolithic-BEAR classification of 2026 is a lookback artifact, not a market fact: with regime_scope held at market, shortening trend_period from 284 to 63 and confirmation_bars from 43 to 10 will let the detector respond to price action inside the 212-bar forward window, causing at least 15% of 2026 bars to resolve to SIDEWAYS or BULL, cutting the BEAR dip-buy count below the incumbent's 96 trades and lifting forward return above the incumbent's +1.12%.

**Killed by:** Refuted if 2026 still resolves >=95% to BEAR (combined BULL+SIDEWAYS bar share under 5%), which would mean the window genuinely is a downtrend and lag was never the cause; also refuted if forward return is <= +1.117% even when the classification does break up.

Every prior attempt to reach the risers failed on the wrong axis. H-L060 and H-L060R killed regime_scope as the cause (asset scope still gave zero BULL/SIDEWAYS trades and -19.35%). H-L061/H-L062 tried to hand BULL and SIDEWAYS working rules and both failed the fold-fit gate. None of them changed the detector's lookback. trend_period=284 is longer than the entire 212-bar forward window, so the trend term for every 2026 bar is computed mostly from pre-lock 2025 data and cannot turn before the tape ends; confirmation_bars=43 makes the state change even stickier. That is why 2026 is one frozen BEAR block regardless of scope or of what the risers do. Since more BEAR exposure has consistently meant worse returns (H-L060), routing marginal bars to SIDEWAYS -- which currently takes zero trades -- should remove net-losing BEAR dip-buys and improve the forward result. This is a distinct hypothesis from anything in the ledger: it moves trend_period/confirmation_bars, not scope, not the rule trees.

