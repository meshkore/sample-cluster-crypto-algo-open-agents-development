"""Resolving a system's bar source by NAME, at run time.

`train` and `meta` are command-line entry points: they need somewhere to get
candles from, and until now they imported `system002_intraday_momentum_5m`
directly at the top of the file. That made the shared learning library depend on
one particular hypothesis -- so a change inside system 002 could alter what
every other system trained on, and `check_layering.py` was right to refuse it.

The dependency is not real, though. It is a DEFAULT: the trainer does not care
whose bars these are, only that the object answers `research()`, `combined()`
and carries a `lock`. So the system is an argument now, resolved by name when
the command runs, and nothing is imported until someone asks for it:

    python -m quantlab_ml.meta --system system006_oracle_net_15m

which is also the first time that command has been possible.
"""

from __future__ import annotations

import importlib
from typing import Any

DEFAULT_SYSTEM = "system002_intraday_momentum_5m"


class BarSource:
    """What a system must expose under `<system>.dataset` to be trainable."""

    def __init__(self, module: Any):
        self.module = module

    @property
    def symbols(self) -> list[str]:
        return list(getattr(self.module, "DEFAULT_SYMBOLS"))

    @property
    def lock(self) -> Any:
        return getattr(self.module, "LOCK")

    def open(self, data_root, symbols, interval: str):
        """Build the system's dataset object over its own candles."""
        for name in ("IntradayDataset", "Dataset"):
            factory = getattr(self.module, name, None)
            if factory is not None:
                return factory(data_root, self.lock, symbols, interval=interval)
        raise AttributeError(
            f"{self.module.__name__} exposes no IntradayDataset or Dataset; "
            "a trainable system must offer one of them"
        )


def bar_source(system: str = DEFAULT_SYSTEM) -> BarSource:
    try:
        module = importlib.import_module(f"{system}.dataset")
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"no dataset for system {system!r}: {exc}. Expected an importable "
            f"module `{system}.dataset` on the path."
        ) from exc
    return BarSource(module)
