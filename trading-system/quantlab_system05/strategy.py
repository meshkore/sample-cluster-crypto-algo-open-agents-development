"""Generation 5: the champion's rule, with a second opinion on every entry.

**The hypothesis, in one sentence.** The incumbent's entry rule has forward edge
but no discretion -- it takes every 1.5% morning move it sees -- and a model that
predicts which of those resolve upward can decline the rest, raising the return
and LOWERING the bill at the same time.

That last clause is why this shape and not another. Everything tried in this
laboratory so far traded MORE: generation 4 went from the incumbent's 24 trades
to 65, paid 4.9% of capital in toll, and its gross was -0.87%. At a 30 bps round
trip an extra trade is a certain cost against an uncertain gain, so a filter is
the only change that improves both sides of the ledger. This is Lopez de Prado's
meta-labelling (AFML ch. 3): the primary model picks the side, the secondary picks
the size, and here the only sizes are one and zero.

**The primary is the champion itself, by composition rather than by copy.** This
brain instantiates `intraday-momentum` with the incumbent's exact genome and
vetoes entries. It does not reimplement the trigger, the exits, the sizing, the
de-leverage ramp or the mandate -- so "generation 5 minus the filter" is not
merely similar to the champion, it IS the champion, and the run measures one
variable. A copy would have drifted the first time either file was touched.

**Where the verdicts come from, and why not from a model in here.** The 46
features are built by `quantlab_ml.dataset` from every symbol on a shared clock;
a brain recomputing them tick by tick would be a second implementation of that
arithmetic, and the day the two drift the model is fed garbage while every metric
still reads normally. So `quantlab_ml.meta` precomputes a verdict per candidate
bar and this reads the table. Research-era verdicts come from the purged
walk-forward -- a fold model that never saw the bar it is judging -- and only the
sealed rows are scored by the model fitted on all of history before the lock.

**A missing verdict is a refusal.** Bars before the first walk-forward test block
have no honest verdict available, and the tempting default is to let those trade
unfiltered so the training half keeps its history. That would report the
champion's own results for the years the filter was silent and the filter's for
the rest, which is a card describing no strategy at all.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Imported for its side effect: the primary registers itself on import, and
# `build("intraday-momentum", ...)` below cannot find it otherwise. A brain that
# is only reachable when some other module happened to be imported first is the
# failure this laboratory has already had once, reported as "no brain named ...".
import quantlab_intraday.momentum  # noqa: F401
from quantlab_trading.brains import build, register
from quantlab_trading.policy import policy_keys
from quantlab_trading.runner import Decision

# The incumbent's genome, verbatim from the run that holds the record
# (`intraday-itsm-30d-2026`, +5.05% over the sealed window). Written down here
# because generation 5's claim is "the champion plus a filter", and that claim is
# only meaningful if the champion half is not a near-miss.
CHAMPION: dict[str, Any] = {
    "entry_rule": "itsm",
    "itsm_hour": 6,
    "itsm_threshold": 0.015,
    "trend_filter": "none",
    "trend_ma_days": 30,
    "maximum_holding_bars": 864,
    "maximum_positions": 3,
    "stop_atr": 60,
    "trail_atr": 0,
    "exit_end_of_day": False,
    "minimum_daily_turnover": 10_000_000.0,
    "volatility_quantile": 1.0,
    "volatility_window_days": 5,
    "volatility_minimum_days": 2,
}

DEFAULTS: dict[str, Any] = {
    # The table of verdicts, written by `python3 -m quantlab_ml.meta`.
    "verdict_table": "",
    # How much expected net return a candidate must clear. The round trip is
    # already subtracted inside the expectation, so 0.0 means "expected to cover
    # its own costs" rather than "expected to make money before them".
    "verdict_margin": 0.0,
    # Refuse when the table has nothing to say. Configurable so the effect of the
    # filter on the covered era can be measured separately, never for a published
    # run -- see the module docstring.
    "allow_unjudged": False,
}


def _moment(value: Any) -> datetime | None:
    """A tick timestamp as a datetime. It arrives as an ISO STRING."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def load_verdicts(path: str) -> dict[tuple[str, str], float]:
    """The table, keyed by symbol and ISO timestamp.

    Keys are the timestamp's ISO form as the table wrote it, which is what
    `str(numpy.datetime)` and `datetime.isoformat()` agree on for these bars. A
    key that does not match reads as an absent verdict and therefore as a
    refusal, so a format disagreement shows up as a run that never trades rather
    than as one that trades unfiltered -- the loud failure of the two.
    """
    if not path:
        return {}
    payload = json.loads(Path(path).read_text())
    return {
        (str(row["symbol"]), str(row["timestamp"])): float(row["value"])
        for row in payload.get("table", [])
    }


