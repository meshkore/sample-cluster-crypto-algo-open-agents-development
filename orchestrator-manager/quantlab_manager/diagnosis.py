"""Where did the money go? The stage that decides what the next iteration does.

A loop that reads only the headline number can do one thing: try again. "It lost
6.78%" is not a finding, it is a prompt to guess. "The bear branch took 51 of the
64 trades and lost 9.1% of equity while the bull branch made 2.3% on 13" names
the module to work on, and that is the difference between a research loop and a
random walk with a database.

Everything here is arithmetic on a run the backtester already recorded. It forms
no opinion the ledger cannot check and it reads no window the run did not cover.

The entry reason carries the attribution. `FourModuleBrain` stamps every buy as
`<REGIME>_<RULE>` -- `BEAR_PARTICIPATION`, `BULL_TREND` -- so the module that
opened a position is recoverable from the order book without the brain having to
keep a parallel record that could disagree with it.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

# The four pieces, in the order a report should read them.
MODULES = ("BULL", "SIDEWAYS", "BEAR", "DETECTOR")


def _module_of(reason: str) -> str:
    """Which piece opened this position.

    Exits carry their own vocabulary (`TAKE_PROFIT`, `REGIME_HANDOVER`), so only
    entry reasons are asked this question.
    """
    head = (reason or "").split("_")[0].upper()
    return head if head in ("BULL", "SIDEWAYS", "BEAR") else "UNATTRIBUTED"


def attribute(orders: list[dict], trades: list[dict], initial: float) -> dict[str, Any]:
    """Split a run's realised P&L by the module that opened each trade.

    Trades are paired by the store and carry an exit reason but not an entry
    one, so the entry is recovered from the BUY that opened the position:
    same symbol, same timestamp. Matching on both rather than on symbol alone
    matters once a symbol has been traded more than once in a run, which is the
    normal case.
    """
    entry_reason: dict[tuple[str, str], str] = {}
    for order in orders:
        if str(order.get("side", "")).upper() == "BUY":
            entry_reason[(order["symbol"], str(order["timestamp"]))] = order.get(
                "reason", ""
            )

    by_module: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"trades": 0, "wins": 0, "pnl": 0.0, "worst": 0.0, "best": 0.0}
    )
    by_exit: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"trades": 0, "wins": 0, "pnl": 0.0}
    )

    for trade in trades:
        reason = entry_reason.get((trade["symbol"], str(trade["entry_time"])), "")
        bucket = by_module[_module_of(reason)]
        pnl = float(trade.get("pnl") or 0.0)
        bucket["trades"] += 1
        bucket["pnl"] += pnl
        bucket["wins"] += 1 if pnl > 0 else 0
        bucket["worst"] = min(bucket["worst"], float(trade.get("pnl_pct") or 0.0))
        bucket["best"] = max(bucket["best"], float(trade.get("pnl_pct") or 0.0))

        exit_bucket = by_exit[str(trade.get("exit_reason") or "UNKNOWN")]
        exit_bucket["trades"] += 1
        exit_bucket["pnl"] += pnl
        exit_bucket["wins"] += 1 if pnl > 0 else 0

    for bucket in by_module.values():
        bucket["win_rate"] = (
            bucket["wins"] / bucket["trades"] if bucket["trades"] else 0.0
        )
        # As a share of the deposit, so two modules in the same run are
        # comparable and a module's contribution reads in the same units as the
        # run's headline return.
        bucket["contribution"] = bucket["pnl"] / initial if initial else 0.0
    for bucket in by_exit.values():
        bucket["win_rate"] = (
            bucket["wins"] / bucket["trades"] if bucket["trades"] else 0.0
        )
        bucket["contribution"] = bucket["pnl"] / initial if initial else 0.0

    return {"by_module": dict(by_module), "by_exit": dict(by_exit)}


def diagnose(store: Any, backtest_id: str) -> dict[str, Any]:
    """Read a recorded run and say what is wrong with it, and which piece owns it.

    The verdict is deliberately mechanical. A loop that asked a language model
    "what went wrong" before looking would get a fluent answer built on nothing;
    this hands the model the arithmetic and lets it argue about the arithmetic.
    """
    run = store.run(backtest_id)
    if run is None:
        raise KeyError(f"no recorded backtest {backtest_id}")
    orders = store.orders(backtest_id, limit=100_000)
    trades = store.trades(backtest_id, limit=100_000)
    initial = float(run.get("initial_capital") or 0.0) or 1.0

    split = attribute(orders, trades, initial)
    modules = split["by_module"]

    active = {k: v for k, v in modules.items() if v["trades"] > 0}
    worst_module = min(active, key=lambda k: active[k]["contribution"], default=None)
    best_module = max(active, key=lambda k: active[k]["contribution"], default=None)

    findings: list[str] = []
    target = "BEAR"
    if not trades:
        # The most informative case and the easiest to misread. A run with no
        # trades has not failed to find a signal -- something refused to let it
        # trade at all, and which gate that was is the finding.
        findings.append(
            "no trades at all: the run was gated, not outvoted. The gate that "
            "refused is the thing to change, not the entry rule behind it."
        )
        target = "DETECTOR"
    else:
        for name, bucket in sorted(modules.items()):
            findings.append(
                f"{name}: {bucket['trades']} trades, {bucket['win_rate']:.0%} won, "
                f"{bucket['contribution']:+.2%} of deposit"
            )
        if worst_module and modules[worst_module]["contribution"] < 0:
            target = worst_module
            findings.append(
                f"{worst_module} is the losing module and is where the next "
                f"iteration should work."
            )
        elif best_module:
            target = best_module
            findings.append(
                "no module lost money; the next iteration should push the "
                f"strongest one ({best_module}) rather than repair anything."
            )

    losing_exits = sorted(
        (
            (name, bucket)
            for name, bucket in split["by_exit"].items()
            if bucket["contribution"] < 0
        ),
        key=lambda item: item[1]["contribution"],
    )
    for name, bucket in losing_exits[:2]:
        findings.append(
            f"exit {name}: {bucket['trades']} trades, {bucket['contribution']:+.2%}"
        )

    return {
        "backtest_id": backtest_id,
        "label": run.get("label"),
        "window": [run.get("window_start"), run.get("window_end")],
        "return_pct": run.get("return_pct"),
        "max_drawdown": run.get("max_drawdown"),
        "trades": run.get("trades"),
        "by_module": modules,
        "by_exit": split["by_exit"],
        "worst_module": worst_module,
        "best_module": best_module,
        "target_module": target,
        "findings": findings,
    }


def summarise(report: dict[str, Any]) -> str:
    """The diagnosis as prose, for the Wall and for a model's briefing."""
    lines = [
        f"{report['label']} ({report['backtest_id']}) "
        f"{report['window'][0]} -> {report['window'][1]}",
        f"return {(report['return_pct'] or 0):+.2%} · "
        f"drawdown {(report['max_drawdown'] or 0):.2%} · "
        f"{report['trades'] or 0} trades",
        "",
    ]
    lines += [f"- {finding}" for finding in report["findings"]]
    lines += ["", f"Next iteration targets: {report['target_module']}"]
    return "\n".join(lines)
