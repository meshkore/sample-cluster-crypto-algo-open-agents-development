---
title: "System 09 - The Ledger: a reconstructed-participant simulation of the crypto market"
category: context
updated: 2026-09-14
owner: master
status: phase 3 built (MVP runs); phases 4-8 still design
---

# System 09 - The Ledger

**One sentence.** Price is the residual of a balance-sheet process: every trade is a
conserved transfer of units and of cash between participants, only a handful of boundary
events change the totals inside the ecosystem, and if we reconstruct the distribution of
coins and dry powder across a tractable number of representative participants we can ask
what price has to be for the market to clear.

Slot: `trading-system/quantlab_system09/`. Systems 04-08 are taken; 09 is the next one.

> **STATUS, 2026-09-14.** This document was written under the code gate and executed
> nothing. The operator lifted the gate the same day with "GO TO FIRST MVP", and **phase 3
> is now built and run**: L0 and L1 exist, V0 passes, V2 does not. Phases 4-8 remain
> design. Two things changed against the plan below and both are recorded rather than
> quietly absorbed:
>
> 1. **Phase 2 - the kill switch - was skipped**, on the operator's instruction to go
>    straight to the MVP. It is still the cheapest test in this document and it is now the
>    recommended next move.
> 2. **V2 returned a negative.** Held out of the ETF series, the inferred institutional
>    cohort tracks published ETF flow but does not beat the naive trend signal that drives
>    it - 4 of 9 statistics. See `trading-system/quantlab_system09/docs/RESULTS.md`. The
>    reading of that result, and what it does and does not rule out, is in the same file.
>
> The MVP also proved one thing the plan got wrong in a useful direction: section 5's
> "volume problem" assumed the tape had to be downloaded. It did not. `taker_buy_volume` is
> already on this machine in the 15m candles from 2017-08, and it carries the entire
> aggressor/passive split the design calls the spine, so the MVP needed **zero** tape bytes.

---

## 0. Read this before anything else: the one correction to the premise

The operator's framing was: *"if two bitcoin are bought for $100, then $200 has entered
the liquidity of the system."*

Almost. A trade does **not** change the amount of cash inside the crypto ecosystem. It
moves cash from the buyer to the seller and units from the seller to the buyer. After the
trade the sector holds exactly the same total dollars and the same total coins as before.
What changed is the **distribution**, and the distribution is precisely the state variable
we are after.

Money genuinely enters or leaves the ecosystem only at the **boundary**, and the boundary
is a short, finite, mostly *observable* list:

| Boundary event | Direction | Observability |
|---|---|---|
| Fiat deposit / withdrawal at an exchange | in / out | not directly observable; proxied |
| Stablecoin mint / burn | in / out | **exactly observable, on-chain, per issuer, per chain** |
| ETF share creation / redemption | in / out | **observable daily since 2024-01** |
| Miner issuance sold for cash | out (cash leaves to miners) | observable on-chain |
| Fees paid to exchanges and to chains | out | estimable from the tape |
| Lost keys, permanent burns | units leave | estimable, slow |

This correction is not pedantry. It is the thing that makes the project *identifiable*
rather than merely large. It says:

- the **inside** of the system is a conservation law (a closed accounting identity), and
  conservation laws are checkable at every single step, which is what will keep a
  simulation of this size honest;
- the **outside** of the system - the operator's "how much money enters the crypto
  ecosystem and how much leaves" - is a short list of series we can actually obtain;
- therefore the model is: *observable boundary flows drive a conserved internal
  redistribution, and price is what clears it.*

That is a stock-flow-consistent (SFC) model of a market sector. It has a literature, it has
accounting invariants that can be asserted in tests, and it fails loudly rather than
quietly.

---

## 1. The second thing to be honest about: what can and cannot be reconstructed

The operator wants to know **who holds which coins today and who has cash to invest.**

Exchange tape is anonymous. Binance publishes, per trade, price, quantity, timestamp and
which side was the aggressor - and nothing that identifies an account. There is no
off-chain data set in the world, free or paid, that attributes exchange trades to named
participants. Anyone who claims otherwise is selling a clustering heuristic.

So the honest statement of the project is:

