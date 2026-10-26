"""Paths, market constants and the frozen selection, in one place."""

from __future__ import annotations

import json
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent

# Everything the system writes lives outside the repository.
DATA_ROOT = Path(os.environ.get("SYSTEM12_DATA", ROOT.parent / "meshkore-crypto-data"))
CANDLES_DIR = DATA_ROOT / "system12"
PAPER_DIR = DATA_ROOT / "paper"
SITE_DIR = DATA_ROOT / "site"

COINS = ("BTC", "ETH")
FIRST_YEAR = 2018  # first year on the grids; signals warm up from here
BAR_NS = {"4h": 4 * 3600 * 10**9, "1d": 24 * 3600 * 10**9}
BARS_PER_DAY = 6

HALF_COST = 0.0010  # per side on USD-M perpetuals
IMPACT_BOOK_USD = 100_000.0  # square-root impact is priced for a book of this size

SELECTION = json.loads((PACKAGE / "selection.json").read_text(encoding="utf-8"))
RECORD = json.loads((PACKAGE / "record.json").read_text(encoding="utf-8"))
