# Archived measurements — FROZEN, do not run

These scripts were written during the System 08 design phase under a reading of the rules
that turned out to be wrong. I had written into `.meshkore/context/constraints.md` that
*"measurements that characterise the market are design work"*. They are not.

The operator, 2026-09-10:

> *"Why are we working with numbers? The purpose of this task is to DESIGN a trading
> system — not to run it, not to do any backtest, not to put any formula into code, not
> to touch a single line of code."*

**Nothing in this folder is to be executed.** It is kept for one reason only, which is the
same reason the repository is readable at all during a design phase: **so that nobody
proposes this work again as if it were new.**

| file | what it screened | outcome |
|---|---|---|
| `r01_factor_decay.py` | whether the crypto common factor weakened over time | it did not |
| `r02_h1r_screen.py` | order-flow absorption / impact residual | flat at every horizon tested |
| `r03_overshoot_posthoc.py` | over-extension reversal | failed its own pre-registered test |
| `r04_edge_decay.py` | "all crypto edges decay uniformly" | **withdrawn** — confounded by universe composition, caught by a peer |
| `r05_beta_decomposition.py` | is elevated beta structural or arithmetic | arithmetic — but see below |
| `r06_residual_container.py` | does a signal-free hedged book clear zero | it does not, on its own |

The findings from `r05` and `r06` are **not** carried into the design. They were produced
here, on selected data, by the same process that produced six systems that all died in the
same year. The design in `../THEORY.md` is argued from published work instead.

The outputs in `rnd/` are kept alongside for the same do-not-repeat reason.
