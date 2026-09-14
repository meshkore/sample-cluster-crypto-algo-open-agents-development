# System 09 - The Ledger

> **Status: v1 complete - all four phases have run.** Opened 2026-09-14 as a design; the code gate was
> lifted the same day. The laboratory reports against the operator's three phases - see
> `.meshkore/context/system09-design.md`, which maps them onto the design's eight and keeps
> all of that detail:
>
> | | | |
> |---|---|---|
> | **Phase 1** | reconstruct the whole record, every asset from the day it first trades, liquidity and players managed through time, balances set at 2025-12-31 | **BUILT** - `python -m quantlab_system09.phase1` |
> | **Phase 2** | train the model on how the players actually behaved | **BUILT** - `python -m quantlab_system09.train` |
> | **Phase 3** | forward-test from 2026-01-01, simulate trading as close to reality as possible, measure the success ratio | **RUN** - `python -m quantlab_system09.phase3`, and see the caveat below |
> | **Phase 4** | local frontend: totals, market capitalisation, balances by segment, the 2026 section | **BUILT** - `research/system09/preview/server.py`, port 8709 |
>
> **The sealed 2026 window was read three times** and no reading is a clean out-of-sample
> result. The last one returned +17.85% with a *negative* skill statistic on the same rows
> (IC -0.0553), which is the finding: research-fold IC +0.1412 collapsed to -0.0553 out of
> sample. `docs/RESULTS.md` carries all three readings and why none may be quoted.
>
> Before touching this system, read `.meshkore/context/LESSONS.md` - the digest of every rule
> the previous systems paid for. System 09 is not allowed to re-derive any of them.

## 1. Hypothesis

The forecastable part of crypto returns is driven by participant *constraint* rather than by
chart shape: who has run out of cash, who is underwater and by how much, who is levered near
a liquidation band, who is mechanically obliged to rebalance. Those constraints are stocks,
they move slowly, and a conserved stock-flow-consistent reconstruction of them from the
public tape plus the observable boundary flows should therefore carry information that the
candle features of systems 04-08 do not contain.

## 2. What it is

A double-entry, stock-flow-consistent model of the crypto market as a closed sector with a
short boundary. Inside, every trade is a conserved transfer of units and cash between latent
behavioural cohorts; the totals change only at the boundary. Six layers are planned; **two
exist**:

- **L0 `ledger.py`** - the books. `settle()` is handed unit deltas that must sum to zero and
  derives every cash leg itself, so no caller can write one side of a transfer. Totals move
  only through `issue`, `mint`, `burn`, `inject`. Agents hold a book of coins per symbol and
  **one shared cash balance**. The conservation law is asserted in the hot path.
- **L1 `reconstruct.py`** - the inverse problem. Per dollar-volume bucket the tape gives four
  pool sizes exactly (aggressive and passive, buy and sell); the model decides only *which
  participants filled them*, by water-filling desire x capacity against hard cash and unit
  limits plus a per-cohort daily turnover budget.

**The population is a pyramid, and an agent is a profile group.** Each agent is born into a
class - retail, whale, institution, market maker, miner, venue - and the number of agents per
class follows the real market: retail is by far the most numerous, market makers are a
handful. One retail agent stands for about a hundred thousand people who behave the same way,
so the books carry hundreds of balance sheets and report tens of millions of participants.

**The record is the whole record.** It opens on 2017-08-17, the first day Binance has a tape,
with an empty ledger and an empty population - nothing is handed out by a constructor. The
fourteen assets of the laboratory's universe join on the day each first trades, bringing
their float. Players are born and retired against observed activity. It closes on 2025-12-31
and the balances there are the opening state for phase 2.

**The five boundary channels**, four observed and one inferred: Bitcoin issuance
(`chain_total-bitcoins`), asset listings, stablecoin mint and burn (DefiLlama), ETF creations
and redemptions (Farside, from 2024-01), and **fiat** - which no public series has ever
measured, and which is therefore treated as a residual: the reconstruction reports how many
dollars of buying the population could not fund, and exactly that much is ramped in and
recorded. The resulting series is a measurement of what the stablecoin float fails to
explain, not a plug.

Propensity rules are the Brock-Hommes family and **none of their constants are fitted to this
laboratory's data**. The perpetual book is pinned to Binance's published open interest.

## 3. What helped

| Change | Measured effect | Evidence |
|---|---|---|
| Using the existing 15m `taker_buy_volume` instead of downloading aggTrades | the aggressor/passive split the design calls the spine was already local from 2017-08; the whole build needed zero tape bytes | `quantlab_catalog.research()` schema |
| One shared cash pool across fourteen assets | removed the single largest fudge of the one-asset MVP, which gave BTC a private share of the sector's cash and so invented liquidity. Dry powder spent on one asset is now gone from the others. | `ledger.Agent`, `test_cash_is_shared_across_assets` |
| Allocating flow by **desire x capacity** rather than desire alone | without it the size ladder is inert: a bottom-rung agent with a rounding error of cash wins the same share as the top rung | Q1-2024 smoke runs |
| A per-cohort **daily turnover budget** | the constraint that makes a holder a holder; before it, long-term holders with 60% of the float became the market's largest day trader | Q1-2024 smoke runs |
| **Structural** miner selling, allocated before the shared pool | miners were net *buyers* of 105k BTC in H1-2024 when they competed for a weighted share; correct sign restored once issuance was pre-allocated | H1-2024 smoke runs |
| A **velocity-aware** fiat ramp | ramping the bare shortfall converges far too slowly, because a dollar given to a cohort that turns over 3%/day buys 3 cents of the gap. Dividing by the velocity the sector just demonstrated lifted the early-record fill from 0.73 to 0.97. | 2017-2018 slice, before and after |
| Renormalising an asset's listing float over the cohorts that actually hold it | a thinly-held token has cohorts with no interested agent, and skipping their share floated less than the real supply - Worldcoin arrived two thirds short | asset table, before and after |
| Anchoring the perp book to observed open interest | replaced a constant times a trend with Binance's published series, 2,143 days from 2020-11 | `oi_BTCUSDT.json` |
| Conservation asserted in the hot path | caught every real bug at the bucket that caused it and named the offending agent | `ledger.check`, `tests/test_system09_ledger.py` |

