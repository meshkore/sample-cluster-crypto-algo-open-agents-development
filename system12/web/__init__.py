"""The public pages: build them from the paper book and the docs, serve them locally, publish them to Cloudflare.

python -m system12.web             # build into SITE_DIR
python -m system12.web --deploy    # build and publish
python -m system12.web.serve       # http://localhost:8799
"""

from __future__ import annotations

import numpy as np

from .. import backtest, market, paper, strategy
from ..config import RECORD, ROOT, SITE_DIR
from ..market import Market
from . import pages

FILES = {"/": "index.html", "/architecture": "architecture.html", "/architecture.txt": "architecture.txt"}
HTML, TEXT = "text/html; charset=utf-8", "text/plain; charset=utf-8"


def year_table(m: Market, W: np.ndarray) -> dict[int, tuple[float, float, float]]:
    """The walk-forward record, plus the current year read live from the frozen system."""
    rows = {int(y): (v["ret"], v["dd"]) for y, v in RECORD["years"].items()}
    current = int(m.year4[-1])
    if current not in rows:
        r = backtest.run(m, W, np.flatnonzero(m.year4 == current))
        rows[current] = (r.ret, r.max_dd)
    btc = backtest.btc_yearly(m, rows)
    return {y: (ret, dd, btc.get(y)) for y, (ret, dd) in rows.items()}


def build(m: Market, W: np.ndarray, state: dict) -> dict[str, tuple[str, str]]:
    md = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    site = {
        "/": (HTML, pages.live(state, year_table(m, W))),
        "/architecture": (HTML, pages.architecture(md)),
        "/architecture.txt": (TEXT, md),
    }
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    for path, (_, body) in site.items():
        (SITE_DIR / FILES[path]).write_text(body, encoding="utf-8")
    return site


def build_latest() -> dict[str, tuple[str, str]]:
    """Load the latest market data and build every page."""
    m = market.load()
    W = strategy.target_weights(m)
    return build(m, W, paper.state(m, W))
