# The intraday system — 5-minute bars

A second trading system beside System Four (`quantlab_trading/`), which it does
not touch and cannot affect. One timeframe: **5 minutes**. Five USDT majors.
Everything below is set up so a new hypothesis is one file and one command.

## Ready to run

```bash
pip install -e .

# once: downloads 5m candles and caches the indicator panel for every window
python3 -m quantlab_intraday.prepare

# every iteration after that: 12 training blocks + the sealed 2026 window
python3 -m quantlab_intraday.launch --phase both
python3 -m quantlab_intraday.launch --phase both --set stop_atr=2.5 --set target_atr=1.5
```

`prepare` is idempotent. Candles already on disk are not downloaded again, and a
panel is rebuilt only if the candles it was built from changed — the cache key
is a digest of the OHLCV stream, so a stale panel is discarded rather than
served.

Data lands under `backtester/data/{research,forward}/processed/binance/<SYM>/5m/`,
indicator panels under `backtester/data/indicators/5m/`. All gitignored.

## Adding a hypothesis

Write a brain, register it, launch it by name. Nothing else to wire.

```python
# trading-system/quantlab_intraday/mynewidea.py
from quantlab_trading.brains import register
from quantlab_trading.runner import Decision


@register("intraday-breakout", "buys 5m range expansions, exits on a time stop")
class IntradayBreakout:
    def decide(self, tick) -> Decision: ...
```

```bash
python3 -m quantlab_intraday.launch --brain intraday-breakout --phase both
```

It is then measured by exactly the same harness: same blocks, same costs, same
sealed window, same cost decomposition — which is the only reason two
hypotheses here are comparable at all. Import it from `__init__.py` so a fresh
process can find it.

`reversion.py` is the worked example. Every number in it is a decision and
every decision is in that one file.

## The one number a new idea has to beat

A round trip costs 10 bps commission + 5 bps slippage, each way: **0.30% of
notional**, a project invariant that is never relaxed. So the system-level cost
is:

    toll = round trips × position size × 0.30%

At ~330 round trips per block and ~13% positions that is 12–18% of capital per
block before the strategy has been right about anything. **State what makes your
average trade move more than 0.30% before coding it.** If the answer is "a high
win rate", it is the first hypothesis again — see below.

## What H-INTRA-001 (reversion) measured

Buy a bar closing near its low, well below its 20-bar VWAP; exit on reversion,
an ATR target, an ATR stop or a time stop. **Refuted**, and the way it failed is
the useful part.

- The signal is real: at a one-bar horizon it returns 17× the unconditional
  drift. It is also worth 3–13 bps, against a 30 bps toll.
- 12 blocks 2017–2025 and the sealed window: win rates 51–62%, returns −8% to
  −17%, forward 2026 **−24.18% over 921 trades**. Pre-cost the blocks are a coin
  flip (3 of 7 positive) — the toll is the entire result.
- Not cycle-agnostic, which was the whole premise: net by year is +1.40% (2017),
  −0.28% (2018), +0.93% (2021), −0.57% (2022), −0.08% (2025), and one asset
  (SOL) carries the average.
- Measured at 5m/15m/30m/1h/4h; all negative at their own best horizon. Raising
  resolution multiplies opportunities, not edge per opportunity.

**Instrument note, and it applies to any study written here.** The first scan
reported 5m at +0.193% net with t = 6.7. It was an artifact: sampling every
qualifying bar with a 288-bar forward window counts one day's move up to 288
times, so the error bar divides by a sample size that does not exist. `edge.py`
now also reports the same observations thinned to non-overlapping windows —
5,077 of them, −0.098% at **t\* = −1.4**. Quote `t*`, never `t`.

Where the numbers point next: reversion's upside is capped by construction
(price returns to the anchor and the trade stops), so its mean is bounded near
the toll however good the win rate. Breakout and volatility-expansion rules have
an uncapped right tail, where a 35% win rate can clear a fixed toll that a 60%
win rate cannot.

Full tables: `research/agent_runs/intraday/`.

## What H-INTRA-002 (momentum) measured

**At 06:00 UTC, when the day is already up 1.5%, buy and hold three days.** Five
symbols, non-overlapping windows, net of the 0.30% toll and quoted as excess
over the same-horizon drift: **+0.126%** in 2017-2022 and **+0.543%** in
2023-2025, breakeven 72.7 bps, monotone in the entry threshold in both eras and
positive on all five symbols in both. The dose-response is what makes it a
mechanism rather than a lucky cell.

Six portfolio variants over eight 90-day blocks, same entries throughout:

| | stop | trend filter | mean/block | median | +blocks | worst | maxDD | w/o best |
|---|---|---|---|---|---|---|---|---|
| A | 7% | — | +0.55% | −0.07% | 4/8 | −21.90% | 22.17% | −2.37% |
| B | none | — | +4.24% | +2.03% | 4/8 | −20.10% | 21.66% | −1.79% |
| C | 7% + trail | — | −0.89% | −1.54% | 4/8 | −21.90% | 22.17% | −3.31% |
| D | 7% | 30-day | +2.16% | +5.23% | 5/8 | −11.16% | 18.01% | −0.04% |
| E | 7% | 14-day | +0.59% | +3.41% | 5/8 | −17.11% | 17.71% | −1.22% |
| **F** | **none** | **30-day** | **+2.69%** | **+2.41%** | 4/8 | **−10.04%** | **17.31%** | **+0.25%** |