> **The participants are latent.** We are not reconstructing real wallets from the tape.
> We are inferring the *joint distribution of holdings and cash across behavioural
> cohorts*, constrained by accounting identities and pinned to observable anchors.

This is not a weaker project - it is the only version of the project that can be validated.
And a surprising amount is genuinely pinned:

- **On-chain gives real cost basis.** UTXO age bands (HODL waves), realized cap and the
  cost-basis distribution are computed from the chain itself and are exactly the "who bought
  at what price and still holds it" object, for Bitcoin, at a resolution good enough for
  cohorts. Realized cap is already the on-chain community's published answer to "how much
  money has ever flowed in, net" - so part of the operator's question has an answer we
  should start from rather than re-derive.
- **Exchange reserves** bound how many coins sit where the tape can touch them.
- **Perp open interest, funding and liquidation prints** pin the leveraged cohort's
  inventory and the sign of its pain.
- **ETF holdings** pin one cohort exactly, by law, daily.
- **Stablecoin supply** pins the dry powder that never left the ecosystem.
- **Venue premia** (Coinbase gap, Kimchi premium, USDT premium) identify *which sector* is
  the aggressor - the classic trick for splitting US institutional from Asian retail from
  stablecoin-native flow.

The reconstruction is an inverse problem with a lot of side constraints. That is a
tractable, well-posed research object. "Rebuild every wallet since 2010" is not.

---

## 2. Hypothesis (the claim, not the architecture)

1. The forecastable part of crypto returns is driven by **participant constraint**, not by
   chart shape: who has run out of cash, who is underwater and by how much, who is levered
   near a liquidation band, who is mechanically obliged to rebalance.
2. Those constraints are **stocks**. They move slowly and they are partially observable -
   which is why they can still carry information at horizons where price-only features have
   been arbitraged away.
3. A conserved, stock-flow-consistent reconstruction of those stocks therefore contains
   information that is **not** in the candle features systems 04-08 have already mined, and
   that is the only reason to build it.

Point 3 is the whole bet. Phase 2 below exists to kill it cheaply before we spend a year on
the simulator.

---

## 3. What already exists in the world (do not re-derive it)

Design comes from the outside world, per the gate. The relevant bodies of work:

**Agent-based market models.** The Santa Fe Artificial Stock Market (Arthur, Holland,
LeBaron, Palmer, Tayler); Lux & Marchesi (herding produces fat tails and volatility
clustering); Cont & Bouchaud (random herding); Brock & Hommes (adaptive belief systems,
fundamentalist/chartist switching driven by realised profit - the cleanest existing template
for "cohorts that change their mind"); Farmer & Joshi; Chiarella & Iori (order-book ABM);
Gode & Sunder and Farmer-Patelli-Zovko on zero intelligence, which tells us how much market
structure comes from constraints alone rather than from cleverness. That last one is our
null model and it matters more than it sounds.

**Modern simulators and their honesty checks.** ABIDES (Byrd, Hybinette, Balch) as the
reference multi-agent discrete-event market simulator, plus ABIDES-Gym for RL; Vyetrenko et
al., *Get Real: Realism Metrics for Robust Limit Order Book Market Simulations* (ICAIF '20)
- the checklist our simulated tape must pass before it is allowed to claim anything; Coletta
et al., *Learning to simulate realistic limit order book markets from data as a World
Agent*; the generative order-stream line of work.

**Calibration - the part that kills ABM projects.** Method of simulated moments / simulated
minimum distance; Grazzini & Richiardi on ABM estimation; Platt, *A Comparison of Economic
Agent-Based Model Calibration Methods*; Dyer et al. on black-box Bayesian inference for
economic ABMs and the `sbi4abm` line (neural posterior estimation and neural ratio
estimation reach good posteriors with orders of magnitude fewer runs); Quera-Bofarull et al.
on differentiable ABMs and the traps in calibrating them; and the non-identifiability work
(*Alleviating Non-identifiability: a High-fidelity Calibration Objective for Financial Market
Simulation*), which is the single most important warning for us: **many different agent
populations reproduce the same stylized facts.** Matching stylized facts is necessary and
nowhere near sufficient.

**Market impact.** Kyle's lambda; the square-root law of impact (Torre, Almgren, Bouchaud,
and Donier & Bonart specifically for Bitcoin); propagator models. These are among the most
robust empirical regularities in finance and they are what lets us clear a market without
simulating a full order book.

