"""Where the live layer keeps its things, and how it finds a key without leaking one.

Two rules encoded here rather than remembered:

* **Credentials never enter the repository.** They are read from `~/.quantlab_live_env`,
  a file outside every git tree on this machine, in the same shape as the Cloudflare
  deploy env that has kept that promise since August. `credentials()` returns them;
  nothing else in this package may touch the file, and no code path prints a value.
* **The live layer writes only under `live-trading/state/`.** Not into `research/`, not
  into the catalogue, not into any dataset the lab reads. A running trader must not be
  able to change a single number an experiment would measure.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIVE_ROOT = REPO / "live-trading"
ENGINES = LIVE_ROOT / "engines"
CURRENT_ENGINE = ENGINES / "current.json"
STATE_DIR = LIVE_ROOT / "state"
BOOK_PATH = STATE_DIR / "book.json"
LEDGER_PATH = STATE_DIR / "orders.jsonl"
STATE_PATH = STATE_DIR / "live_state.json"
LOG_PATH = STATE_DIR / "trader.log"

# The candles this system trades on, and the history it needs in front of them. The
# slow-trend channel alone looks back `trend_span` = 5,760 bars (sixty days); the Hurst
# and fear-greed channels look back 2,880. WARMUP_BARS is the deepest of those plus the
# net's own 96-bar window, rounded up - short a single bar and the first live decision
# would be made on a channel that is still filling.
INTERVAL = "15m"
BAR_SECONDS = 15 * 60
WARMUP_BARS = 7_000

# The forward window closes and live trading opens at the moment the operator named:
# 2026-09-17, 11:00 Europe/Madrid, which is 09:00 UTC. Before this instant the system is
# still being measured on sealed 2026 data; after it, it is trading.
CUTOVER = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)

# The mandate the whole laboratory has always measured: one account, $100,000, long only.
INITIAL_CAPITAL = 100_000.0

ENV_FILE = Path(os.environ.get("QUANTLAB_LIVE_ENV", str(Path.home() / ".quantlab_live_env")))


def credentials() -> dict[str, str]:
    """Venue keys, read from OUTSIDE the repository. Empty when the file is absent.

    Callers get a dict and must never log it. The paper broker needs nothing from here;
    only a venue broker does, and that one cannot start on an empty dict.
    """
    out: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def has_venue_keys(venue: str) -> bool:
    """Whether keys for a venue exist, WITHOUT revealing anything about them."""
    creds = credentials()
    prefix = venue.upper()
    return bool(creds.get(f"{prefix}_API_KEY") and creds.get(f"{prefix}_API_SECRET"))


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def universe() -> list[str]:
    """The traded symbols, from the system's own universe table - never a second list."""
    from system006_oracle_net_15m import universe as u  # noqa: PLC0415

    symbols = u.load()
    if not isinstance(symbols, list) or len(symbols) < 5:
        raise RuntimeError(f"degenerate universe: {symbols!r}")
    return symbols