@register(
    "meta-labelled-itsm",
    "the champion's 06:00 momentum entry, filtered by a walk-forward model's "
    "expected net return on that exact bar",
)
class MetaLabelledITSM:
    """The champion, wrapped. Every member of the contract delegates or vetoes."""

    def __init__(self, **params: Any) -> None:
        mine = {key: params.pop(key) for key in list(DEFAULTS) if key in params}
        self.params = {key: mine.get(key, default) for key, default in DEFAULTS.items()}

        # The primary. Anything the caller passes that the momentum brain knows
        # wins over the recorded genome -- `trade_from`, the cost model and
        # `bars_per_day` are set by the harness on every run and must not be
        # frozen here -- but the entry rule and the exits come from CHAMPION
        # unless deliberately overridden.
        genome = dict(CHAMPION)
        genome.update(params)
        self.primary = build("intraday-momentum", **genome)
        self.policy = self.primary.policy

        self.verdicts = load_verdicts(str(self.params["verdict_table"]))
        self.margin = float(self.params["verdict_margin"])
        self.allow_unjudged = bool(self.params["allow_unjudged"])
        self.vetoed = 0
        self.unjudged = 0
        self.approved = 0

    # -- the contract --------------------------------------------------------- #

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = self.primary.decide(tick)
        if decision.stop or not decision.orders:
            return decision

        moment = _moment(tick.get("timestamp"))
        stamp = str(moment) if moment is not None else ""
        kept: list[dict[str, Any]] = []
        refused: list[str] = []
        for order in decision.orders:
            # SELLs are never touched. The filter is a second opinion on getting
            # IN; vetoing an exit would leave a position the primary believes it
            # has closed, with its stop and its timer already forgotten.
            if str(order.get("side", "")).upper() != "BUY":
                kept.append(order)
                continue
            symbol = str(order.get("symbol", ""))
            value = self.verdicts.get((symbol, stamp))
            if value is None:
                self.unjudged += 1
                if self.allow_unjudged:
                    kept.append(order)
                else:
                    refused.append(f"{symbol} unjudged")
                continue
            if value > self.margin:
                self.approved += 1
                order["rationale"] = (
                    f"{order.get('rationale', '')} | filter E[net] "
                    f"{value:+.4%} > {self.margin:+.4%}"
                ).strip(" |")
                kept.append(order)
            else:
                self.vetoed += 1
                refused.append(f"{symbol} E[net] {value:+.4%}")

        # The primary's `pending` book self-heals: it drops any symbol that did
        # not become a position on the next tick, so a vetoed entry leaves no
        # state behind and does not block the slot.
        decision.orders = kept
        if refused:
            note = f"filter refused {', '.join(refused)}"
            decision.note = f"{decision.note} | {note}" if decision.note else note
        return decision

    def parameters(self) -> dict[str, Any]:
        # The primary's genome plus this brain's own knobs, so `pair_key` sees
        # every parameter that shaped the run. The table PATH is deliberately
        # included: two runs filtered by different tables are not two halves of
        # one hypothesis.
        out = dict(self.primary.parameters())
        out.update(
            {
                key: value
                for key, value in self.params.items()
                if isinstance(value, (int, float, str, bool, type(None)))
            }
        )
        return out

    def diagnostics(self) -> dict[str, Any]:
        out = dict(self.primary.diagnostics())
        out.update(
            {
                "filter_approved": self.approved,
                "filter_vetoed": self.vetoed,
                "filter_unjudged": self.unjudged,
                "filter_margin": self.margin,
                "verdicts_loaded": len(self.verdicts),
            }
        )
        return out


def known_parameters() -> set[str]:
    """Every key this brain accepts, for a caller that wants to check first."""
    from quantlab_intraday.momentum import DEFAULTS as PRIMARY

    return set(DEFAULTS) | set(PRIMARY) | set(policy_keys())
