# The intraday system (5m)

*Status: **frozen** · opened 2026-08-12, closed 2026-08-14.*

> Written from this system's own measured record — its README tables, the task
> records under `.meshkore/modules/`, and its commit bodies. Every figure below
> carries the source that holds it, so a reader who distrusts a number can check
> the same place I did.

## 1. Hypothesis

A second timeframe carries edges the daily and 15m books cannot see: five USDT majors on 5-minute bars, one hypothesis per file.

## 2. What it is

5-minute bars, five USDT majors, cached indicator panels, one file per hypothesis.

**Data consumed:**

- 5m candles, five USDT majors, downloaded and cached by system002_intraday_momentum_5m.prepare
- indicator panels keyed by a digest of the OHLCV stream they were built from

## 3. What helped

- **One harness for every hypothesis - same blocks, same costs, same sealed window, same cost decomposition** — the only reason two hypotheses in this system are comparable at all; a new idea is one file and one command *(README.md)*
- **An idempotent prepare whose cache key is a digest of the candles** — a panel is rebuilt only when the candles it was built from changed, so a stale panel is discarded rather than served *(README.md)*
- **Sizing the trade by how strong the signal is** — adopted because the measured response is monotone, not because it sounded right *(16234be)*
- **A market-wide gate that exists in BOTH halves via the warm-up** — a strategy that forgets the warm-up gate now cannot trade the warm-up, so training and forward see the same rule *(e902834, efda7b4)*

## 4. What hurt

*This section matters more than the one above: it is the part that cannot be
reconstructed from the code.*

- **Assuming a closing bell** — nothing closes because of the clock - this market has no bell, and the rule that assumed one was measuring a different market *(b585b55)*
- **A sealed window that only measures rules which trade in a bear year** — the window could not see a rule that sat out 2022, so the comparison it produced was not the one anybody wanted *(5113580)*
- **The incumbent's 24 sealed trades** — read as a frequency problem for months. Generation four tested that directly and refuted it: the three-to-24 trade count was not the weakness, those trades were simply good ones *(ede2570)*

## 5. What is still open

- **Whether 5m carries edges the 15m book cannot see** — the founding hypothesis of this system, and it has one champion and no second data point

## 6. Rules learned

1. This market has no bell. Any rule that closes, resets or aggregates on a session boundary is importing an assumption from equities.
2. A sealed window can only measure a rule that actually trades in it - check the trade count before reading the return.
3. The incumbent bar for this laboratory is +5.05% sealed 2026 (24 trades, 7.88% drawdown). Every later generation is measured against that number.
