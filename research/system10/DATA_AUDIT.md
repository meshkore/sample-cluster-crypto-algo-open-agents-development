# System 10 — data audit (S10-4)

*2026-09-30. Produced by `tools/audit_candles.py` → `tools/audit_candles_2026-09-30.json`
and a read-only review of how system 06 aligns its external series. Seal and registry
enforced by `trading-system/tests/test_system010_seal.py`.*

**Verdict: the candles are whole and sealed; nothing needed fixing.** One external series
the *champion* uses has no declared publication lag, and system 10 will not use it until it
has one.

## 1. Candles — 14 symbols, 15m, through the catalogue's `research()` entry point

| symbol | first bar | bars | coverage | gaps | missing bars | longest gap | zero-volume bars |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 2017-08-17 | 293,083 | 99.81% | 33 | 565 | 33.75 h after 2018-02-08 00:15 | 56 |
| ETHUSDT | 2017-08-17 | 293,083 | 99.81% | 33 | 565 | 33.75 h after 2018-02-08 00:15 | 150 |
| BNBUSDT | 2017-11-06 | 285,335 | 99.81% | 32 | 538 | 33.75 h after 2018-02-08 00:15 | 156 |
| ADAUSDT | 2018-04-17 | 269,931 | 99.86% | 26 | 389 | 10.25 h after 2018-06-26 01:45 | 14 |
| XRPUSDT | 2018-05-04 | 268,283 | 99.86% | 26 | 389 | 10.25 h after 2018-06-26 01:45 | 14 |
| TRXUSDT | 2018-06-11 | 264,621 | 99.85% | 26 | 389 | 10.25 h after 2018-06-26 01:45 | 14 |
| LINKUSDT | 2019-01-16 | 243,722 | 99.89% | 21 | 270 | 10.25 h after 2019-05-15 02:45 | 161 |
| ZECUSDT | 2019-03-21 | 237,626 | 99.90% | 20 | 246 | 10.25 h after 2019-05-15 02:45 | 291 |
| DOGEUSDT | 2019-07-05 | 227,462 | 99.91% | 18 | 202 | 8.25 h after 2019-08-15 01:45 | 614 |
| SOLUSDT | 2020-08-11 | 188,906 | 99.95% | 10 | 94 | 4.75 h after 2021-04-25 04:00 | 10 |
| NEARUSDT | 2020-10-14 | 182,766 | 99.95% | 10 | 94 | 4.75 h after 2021-04-25 04:00 | 10 |
| SUIUSDT | 2023-05-03 | 93,456 | 100.00% | 0 | 0 | — | 0 |
| WLDUSDT | 2023-07-24 | 85,596 | 100.00% | 0 | 0 | — | 0 |
| ACEUSDT | 2023-12-18 | 71,496 | 100.00% | 0 | 0 | — | 7 |

**Integrity checks — zero on every symbol:** duplicate stamps, steps off the 15-minute
grid, stamps off the quarter-hour clock, non-positive prices, high < low, open or close
outside [low, high].

**The gaps are the exchange's, not the loader's.** Symbols listed at the same time carry
identical gap counts and the same longest outage at the same minute (2018-02-08: Binance's
33-hour maintenance halt; 2019-05-15, 2021-04-25 likewise). They are not filled: a filled
bar is a price nobody could trade at. The environment (S10-7) must treat a gap as time
passing with no fill, which is what the backtester already does.

