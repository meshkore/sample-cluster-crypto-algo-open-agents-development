# Forward tracker: the 4h / 1-day signal on the prospective window

Updated 2026-10-21T14:26:40+00:00. Models frozen on 2020-2025; window from 2026-10-19 00:00 UTC; the 2026 PIT list.
Sealed-2026 reference (READINGS.md #1): gross IC 0.049-0.059, t 2.4-2.8. A t is reported once 30+ days exist.

| model, seed set | bars predicted | bars scored | mean gross IC | t (daily, non-overlapping) | top-3 minus bottom-3, gross per day |
|---|---|---|---|---|---|
| ridge s1 | 15 | 8 | -0.4451 | n < 30 days | -0.02086 |
| gbm s1 | 15 | 8 | -0.5115 | n < 30 days | -0.03184 |
| ridge s2 | 15 | 8 | -0.428 | n < 30 days | -0.02035 |
| gbm s2 | 15 | 8 | -0.5083 | n < 30 days | -0.03941 |
