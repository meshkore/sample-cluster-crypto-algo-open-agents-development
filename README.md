# System 12

A BTC trend-regime strategy on Binance USD-M perpetuals: long BTC+ETH while the BTC trend is up, a half-size short
when it turns down, sized to a volatility target. It runs as a $50,000 paper book and places no real orders.

- **Live page:** https://quantlab-public-mirror.rjj.workers.dev
- **Architecture brief:** https://quantlab-architecture.rjj.workers.dev/architecture (source: `docs/ARCHITECTURE.md`)

| walk-forward | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| System 12 | +148% | -13% | +48% | +25% | +9% |
| BTC | +60% | -64% | +156% | +121% | -6% |

Each year was traded with rules chosen on earlier years only. `docs/RESULTS.md` holds the record and the log.

## Layout

```
system12/
  config.py      paths, costs, the frozen selection
  data.py        Binance candles and funding, cached outside the repository
  market.py      aligned BTC/ETH panels (4h and daily) and the impact model
  strategy.py    regime signals -> 20 frozen members -> overlays -> target weights
  backtest.py    execution and cost model, equity over any window, yearly statistics
  paper.py       the live paper book and its audit trail
  web/           the public pages: build, local server, Cloudflare publish
  selection.json the frozen members, overlay parameters and paper start
  record.json    the walk-forward record shown on the pages
docs/            ARCHITECTURE.md (public brief), RESULTS.md (record and log of actions)
tests/           offline tests on a synthetic market
scripts/         run_paper.ps1, the 4-hourly job
```

## Run

```
pip install -e ".[dev]"
python -m system12.backtest            # yearly table of the frozen system
python -m system12.paper               # update the paper book
python -m system12.web                 # build the pages; --deploy also publishes them
python -m system12.web.serve           # http://localhost:8799
python -m pytest
```

Data, paper state and the built pages are written to `../meshkore-crypto-data/`, or to `SYSTEM12_DATA` if set.
Publishing reads Cloudflare credentials from `~/.cf_deploy_env`, which never enters the repository.

## Scope

Research software. It simulates trading on public market data; it holds no exchange keys and cannot place orders.
Nothing here is investment advice. MIT licence.
