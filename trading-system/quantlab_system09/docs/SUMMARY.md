# System 09 - The Ledger

> **Status: workshop.** Opened 2026-09-14 as a design; the code gate was lifted the same
> day and the Phase 3 MVP (L0 + L1, validated at V0 and V2) now runs end to end with
> `python -m quantlab_system09.mvp`. The full plan is
> `.meshkore/context/system09-design.md`. Before touching this system, read
> `.meshkore/context/LESSONS.md` - it is the digest of every rule the previous systems
> paid for, and system 09 is not allowed to re-derive any of them.

## 1. Hypothesis

The forecastable part of crypto returns is driven by participant *constraint* rather than by
chart shape: who has run out of cash, who is underwater and by how much, who is levered near
a liquidation band, who is mechanically obliged to rebalance. Those constraints are stocks,
they move slowly, and a conserved stock-flow-consistent reconstruction of them from the
public tape plus the observable boundary flows should therefore carry information that the
candle features of systems 04-08 do not contain.

## 2. What it is

A double-entry, stock-flow-consistent model of the crypto market as a closed sector with a
short, observable boundary. Inside, every trade is a conserved transfer of units and cash
between latent behavioural cohorts; the totals change only at the boundary - stablecoin mint
and burn, ETF creation and redemption, miner issuance, exchange fees. Six layers are
planned; **two exist**:

- **L0 `ledger.py`** - the books. `settle()` is handed coin deltas that must sum to zero and
  derives every cash leg itself, so no caller can write one side of a transfer. Totals move
  only through `issue`, `mint`, `burn`, `inject`. The conservation law is asserted in the
  hot path, not in a test.
- **L1 `reconstruct.py`** - the inverse problem. Per dollar-volume bucket the tape gives
  four pool sizes exactly (aggressive and passive, buy and sell); the model decides only
  *which cohorts filled them*, by water-filling desire x capacity against hard cash and coin
  limits plus a per-cohort daily turnover budget.

Population: 106 agents - seven trading types on a 13-rung Zipf size ladder, a miner ladder,
a perpetual ladder, and two boundary operators. Propensity rules are the Brock-Hommes family
and **none of their constants are fitted to this laboratory's data**.

Data consumed, all free and all now in the shared catalogue: Binance 15m candles **with
`taker_buy_volume`** (the aggressor/passive split, the spine of the whole design - it was
already on this machine, which is why the MVP needed no tape download), perp funding,
`chain_total-bitcoins`, `stablecoin_supply` (DefiLlama), `etf_flow_btc` (Farside).

## 3. What helped

| Change | Measured effect | Evidence |
|---|---|---|
| Using the existing 15m `taker_buy_volume` instead of downloading aggTrades | the aggressor/passive split - the field the design called the spine - was already local from 2017-08; the MVP needed zero tape bytes | `quantlab_catalog.research()` schema |
| Allocating flow by **desire x capacity** rather than desire alone | without it the size ladder is inert: a rung-12 agent with a rounding error of cash wins the same share as rung-0 | first Q1-2024 smoke run vs the second |
| A per-cohort **daily turnover budget** (`TURNOVER_CAP`) | the constraint that makes a holder a holder; before it, long-term holders with 60% of the float became the market's largest day trader | Q1-2024 smoke runs |
| **Structural** miner selling, allocated before the shared pool | miners were net *buyers* of 105k BTC in H1-2024 when they competed for a weighted share; they became net sellers, the correct sign, once their issuance was pre-allocated | H1-2024 smoke runs |
| Opening every agent's cost basis at the opening price | an opening basis of zero makes every cohort infinitely profitable on day one and silences every profit-based rule | `cohorts.build_population` |
| Conservation asserted every step rather than at the end | caught both real bugs immediately and named the offending agent (levered cohort paying funding with no margin; one-sided deltas) | `ledger.check`, `tests/test_system09_ledger.py` |

## 4. What hurt

