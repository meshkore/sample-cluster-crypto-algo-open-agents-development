"""The intraday system: a second, independent trading system on 15-minute bars.

`quantlab_trading` (System Four -- detector, branches, router, policy) is not
touched by anything in this package and cannot be affected by it. What is
shared is the *contract* and nothing else: `runner.Decision`, the brain
registry, and the money-management dataclass the instrument reads structurally.
Two systems, one instrument, comparable numbers -- the same property
`CONTRACT.md` gives the backtester, applied one level up.

Why a second system at all, in one paragraph: every result this laboratory has
is on daily candles, where a mechanism needs a multi-week move to clear costs,
so in a falling market the honest answer is cash. That is a ceiling, not a bug.
At 15 minutes the same nine years carries 96x the bars and the sealed 2026
window holds ~21,500 bars per asset instead of ~215, which is the difference
between a hypothesis that can be tested this year and one that cannot. The
price of the resolution is that costs stop being noise: 30 bps round trip
against a typical 15m range of 30-60 bps. So the cost hurdle is part of the
entry rule here, not an accounting step applied afterwards.

Importing this package registers its brains, which is the only wiring step:

    import quantlab_intraday                       # noqa: F401
    from quantlab_manager.orchestration import Orchestrator

    lab = Orchestrator(database="research/quantlab.db")
    lab.launch("intraday-reversion", candles=..., parameters={...})

See `README.md` beside this file for the hypothesis, the arithmetic behind
every default, and what would refute it.
"""

from __future__ import annotations

FAMILY = "intraday-reversion"
INTERVAL = "5m"
BARS_PER_DAY = 288

# Registered on import so a fresh process can launch by name. A strategy that
# exists but cannot be found is worse than one that does not exist, because
# nobody knows it is missing -- `quantlab_trading.brains` makes the same
# argument in the same words, and this is the same problem one package over.
from . import momentum, reversion  # noqa: E402,F401

__all__ = ["FAMILY", "INTERVAL", "BARS_PER_DAY", "momentum", "reversion"]
