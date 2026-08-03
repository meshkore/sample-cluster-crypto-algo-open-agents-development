# Autonomous Crypto Quant Research Lab — Architecture

## Purpose and invariants

This repository is a research system, not a trading promise or a live execution
system. It seeks falsifiable, reproducible evidence of net edge. The following
rules are architectural boundaries:

1. Market data and experiment inputs are immutable and content-addressed.
2. Signal generation may only observe the current and earlier bars. Execution is
   delayed to the next bar's open.
3. Fees, slippage and funding are applied by the engine, never by strategy code.
4. The 2025 historical holdout is consumed only by an explicit final-test command;
   2026 is rejected by the research runner.
5. Every state transition and experiment outcome is committed before proceeding.
6. Failed and duplicate experiments remain queryable.
7. Language models may propose code or hypotheses, but deterministic code owns
   data splits, execution, accounting and metrics.

## Components

```text
ResearchDirector (persistent state machine)
  ├─ Scheduler         weighted, seeded creativity-mode allocation
  ├─ HypothesisLibrary three mechanism-led initial families
  ├─ ExperimentDesigner canonical specifications and dataset versions
  ├─ DataManager       provider interface, validation, CSV cache
  │   ├─ SyntheticProvider (offline/reproducible)
  │   └─ BinanceProvider (public REST, paginated klines)
  ├─ Backtester        next-open execution, costs, equity and trade ledger
  ├─ WalkForward      rolling train/test folds with embargo, out-of-sample rank
  ├─ Validator         minimum evidence and simple robustness stresses
  ├─ AdversarialCritic leakage/execution/fragility/evidence checks
  ├─ NoveltyArchive    structural + semantic fingerprints
  ├─ ExperimentMemory  SQLite transactions, append-only outcomes/events
  └─ Reporter          complete per-iteration artifact bundle
```

The CLI is headless and has no dependency beyond Python's standard library. This
keeps the first audited vertical easy to run. Downloaded CSV datasets use content-
addressed paths and atomic JSON lineage manifests. The import gate audits interval
continuity, UTC alignment, requested coverage, finite values and market-field bounds;
checksums are reverified before consumption. Polars, Parquet and DuckDB remain the
planned storage path once real multi-asset volume justifies them.

## Continuous supervisor and dashboard

`AutonomousService` owns three independent responsibilities: a bounded research
worker, a bounded headless development-agent worker and a read-only local web
dashboard. The workers checkpoint after every unit of work and catch failures;
macOS `launchd` owns process restart and login persistence. This creates continuous
operation without relying on a single unbounded command.

The development worker runs two independent ephemeral Codex sessions. A read-only
critic follows `ADVERSARIAL_REVIEW.md`, audits the evidence and proposes novel,
falsifiable directions in `research/advisory/LATEST.md`. A separate workspace-write
builder follows `AUTONOMOUS_DEVELOPMENT.md`, consumes that advisory and completes
one roadmap increment. The role split prevents the implementer from silently acting
as its own validator. Both turns write separate logs and exit. Timeouts prevent a wedged agent from
blocking later turns. After a turn, the supervisor exits cleanly and `launchd`
restarts it from the updated source; the next due time is recovered from SQLite so
restart cannot accidentally increase agent frequency. The agent is prohibited from trading, changing locked splits,
starting child agents or weakening validation.

The backend configuration already reserves a disabled Claude executable. Codex is
the only active backend; enabling another provider requires an explicit adapter for
its CLI and does not change the critic/builder contracts.

The dashboard binds to `127.0.0.1` by default and exposes no mutation endpoint. It
shows the current experiment and the best promoted champion only. When no strategy
has passed validation it labels the highest-scoring rejected/unvalidated candidate
as such instead of implying it is tradable. Historical experiments remain available
to the novelty archive but are deliberately absent from the primary UI.

## State and failure model

The states are `OBSERVE → RESEARCH → IDEATE → SELECT → DESIGN → IMPLEMENT → TEST
→ VALIDATE → CRITIQUE → COMPARE → EVOLVE → DOCUMENT`. SQLite stores the current
state, cycle and JSON context. Each transition is a separate transaction and an
event is appended to the audit log. On restart, the same state is re-entered; all
handlers are idempotent through stable experiment and iteration identifiers.

`DOCUMENT` writes into a temporary iteration directory and atomically renames it.
The database is then advanced to the next cycle. A process failure therefore
leaves either the previous complete report or a safely repeatable state.

## Data contracts and temporal safety

`Bar` is timestamped at interval open and contains OHLCV plus optional market
microstructure fields. Providers return bars in strict increasing order. Validation
rejects duplicates, impossible OHLC values, negative volumes and any bar at or
after the configured future lock. Dataset identity schema `quantlab-bars-v2` covers
all optional market fields; historical v1 experiment identifiers remain preserved.