**Crypto-specific accounting.** Realized cap and the cost-basis distribution; HODL waves;
entity clustering via the common-input-ownership heuristic (Meiklejohn et al., *A Fistful of
Bitcoins*) and its descendants; Coin Metrics' entity-adjusted metrics.

**Verdict on novelty.** Agent-based simulation of a market is old. Agent-based simulation of
*crypto*, fused with the boundary flows that only crypto publishes - stablecoin mint, ETF
creation, on-chain cost basis, perp funding and liquidations - and then used as a trading
signal under a sealed forward window: that combination is where the new ground is. Lean hard
on the published machinery; spend our originality on the fusion.

---

## 4. The population: how many actors, and which

The operator asked whether it is 100 or 200, told us to choose whatever is mathematically
coherent, and gave the right intuition himself: ten operators each buying $10 at the same
moment are, for our purposes, one operator buying $100.

The literature's answer: **headcount is not the design parameter. The number of distinct
behavioural types is, and so is the size distribution.**

### 4.1 Behavioural types (the taxonomy)

Ten types, each distinct for a mechanical reason rather than a psychological one:

| # | Cohort | What makes it distinct | How it is anchored |
|---|---|---|---|
| 1 | Long-term holders | almost never sell; sell only on extreme profit | HODL waves, coin-days destroyed |
| 2 | Trend followers / momentum retail | buy strength, sell weakness, no cash discipline | taker-flow autocorrelation, retail-venue premia |
| 3 | Mean-reverting dip buyers | buy drawdown, finite dry powder | taker flow against price |
| 4 | Market makers / passive liquidity | inventory-averse, quote both sides, earn spread | maker side of the tape, spread, depth |
| 5 | Basis and funding arbitrageurs | spot long vs perp short; care only about carry | funding, open interest, basis |
| 6 | Leveraged directional (perp) | liquidation-constrained; produces forced flow | OI, liquidation prints, funding sign |
| 7 | Institutional / ETF allocators | slow, calendar-driven, size-constrained | ETF creations/redemptions, CME COT |
| 8 | Miners | continuous unit issuance, structural sellers, cost floor | issuance, miner outflows, hash rate |
| 9 | Stablecoin issuers | mint/burn is the sector's cash faucet | supply series per issuer |
| 10 | Exchanges / custodians | hold others' coins, take fees | reserves, fee estimates |

Types 8, 9 and 10 are not traders. They are **boundary operators**, and they are the reason
this model can say anything at all about money entering and leaving.

### 4.2 Size distribution

Within each type, wealth is power-law distributed - one of the most robust facts in both
traditional and crypto markets. So each type is represented by a short ladder of size
buckets rather than by one average agent, because **the tail agents are the ones that move
price** and averaging them away destroys exactly the dynamics we are trying to capture.

### 4.3 The recommended counts

- **Prototype (Phase 3): O(100) representative agents.** Ten types times about ten size
  buckets, one asset. This is the number the operator guessed, and it is the right number to
  start with.
- **Working model (Phase 5): O(10^3 - 10^4).** Types x size buckets x venue/geography x
  asset affinity. The operator is right that an agent does not trade fifty coins at once:
  each agent carries a small **asset-affinity set** (one to five assets), which is both
  realistic and an enormous saving.
- **Never O(10^6).** Simulating individual humans buys nothing here. Two agents whose
  actions are statistically indistinguishable at our observation timescale are one agent.

### 4.4 The rule that sets the count (this is the important part)

> **Add agents only while the simulated tape's realism metrics keep improving.**

Concretely: generate the tape, measure it against the realism checklist - fat-tailed
returns, aggregational Gaussianity, absence of return autocorrelation, volatility
clustering, long-memory order-flow autocorrelation, power-law trade sizes, realistic spread
and depth dynamics, the leverage effect - and stop adding heterogeneity the moment the curve
flattens. The population size becomes a **measured quantity rather than a taste.** That is
the discipline separating this from a very expensive toy.

---

## 5. Data plan

