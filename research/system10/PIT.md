# Point-in-time universe (audit 2026-10-15, item 1)

**Method.** Test year N trades the top 14 USDT pairs by trailing-30-day turnover on 31 Dec N-1,
among pairs with >= 540 days of 15m history and >= $10M/day turnover then; delisted pairs
included (Binance archive). Rule: `universe_pit.py`, lists: `rnd/universe_pit.json`. One world
per year, walk-forward as `search.evaluate` (selector < N-1, bar on N-1, exit < N, read N).
Breadth is rebuilt from candles; on today's 14 it equals 06's cache on all 3,005,366 bars.
Both columns re-run today, same code and seeds; the 14-coin run reproduces the releases' numbers.

| 2022-2026 | 2022 | 2023 | 2024 | 2025 | 2026 fwd | law score | CAGR 22-25 | max DD |
|---|---|---|---|---|---|---|---|---|
| r31, today's 14 | +29.1 | +17.5 | +47.8 | +30.6 | +22.3 | 0.226 | +30.8 | 22.6 |
| **r31, PIT** | 0 (0 tr) | +7.4 | +4.8 | +42.9 | **-10.6** | 0.038 | +12.6 | **30.6** |
| r34 (champion), 14 | +43.0 | +19.4 | +80.4 | +35.2 | +40.3 | 0.270 | +42.9 | 24.4 |
| **r34, PIT** | 0 (0 tr) | +8.9 | +12.1 | +63.6 | **-15.1** | 0.072 | +18.9 | **32.2** |
| r43 (paper), 14 | +9.2 | +16.2 | +105.5 | +79.5 | +49.3 | 0.272 | +47.1 | 20.0 |
| **r43, PIT** | 0 (0 tr) | +10.7 | +35.5 | +97.6 | **-6.3** | 0.158 | +31.2 | 23.2 |

Return % / max DD %. Win rate and trades per year: `rnd/pit_rebook.json`. PIT trades 2022/23/24/25/26
for r31: 0 / 11 / 1,313 / 915 / 423 (today's 14: 327 / 86 / 1,677 / 1,447 / 1,489).

**Coins.** 2022: BTC ETH BNB MATIC XRP ADA DOGE FTM TRX GXS LINK LTC ATOM CTXC (GXS delisted
04/2022). 2023: + SOL SHIB TWT CHZ. 2024: + AVAX OP INJ NEAR DOT. 2025: + PEPE SUI HBAR.
2026: BTC ETH SOL ZEC XRP BNB DOGE SUI TRX ADA LINK AVAX BCH PEPE (today's list has ACE WLD NEAR).

**Reading.** The edge does not survive an honest coin list. 2022: on 2021 (BTC up-regime 69% of
bars) the selector picked a 10% take-bar (q 8.0 vs 5.5 at 50%); in 2022 (up-regime 7%) no bar
clears it, so the year is flat with 0 trades (at 50% it would take 49,537 bars). 2023 trades 11
times, 2024 breaks the 25% DD cap, 2026 forward is negative for all three; 2025 is higher. The
take-bar share flips 0.1 <-> 0.5 with the coin list: a bar fixed on one regime year and applied
to the next is the fragile part, and today's 14 survivors were hiding it.

**Decision.** No release is eligible on PIT (zero-trade year, DD > 25%). Do not switch the
search yet (memory: one world per year; operator review pending). Next: make PIT the evaluation
universe (union world with per-year masks), then nested selection on it. Opt-in only:
`search.World(universe=N)`; re-book: `python -m system010_conditioned_rl.pit --releases 31 34 43`.
