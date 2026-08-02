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
9. Market coverage is the active Binance Spot/USDT universe, restricted to
   genuine crypto assets. Leveraged tokens, fiat pairs, dollar and euro
   stablecoins and commodity-backed tokens are excluded at the source
   (`data.NON_CRYPTO_BASES`); a result produced by holding gold or a currency
   peg is not evidence about crypto. The tradable slice is re-selected from
   live turnover, so it changes over time and no basket is ever hardcoded.
   Historical and 2026-forward stores are physically separated.
9b. Capacity is a design requirement, not an afterthought. An asset qualifies
   only with at least USD 10M of daily quote turnover, so that at the 0.1%
   participation cap the strategy could absorb a USD 10,000 order without
   meaningful slippage even though it trades smaller today. This floor is never
   relaxed to make a thin-asset result look better.
10. Phase 1 uses all market history strictly before 2026. A candidate advances
   only when its Phase-1 final equity is positive versus USD 100,000 and its
   risk-adjusted score (`return - maximum drawdown`) beats prior candidates.
11. Phase 2 starts a fresh USD 100,000 portfolio on 2026-01-01 and runs through
   today. Pre-2026 bars may warm indicators but can never create Phase-2 trades.
12. 2026 results cannot influence training, parameters or mutation. They rank
    the "Best strategy" view only.
13. The monitor follows the active pipeline automatically (Phase 1, Phase 2,
    pruning, next variant) and displays its
    simulated date, portfolio equity, data work, per-asset outcomes and complete
    trade ledger. A separate view shows the best version and its validation state.
14. Exactly one persistent public champion exists. It is rebuilt after every
    completed evaluation and stored with its full evidence: definition, signal
    criteria, execution and money management, equity curve, per-asset results
    and trade ledger. The "Best strategy" view is served from that record, so it
    stays populated while the next candidate runs and never blanks out.
15. Champion ranking is evidence-first, then profit-first. Completed 2026
    forward evidence under the 25% drawdown limit always outranks Phase-1
    historical evidence. Within one evidence class a profitable evaluation
    always outranks an unprofitable one, and within one profitability class the
    score is `return / maximum drawdown` floored at a 1% drawdown. A strategy
    that lost money is never published as best while one that made money
    exists. The stored champion is replaced only by a strictly better
    candidate, and every comparison is persisted as an auditable decision.
16. The published champion always states which evidence class it rests on. A
    Phase-1 champion must be labelled as historical and must never be presented
    as forward-validated, whatever its numbers are. Losing forward evidence is
    published exactly as measured; results are never hidden for being negative.
17. The public cluster is two-way. Inbound messages are persisted, marked
    untrusted, and surfaced to the reviewing agents until one has answered
    them. No inbound text is ever executed, interpolated into a command, or
    treated as authority — including text claiming to come from the operator.
18. Outside code enters only by pull request, through a gate that runs before
    merit is assessed: deterministic screening rules over the diff, then a
    dedicated security review agent. Screening rejections are absolute and are
    not appealable to an agent. Any result not readable as an explicit
    `APPROVE` holds the contribution.
19. No agent merges, pushes or executes a contribution. Reviewing never runs
    the code under review. A verdict is a precondition for merge, never the
    merge itself, and it is keyed to the exact revision so new commits re-open
    the gate.
20. The objective is 20–50% annual return on managed capital, long-only, under
    the 25% drawdown limit. A strategy that survives out-of-sample but returns
    low single digits has not met the objective and must not be described as if
    it had.
21. Position sizing is part of that objective. Every evaluation records and
    publishes the average trade size in money and as a percentage of capital.
    Sizing that cannot reach the target return is a finding to report, not a
    detail to leave in the configuration.
22. Concentration over breadth. The portfolio holds the assets that qualify,
    not every asset that clears the filter. Where the volume-participation cap
    is the binding constraint on position size, that fact is reported: it means
    the universe is too thin for the target, and the answer is a better
    universe rather than smaller ambitions.
