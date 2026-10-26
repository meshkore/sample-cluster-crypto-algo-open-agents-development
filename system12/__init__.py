"""System 12: a BTC regime book on Binance USD-M perpetuals (paper trading).

data      Binance candles and funding, cached outside the repository
market    aligned BTC/ETH panels (4h and daily)
strategy  regime signals -> frozen members -> overlays -> target weights
backtest  costs, funding and impact; equity over any window; yearly statistics
paper     the live paper book and its audit trail
web       the public pages: build, serve locally, publish
"""

__version__ = "12.6.0"
