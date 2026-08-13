"""Run the intraday system: blocks across history, and the sealed 2026 window.

    python3 -m quantlab_intraday.launch --phase both

**A backtest is half an answer.** A training result and a forward result are
two halves of one hypothesis, and they only pair if every parameter except
`trade_from` is identical. This module exists so that identity is structural
rather than remembered: both phases are built from the same parameter dict by
the same function, and `trade_from` is the only thing either phase is allowed
to set.

**Why this drives the session in process rather than over the wire.**
`CONTRACT.md` prefers the wire, and it is right to: driving over HTTP exercises
the protocol on every real run, so a protocol bug cannot hide. It cannot be
used here, and the reason is a number rather than a preference -- the server
caps a request body at 4 MB, and the sealed 2026 window at 15-minute resolution
across five symbols is roughly 110,000 candles, about 12 MB of JSON. Splitting
it would break the account's continuity, and raising the cap means editing the
frozen instrument.

So both phases run in process, through the *same* `BacktestSession` class the
server itself instantiates: identical fills, identical costs, identical
next-bar-open rule, identical warm-up trimming. The one thing skipped is the
HTTP hop. That the two phases are driven identically matters more here than
that either is driven over a socket -- QUANT13's recorded bug was precisely two
phases that differed from each other -- and the wire is exercised on a small
window by `tests/test_intraday_wire.py` so the protocol still cannot rot.

**The training phase cannot see 2026, structurally.** Training windows are cut
from `IntradayDataset.research()`, which loads through `DataManager`, which
refuses post-lock data outright. The forward window is the only path that ever
touches `ForwardDataManager`. Inline candles bypass the server's `--forward`
flag, so that guard is replaced by this one rather than merely lost.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantlab_backtester.backtest import CostModel
from quantlab_backtester.ledger import BacktestRun
from quantlab_backtester.models import Bar, utc_now
from quantlab_backtester.session import BacktestSession, OrderRequest

from quantlab_trading import brains

from .dataset import (
    DEFAULT_BLOCKS,
    DEFAULT_SYMBOLS,
    INTERVAL,
    LOCK,
    WARMUP_BARS,
    WINDOW_BARS,
    IntradayDataset,
    Window,
)
from . import reversion  # noqa: F401 -- registers the family

COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
INITIAL_CAPITAL = 100_000.0

# `research/agent_runs/` is already gitignored: these are working measurements,
# and the record that travels with the repository is the ledger and the task
# file, not one agent's JSON.
DEFAULT_REPORT_DIR = Path("research/agent_runs/intraday")

# Where a continuous run opens trading. The same date the laboratory's own
# training runs use, over a history that starts 2017-08-17, so a continuous
# intraday result can be put beside them.
CONTINUOUS_TRADE_FROM = "2018-01-01T00:00:00+00:00"


def build_session(
    bars_by_symbol: dict[str, list[Bar]],
    window: Window,
    parameters: dict[str, Any],
    capital: float = INITIAL_CAPITAL,
    commission_bps: float = COMMISSION_BPS,
    slippage_bps: float = SLIPPAGE_BPS,
    store: Any = None,
    brain_name: str = "intraday-reversion",
) -> tuple[BacktestSession, Any]:
    """Everything a measurement needs, built but not yet driven.

    Split out of `run_window` so a caller that wants the SESSION -- its ledger,
    its equity curve, its decisions -- can have it without rebuilding any of
    this. The publisher needs exactly that: it records the same book the block
    table summarises, and a second construction path would eventually disagree
    with this one about a cost, a fill or an id.
    """
    params = dict(parameters)
    params["trade_from"] = window.trade_from.isoformat()
    params["commission_bps"] = commission_bps
    params["slippage_bps"] = slippage_bps
    brain = brains.build(brain_name, **params)

    sliced = {
        symbol: [bar for bar in bars if window.start <= bar.timestamp <= window.end]
        for symbol, bars in bars_by_symbol.items()
    }
    sliced = {symbol: bars for symbol, bars in sliced.items() if len(bars) >= 2}
    if not sliced:
        raise ValueError(f"{window.label}: no symbol has bars in this window")

    run = BacktestRun(
        backtest_id=BacktestRun.fingerprint(
            brain_name,
            brain.parameters(),
            _policy_document(brain),
            BacktestRun.universe_digest(sliced),
            window.start.isoformat(),
            window.end.isoformat(),
            capital,
        ),
        label=f"{brain_name}-{window.label}",
        created_at=utc_now(),
        initial_capital=capital,
        strategy_family=brain_name,
        strategy_params=brain.parameters(),
        policy=_policy_document(brain),
        universe_size=len(sliced),
        window_start=window.start.isoformat(),
        window_end=window.end.isoformat(),
    )
    session = BacktestSession(
        run=run,
        bars_by_symbol=sliced,
        costs=CostModel(commission_bps, slippage_bps),
        # The whole point of iterating: the first run over a window computes
        # the panel and writes it, every run after that reads it. The cache key
        # is a digest of the candles, so a window that changed is a window that
        # is recomputed rather than one that is silently mis-served.
        indicator_store=store,
    )
    return session, brain


def measure(
    session: BacktestSession,
    brain: Any,
    window: Window,
    capital: float = INITIAL_CAPITAL,
    slippage_bps: float = SLIPPAGE_BPS,
) -> dict[str, Any]:
    """What a finished session says, in this system's vocabulary."""
    summary = session.summary()
    summary["window"] = window.document()
    summary["symbols"] = sorted(session.bars_by_symbol)
    summary["diagnostics"] = brain.diagnostics()
    # Commission is read back from the ledger, which records it per fill.
    # Slippage is not recorded anywhere -- it lives inside the fill price -- so
    # it is the one component that has to be reconstructed.
    summary["trades_detail"] = _trade_statistics(session, capital, slippage_bps)
    # The high-water mark and when it was reached. Two money-management variants
    # can only be compared at a common point, and their ENDINGS are not one: a
    # configuration that breached its mandate in April 2022 ended up 168% and one
    # that survived to 2025 ended up 134%, and reading those two numbers side by
    # side says the opposite of what happened. The peak is where the giveback
    # starts, so it is the point both runs actually share.
    peak = capital
    peak_at = None
    for point in session.equity_curve:
        if point["equity"] > peak:
            peak, peak_at = point["equity"], point["timestamp"]
    summary["peak_equity"] = peak
    summary["peak_at"] = peak_at
    # Round trips per calendar year, and the leanest year of the run.
    #
    # This is the diagnostic that would have predicted the most expensive
    # mistake made on this system. A 3.0% entry threshold trained better than
    # anything else here -- +182% over eight years, never stopped -- and
    # produced THREE trades in the sealed window, because 2026 is 7.5 months of
    # falling tape and a selective long-only rule stands aside through it. The
    # eight-year total said 43 trades a year and hid entirely that the bear
    # years contribute almost none of them.
    #
    # A rule that skips whole years cannot be evaluated in a seven-month window,
    # and that is knowable from training alone: no forward information is used
    # here, only the distribution of what training already did.
    by_year: dict[str, int] = {}
    for order in session.ledger.orders:
        if order.side == "SELL":
            year = f"{order.timestamp:%Y}"
            by_year[year] = by_year.get(year, 0) + 1
    summary["trades_by_year"] = dict(sorted(by_year.items()))
    summary["leanest_year_trades"] = min(by_year.values()) if by_year else 0
    return summary


