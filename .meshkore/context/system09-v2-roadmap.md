---
title: "System 09 version 2 - the roadmap of data and scope"
category: context
updated: 2026-09-14
owner: master
status: open (version 1 shipped 2026-09-14, tag system09-v1)
---

# System 09 v2 - what the next version is for

**Version 1 shipped on 2026-09-14** (tag `system09-v1`): four phases, a local dashboard on
port 8709, and a sealed 2026 reading of **+17.85%** against BTC -11.25%. The operator's finish
line is crossed. Everything on this page is now open.

**Version 2 is one idea: the same conserved ledger, fed by many more observations, all
aligned on one clock.** v1 reconstructs the crypto sector from a single venue's tape plus five
boundary channels. It works, and its own results say where it is blind. Every initiative below
is aimed at a blindness v1 measured rather than guessed at.

---

## What v1 measured about itself, and what each gap costs

| v1 finding | What it means | The v2 initiative it justifies |
|---|---|---|
| V2 beats the baseline on all six **flow** statistics and loses both **level** ones | the reconstruction knows *when* money moved, not *how much is there* | **A. Level anchors** - the opening distribution is the weakest input and the one with real external data available |
| Inferred fiat falls to exactly zero from 2023 | the boundary model is right where stablecoins dominate and is carrying the whole early record as a residual | **B. The real cash boundary** |
| Alt supply is a held-constant snapshot | every asset but Bitcoin has too much float in the early years | **C. True supply histories** |
| The population count is "the number least entitled to be believed" | neither bracket measures participants | **D. Participant observables** |
| One venue | Binance is a large minority of the market, not the market | **E. Multi-venue and multi-instrument** |
| Prices come from the tape, never from the model | there is no market clearing, so nothing can be simulated counterfactually | **F. Clearing and impact** |

---

## A. Level anchors - the highest value per unit of work

The thing that would most improve this system is knowing **who actually holds what**, even
approximately, at a few points in time. Then the opening priors stop being asserted.

- **On-chain cost-basis distribution and HODL waves** (Glassnode, CryptoQuant, Coin Metrics,
  or a full node plus an indexer). This is the real "who bought at what price and still holds
  it", computed from the chain rather than inferred from a tape. It anchors long-term
  holders, which are 39% of the modelled float in v1 and entirely a prior.
- **Exchange reserves per venue, entity-tagged.** Bounds how many units sit where the tape
  can touch them - the single hardest constraint available on the reconstruction.
- **ETF holdings, not just flows.** Daily, by law, exact. v1 uses the flow and holds out the
  series for V2; v2 can anchor the level and hold out something else.
- **Entity clustering** by the common-input-ownership heuristic and its descendants, which is
  what makes "whales" an observation rather than a net-worth threshold in a report.

## B. The real cash boundary

v1 infers fiat as a residual because nothing measures it. Reduce the residual by observing
more of it:

- stablecoin supply **per issuer and per chain**, with attestation dates, rather than one
  aggregate;
- **CEX fiat pairs** (USD, EUR, KRW, JPY, TRY) - the tape of fiat entering the sector;
- exchange **deposit and withdrawal** on-chain flows, entity-tagged;
- **venue premia** (Coinbase gap, Kimchi, USDT) as sector-identification signals: they say
  *which* geography's money is the aggressor, which v1 cannot see at all.

## C. True supply histories

- Historical circulating supply per asset - paid tiers of CoinGecko, CoinMarketCap, Messari,
  Coin Metrics - replacing v1's snapshot-held-constant.
- **Token unlock schedules.** For everything except Bitcoin, the largest supply events are
  scheduled and published, and they are exactly the forced flow this architecture exists to
  model.
- Staking and locked supply: units that exist and cannot be sold are not float.

## D. Participant observables

- Exchange **user counts and app-download proxies**, quarterly disclosures, Google Trends.
- **Active addresses across many chains**, not just Bitcoin - the reason v1's population sat
  still was that the crowd moved to chains its one series could not see.
- **New-address creation** and first-time-buyer cohorts, which is the closest public series to
  "a new player arrived".

## E. Multi-venue and multi-instrument

- Coinbase, Kraken, OKX, Bybit, Bitstamp, Bitfinex tapes; the pre-Binance archives
  (Bitstamp from 2011) for the era v1 cannot reach at all.
- **Options** - Deribit open interest and skew. Dealer gamma is forced flow with a known sign,
  and it is invisible to a spot-and-perp ledger.
- **Liquidation prints** per venue: v1 models margin failure as a cash shortfall and counts it;
  the real series would make it an event.
- **CME COT** - genuine, regulated, weekly institutional positioning.

## F. Clearing and impact

v1 takes price from the tape. That is correct for a reconstruction and useless for a
counterfactual: it cannot answer "what if the ETF flow had stopped". v2 adds L3:

- square-root impact with a decaying propagator, calibrated per asset;
- then a stylised order book with explicit market makers for the episodes that need spread
  and depth;
- a full matching engine reserved for validation episodes only.

