# Autonomous development contract

You are one bounded worker in a continuously supervised development loop for this
repository. Complete exactly one useful roadmap increment per invocation.

## Required procedure

1. Read `ARCHITECTURE.md`, `ROADMAP.md`, `research/STATE.md`, test results and the
   current source before choosing work.
   `SYSTEM_CRITERIA.md` is binding and must also be read before any change.
2. Read every advisory in `research/advisory/` that is present:
   `OPUS.md` and `SONNET.md` are two independent reviews of the same evidence,
   produced by Claude Opus 5 and Claude Sonnet 5 running the same contract on
   different models. Neither overrides the other. `LATEST.md` is a retired
   Codex advisory; read it only if it is newer than both. Where the reviewers
   disagree, say so explicitly and pick the reading the evidence supports.
3. Inspect prior experiment and development records. Do not repeat completed work.
4. Treat the critic's `MUST_FIX_NEXT` as the default task. Depart from it only when
   repository evidence proves another task is safer or more valuable, and record why.
5. Choose the highest-value safe task that advances trustworthy data, backtesting,
   validation, research diversity, reporting or dashboard quality.
6. Implement it completely, including migrations and tests when appropriate.
7. Run focused tests and then the full test suite.
8. Update architecture/roadmap documentation truthfully.
9. End after this one increment so the supervisor can checkpoint and restart you.

## Public evidence contract

The live monitor is the project's public face. Two views must always be true and
populated: the active testing strategy and the best strategy.

- After any change that produces or ranks results, confirm the champion is still
  published: `src/quantlab/champion.py` owns the record, `publish_champion()` in
  `src/quantlab/autonomous.py` refreshes it after every completed evaluation, and
  `DashboardData.snapshot()` serves it as `best_strategy` plus `champion_record`.
- The best-strategy view must ship its complete evidence — definition, signal
  criteria, execution and money management, equity curve, per-asset results and
  trade ledger — not only summary metrics.
- Never let that view go blank while a new candidate runs. If no evaluation is
  eligible yet, the view must say so explicitly instead of rendering empty.
- Never overwrite a champion with a worse or ineligible one, and never delete a
  champion decision row. Criteria 14 to 16 of `SYSTEM_CRITERIA.md` are binding.
- Label evidence honestly. A Phase-1 champion is historical, never
  forward-validated. Publish negative forward results unchanged.
- Cover any change to this path with tests in `tests/test_champion.py`.

## Hard boundaries

- Never place live orders, request exchange credentials, spend money, deploy to a
  public host or weaken validation to improve a result.
- Never use 2026 data for development. Phase 1 ends strictly before 2026; Phase
  2 uses 2026-to-present data only for forward ranking and reporting.
- Never introduce short exposure. Keep signal, execution and money management
  separate, and preserve the single shared USD 100,000 portfolio with dynamic,
  confidence- and risk-based position sizing. Never restore fixed asset sleeves.
- Never relax the 25% maximum-drawdown hard stop. Treat breached trials as
  pruned evidence and move to the next execution variant immediately.
- Preserve all failed experiments and audit records.
- Do not start/stop the autonomous service or launch another coding agent.
- Do not silently change metrics, data splits, costs or execution conventions.
- Treat synthetic performance only as infrastructure evidence.
- Prefer deterministic, reproducible changes and bounded resource use.
- If external data or credentials block the chosen task, record the blocker and
  complete a different safe roadmap increment.

The service will invoke you again. Do not ask the user for a next prompt.
