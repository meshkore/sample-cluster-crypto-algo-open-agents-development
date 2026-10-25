# System 12: a BTC regime book

System 12 follows the BTC trend: long BTC+ETH in bull phases, a half-size short in bear phases, on Binance USD-M
perpetuals. It paper-trades $50,000 and places no real orders.

- **Live page:** https://quantlab-public-mirror.rjj.workers.dev
- **Architecture:** https://quantlab-public-mirror.rjj.workers.dev/architecture, or `docs/ARCHITECTURE.md`

| walk-forward | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| System 12 | +148% | -13% | +48% | +25% | +9% |
| BTC | +60% | -64% | +156% | +121% | -6% |

## Layout

| path | what |
|---|---|
| `system12/strategy.py` | the rules: 20 frozen regime configurations plus two overlays, costs and funding |
| `system12/selection.json` | the frozen selection (members, overlay parameters, paper start) |
| `system12/data.py` | Binance candles and funding, cached outside the repo |
| `system12/paper.py` | the paper book |
| `system12/publish.py` | the live page and the architecture page (local build, Cloudflare deploy) |
| `docs/` | `ARCHITECTURE.md` (public) and `RESULTS.md` (record and log of actions) |
| `tests/` | `python -m pytest tests` |
| `scripts/run_paper.ps1` | the 4-hourly job: paper book, then the page |

## Run

```
pip install numpy pandas pytest
python -m system12.paper              # recompute the paper book
python -m system12.publish            # build the pages into ../meshkore-crypto-data/site
python -m system12.publish --deploy   # and publish them (needs ~/.cf_deploy_env)
```

Data, paper state and the built site are kept outside the repository: `../meshkore-crypto-data/`, or set
`QUANTLAB_DATA`. Earlier systems (01-11), the research behind System 12, models and backtests are archived in
`../meshkore-crypto-archive/`, and the git history before 2026-10-25 still holds them.

MIT licence. Research software, not investment advice.