Tiered by observability and by cost. Nothing is downloaded before the gate lifts; Phase 1
produces the licence map, not the bytes.

### Tier A - the off-chain spine (free)

- **Binance public data** (`data.binance.vision`, the `binance/binance-public-data` repo):
  spot from 2017-08-17, futures from 2019-09. Per symbol, per day and month: `aggTrades`,
  `trades`, `klines`, `bookTicker`, `fundingRate`, `liquidationSnapshot`, `metrics` (open
  interest). Free, no key, bulk zips.
  - The single most valuable field is `isBuyerMaker` on every trade, which splits the tape
    into **aggressor and passive**. Without a side split there is no behaviour to attribute;
    with it the whole project becomes possible on free data. This is the spine.
- **Pre-Binance history**: Bitstamp (from 2011), Coinbase, Kraken, Bitfinex, Gemini, and the
  Bitcoincharts / cryptodatadownload archives for the Mt. Gox and BTC-e era. Quality decays
  going back; treat pre-2014 as narrative, not as training data.
- **Paid, only if a phase justifies it**: Kaiko, Tardis.dev, CoinAPI, Amberdata for true
  L2/L3 book reconstruction and wide multi-venue coverage.

### Tier B - the boundary (the operator's "money in and out")

- **Stablecoin supply** by issuer and chain - DefiLlama (free API, history back to roughly
  2017), cross-checked against issuer attestations. The cleanest cash-faucet series in
  existence; traditional finance has no equivalent.
- **US spot BTC and ETH ETF daily flows** - Farside Investors, SoSoValue, CoinGlass; daily
  creations and redemptions per fund since 2024-01. An exactly-known cohort.
- **Exchange reserves and netflows** - on-chain, entity-tagged; Coin Metrics community data
  for the free subset, Glassnode or CryptoQuant if we pay.
- **Miner issuance, revenue, hash rate** - free, and the repo already carries
  `chain_miners-revenue`, `chain_hash-rate`, `chain_n-transactions` and
  `chain_n-unique-addresses` under `backtester/data/external/`.
- **Sector-identification premia** - Coinbase premium gap (US institutional), Kimchi premium
  (Korean retail), USDT premium (stablecoin-native). Derivable from the Tier A tapes at no
  extra cost.

### Tier C - positioning

Perp **open interest** and **funding** (the repo already carries funding for fourteen
symbols), **liquidation** prints, **CME COT** (free, weekly, from the CFTC - genuine
institutional positioning), Deribit options open interest and skew.

### Tier D - on-chain (Phase 6, not before)

UTXO age bands, realized cap, cost-basis distribution, entity clustering by
common-input-ownership. Either paid (Glassnode, Coin Metrics) or built from a full node plus
an indexer. Bitcoin first; account-based chains need a different entity model.

### The volume problem, and the answer to it

The full tick tape across hundreds of symbols and many venues is multi-terabyte, and the
operator is right that this needs serious compute. But **the ledger does not need ticks. It
needs conserved flow per bucket.**

The sufficient statistic per symbol per bucket is small: signed taker volume, a trade-size
histogram over a handful of size bands, trade count, VWAP, high and low, and the passive
side's implied inventory change. That compresses the tape by orders of magnitude while
preserving everything the cohort model consumes. Ticks are retained only for a small
validation subset, where we check that the compression destroyed nothing that mattered.

Bucket choice: **dollar-volume or volume buckets rather than clock time.** Clock bars
over-sample dead hours and under-sample the moments that matter; volume and dollar bars have
better statistical properties and are the standard choice in the literature.

---

## 6. Architecture

Six layers, each independently testable. The dependency direction is strict and downward.

```
L5  Trading policy       what the lab actually trades: fragility of the cohort state
L4  Forward simulation   Monte Carlo ensembles conditioned on boundary scenarios
L3  Market clearing      orders -> price (impact law | stylized LOB | full engine)
L2  Behaviour            per-cohort policy: action given market state AND own balance sheet
L1  Reconstruction       inverse problem: observables -> latent cohort state trajectory
L0  Ledger core          double-entry, stock-flow consistent, conserved, asserted
```

### L0 - Ledger core