**Zero-volume bars** (0.00–0.27% of a symbol's bars, DOGE the most) are kept. They are real
prints of an idle market; `volume_ratio_20` and the impact model already see them as such.

**Clock alignment across symbols.** From the last listing (ACEUSDT, 2023-12-18 06:00) on,
all 14 symbols carry exactly the same 71,496 stamps; none is missing anywhere.

**The universe is not constant.** It grows from 2 symbols (2017-08) to 14 (2023-12). A
per-year result before 2021 is a result on a smaller book; S10-6's coverage table must be
read per year for that reason. (The task sheet mentioned DOT and AVAX; neither is in the
frozen universe `research/system06/universe.json` — the listing dates above are the
universe's own.)

## 2. External series — are they point-in-time with a declared lag?

| series | used by 06 as | how it is aligned | declared lag | 010 may use it? |
|---|---|---|---|---|
| FRED: NASDAQCOM, VIXCLS, DTWEXBGS, DCOILWTICO, DGS10, T10Y2Y | optional net features (A96), **not** in the shipped net | `cutoff = bar − lag`, last observation at or before it (`reference.py:122`) | yes, per series, 4–14 days (`reference.py:57`) | yes |
| Fear & Greed (`feargreed.json`) | **the champion's veto gate** (`fng_min: 25`) | last value stamped strictly before the bar (`modules/crowd.py:63`) | **none** — the daily stamp (00:00 UTC) is taken as the publication time, so a bar from 00:15 on day D reads day D's value | **no, until a lag is recorded** |
| funding_* (14) | optional gate (`micro_gate`), off in the champion | last settlement strictly before the bar (`microstructure.py:140`) | none; the settlement stamp *is* the moment the rate is final, which is sound | yes, with the lag recorded as 0 by argument |
| chain_n-unique-addresses | optional gate (`activity_min`), off in the champion | last point stamped strictly before the bar (`modules/onchain.py:79`) | **none**, on a 4-day grid stamped at 00:00 — if a stamp opens the window it measures, up to ~4 days of look-ahead | **no, until a lag is recorded** |
| other chain_*, oi_BTCUSDT, etf_flow_btc, stablecoin_supply, market-cap series, circulating_supply | not consumed by 06 (some by 09) | — | — | no |

**The shipped net uses no external series.** Its standardizer is exactly the 44 price- and
volume-derived columns of `FEATURE_COLUMNS`; the `feargreed` channel feeding the
`sentiment` module is a proxy built from price (`infer.py:143`), not the file above.

## 3. The seal

`test_system010_seal.py` proves, on this machine's data, that both research paths 010
trains from — `quantlab_catalog.candles.research()` and the inherited
`system006_oracle_net_15m.dataset.Dataset.research()` — return no bar dated 2026 and end at
**2025-12-31 23:45 UTC** on every symbol. Reading 2026 requires `candles.forward()` or
`include_sealed=True`, each a deliberate call that shows in a diff; only S10-11 makes it.

## 4. The feature registry

`trading-system/systems/system010_conditioned_rl/features.py` freezes the state: a 96-bar
window of the 44 market columns (copied as literals, and tested equal to both 06's
`FEATURE_COLUMNS` and the live net's standardizer) plus six book fields — position held,
unrealised return, bars held, slots free, drawdown from the year's peak, region id.

**Content hash: `fa689b86f14e85c979cac86727085791a1a1414ec6b428838b947ef030c87e3c`**

The test pins it. A feature is added only with a row in the system's *What helped* or
*What hurt*, and the hash moves in the same commit.

## 5. Open

| item | why it matters | owner |
|---|---|---|
| Fear & Greed has no declared publication lag, and 06 gates on it | if the index for day D is not published by 00:15 UTC, 06's backtests read it early, and a veto that only *blocks* entries would flatter them by skipping bad days it could not yet see. **Bounded for the live engine:** v3-exit-010 vetoes below 6.93, which the index reached on 3 research days in 8 years (2019-08-22, 2022-06-18/19); a 1-day lag changes the gate on at most 4 days, so no live number can depend on it. `best.json`'s `fng_min: 25` fires far more often and is the configuration exposed | system 06 — measure the index's real publication time and declare the lag before any configuration with a high `fng_min` is shipped |
| `chain_n-unique-addresses` is stamped at the start of a 4-day window with no lag | possible look-ahead; off in the champion, so no shipped number depends on it | system 06 — declare the lag before anyone turns `activity_min` on |

Neither is fixed here: the fix belongs in 06's modules, not in the catalogue loaders, and
S10-4 only fixes what is additive in the catalogue.