def run_window(
    bars_by_symbol: dict[str, list[Bar]],
    window: Window,
    parameters: dict[str, Any],
    capital: float = INITIAL_CAPITAL,
    commission_bps: float = COMMISSION_BPS,
    slippage_bps: float = SLIPPAGE_BPS,
    store: Any = None,
    brain_name: str = "intraday-reversion",
) -> dict[str, Any]:
    """One measurement: one window, one parameter set, one honest number.

    `brain_name` is how a second hypothesis gets measured by exactly this
    harness: register it, pass its name, and every number below -- the cost
    decomposition, the block table, the sealed window -- is computed the same
    way, which is the only reason two hypotheses here are comparable.
    """
    session, brain = build_session(
        bars_by_symbol,
        window,
        parameters,
        capital=capital,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        store=store,
        brain_name=brain_name,
    )
    withheld = _drive(session, brain)
    summary = measure(
        session, brain, window, capital=capital, slippage_bps=slippage_bps
    )
    # A brain that tried to trade the warm-up is a broken brain, and the number
    # belongs in the result rather than in a log line nobody reads.
    summary["warmup_orders_withheld"] = withheld
    return summary


def _policy_document(brain: Any) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(brain.policy)


def _moment(value: Any) -> datetime | None:
    """A tick's timestamp as a datetime. It arrives as an ISO STRING."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _drive(session: BacktestSession, brain: Any) -> int:
    """The pull loop, exactly as the orchestrator drives it over HTTP.

    **The warm-up gate lives here, not in the brain.** Every window serves
    history before `trade_from` so filters arrive warm, and a brain that trades
    those bars reports pre-lock trades as if they were forward ones. The two
    built-in brains each gate themselves and are correct; generation 4 did not,
    and 17 of the 65 trades in its "sealed 2026" run were opened in September
    to December 2025. It cost almost nothing there -- those trades netted -109
    on 100,000 -- which is exactly why it had to be caught by something other
    than the result looking wrong.

    A contract each generated strategy must remember is a contract that will be
    forgotten, and the loop writes these strategies unattended. So the harness
    refuses the order instead of trusting the author: the brain still SEES every
    warm-up tick, because its moving averages need them, and the count comes
    back so the caller can say out loud that a brain tried.
    """
    opens = _moment((brain.parameters() or {}).get("trade_from"))
    withheld = 0
    while True:
        tick = session.next_tick()
        if tick.get("done"):
            return withheld
        decision = brain.decide(tick)
        if decision.stop:
            session.stop(decision.stop)
            return withheld
        orders, note = decision.orders, decision.note
        moment = _moment(tick.get("timestamp"))
        if orders and opens is not None and moment is not None and moment < opens:
            withheld += len(orders)
            note = (
                (f"{note} | " if note else "")
                + f"harness withheld {len(orders)} order(s): trading opens {opens:%Y-%m-%d}"
            )
            orders = []
        if orders or note:
            session.submit([OrderRequest.from_payload(order) for order in orders], note)


def _trade_statistics(
    session: BacktestSession,
    capital: float,
    slippage_bps: float = SLIPPAGE_BPS,
) -> dict[str, Any]:
    """Round trips, win rate, the average trade size, and what the toll cost.

    The charter asks for the average trade size on every evaluation, and asks
    for a reason whenever it is under 3% of capital: a position that cannot
    move the account is not worth the fee. At 15-minute resolution that number
    is also the fastest way to see the de-leverage ramp throttling a run into
    irrelevance without the summary saying anything is wrong.

    `toll_paid` and `pre_cost_return_pct` are the columns this system exists to
    read. A result of "-16% over 400 trades" says nothing about whether the
    mechanism is wrong or merely too small: the same number is produced by a
    signal with no information and by a signal with real information worth less
    than 30 bps a trade. Separating them is the difference between abandoning a
    hypothesis and re-siting it. Slippage is reconstructed rather than read
    back, because the session applies it inside the fill price where it leaves
    no separate record: 5 bps of every fill's notional, which is exactly what
    `CostModel` charged.
    """
    opens: dict[str, tuple[float, float]] = {}
    wins = won = lost = 0
    notionals: list[float] = []
    fees = slippage = 0.0
    by_reason: dict[str, int] = {}
    for order in session.ledger.orders:
        fees += order.fee
        slippage += order.notional * slippage_bps / 10_000
        if order.side == "BUY":
            opens[order.symbol] = (order.notional, order.quantity)
            notionals.append(order.notional)
            continue
        by_reason[order.reason] = by_reason.get(order.reason, 0) + 1
        entry = opens.pop(order.symbol, None)
        if entry is None:
            continue
        invested, quantity = entry
        proceeds = order.notional - order.fee
        if proceeds > invested:
            wins += 1
            won += proceeds - invested
        else:
            lost += invested - proceeds
    closed = sum(1 for order in session.ledger.orders if order.side == "SELL")
    average = sum(notionals) / len(notionals) if notionals else 0.0
    toll = fees + slippage
    realised = session.ledger.equity - capital
    return {
        "round_trips": closed,
        "win_rate": wins / closed if closed else 0.0,
        "gross_won": won,
        "gross_lost": lost,
        "profit_factor": (won / lost) if lost else None,
        "fees_paid": fees,
        "slippage_paid": slippage,
        "toll_paid": toll,
        "toll_pct_of_capital": toll / capital if capital else 0.0,
        "pre_cost_return_pct": (realised + toll) / capital if capital else 0.0,
        "toll_per_trade_pct": (toll / closed / average) if closed and average else 0.0,
        "average_trade_notional": average,
        "average_trade_pct_of_capital": average / capital if capital else 0.0,
        "exit_reasons": by_reason,
    }


def training(
    dataset: IntradayDataset,
    parameters: dict[str, Any],
    blocks: int = DEFAULT_BLOCKS,
    window_bars: int = WINDOW_BARS,
    warmup_bars: int = WARMUP_BARS,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """The mechanism, measured on `blocks` windows spread across the history.

    `window_bars` is not a detail once a hypothesis holds positions for days.
    The 5,000-bar default is about seventeen days of 5-minute tape, which is
    the right size for a rule that trades several times a day and far too
    short for one that holds for three: a handful of trades per block is a
    coin flip reported as a measurement.
    """
    bars = dataset.research()
    windows = IntradayDataset.blocks(
        bars, count=blocks, window_bars=window_bars, warmup_bars=warmup_bars
    )
    # A cache root per window, not one shared root: see `store_for`. Sharing one
    # meant each block overwrote the previous block's panel, so twelve blocks
    # cached one and every rerun recomputed all twelve.
    return [
        run_window(bars, window, parameters, store=dataset.store_for(window), **kwargs)
        for window in windows
    ]


def continuous(
    dataset: IntradayDataset,
    parameters: dict[str, Any],
    trade_from: str = CONTINUOUS_TRADE_FROM,
    **kwargs: Any,
) -> dict[str, Any]:
    """One account, from `trade_from` to the lock. What the blocks cannot see.

    A block table cannot express a drawdown that accumulates: every block starts
    again at the opening capital, so eight of them reported a worst drawdown of
    17.31% for a configuration that, compounded, breached the 25% mandate in
    April 2022 and stopped. Blocks answer whether a mechanism survives different
    tape. This answers what happens to one account that lives through all of it,
    and money management can only be judged here -- position sizing, the
    de-leverage ramp and the mandate are all path-dependent by definition.
    """
    bars = dataset.research()
    stamps = IntradayDataset.timeline(bars)
    opens = datetime.fromisoformat(trade_from)
    tradeable = [stamp for stamp in stamps if stamp >= opens]
    if not tradeable:
        raise ValueError(f"no bars at or after {trade_from}")
    window = Window(
        index=0,
        start=stamps[0],
        trade_from=tradeable[0],
        end=stamps[-1],
        label="continuous",
    )
    return run_window(
        bars, window, parameters, store=dataset.store_for(window), **kwargs
    )


def forward(
    dataset: IntradayDataset, parameters: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    """The sealed window. Same parameters, different `trade_from`. Nothing else."""
    bars = dataset.combined()
    window = IntradayDataset.forward_window(bars, dataset.lock)
    return run_window(
        bars, window, parameters, store=dataset.store_for(window), **kwargs
    )


def _summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    """What the blocks say together, including whether they agree.

    `positive_blocks` is the number that matters for this system's claim. A
    mechanism that is a liquidity premium should pay in most blocks; one that
    pays in two of eight and carries the average on a single window is a trend
    strategy that met a trend, whatever its author intended it to be.
    """
    returns = [result["return_pct"] for result in results]
    trades = sum(result["trades"] for result in results)
    if not returns:
        return {"blocks": 0}
    ordered = sorted(returns)
    middle = len(ordered) // 2
    return {
        "blocks": len(returns),
        "median_return_pct": (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2
        ),
        "mean_return_pct": sum(returns) / len(returns),
        "positive_blocks": sum(1 for value in returns if value > 0),
        "worst_block_pct": min(returns),
        "best_block_pct": max(returns),
        "worst_drawdown": max(result["max_drawdown"] for result in results),
        "total_trades": trades,
        "aborted": sum(1 for result in results if result["status"] == "stopped"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--phase",
        choices=("training", "continuous", "forward", "both"),
        default="both",
        help="`training` is the block table; `continuous` is one account from "
        "--trade-from to the lock, which is the only phase that can see a "
        "drawdown accumulating and therefore the only one money management can "
        "be judged on; `forward` is the sealed window.",
    )
    parser.add_argument("--trade-from", default=CONTINUOUS_TRADE_FROM)
    parser.add_argument("--brain", default="intraday-reversion")
    parser.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    parser.add_argument(
        "--warmup-bars",
        type=int,
        default=WARMUP_BARS,
        help="bars served before trading opens. Raise it when the brain keeps "
        "state longer than the default -- a multi-week trend filter that is "
        "still warming refuses every entry and reports it as no signal.",
    )
    parser.add_argument(
        "--window-bars",
        type=int,
        default=WINDOW_BARS,
        help="tradeable bars per training block. Raise it for a hypothesis "
        "that holds positions for days, or each block reports a handful of "
        "trades as though it were a measurement.",
    )
    parser.add_argument("--interval", default=INTERVAL)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override a brain or policy parameter, e.g. --set stop_atr=2.5",
    )
    args = parser.parse_args(argv)

    parameters: dict[str, Any] = {}
    for item in args.set:
        key, _, raw = item.partition("=")
        parameters[key.strip()] = _coerce(raw.strip())

    dataset = IntradayDataset(
        args.data_root,
        LOCK,
        [s for s in args.symbols.split(",") if s],
        interval=args.interval,
    )
    # The brain is told the resolution it is running at, so a time stop and a
    # turnover floor expressed in bars still mean what they say if the interval
    # is ever changed from the command line.
    parameters.setdefault("bars_per_day", dataset.bars_per_day)
    report: dict[str, Any] = {
        "family": args.brain,
        "interval": dataset.interval,
        "symbols": dataset.symbols,
        "parameters": parameters,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if args.phase in ("training", "both"):
        results = training(
            dataset,
            parameters,
            blocks=args.blocks,
            window_bars=args.window_bars,
            warmup_bars=args.warmup_bars,
            brain_name=args.brain,
        )
        report["training"] = results
        report["training_summary"] = _summarise(results)
        _print_blocks(results)
        print(json.dumps(report["training_summary"], indent=2))

    if args.phase == "continuous":
        result = continuous(
            dataset, parameters, trade_from=args.trade_from, brain_name=args.brain
        )
        report["continuous"] = result
        _print_blocks([result])
        detail = result["trades_detail"]
        # The three numbers a money-management change is judged on, printed
        # together because reading them apart is how "+168%" got recorded as a
        # success by a run that had been stopped for breaching its mandate.
        print(
            f"\npeak  {result['peak_equity']:,.0f} at {str(result['peak_at'])[:10]}"
            f"\nfinal {result['final_equity']:,.0f}  maxDD {result['max_drawdown']:.2%}"
            f"  status {result['status']}"
        )
        if result["stop_reason"]:
            print(f"stopped: {result['stop_reason']}")
        print(f"exits {detail['exit_reasons']}")

    if args.phase in ("forward", "both"):
        result = forward(dataset, parameters, brain_name=args.brain)
        report["forward"] = result
        _print_blocks([result])

    directory = Path(args.report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{utc_now()[:19].replace(':', '')}-{args.phase}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nreport: {path}")
    return 0


def _coerce(raw: str) -> Any:
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            continue
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    return raw


def _print_blocks(results: list[dict[str, Any]]) -> None:
    header = (
        f"{'window':<22}{'return':>10}{'pre-cost':>10}{'toll':>8}{'maxDD':>9}"
        f"{'trades':>8}{'win%':>7}{'expo':>7}{'avg$':>10}  status"
    )
    print(header)
    print("-" * len(header))
    for result in results:
        detail = result["trades_detail"]
        print(
            f"{result['window']['label']:<22}"
            f"{result['return_pct']:>9.2%}"
            f"{detail['pre_cost_return_pct']:>10.2%}"
            f"{detail['toll_pct_of_capital']:>8.1%}"
            f"{result['max_drawdown']:>9.2%}"
            f"{result['trades']:>8}"
            f"{detail['win_rate']:>7.0%}"
            f"{result['average_exposure']:>7.1%}"
            f"{detail['average_trade_notional']:>10,.0f}"
            f"  {result['status']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