Every event is a transfer with two legs. Units are conserved except at issuance and burn;
cash is conserved except at the boundary; the sum over agents of holdings equals the
observable float; the sum of cash equals stablecoin supply plus estimated fiat balances.
These are **assertions that run every step**, not documentation. A simulation of this size
with no conservation law is a random number generator with good manners.

### L1 - Reconstruction (the inverse problem)

Given observed flow and boundary series, infer the cohort state trajectory. Candidates, in
order of preference:

1. **State-space filtering** over a low-dimensional cohort state (particle filter or
   ensemble Kalman). A natural fit: the state is stocks, the observation is flow, the
   identities are hard constraints.
2. **Constrained flow assignment / optimal transport** - allocate each bucket's observed
   signed flow across cohorts so the resulting stocks stay consistent with every anchor.
   Cheap, well-behaved, and a good first cut.
3. **Simulation-based inference** (neural posterior or neural ratio estimation) if the
   forward model turns out too expensive to filter through directly.

Anchoring is everything. The filter must be pinned by ETF holdings, exchange reserves,
stablecoin supply, open interest and later on-chain cost basis - otherwise it drifts into
any of the infinitely many decompositions that fit the tape equally well.

### L2 - Behaviour

Per cohort, a policy conditioned on **market state and on the agent's own balance sheet**:
cash, inventory, unrealised P&L, leverage, time since last trade. Conditioning on own state
is not a detail - it is what makes forward simulation self-limiting. A cohort with no cash
cannot buy, and a cohort deep underwater behaves differently from the same cohort in profit.
Without it, simulated agents buy forever and the model explodes.

Families, in increasing order of ambition:

1. Parametric heterogeneous-agent rules with profit-driven switching (Brock-Hommes). Few
   parameters, calibratable, interpretable, and the published baseline.
2. Behavioural cloning or inverse RL on the reconstructed cohort flows.
3. A conditional generative model of cohort flow (the world-agent approach).

Start at 1. It is the only one whose failure is diagnosable.

### L3 - Market clearing

1. **Impact-law clearing** - square-root impact with a decaying propagator, calibrated per
   asset. Cheap, calibratable from free data, grounded in the most robust empirical law
   available. **This is the recommendation for Phases 3-5.**
2. Stylized order book with explicit market makers - adds spread and depth dynamics.
3. Full matching engine, ABIDES-style - correct, and far too expensive to run over a decade
   of history across many assets. Reserve it for validation episodes.

### L4 - Forward simulation

Ensembles, not a path. Boundary flow is the exogenous driver, which makes the natural output
a **scenario engine**: if stablecoin supply stops growing and ETF flow goes flat for a month,
what does the distribution of paths look like given who currently holds what?

### L5 - Trading policy

The lab trades **cohort fragility**, not the simulator's point forecast. The signals this
architecture exists to produce: dry-powder exhaustion, leveraged-cohort underwater depth,
concentration of cost basis just above spot (overhead supply), and forced-flow potential.
Sizing and stops are inherited from system 06 - stops, slow trend and concentration are what
made a model beat the incumbent, and system 09 does not get to re-learn that.

---

## 7. Validation ladder

Most ABM projects die by producing a beautiful simulator that predicts nothing. The ladder
is built so we find that out early and cheaply.

- **V0 Accounting.** Invariants hold exactly, every step, in tests. Binary.
- **V1 Realism.** The simulated tape passes the realism checklist. Necessary, and explicitly
  **not sufficient** - the non-identifiability literature shows many populations produce
  identical stylized facts.
- **V2 Anchor recovery.** Fit without an anchor, then predict it. Example: reconstruct
  without ETF flows and check whether the inferred institutional cohort matches the published
  ETF series. This is the test that separates reconstruction from storytelling.
- **V3 Event replay.** Fed only boundary flows, does the simulator reproduce the shape of
  March 2020, May 2021, LUNA, FTX, the ETF launch? Out of sample, not fitted.
- **V4 Incremental information.** Does the cohort state add anything **beyond** the features
  systems 04-08 already use? Measured as a strict addition to an existing baseline, never
  standalone. A cohort state that cannot beat features this lab already has is an ornament.
