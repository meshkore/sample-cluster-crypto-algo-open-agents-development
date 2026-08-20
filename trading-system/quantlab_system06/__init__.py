"""System 06 — the oracle-taught net (15m, BTCUSDT).

A new research line beside `quantlab_trading` and `quantlab_intraday`, depending
on the contract only. See README.md for the hypothesis. The brain registers on
import so a fresh process (`Orchestrator.launch`, the publisher) can find it.
"""

from __future__ import annotations

__all__ = ["Dataset", "OracleNetBrain"]

from .dataset import Dataset
from .strategy import OracleNetBrain  # noqa: F401 -- registers "system06-oracle-net"
