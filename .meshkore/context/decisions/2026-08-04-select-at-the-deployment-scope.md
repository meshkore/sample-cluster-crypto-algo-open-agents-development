---
title: "Parameter selection happens at the deployment scope"
updated: 2026-08-04
status: stable
---

Context: this laboratory allocates one shared capital pool across every asset
in a run, so exposure and drawdown are portfolio quantities, not per-asset
ones. Tuning on a single asset and then deploying on a basket produced a
configuration that breached the mandated 25% drawdown abort **twice in one
day** — QUANT13 stage 4 (`risk_per_trade` 0.10: +119.66% on BTCUSDT at 23.84%,
aborted on the basket at 25.34%) and QUANT14 stage 5 (exit 0.35 / sizing 0.10:
+68.95% on BTCUSDT at 14.11%, aborted on the basket at 25.47%). Both looked
comfortably legal on the asset they were fitted to.

This is a bias, not variance. Every per-asset exposure gain multiplies into
portfolio drawdown once breadth is added, so a single-asset search is
systematically drawn toward cells that are illegal at the scope that matters.
Averaging more single-asset results does not fix a bias that points one way.

Decision: **a parameter is only selected on the scope it will be deployed at.**
Single-asset runs are legitimate for diagnosis, attribution and controlled
comparison — that is how the exit/sizing decomposition was measured — but no
configuration is adopted on single-asset evidence. The final selection run uses
the full declared asset set of the family, at its declared interval.

Consequence: selection runs cost roughly the asset count more, which is
accepted. The alternative already cost two rejected configurations and would
eventually have published one that aborts in the forward window. Held-out
assets keep their separate role as a generalisation check; they do not
substitute for selecting at scope, because a per-asset held-out result is still
a per-asset result.

Corollary: the 25% abort is a constraint on the search, never a parameter
inside it. A cell that trips it is disqualified and reported as such. No sweep
in this laboratory relaxes it to explore beyond it.