- **V5 Sealed 2026.** Once. Under the existing gate: two walk-forward exams, the odds priced
  first, and no sealed reading spent on an edge whose year-to-year spread straddles 1.0.

---

## 8. The phase plan

Every phase names its kill criterion. A phase with no kill criterion is a hobby.

### Phase 0 - Design and literature (now; no code, no data, no numbers)

- **Do**: finish this document; assign reading across the cluster peers; produce the theory
  and the diagram for the public page.
- **Deliverable**: this file, the `quantlab_system09/docs/` skeleton, and a diagram of the
  ledger, the boundary and the six layers.
- **Kill**: if the literature already answers the incremental-information question (V4)
  negatively on public data, we stop here and write that down.

### Phase 1 - Data survey and licence map (no downloads; the map only)

- **Do**: for every series in section 5 - source, exact coverage window, granularity, update
  cadence, licence, cost, and what breaks if it is missing. Delegate the legwork to the
  cluster peers; integrate here.
- **Deliverable**: a new section in `.meshkore/context/data-catalogue.md` plus the loader
  signatures `quantlab_catalog` would need.
- **Kill**: if the boundary series - stablecoin supply, ETF flows, exchange reserves - cannot
  be had at daily granularity over a long enough window under an acceptable licence, the
  boundary model collapses to a proxy model and the ambition drops one tier.

### Phase 2 - The cheap pre-test (**the kill-switch phase; run it before building anything**)

- **The question**: do *observable* cohort proxies carry any edge at all, over and above what
  this lab already trades?
- **Do**: take the proxies that need no simulator - funding, open interest, liquidation
  intensity, ETF net flow, stablecoin supply growth, exchange netflow, Coinbase/Kimchi/USDT
  premia, realized-cap growth, cost-basis overhead - and test them as a **strict addition** to
  the existing champion's features. Two walk-forward exams, odds priced first, no sealed
  reading.
- **Why first**: it costs a fraction of the full build and it tests the load-bearing
  assumption head on. The full reconstruction's entire claim is that it recovers a *sharper*
  version of these proxies. If the sharp, exactly-observed versions carry nothing, the blurry
  inferred version will carry less.
- **Kill**: no incremental information from the observable proxies across two exams - stop,
  and write it into *What hurt*. That would be a cheap and genuinely valuable negative
  result, and it is the most likely single outcome of the whole project.

### Phase 3 - Ledger core and reconstruction, one pair

- **Scope**: BTCUSDT on Binance, spot plus perp, one to two years, O(100) agents, impact-law
  clearing.
- **Do**: build L0 and L1. Compress the tape to bucketed sufficient statistics. Reconstruct
  the cohort state. Run V0 and V2.
- **Deliverable**: a cohort-state time series for one pair with the anchor-recovery result
  beside it.
- **Kill**: V2 fails - the reconstruction cannot recover an anchor it was never shown. That
  means the inverse problem is not identified with the data we have, and no number of extra
  layers fixes an unidentified state.

### Phase 4 - Behaviour and replay fidelity

- **Do**: build L2 and L3. Learn cohort policies from the Phase 3 reconstruction. Replay
  history: drive the simulator with observed boundary flows only, and compare the generated
  tape with the real one. Run V1 and V3.
- **Deliverable**: a replay report against the realism checklist and against the named
  historical events.
- **Kill**: the simulator cannot reproduce stylized facts without per-episode refitting.

### Phase 5 - Scale: multi-symbol, multi-venue, power-law cohorts

- **Do**: extend to the lab's dynamic universe; add asset-affinity sets; add the second and
  third venues; grow towards O(10^3 - 10^4) agents using the realism-metric stopping rule of
  section 4.4.
- **Watch**: this is where compute becomes the binding constraint. Budget it explicitly
  before starting. The work is IO- and CPU-bound; the GPU only matters at L2.
- **Kill**: realism degrades with scale, or the compute budget exceeds what this box and the
  cluster can carry overnight.

### Phase 6 - On-chain fusion

- **Do**: add Tier D. Entity clustering, cost-basis distribution, HODL waves. Fuse the
  on-chain holder state with the off-chain cohort state - the point at which the operator's
  "who holds what today" becomes a genuinely answerable question for Bitcoin.
