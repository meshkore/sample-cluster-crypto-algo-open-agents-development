## Iteration 45 — REFUTED

**Module:** BULL

**Hypothesis:** The BULL module's frozen state is a routing defect, not an entry defect: because bull/bear are both scored on the same overlapping breadth band (0.423 vs 0.392) BEAR wins every shared bar and 67/67 trades route short. Replacing the deciding axis with a strictly mutually-exclusive directional-movement discriminant — di_plus > di_minus, gated by adx > 20 so it only fires when a trend actually exists — will emit BULL states that are disjoint-by-construction from BEAR (which requires di_minus > di_p

**Fit:** score 0.03993606773347036

**Forward 2026:** -7.11% on 67 trades

forward -7.11% on 67 trades, against incumbent -7.11%. The incumbent stands; this direction is recorded as dead.

- entry_rule: `vortex_plus > 1.316`
- exit_rule: `(42.59 > supertrend*1.0927 OR (low > supertrend*1.0927 OR close crosses below mid_55))`