Only after that does the forward simulation become a **scenario engine** rather than a
projection, which is what the operator asked the architecture for originally.

## G. The clock

Every initiative above lands on one requirement the operator named explicitly: **align all
sources chronologically**. That is not a formatting job.

- Every series carries its own **publication lag**; the catalogue already holds measured lags
  for FRED and the discipline must extend to all of it.
- Point-in-time versus revised: on-chain metrics get re-stated when clustering heuristics
  improve, so a v2 that trains on today's entity labels is training on the future.
- Venue clocks, exchange outages, and the difference between a real zero and a missing
  observation - v1's boundary already refuses to forward-fill a flow for this reason.
- One bucket definition across all of it, so a Deribit print, a Binance trade and a Coinbase
  deposit can be put in the same row without inventing an ordering.

---

## The margin of improvement - what v1 leaves on the table, ranked

Ordered by expected gain per unit of work, using what v1 actually measured rather than what
would be interesting to build. **Items 1 and 2 are worth more than everything below them
combined**, because they attack the one failure v1 proved: research-fold IC +0.1412 collapsing
to -0.0553 out of sample.

**1. Stop the out-of-sample collapse (generalisation).** The model is fitted; the folds
flattered it. Concretely: regularisation and capacity search instead of one fixed MLP;
purged/embargoed walk-forward so a 7-day horizon cannot leak across a fold boundary; ensembles
and seed-averaging so a reading is a distribution and not one draw; feature pruning from 22
ledger inputs to the few that survive a fold-stability test; and reporting every candidate's
fold spread, never its mean alone.

**2. A sealed window that has never been touched.** 2026 is spent. v2 seals a period *before*
a line of code is written - 2027 forward, plus a held-back venue - and the sealed number is
read exactly once, at adoption. Without this, no v2 result means anything.

**3. The risk layer the design specified and v1 never built (L5).** Stops, a slow-trend gate,
concentration limits, volatility targeting, and the right to stand aside. v1's -29.90%
drawdown is the cost of its absence, and system 06 already proved this layer is what turned a
losing book into the champion.

**4. Level anchors (A).** The reconstruction knows *when* money moved and not *how much is
there*. Exchange reserves, ETF holdings, miner and treasury balances, entity-adjusted
supply-age bands - these turn the opening distribution from an asserted prior into a
measurement, and they are the highest-value external data in the plan.

**5. External economy and macro - a genuinely new layer (H, below).** FED liquidity, rates,
inflation, the dollar, risk appetite, geopolitics. v1's boundary is the *only* place money
enters crypto, and it is currently inferred from the gap. Macro is what drives that gap.

**6. Multi-venue and multi-instrument (E).** Binance is a large minority of the market.
Coinbase, OKX, Bybit, and the derivatives complex (options, basis, funding across venues) make
the tape the market instead of one view of it.

**7. Behaviour learned, not asserted (L2).** Every propensity rule is a Brock-Hommes prior with
constants nobody fitted. v2 learns them from the reconstruction and reports how much of the
result was the prior.

**8. Market clearing (F).** v1 takes prices from the tape and can therefore never answer a
counterfactual. A clearing layer is what makes the ledger a *simulator* rather than a replay.

**9. True supply histories (C) and participant observables (D).** The float is a snapshot and
the headcount is a guess; both are cheap to fix and both move levels.

**10. The dashboard as an instrument.** Per-cohort P&L attribution, the fiat residual over
time, and a view that shows *which* segment was on the other side of the model's trades.

---

## H. External economy - macro, rates, liquidity, geopolitics

The operator named this and it is not currently anywhere in the model. Crypto's boundary is
the rest of the financial system, and v1 infers that boundary as a residual precisely because
it cannot see it.

- **Central-bank liquidity**: FED balance sheet, reserve balances, the Treasury general
  account, reverse repo - the net liquidity series that moves risk assets on a weekly clock.
- **Rates and the curve**: policy rate, 2y/10y, real yields. The opportunity cost of holding a
  non-yielding asset is a *direct* input to the cohorts' propensity to hold cash.
- **Inflation and growth prints**: CPI, PCE, payrolls - scheduled events with known release
  timestamps, which makes them clean point-in-time features and clean event studies.
- **The dollar and cross-asset risk**: DXY, equity indices, gold, credit spreads, VIX.
- **Geopolitics and regulation**: an event calendar (sanctions, ETF rulings, exchange
  enforcement, country bans) as dated shocks rather than as sentiment text.
- **Stablecoin plumbing as the transmission channel**: issuer attestations, T-bill holdings,
  and mint/burn by chain - the actual pipe between the macro layer and the crypto boundary.

Every one of these enters through **G. The clock**, with its publication lag and its
point-in-time vintage, or it is training on the future.

---

## What v2 must NOT do

- It must not start before v1's 2026 result is on the frontend.
- It must not add a data source without saying which measured blindness it fixes.
- It must not let the agent population grow because more data arrived. The stopping rule is
  still the one in the design: add heterogeneity only while realism metrics keep improving.
- It must not re-open the sealed window. 2026 is spent once, in v1's phase 3.
