# The original rule grammar

*Status: **frozen** · opened 2026-08-06, closed 2026-08-12.*

> Written from this system's own measured record — its README tables, the task
> records under `.meshkore/modules/`, and its commit bodies. Every figure below
> carries the source that holds it, so a reader who distrusts a number can check
> the same place I did.

## 1. Hypothesis

Trading rules can be bred as a grammar over indicators, and a search over that grammar finds combinations a person would not write by hand.

## 2. What it is

Rule grammar plus a regime router (codex_regime_system). The lineage the later generations branch from.

**Data consumed:**

- daily and 15m candles across every listed asset of the era, not a survivor set

## 3. What helped

- **Defining the market as every listed asset of the time** — removed the survivorship bias that six hand-picked survivors had been quietly supplying *(cd3df05)*
- **Three levels of trend plus a global one that does not churn** — a trend read that changes when the trend changes rather than when the noise does *(01c3907)*
- **Seeding the search from what the bounce ladder actually measured** — the search starts from a measured shape instead of a random point in the grammar *(4f7bcef)*

## 4. What hurt

*This section matters more than the one above: it is the part that cannot be
reconstructed from the code.*

- **Sizing by name rather than by volatility** — the book bought a 15%-a-day asset the same size as a 5%-a-day one, so the portfolio's risk was set by whichever names happened to be in it *(b7553df)*
- **A bear label that selected recoveries, not falls** — every conclusion drawn about bear behaviour before it was fixed described the wrong bars *(2f76d6a)*
- **A loop that could not start, with no test able to see why** — the failure was invisible to the suite, which is the class of bug this laboratory has since spent the most time on *(74b8246)*

## 5. What is still open

- **Whether a bred rule grammar beats a trained model** — the lineage moved to learned models at generation 06 without ever settling this directly

## 6. Rules learned

1. The universe is every asset LISTED AT THE TIME, never the ones that survived to today. Survivorship is the easiest large error to make here and the hardest to see afterwards.
2. Size by volatility, not by name. Equal notional across unequal assets is a risk decision disguised as a neutral one.
3. A label is a measurement. Check what the bear label SELECTED before trusting anything conditioned on it.
