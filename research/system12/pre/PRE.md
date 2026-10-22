# System 12 - the state before a signal

316 entries in 2021-2025 (the 20 configurations of each year's book, each entry once), 105 winners, 211 losers. Features read on the 4h candles BEFORE the entry bar.

## Out of sample: a model trained on earlier years, read on year N

| year | entries | AUC (0.5 = nothing) | win rate | win rate, model's top half | bottom half | mean return top | bottom |
|---|---|---|---|---|---|---|---|
| 2021 | 60 | 0.646 | 38% | 50% | 27% | +1.26% | +0.55% |
| 2022 | 56 | 0.577 | 25% | 29% | 21% | -0.62% | -1.95% |
| 2023 | 62 | 0.59 | 36% | 45% | 26% | +3.35% | +1.11% |
| 2024 | 63 | 0.52 | 32% | 31% | 32% | +1.90% | -1.37% |
| 2025 | 75 | 0.501 | 35% | 37% | 32% | +1.05% | +0.83% |

## Winners vs losers, feature by feature (q = p corrected for testing many features; < 0.05 = real difference)

| feature | winners (median) | losers (median) | p | q |
|---|---|---|---|---|
| lower_wick_6 | +0.319 | +0.289 | 0.014 | 0.481 |
| upper_wick_42 | +0.277 | +0.272 | 0.048 | 0.533 |
| accel_18 | +0.141 | +0.010 | 0.056 | 0.533 |
| shooting_star | +0.000 | +0.000 | 0.063 | 0.533 |
| body_6 | +0.413 | +0.436 | 0.083 | 0.563 |
| accel_42 | +0.071 | -0.008 | 0.110 | 0.623 |
| up_share_6 | +0.500 | +0.500 | 0.141 | 0.685 |
| body_18 | +0.413 | +0.423 | 0.205 | 0.803 |
| body_42 | +0.416 | +0.426 | 0.243 | 0.803 |
| hammer | +0.000 | +0.000 | 0.255 | 0.803 |
| upper_wick_18 | +0.283 | +0.276 | 0.279 | 0.803 |
| speed_6 | +0.243 | +0.121 | 0.314 | 0.803 |
| speed_18 | +0.168 | +0.129 | 0.322 | 0.803 |
| range_x_6 | +0.894 | +0.981 | 0.331 | 0.803 |
| up_share_18 | +0.500 | +0.500 | 0.361 | 0.818 |
| range_x_42 | +0.932 | +0.946 | 0.412 | 0.838 |
| lower_wick_18 | +0.311 | +0.302 | 0.441 | 0.838 |
| lower_wick_42 | +0.300 | +0.304 | 0.444 | 0.838 |
| range_x_18 | +0.899 | +0.944 | 0.498 | 0.892 |
| upper_wick_6 | +0.257 | +0.255 | 0.653 | 0.952 |
| volume_x_42 | +0.940 | +0.938 | 0.657 | 0.952 |
| engulf_bear | +0.000 | +0.000 | 0.662 | 0.952 |
| engulf_bull | +0.000 | +0.000 | 0.680 | 0.952 |
| up_share_42 | +0.524 | +0.524 | 0.694 | 0.952 |
| volume_x_6 | +0.964 | +0.975 | 0.761 | 0.952 |
| dist_30d_high | -0.080 | -0.088 | 0.789 | 0.952 |
| speed_42 | +0.007 | +0.068 | 0.825 | 0.952 |
| volume_x_18 | +0.921 | +0.907 | 0.827 | 0.952 |
| inside_bar | +0.000 | +0.000 | 0.838 | 0.952 |
| dist_30d_low | +0.118 | +0.113 | 0.861 | 0.952 |
| taker_6 | +0.000 | +0.000 | 0.883 | 0.952 |
| accel_6 | +0.012 | +0.025 | 0.910 | 0.952 |
| taker_18 | +0.000 | +0.000 | 0.924 | 0.952 |
| taker_42 | +0.000 | +0.000 | 0.990 | 0.990 |
