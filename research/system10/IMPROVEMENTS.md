# System 10 — open ideas for the main line

Not yet tried. Closed ideas live in README.md's decision log. Keep each line short; when an
idea is tested, move its one-line result to the decision log and delete it here.

| # | idea | why |
|---|---|---|
| 1 | Wider universe for the search (32 coins, `universe_wide.json`) | more opportunities per day; needs RAM per worker |
| 2 | Correlation limit: at most N positions in coins moving together | 5 slots in one BTC move is one bet |
| 3 | Equity-curve filter: halve stakes while the account is below its 30-day average | cheaper than a drawdown brake that only bites late |
| 4 | Winner map: trade only conditions holding 80% of winning trades (within the 70% availability rule) | the veto (loser map) hurt; the positive side is untested |
| 5 | Taker-buy share from Binance klines as a feature | free, already on disk |
| 6 | Funding rates / open interest | crowding signal; needs history to 2019 |
| 7 | Paper book: swappable release (steppable book) | today a new release cannot replace the pinned one without rewriting the book |
| 8 | Paper book: cache the fitted models between cycles | cycle 7–10 min; most of it is refitting |
