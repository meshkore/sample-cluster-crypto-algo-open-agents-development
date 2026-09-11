---
title: "Experiment catalogue"
updated: 2026-09-10
status: stable
---

# Experiment catalogue

**What this is.** Everything this laboratory has considered, tried, closed or wants to try
one day, in one place. It exists so that nobody — human or agent — re-opens a question that
has already been answered here, and so that a good idea parked for later is parked
*somewhere findable* rather than lost in a conversation.

**What this is not.** A backlog. Nothing in this file is scheduled, assigned or pending.
The roadmap is deliberately near-empty: **System 08 is in a design-only phase.** No code, no
backtests, no measurements, until the operator authorises it in words. Read
[`constraints.md`](constraints.md) before proposing anything.

**How to use it.** Before you propose an experiment, search this page. If it is in §7 it is
closed — argue with a *source*, not an intuition. If it is in §1–§6 it is an open option and
you should say what new evidence makes it worth revisiting now.

---

## 1. The signal slot — decided 2026-09-11

The design ([`research/system08/THEORY.md`](../../research/system08/THEORY.md)) holds the
idiosyncratic component of a crypto book and hedges away the common factor. The slot marked
`s` is now **filled**, and it was filled by **elimination against published constraints**
rather than by preference.

> **`s` = cross-sectional momentum of the residual, on large-capitalisation crypto only,
> expressed long AND short.**

| candidate | published basis | verdict |
|---|---|---|
| **residual momentum** | Blitz, Huij & Martens (equities, held up post-publication); survives LASSO selection as a crypto factor in DS3; momentum works **in the large caps** | **ADOPTED** |
| **residual reversal** | crypto reversal portfolios and market uncertainty (*RIBAF* 2025) | **rejected — capacity.** Driven mostly by low volume and low liquidity; below our turnover floor |
| **size** | one of the three factors in Liu, Tsyvinski & Wu | **rejected — capacity.** Profitability comes *solely* from the 30–70% smallest coins; the effect also disappears out of sample |
| **funding / crowding** | documented funding-rate predictability; leveraged retail is the named counterparty | **held in reserve.** Not the signal; the pure carry version is closed (§7), but a crowding *state* may gate the book |
| **multifractal / Hurst state** | asymmetric multifractality in crypto (*Physica A* 2026) | **rejected.** No peer-reviewed rule survives realistic costs out of sample — explanation, not signal |
| **non-price inputs** | retail flow is momentum-chasing in crypto specifically (Kogan, Makarov, Niessner & Schoar, *JFE* 2024) | **deferred on purpose.** The most promising direction for the *next* version of `s`; held back so we do not spend every hypothesis on the first system |

**Four constraints travel with the adopted signal**, each forced by a citation rather than
chosen: large caps only; the short side is mandatory (the alpha is extracted largely from
short positions); turnover is the enemy and the horizon should be slow; and expect decay —
later-period alphas run 9–76% lower, so the design is built to be retired, not defended.

**One thing is still a choice, not an open question:** which factor set the residual is taken
against — Bitcoin alone, CPT3, or DS3. It is the first decision of implementation and it is
registered as a decision rather than smuggled in as a default.

**The weakest claim in the design** is that the short leg is *paid* rather than *charged*.
It rests on market funding data, not a peer-reviewed full-cycle measurement, and it sits in
tension with the closed carry trade whose Sharpe went negative in 2025. If it is wrong, kill
criterion K3 fires.

## 2. Architecture variants worth arguing

Options for the *container*, independent of which signal fills the slot.

- **What counts as "the factor".** BTC alone, or the market/size/momentum triple that the
  published crypto factor model uses. A single-asset hedge is simpler and cheaper; the
  three-factor version is what the literature actually validated.
- **Estimation window for the loading.** Short windows track a drifting exposure but are
  noisy; long windows are stale. The trade-off is a design decision with a cost on both
  sides, not a parameter to optimise later.
- **Rebalance interval of the hedge.** Turnover versus staleness. Cheaper hedging leaves
  more residual exposure to the factor; the two errors are not symmetric and should be
  argued before either is measured.
- **Cross-sectional versus time-series construction.** Rank names against each other, or
  each name against its own history. These have different capacity and different failure
  modes under a universe that changes composition.
- **Where volatility scaling is applied** — to price or to the residual. The design as
  written scales by residual volatility, which is a claim, not a convention.
- **Do nothing at all in some states.** Standing aside is a position. The operator's
  constraint that leverage is minimal *because of execution risk* argues for it.

## 3. Risk and money-management complements

Decision-tree complements: things that sit around a signal rather than inside it.

- **Protective stops** versus **position sizing** as the primary drawdown control. The
  operator's stated preference is stops and standing aside over size.
- **Volatility targeting** at the book level, on top of per-name residual scaling.
- **Concentration limits** — how much of the book any one name or any one narrative cluster
  may carry.
- **Regime gating** — a slow state variable that switches the book off rather than
  reversing it. Cheaper to be flat than to be wrong in the other direction.
- **Meta-labelling** — a second model that decides whether to *act* on the primary signal,
  rather than what to do. In this lab's own history this behaved as a drawdown reducer, not
  a return generator, and should be proposed on that basis or not at all.
- **Execution realism as a design constraint, not an afterthought.** The operator's words:
  *"the moment you send the order there will be a thousand orders ahead of yours."*
  Anything whose edge lives inside the queue is not available to us.

