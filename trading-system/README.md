# The trading system

`CONTRACT.md` at the repository root splits the laboratory into an instrument that decides
nothing and a trading system that decides everything. This folder is that second half.

```
quantlab_core/        the shared runtime: the tick contract (runner), the brain
                      registry (brains), money management (policy) and the per-bar
                      liquidity gate (universe). Decides nothing about direction.
quantlab_catalog/     the shared data catalogue. One import for candles, universe,
                      funding, Fear & Greed, on-chain and reference markets.
quantlab_ml/          the shared learning library: feature table, triple-barrier
                      labels, purged splits, meta-labelling.
systems/              one folder per hypothesis, numbered by the day it opened.
                      ---> systems/README.md is the index. Read it first.
tests/                the whole folder's tests.
backtester/data/      the data ROOT for the whole laboratory. Gitignored and
                      re-downloadable; nothing else on this machine holds candles.
```

**The index of systems, what each one measured and which one is the champion, is
[`systems/README.md`](systems/README.md).** It is the file to open before anything else in
this folder.

## What the three shared packages are for, and what they are not

A shared package is shared because several systems need the *same arithmetic* — not
because the code happened to be written once. The distinction matters: if two systems
compute 46 features by two implementations, the drift between them is invisible and every
metric on the page still reads normally.

So `quantlab_core`, `quantlab_catalog` and `quantlab_ml` may be imported by any system and
import no system themselves. That is enforced, not requested:

```
systemNNN_*  ──▶  quantlab_core / quantlab_catalog / quantlab_ml  ──▶  quantlab_backtester
```

`orchestrator-manager/scripts/check_layering.py` fails the build rather than trusting this
paragraph. The one exception is **lineage** — system 005 is system 002's entries filtered
by a second model, so it may import 002 and nothing else. Every such edge is listed with
its reason in that script.

## Where a contribution lands

- A new hypothesis → a new folder under `systems/`. See `systems/README.md` for the five
  steps and the hard rules that do not move.
- A better feature, label or split that **every** system should get → `quantlab_ml/`.
- A data series nobody has → `quantlab_catalog/`, with a fetcher that is a deliberate act
  and never runs inside a backtest.
- Sizing, stops or the drawdown mandate → `quantlab_core/policy.py`. Changing it changes
  every system's recorded result, so it is the one file to touch last and argue about most.

## Running it

```bash
pip install -e ".[ml]"                                    # once

python -m pytest trading-system/tests -q
python orchestrator-manager/scripts/check_layering.py
python -m quantlab_catalog.inventory                      # what data exists, and what does not
```

Paths no longer depend on the working directory: `quantlab_catalog.paths.DATA_ROOT` is
absolute and every default resolves through it. A script run from the wrong folder used to
load an empty universe, fall back silently to BTCUSDT, and produce results roughly 24x too
weak.