| Change | Measured effect | Evidence |
|---|---|---|
| **V2 anchor recovery did not clear its baseline** | held out of the ETF series, the inferred institutional cohort tracks published ETF flow (weekly pearson **+0.451**) but the naive trend rule that drives it already scores **+0.383**, and the reconstruction wins only **4 of 9** statistics. The ledger machinery added nothing a moving average did not already have. | `research/system09/mvp_report.json` |
| Scoring the verdict on the best statistic | the first implementation declared RECOVERED on weekly pearson alone; a vote over all nine reverses it. This is the lab's selection optimism in miniature and it was caught in the same hour it was written. | `validate.anchor_recovery` |
| Stablecoin float as the cash side, before ~2022 | the population cannot fund the observed tape: fill ratio 0.959 in 2020 and **0.898 in 2021**, worst day 0.160. Pre-2022 exchange cash was mostly fiat and is not observable anywhere. | per-year table in `RESULTS.md` |
| Handing BTC cohorts a share of the *whole* sector's stablecoin float | the largest modelling liberty in the MVP. `btc_cash_share` splits it by BTC's measured share of universe dollar volume, which is a measurement, but attention is not allocation. | `boundary.btc_cash_share` |
| Turnover cap of 0.2%/day for long-term holders | still far too loose: the cohort sheds 2.09M coins in 2021 alone and falls from 60% to 21.7% of the float over six years. Real long-term-holder supply does not move like that. | per-year table |
| Opening cohort priors (`COIN_PRIOR`, `CASH_PRIOR`) | asserted, not measured. They set the *levels* of every stock in the output, so the level of any cohort's holdings is a prior with six years of tape on top, not a measurement. | `cohorts.py` |

## 5. What is still open

- **The kill switch was skipped.** Phase 2 - testing the *observable* proxies as a strict
  addition to the champion - was designed to run before any of this and did not. It is now
  the single most valuable next step, and V2's result makes it more urgent, not less.
- **Is the state identified at all?** V2 says the institutional cohort is not identified
  beyond its own driving signal. It does not say the *other* cohorts are not; the test can
  be repeated against open interest (Binance `metrics`, free, not yet downloaded) and
  against exchange reserves.
- **Would calibration change the answer?** Every constant is an unfitted prior. The design
  names the machinery (simulated minimum distance, neural posterior estimation); none of it
  has been applied, and V2 failing with unfitted priors is weaker evidence than V2 failing
  after calibration.
- **L2-L5 do not exist.** No behaviour learning, no market clearing, no forward simulation,
  no trading policy. Nothing here is evidence about any of them.
- **One pair, one venue.** BTCUSDT on Binance. Multi-symbol and multi-venue is Phase 5.

## 6. Rules learned

- A trade does not move money into or out of the ecosystem; it redistributes it. Only the
  boundary changes the totals. Any "money flowing into crypto" claim that counts trade
  notional is counting the same dollar many times.
- Exchange tape is anonymous. Participants are latent cohorts pinned by accounting
  identities and external anchors; they are not reconstructed wallets, and a design that
  claims otherwise cannot be validated.
- **Wanting and being able to are both required.** An allocator that uses capacity only as a
  cap, never as a weight, silently deletes its own size distribution.
- **A cohort is defined by its turnover, not only by its opinion.** Without a rate limit,
  every cohort collapses into "whoever holds the most", and the taxonomy is decoration.
- **Forced flow must be allocated before discretionary flow.** A structural seller that
  competes for a weighted share stops being structural and changes sign.
- A held-out anchor is only evidence if it is scored against the signal that drove the
  prediction. Correlating an inferred cohort with a published series, without that control,
  is claiming credit for the trend.
- Declare a verdict on a vote over every statistic computed, never on the best one.
- Matching stylized facts is necessary and nowhere near sufficient - many different agent
  populations produce the same ones.
- A new system reads the previous systems' summaries first, and
  `.meshkore/context/LESSONS.md` before that. System 06's risk layer and consistency law are
  inherited here, not re-derived.