- **Kill**: on-chain adds nothing beyond what the off-chain reconstruction already carries.
  A real possibility: coins held on exchanges are invisible to chain analysis by design.

### Phase 7 - Forward simulation, scenarios, and the trading policy

- **Do**: build L4 and L5. Ensembles, boundary scenarios, fragility signals. Sizing, stops
  and concentration inherited from system 06's risk layer rather than re-derived.
- **Deliverable**: a `decide(tick) -> Decision` brain in the lab's standard shape.
- **Kill**: the edge disappears once the 0.30% round-trip cost invariant and the capacity
  floor are applied.

### Phase 8 - Exams, pricing the odds, and the sealed window

- **Do**: two walk-forward exams, then `price_the_edge()`, then - only if decisive - open the
  2026 sealed window once through `may_open_sealed_window()`.
- **Deliverable**: `docs/RESULTS.md` filled in, both eras labelled, drawdown beside every
  return, and the per-calendar-year consistency test the lab now requires.
- **Kill**: this is the lab's existing gate. It needs no new rules.

---

## 9. Risks, named

| Risk | Why it bites | Mitigation |
|---|---|---|
| **Non-identifiability** | many agent populations reproduce identical stylized facts | never calibrate on stylized facts alone; V2 anchor recovery is the real test |
| **Explains everything, predicts nothing** | ABM's classic failure mode | V4 measured as a strict addition to an existing baseline; Phase 2 runs before the build |
| **Reconstruction overfit** | the inverse problem has a vast null space | hard accounting constraints, external anchors, held-out anchor recovery |
| **Selection optimism** | this lab has already been burned by nested max-selections | pin the band before selecting; system 06's lesson applies unchanged |
| **Data volume and cost** | multi-TB tapes, paid on-chain | bucketed sufficient statistics; ticks only for validation subsets |
| **Universe composition drift** | the tradable set changes through time | every per-era statistic states its composition; already a lab rule |
| **Venue survivorship** | Mt. Gox, BTC-e and FTX are gone; their tape is not comparable | pre-2014 treated as narrative; dead venues flagged explicitly |
| **Scope** | the largest system this lab has attempted | the kill criteria above are load-bearing, and Phase 2 exists to end it cheaply |

---

## 10. What this system must not do

- No live-order capability, no wallet, no exchange secrets. Absolute.
- It does not touch `backtester/`.
- It does not read 2026 before Phase 8, and then once.
- It does not repeat systems 04-08. Read their `docs/SUMMARY.md` first; in particular system
  06's risk layer and consistency law are inherited, not re-derived.
- It does not write one line of trading-system code until the operator says so.

---

## 11. Sources

- [Get Real: Realism Metrics for Robust LOB Market Simulations](https://arxiv.org/abs/1912.04941)
- [Learning to simulate realistic limit order book markets as a World Agent](https://arxiv.org/pdf/2210.09897)
- [A Comparison of Economic Agent-Based Model Calibration Methods](https://arxiv.org/pdf/1902.05938)
- [Black-box Bayesian inference for economic agent-based models](https://arxiv.org/pdf/2202.00625)
- [sbi4abm: simulation-based inference for agent-based models](https://github.com/joelnmdyer/sbi4abm)
- [Some challenges of calibrating differentiable agent-based models](https://arxiv.org/pdf/2307.01085)
- [Alleviating Non-identifiability: a High-fidelity Calibration Objective for Financial Market Simulation](https://arxiv.org/pdf/2407.16566)
- [Agent-based modeling and simulation for economic markets: a comprehensive review](https://www.tandfonline.com/doi/full/10.1080/17477778.2026.2625187)
- [Binance public data](https://github.com/binance/binance-public-data) / [data.binance.vision](https://data.binance.vision/)
- [Farside Investors - Bitcoin ETF flow, all data](https://farside.co.uk/bitcoin-etf-flow-all-data/)
- [DefiLlama stablecoins](https://defillama.com/stablecoins) / [downloads](https://defillama.com/downloads)
- [Glassnode - The Foundational On-chain Metric: The Realized Cap](https://research.glassnode.com/the-realized-cap-foundation/)
- [CoinGlass - Bitcoin ETF fund flows](https://www.coinglass.com/etf/bitcoin)
