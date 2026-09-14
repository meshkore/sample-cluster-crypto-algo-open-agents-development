---
title: "System 09 version 2 - the roadmap of data and scope"
category: context
updated: 2026-09-14
owner: master
status: planned (version 1 is not finished)
---

# System 09 v2 - what the next version is for

**Version 1 finishes when the frontend shows the 2026 forward test.** The operator set that
line on 2026-09-14: *"cuando tengamos el frontend de este sistema de trading y tengamos
resultados de 2026 y se puedan ver graficamente en el frontend, ahi pararemos"*. Nothing on
this page is started before that.

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

## What v2 must NOT do

- It must not start before v1's 2026 result is on the frontend.
- It must not add a data source without saying which measured blindness it fixes.
- It must not let the agent population grow because more data arrived. The stopping rule is
  still the one in the design: add heterogeneity only while realism metrics keep improving.
- It must not re-open the sealed window. 2026 is spent once, in v1's phase 3.
