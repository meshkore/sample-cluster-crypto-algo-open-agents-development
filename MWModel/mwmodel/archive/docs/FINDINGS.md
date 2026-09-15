# What building the archive found

Every entry here was measured on 2026-09-15, on the day the archive was built. They are
recorded because each one was silently wrong before, and three of them had been silently wrong
for a long time.

## 1. The period stamp — a three-week leak in every monthly series

FRED stamps a monthly figure on the **first day of the month it describes**. Adding a
publication lag to that stamp made February's inflation knowable on 19 February. It is
published in March.

Fixed in `Stream.known_at`: wait for the period to *end*, then wait for the publisher.
`lag_days` is now measured from the period end, which is also how every statistical office
quotes its own calendar.

## 2. Row lookbacks are not calendar lookbacks

A year-on-year change computed as "365 rows back" is a year only on a daily grid. On a 24-row
panel it was silently all-NaN. All lookbacks are now in calendar days.

## 3. Unsorted day lists — the one that would have been hardest to find

System 09's feature matrix has one row per (symbol, day) and is grouped **by symbol**, so its
day column runs 2017→2025 fourteen times over. Both the as-of reader and the lookback walked
it with a single forward pointer. After each symbol boundary they read the wrong row and could
not go back.

Effect, measured: the macro block collapsed from 99% coverage to **2%**. Nine of its ten
columns were zero. A model would have reported "macro does not help" — correctly, about a
block that was not there.

Fixed by resolving the unique days once and scattering back, in both `clock.history` and
`transform.apply`. Sorted, unique input takes the same path and is unchanged.

## 4. A stale reading standing for the present

An as-of reader carries the last observation forward forever. FRED **stopped mirroring the
OECD's national inflation series**, and nothing noticed:

| series | last observation | age today |
|---|---|---|
| Japan CPI | 2021-06 | 1,863 days |
| Korea CPI | 2023-11 | 1,020 days |
| South Africa CPI | 2025-01 | 552 days |
| UK, India CPI | 2025-03 | 493 days |
| China, Brazil, Turkey CPI | 2025-04 | 463 days |

A 2026 evaluation was about to be fed Japan's inflation rate from five years earlier as though
it were current — and a constant column across a whole era is the most reliable way ever found
to teach a model the calendar.

Every stream now carries an expiry (`Stream.stale_after`, derived from its frequency plus its
publication lag). Past it, the reader returns `None` and the column is NaN, which
`Panel.drop_sparse` can remove. `inventory` prints the expired list every run.

## 5. Free monthly inflation for the world does not exist

Probed directly rather than assumed:

| source | coverage | current to | verdict |
|---|---|---|---|
| FRED `CPIAUCSL` | US | last month | good |
| Eurostat `prc_hicp_manr` (keyless JSON) | euro area, EU members, TR, NO, CH, RS | current | good |
| FRED OECD mirrors | JP CN IN BR ZA KR UK TR | 2021-06 … 2025-04 | **dead** |
| IMF via DBnomics (keyless) | JP CN IN BR ZA KR TR GB CA US ID RU AE | 2025-06/07 | a year behind |
| OECD SDMX直 | — | — | 403/404, needs a key |
| World Bank | everywhere | annual | too slow |

So the archive uses what is current, marks the rest expired, and leans on the channel that
*is* daily, current, never revised and genuinely regional: **the currency, the local bond and
the local equity market**. What a holder in São Paulo faces shows up in USD/BRL today;
inflation is the slow confirmation that arrives a quarter later.

## 6. The high-yield spread covers a third of our record

FRED serves only the **last three years** of `BAMLH0A0HYM2` — an ICE BofA licence window, not
a request that can be phrased better. Our copy starts 2023-09-18, so the credit channel had
22% coverage and could not see a single credit cycle.

Replaced with two series that carry the same channel without the restriction:
`BAA10Y` (Moody's Baa over the 10-year, from 1986, 10,174 observations) and `STLFSI4` (the St.
Louis Fed's financial stress composite, from 1993). Credit-channel coverage went from **0.227
to 0.958**. The high-yield spread stays registered, with the licence noted, because where it
exists it is the sharper reading.

## 7. The crypto feeds are seventeen days behind

Not a defect in the archive — a defect the archive *reports*. Funding, Fear & Greed and the
on-chain series were last harvested on 2026-08-29. 25 of the 37 streams that show as expired
today are simply an overdue harvest, and they now say so out loud instead of quietly serving
a fortnight-old number as today's.

---

## 8. The most important finding: the market head is not yet an edge

The market head was measured twice on the same day, with each block priced separately against
a 2025 nobody selected on. Between the two runs **one feature changed** — the credit channel
moved from the three-year high-yield spread to the forty-year Baa spread plus the stress index
(finding 6). Nothing else.

| arm | run A: held-back 2025 | run B: held-back 2025 | selection worst (A → B) |
|---|---|---|---|
| crypto only | −17.61% | −17.61% | +0.00% → +0.00% |
| crypto + liquidity | **+19.01%** | **+5.21%** | −2.55% → −10.94% |
| crypto + regional | +10.42% | +10.42% | −14.06% → −14.06% |
| everything | +5.65% | +0.06% | −5.27% → −11.08% |
| world only | −0.04% | −0.10% | −6.20% → −27.59% |

Repairing *one* input moved the headline arm by **fourteen points** on the held-back year.
That is not a result about credit spreads. It is a measurement of how unstable the measurement
is, and it settles the question honestly: with **~94 independent 30-day windows in the entire
record**, none of these arms is distinguishable from any other, and "the liquidity block pays"
would have been a story told about noise had the run stopped an hour earlier.

What survives:

- **The regional block does not pay for itself.** It is unchanged across both runs (+10.42%)
  and it widens the worst selection year to −14%. A measured answer to the operator's
  question, and not the one that was hoped for.
- **`crypto only` overfits visibly** — best on the selection years, worst by far on the
  held-back one. That is the shape of selection optimism and it is at least legible.
- **No configuration here has earned a sealed 2026 reading.** This laboratory has spent four
  of those, three on edges whose year-to-year spread straddled break-even. The bar is a spread
  that does not straddle it, and nothing above clears that bar.

The right next move is not another arm. It is more independent observations — a shorter
horizon for the market head, or a second market to test the same block on — because at 94
windows the experiment cannot answer the question being asked of it, however the table is
arranged.