## 4. What hurt

| Change | Measured effect | Evidence |
|---|---|---|
| Bitcoin active addresses as the population driver | the population sat at a constant headcount for the entire eight-year record. BTC active addresses peaked in 2017 and have been flat since, because the activity moved onto exchanges and other chains where that series cannot see it. | per-year table, first full run |
| The stablecoin float as the second population bracket | the free series begins at **$110,000** in 2017, so every later reading is a millionfold growth and the ladder saturates in its first year. That number measures the birth of a product, not the arrival of a crowd. | preview run, rungs pinned at the ceiling from 2018 |
| Alt supply as a held-constant snapshot | every asset except Bitcoin carries today's circulating supply across the whole record, because free historical market-cap data stops at one year. Assets still emitting hold too large a float in the early years. | `harvest.fetch_circulating_supply` |
| Opening cohort priors (`COIN_PRIOR`, `CASH_PRIOR`) | asserted, not measured. They set the *levels* of every stock, so any cohort's reported holdings are a prior with eight years of tape on top. | `cohorts.py` |
| Declaring the V2 verdict on the single best statistic | the first implementation reported RECOVERED on weekly pearson alone; a vote over all nine reversed it. This laboratory's selection optimism in miniature. | `validate.anchor_recovery` |
| **The population pyramid was upside down** | 148 whales, 84 institutions, 20 retail. Real crypto is the other way up: institutions are few, whales are more, and retail is thousands upon thousands. Every cohort had been given the same number of rungs, so class headcount was an accident of the ladder rather than a statement about the market. | operator, 2026-09-14; segment table before the fix |
| Splitting whales from retail by a **net-worth threshold** | twice wrong. An absolute $100M line put 99.99% of private wealth in one bucket, because an agent here is a representative bucket worth billions, not a household. Re-ranking the richest tenth each day fixed the arithmetic and still said the wrong thing: a whale is a *kind* of participant, not whoever happens to be rich today. | `segments.py`, two rewrites |
| Long-term-holder turnover cap of 0.2%/day | far too loose - the cohort shed 2.09M coins in 2021 alone. Tightened to 0.03%/day, which is nearer the published cycle amplitude of long-term-holder supply. | one-asset MVP per-year table |

## 5. What is still open

- **The ledger features do not survive out of sample.** Walk-forward mean IC +0.1412 against
  -0.0553 on the sealed rows. Either the reconstruction's information is real but unstable, or
  the folds were optimistic; v1 cannot tell which apart, and that is the first question for v2.
- **The sealed window is spent.** Three readings. The next forward test needs a period this
  system has never touched.
- **No risk layer.** Phase 3 has no stops, no trend gate, no concentration limit - the design
  (L5) specifies them and they were never built. The -29.90% drawdown is that absence.
- **The population count is the number least entitled to be believed.** Neither observable
  bracket measures participants; the geometric mean of two wrong things is a prior.
- **V2 has been run against one anchor.** Open interest and exchange reserves are untested.
- **L2 to L5 do not exist.** No behaviour learning, no market clearing, no forward
  simulation, no trading policy. Nothing here is evidence about any of them.
- **One venue.** Binance only. Multi-venue and on-chain fusion remain in the design.

## 6. Rules learned

- A trade does not move money into or out of the ecosystem; it redistributes it. Only the
  boundary changes the totals. Any "money flowing into crypto" claim that counts trade
  notional is counting the same dollar many times.
- Exchange tape is anonymous. Participants are latent cohorts pinned by accounting identities
  and external anchors; they are not reconstructed wallets.
- **One wallet, many assets.** Giving each market its own pile of cash invents liquidity, and
  competition for one pool is most of what modelling an ecosystem means.
- **Wanting and being able to are both required.** An allocator that uses capacity only as a
  cap, never as a weight, silently deletes its own size distribution.
- **A cohort is defined by its turnover, not only by its opinion.**
- **Class is intrinsic; size is not a class.** A whale, an institution and a market maker are
  different creatures, not three sizes of one. Deciding class from the balance sheet produces
  a market whose shape changes with the price level.
- **Report headcount twice.** An agent is a profile group standing for many real participants,
  so "players" and "people" are different numbers and a dashboard that shows only the first is
  reporting model buckets as if they were humans.
- **Forced flow must be allocated before discretionary flow**, or a structural seller stops
  being structural and changes sign.
- **What cannot be observed should be inferred and reported, never assumed.** The fiat
  channel is a measurement of the gap, and it is checkable because it must fade as the
  stablecoin float grows.
- **Check the base of any growth factor before using it as a driver.** A series that starts
  near zero produces an infinite growth rate and saturates whatever it drives.
- A held-out anchor is evidence only when scored against the signal that drove the
  prediction; without that control you are claiming credit for the trend.
- Declare a verdict on a vote over every statistic computed, never on the best one.
- A new system reads the previous systems' summaries first, and
  `.meshkore/context/LESSONS.md` before that.