## 4. Data we would need, and do not yet have

Documented so the acquisition is a deliberate decision later — **not started, not
scheduled.** The irreversible part is that some of it cannot be recovered after the fact.

| data | why it would matter | note |
|---|---|---|
| perpetual funding history, per venue | prices the short factor leg; the carry literature lives here | partially held |
| order book depth / L2 | execution realism, capacity limits | **irreversible** — not recoverable retrospectively |
| liquidation feeds | the leveraged-retail counterparty, observed directly | **irreversible** |
| circulating supply | capitalisation-weighted anything needs it | discussed at length in the archived generation |
| stablecoin supply and dominance | proposed as a regime input | archived, never resolved |
| social / copy-trading positioning | the named counterparty, made observable | licensing and survivorship questions unanswered |
| on-chain flows | attention and holder behaviour | large literature, very uneven quality |

## 5. Cross-domain leads — and how sceptically to treat them

The operator asked explicitly for these, and they are where genuinely original ideas would
come from. They also attract the weakest evidence in the field, so each carries its own
scepticism note.

| lead | status of the evidence |
|---|---|
| **Multifractal scaling / Hurst** | real, replicated *as a description* of crypto price series. Almost never shown to produce a tradeable rule after costs. Treat a Hurst reading as a state variable to argue about, never as a signal. |
| **Adaptive Markets Hypothesis** | the best available *explanation* of why edges decay, and it fits this lab's six-systems-one-year history exactly. It is a frame, not a strategy. |
| **Self-organised criticality / avalanche models** | power-law event sizes are well documented. Forecasting a specific avalanche is the part that repeatedly fails. |
| **Critical slowing down as a crash warning** | **closed** — see §7. Refuted across five indices over a century. |
| **Log-periodic power law / bubble timing** | prominent, heavily criticised for out-of-sample performance. Any proposal must lead with the out-of-sample record, not the fitted charts. |
| **Long economic cycles (Kondratiev, Juglar)** | horizons far longer than anything we trade; the mapping to a position is where these proposals always break. |
| **Elliott wave and similar** | not falsifiable as usually stated. Out of scope unless someone can state a pre-registered rejection rule. |
| **Ecological / natural analogues** (predator-prey, foraging, network cascades) | genuinely unexplored as a *source of hypotheses*. Useful for generating a mechanism; the mechanism still has to survive §6. |

## 6. Method guards — how anything gets judged

These are not negotiable and they are the direct lesson of this laboratory's own record.

- **Multiple-testing hurdle.** Harvey, Liu and Zhu argue roughly **t > 3**, not 1.96, for a
  new factor. The published crypto base rate is brutal: of 49 crypto anomalies re-examined,
  **only 13 remained significant** over 2014–2023.
- **Deflated Sharpe ratio.** Bailey and López de Prado — correct for selection bias over the
  number of trials *actually run*, not the number reported.
- **Probability of backtest overfitting.** The named failure mode of six systems dying in
  the same year: the more configurations you try, the more certain it is that the winner was
  selected rather than discovered.
- **Pre-registration.** Write the kill criterion before the number exists. A criterion
  invented after the result is not a criterion.
- **Composition control.** The universe is not constant through time. Any per-year or
  per-era statistic pooled over symbols is confounded unless composition is held fixed
  explicitly. This lab published a result that failed exactly this, and a peer caught it.
- **2026 is sealed.** It is never optimisation input and is read only at an adoption.
  Spending it is irreversible.
- **Price the odds before spending a sealed reading.** An edge whose year-to-year spread
  straddles 1.0 cannot be settled by one year.

## 7. Closed — do not re-propose

Argue with a source, or leave it closed.

| hypothesis | why it is closed |
|---|---|
| order-flow absorption / impact residual | screened across horizons; flat |
| signed order flow at 15m | top flow decile did not pay before costs |
| over-extension reversal | failed its own pre-registered test |
| crypto carry — short perp, long spot | the published Sharpe collapses in the recent sample and the source itself reports it turning negative |
| liquidation-cascade recovery | third-party analysis: most of the return was the factor; alpha not significant |
| critical slowing down as a crash warning | refuted across five indices over a century |
| "all crypto edges decay uniformly" | **ours, withdrawn** — confounded by universe composition, caught by a peer agent |
| our own 2026-09-10 measurements (R01–R06) | not closed as *wrong*, but **not carried into the design**: produced here, on selected data, by the same process that produced six systems that all died in the same year. Frozen in `research/system08/archive-measurements/`, kept only so nobody repeats them |

## 8. From the archived generation — worth keeping in mind

The previous system reached a champion and then died forward. What survived as *knowledge*:

- A risk layer (stops, slow-trend gating, concentration limits) mattered more than the
  signal it wrapped.
- Fast trading paid well before 2022 and has paid nothing since; turnover levers fitted on
  the full record describe a market that no longer exists.
- Selection optimism is nested and compounds: two stacked max-selections turned a real but
  small edge into a headline that would not reproduce.
- A bar is a measurement procedure, not a number. Pin the procedure, then read the bar.
- Every one of the six promoted systems was positive across the research years and negative
  in the same forward year. That is the single most informative fact this laboratory has
  produced, and it is an argument about *method*, not about any one strategy.

---

*Research only. No live-order capability, no wallet, no exchange secrets — the one absolute
rule. Nothing in this catalogue is scheduled; it is a reference, and the design phase is
argued from published work rather than from anything computed here.*