C < A < B is the finding: on identical entries a trailing stop is worse than a
stop and a stop is worse than none. **Truncating the winner costs money**, which
is what a right-tail mechanism predicts and is now measured three ways. The
30-day trend filter (A → D) buys drawdown rather than return — worst block
−21.9% → −11.2% — and was justified by prior (Moskowitz/Ooi/Pedersen on the
regime dependence of time-series momentum) before it was measured.

`w/o best` is the mean with the single best block deleted. F is the only variant
that survives it, and it is why F was the one published: B's whole mean is one
window (2021 paid +46.45%; without it B averages −1.79%). Eight blocks cannot
statistically separate D, E and F, and the table should not be read as though
they could.

**The published pair, and what it taught.** Sealed 2026: **+5.05%** net, 7.88%
drawdown, 24 trades, in a year the market fell 22.6%. Training, run continuously
from 2018: +168.19% by May 2021 and then **stopped by the 25% drawdown mandate
on 2022-04-08**, having given back a quarter of its peak — it never traded
2022-2025.

No block could have shown that. **Every block restarts at 100,000, so a block
table cannot express a drawdown that accumulates across years**: F's worst
within-block drawdown was 17.31%, comfortably inside the budget, while the same
rule compounded continuously breaches it. Blocks answer whether a mechanism
survives different tape. They say nothing about the path a real account takes
through all of it, and any hypothesis measured here should be run once
continuously before it is believed.

## The code

| module | what it does |
|---|---|
| `prepare.py` | downloads candles and warms every indicator panel. Run once. |
| `launch.py` | runs a brain over the blocks and the sealed window, with the cost decomposition |
| `dataset.py` | 5m bars, the 2026 lock, the block sampler, the indicator cache |
| `survey.py` | many candidate mechanisms in one pass, each judged against the toll. Run this BEFORE writing a brain. |
| `reversion.py` | H-INTRA-001 — buy dislocation, sell the reversion. Refuted; kept as the control. |
| `momentum.py` | H-INTRA-002 — buy strength, trailing stop, **no take profit**, so the winner is never capped |
| `microstructure.py` | what one bar says, and the entry gates including the cost hurdle |
| `context.py` | the vetoes: volatility crash filter, optional trend and hour gates |
| `moneymanagement.py` | intraday defaults for the lab's `MoneyManagement`, ATR-scaled sizing |
| `edge.py` | signal study: does it predict anything, before any portfolio |
| `resolution.py` | the same rule at other intervals, if that question ever returns |

Two things that are not obvious and cost something to learn:

- **The time stop is counted in bars, by the brain.**
  `MoneyManagement.maximum_holding_days` counts days and cannot express four
  hours. The field stays `None` so no stored policy changes meaning.
- **The panel cache holds ONE window per symbol, not one per run.**
  `IndicatorStore.path_for` keys on symbol, spec and timeframe — never on the
  candles — so every window writes `indicators-<spec>.csv.gz` to the same path
  and the last one wins. Twelve blocks therefore leave one block cached, and
  `prepare` warms a cache that the next window immediately overwrites. Nothing
  is ever mis-served (the digest is checked inside the file and a mismatch
  recomputes), but the cache is close to useless across windows and a full
  eight-year panel costs ~430 MB and several minutes per symbol. The fix
  belongs here rather than in the frozen instrument: a store root per window.
- **`risk_per_trade` is 0.0015, not the daily system's 0.01.** Sizing divides
  the risk budget by the stop distance, ~0.6% here against ~5% daily. Carried
  across unchanged, every position clamps to the 30% cap and the ATR scaling
  never operates. A test asserts a tight stop takes a larger position than a
  wide one; that test found it.

## Putting a result on the monitor

`launch.py` measures; it cannot record or publish, because `trading-system/` may
not import the lab. The bridge lives on the manager's side of that wall:

```bash
GENOME="--set entry_rule=itsm --set itsm_hour=6 --set itsm_threshold=0.015 ..."
python3 orchestrator-manager/scripts/publish_intraday.py --phase training $GENOME
python3 orchestrator-manager/scripts/publish_intraday.py --phase forward  $GENOME
```

Both halves take the **same** `--set` flags; the script sets `trade_from` and
nothing else differs, which is what makes them two halves of one hypothesis
rather than two unrelated runs (`pair_key` hashes the genome with `trade_from`
removed). The training half is one continuous run from 2018-01-01 to the lock —
the house convention every loop run follows — not the eight blocks, because a
card carries one figure per era. Read
`.meshkore/docs/architecture/monitor-frontend.md` before changing any of this.

## Launching through the laboratory

`intraday-reversion` is in `brains.available()` as soon as `quantlab_intraday`
is imported, so `Orchestrator.launch(...)` works with `candles=` from
`IntradayDataset.candles_payload`. Two integration steps are deliberately left
to their owners: `brains._register_builtins` does not import this package (one
line, in a file System Four owns), and the autonomous research loop selects
scope through `FAMILY_DATA_OVERRIDES` in the frozen backtester, which this
system does not need because it supplies its tape inline.