Strategies return a target exposure after bar *t* closes. The backtester fills a
changed target at bar *t+1* open with adverse slippage and commission. Mark-to-
market then uses that bar's open-to-close return. This convention is intentionally
conservative and testable.

2026 data is not destroyed or treated as ordinary research data. It is stored under
an isolated `forward` root accepted only by `ForwardDataManager`. Research data still
fails closed at the 2026 boundary. A promoted, frozen strategy may be shadow-evaluated
from 2026-01-01 through the last complete UTC day; those results cannot feed the
scheduler, validator, mutation logic or champion selection.

## Strategy identity, execution and portfolio

Every unique combination of signal criteria, execution policy and money-management
policy receives an SQLite-generated identifier such as `S00013`. Experiment labels
may change, but the strategy hash prevents the same definition receiving another
number. Legacy experiments are migrated without deletion.

The signal component outputs only long authorization/confidence. The execution
component independently converts confidence and a one-percent risk budget into
notional using stop distance, capped at 25 percent of an asset sleeve. It fills at
the next open, applies adverse costs, resolves stop before take-profit when both are
touched, and records every completed trade. Negative signals are clamped to flat;
short positions are structurally impossible.

The default portfolio has USD 100,000, USD 1,000 minimum asset sleeves and at most
100 concurrent assets. Forward reports include portfolio equity, per-asset returns,
capital preservation, win/loss counts and the full trade ledger.

## Universe acquisition

The data worker refreshes Binance `/api/v3/exchangeInfo`, selects active Spot/USDT
symbols and excludes standard leveraged-token suffixes. It incrementally downloads
daily history for every catalogued symbol, content-addresses passing datasets and
separately stores 2026 forward bars. Errors are retained per symbol and retried.

## Selection: which window ranks a candidate

Phase 1 sweeps parameters across 2017-2025 and, until now, ranked that sweep on
the same 2017-2025 bars. Fitting and selection read one dataset, so the ranking
measured memorisation. Measured against 2026 outcomes the Phase-1 rank correlated
+0.06 with forward rank across 216 paired runs, which is what picking at random
looks like.

`walkforward.py` supplies the alternative. `rolling_folds` cuts a history window
into consecutive train/test pairs separated by a 21-day embargo, with boundaries
derived from the calendar and the arguments alone so no plan can be tuned after
seeing results. `WalkForwardEvaluator` simulates each fold from `train_start`
but passes `trading_start=test_start`, so indicators warm on training bars while
the first fill is held back to the scored window. That is the same separation
Phase 2 applies at the 2026 lock.

`evaluate_folds` summarises the test folds by median score rather than mean,
because one spectacular fold is the artefact the previous ranking kept
promoting. A candidate is eligible to parent a mutation only with at least three
folds, profitability in at least half of them, and no fold that breached the 25%
drawdown stop; criterion 7 already barred a breached trial from parenting, and
this applies that rule per fold. `ExecutionOptimizer` prefers an eligible
walk-forward parent and falls back to the previous in-sample query only for a
family with no fold evidence yet.

`rank_correlation` is the instrument the laboratory lacked: the same Spearman
measure that caught the old protocol, so its replacement can be held to it.
`quantlab walkforward` prints the fold plan and both correlations side by side.
The 2026 numbers it reads rank the two protocols against each other and nothing
else; criterion 12 keeps them out of training, parameters and mutation, and the
diagnostic never writes.

This changes which candidate gets promoted. It does not add return, and its
effect is only visible once enough forward runs accumulate to re-measure the
correlation.

## Experiment identity and novelty

An experiment specification is canonical JSON. Its SHA-256 hash covers the
hypothesis, dataset version, parameters, assets, periods, cost model and engine
version. A second structural fingerprint normalizes numeric parameter values to
detect related strategies; token Jaccard similarity supplies a transparent
semantic approximation. Exact duplicates are not rerun.

## Security and operational scope

The Binance adapter uses only public market-data endpoints. There is no key
handling, order endpoint or live trading path. Network downloads are explicit.
Loops require a finite cycle or time limit. SQLite uses foreign keys and WAL mode.

## Key decisions

- **SQLite first:** transactional, inspectable and zero-configuration. PostgreSQL
  becomes useful only for concurrent workers.
- **Standard-library vertical:** minimizes hidden behavior in the correctness
  baseline. Optimized numerical/storage dependencies come after golden tests.
- **Long/flat MVP:** eliminates leverage and short accounting ambiguity while the
  engine is established. The interfaces already represent signed exposure.
- **Synthetic first cycle:** validates orchestration offline; it is never evidence
  of market profitability and is labeled as such in reports.
