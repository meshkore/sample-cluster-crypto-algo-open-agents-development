# Rocket — a validator for the winning model (opened 2026-10-15)

**What.** An endless search for an outside check that DENIES some of the champion's entries and
so raises its share of winning trades. The champion (System 10 release 34, the paper book's model)
is taken exactly as it is — same signals, same book — and only its entries are filtered.

**The one rule.** Rocket never touches what runs. It reads System 10's code and frozen signal cache
and writes only inside this folder. No System 10 job, ledger, release or switch reads anything here.
A Rocket result reaches the main line only through the operator.

**How a test works** (`rocket.py`, docstring has the detail)
- idea = a feature + a rule: veto above/below a threshold, veto categories, a learned validator
  (gradient-boosted trees), or an OR of 2–3 ideas;
- nested: for each test year N in 2022–2025 the rule is chosen on the champion's own trades of
  2020..N−1 only, then year N is booked again without the denied entries;
- verdict vs the champion without a validator: `win` (better in ≥ 3 of 4 years at bootstrap
  p ≥ 0.90, law up, DD not up, ≥ 50 trades every year), `promising` (better in ≥ 3 of 4 years, law
  up, ≥ 50 trades), `neutral`, `hurts`, `silent` (the rule never fired);
- **placebo**: every 10th test re-runs an earlier idea on its feature shifted 6–18 months in time.
  The placebo win rate is the chance rate. With thousands of tests, some ideas WILL look good by
  luck; only families that beat the placebo are evidence;
- two coin lists: `today` (System 10's 14) and `pit` (each year's point-in-time top 14, built once
  into `cache/`). The 2024 failures live on `pit`. 2026 is never read.

**The cocktail** (`IDEAS.md`): every MA 2–300 on 1h/4h/1d for the coin, BTC and "share of the
market below its MA"; RSI 2–300; MACD grids; MA crosses; 13 more indicators × 28 periods × 3
timeframes × 7 sources; macro (VIX, Nasdaq, dollar, oil, 10-year, curve); funding; fear & greed;
open interest; stablecoins; ETF flows; the 44 engine columns; breadth; calendar; coin identity; the
model's own forecast; learned validators; pairs and triples of the best; random ideas forever.

**Files.** `ledger.jsonl` every test · `REPORT.md` auto summary every 30 min · `JOURNAL.md` what I
learn, by hand · `rocket.log` the live run · `cache/` (gitignored) the point-in-time signals.

**Running.** Windows task `rocket-watchdog` every 15 min runs `watchdog.ps1`: relaunches
`rocket.py run --hours 24` if it is not alive, and builds the point-in-time cache once. Brake: create
`STOP` in this folder. Low priority, CPU, waits whenever free RAM < 3 GB so System 10 always wins.
