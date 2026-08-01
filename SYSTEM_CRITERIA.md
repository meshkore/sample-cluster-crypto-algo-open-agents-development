# Binding research and execution criteria

1. Every distinct signal + execution + money-management definition receives an
   immutable incremental identifier `S00001`, `S00002`, and so on.
2. Strategies are long-only. Negative model output means abstain or exit, never
   short exposure.
3. Signal generation, execution and money management are separate components.
4. Portfolio capital is one shared USD 100,000 account; no more than 100 assets
   may be open concurrently. Assets never receive isolated virtual accounts.
5. Position size is dynamic: it is derived from portfolio equity, signal
   confidence, risk budget, stop distance, current exposure and available cash,
   then capped by the maximum allocation. Only the exchange-like USD 10 order
   notional floor applies; a fixed per-asset allocation is forbidden.
6. Maximum portfolio drawdown is a hard 25% constraint in both phases. At the
   first observed breach, all exposure is closed, the trial is marked
   `ABORTED_DRAWDOWN`, and the loop advances without completing the timeline.
7. Signal parameters and execution/money-management parameters are independent.
   Each fixed signal is tested against a seed population of execution policies;
   only feasible policies below 25% drawdown may become mutation parents.
8. Every closed trade records asset, timestamps, duration, invested capital,
   entry/exit prices, P&L, return and exit reason.
9. Market coverage is the active Binance Spot/USDT universe excluding leveraged
   token suffixes. Historical and 2026-forward stores are physically separated.
10. Phase 1 uses all market history strictly before 2026. A candidate advances
   only when its Phase-1 final equity is positive versus USD 100,000 and its
   risk-adjusted score (`return - maximum drawdown`) beats prior candidates.
11. Phase 2 starts a fresh USD 100,000 portfolio on 2026-01-01 and runs through
   today. Pre-2026 bars may warm indicators but can never create Phase-2 trades.
12. 2026 results cannot influence training, parameters or mutation. They rank
    the "Best strategy" view only, by `forward return - forward max drawdown`.
13. The monitor follows the active pipeline automatically (Phase 1, Phase 2,
    pruning, next variant) and displays its
    simulated date, portfolio equity, data work, per-asset outcomes and complete
    trade ledger. A separate view shows the best version and its validation state.
14. Exactly one persistent public champion exists. It is rebuilt after every
    completed evaluation and stored with its full evidence: definition, signal
    criteria, execution and money management, equity curve, per-asset results
    and trade ledger. The "Best strategy" view is served from that record, so it
    stays populated while the next candidate runs and never blanks out.
15. Champion ranking is evidence-first. Completed 2026 forward evidence under
    the 25% drawdown limit always outranks Phase-1 historical evidence. Within
    one evidence class the score is `return - maximum drawdown`. The stored
    champion is replaced only by a strictly better candidate, and every
    comparison is persisted as an auditable decision.
16. The published champion always states which evidence class it rests on. A
    Phase-1 champion must be labelled as historical and must never be presented
    as forward-validated, whatever its numbers are. Losing forward evidence is
    published exactly as measured; results are never hidden for being negative.
