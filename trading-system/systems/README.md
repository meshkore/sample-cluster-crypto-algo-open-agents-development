# The systems, in the order they were built

One folder per hypothesis, numbered by the day it opened. The number never changes and is
never reused: it is how a result is cited in the ledger, in the dashboard and in every
commit message, so renumbering would silently detach eight weeks of records from the work
they describe.

**The next system is 010.**

## The record

Sealed 2026 is the only column that is out-of-sample. Research-era returns contain
selection by construction and are not comparable across systems; they are in each
system's own `docs/RESULTS.md`.

| # | folder | opened → closed | status | market · bar | sealed 2026 | verdict |
|---|---|---|---|---|---|---|
| 001 | `system001_rule_grammar_daily` | 08-06 → 08-12 | frozen | crypto spot · daily | never read | The lineage everything else branches from. Its record is the biases it removed, not a return. |
| 002 | `system002_intraday_momentum_5m` | 08-12 → 08-14 | frozen | 5 USDT majors · 5m | **+5.05%** | 24 trades, every exit the timer. **The bar the whole laboratory then spent a month trying to beat.** |
| 003 | `system003_supervised_ml` | 08-12 | shared library | — | — | Learned rules instead of being told them. Its machinery outlived it and is now `quantlab_ml/`; see the folder's README. |
| 004 | `system004_llm_written_rules` | 08-12 → 08-13 | frozen | 5 USDT majors · 5m | **−5.81%** | A seat with no tools wrote the strategy. The diagnosis it was built on was confirmed; the fix did not pay. |
| 005 | `system005_meta_label_filter` | 08-13 → 08-13 | frozen | 5 USDT majors · 5m | **−1.03%** | First rule here to survive the training era inside the 25% mandate — and it still did not beat +5.05%. |
| 006 | `system006_oracle_net_15m` | 08-18 → open | **CHAMPION** | 14 pooled USDT pairs · 15m | **+25.71%** @ 22.1% DD, 90 trades | A causal TCN trained to imitate a perfect-hindsight oracle. The only system that ever beat the bar. |
| 007 | `system007_capitulation_dip` | 08-28 → open | workshop | per symbol · 15m | **not spent** | A drop-regime dip-buyer meant to cover exactly where 006 loses. Research-era evidence is strong; no sealed reading has been spent. |
| 008 | `system008_residual_momentum_ls` | 09-08 → 09-14 | **closed** | daily cross-section · long/short | **−26.1%** | Eight of eight research years positive, then the ranking inverted in 2026. Closed. |
| 009 | `system009_participant_ledger` | 09-14 → 09-15 | **stopped** | daily · reconstructed participants | 4 readings, none clean | Research-fold IC +0.1412 collapsed to **−0.0553** out of sample. v1 complete, preserved, runnable. |

## Where to look first

- **If you are about to design something new**, read these two before anything else:
  - `system008_residual_momentum_ls/docs/SUMMARY.md` — fifteen refuted ideas, and the rule
    that would have saved the whole build: bootstrap the annual distribution and read
    `P(year >= target)` *before* writing code, not after.
  - `system006_oracle_net_15m/docs/SUMMARY.md` — the champion's record, and more usefully
    the twenty-odd ideas that looked good and were measured and refused. The refusals are
    the expensive part; the code can be re-read, they cannot be re-derived.
- **If you want to know what is actually working**, it is 006 and nothing else. 007 is the
  only other live candidate and has never been read against 2026.
- **If a number confuses you**, every system carries `docs/SUMMARY.md` (six fixed
  headings, the *what hurt* table being the one that matters), `docs/RESULTS.md` and
  `docs/context.json`. The standard is `.meshkore/context/system-documentation-standard.md`
  and `trading-system/tests/test_system_docs.py` enforces it.

## Adding system 010

1. `trading-system/systems/system010_<two_or_three_words>/` — the suffix says what the
   hypothesis *is* (`oracle_net_15m`, `capitulation_dip`), not what generation it is.
2. Register its brain with `@register` from `quantlab_core.brains`. There is no list to
   append to: `available()` finds any package on the path matching `systemNNN_*`, so a
   system that exists cannot be invisible.
3. Import only `quantlab_backtester`, `quantlab_core`, `quantlab_catalog` and
   `quantlab_ml`. Importing another system is a layering violation unless it is a declared
   lineage — see `orchestrator-manager/scripts/check_layering.py`.
4. Write `docs/SUMMARY.md`, `docs/RESULTS.md` and `docs/context.json` from the start. The
   test suite fails without them.
5. The hard rules do not move: long-only, research ends strictly before 2026, 2026 is
   sealed and served only with `--forward`, 30% max drawdown aborts the evaluation, 0.30%
   round-trip cost, and the backtester is never touched in a strategy change.
