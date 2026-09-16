"""The entry funnel: for every signal that cleared the model's bar, why it did NOT trade.

Born from the 2025 question (operator, 2026-09-04): the champion returns -2.96% in 2025
while every other research year pays, and the first instinct is to call the trades bad.
The trade ledger says the opposite - 2025 has the HIGHEST hit rate of any year, 45.5%.
What it does not have is trades: 75, against 324 in 2024 and 797 in 2021.

So the interesting quantity is not the trades taken, it is the ones REFUSED and by whom.
A veto count alone cannot answer it - two years can refuse the same number of entries for
opposite reasons - so the funnel attributes each refusal to the module that made it.

These counters must never be able to change a decision. That is the property under test
here: the funnel is added beside the filter, never inside it.
"""

import pytest

from system006_oracle_net_15m.modules.base import ModuleOutput
from system006_oracle_net_15m.orchestrator import EnsembleBrain


class _Ch:
    def prob(self, *a): return 0.0
    def uptrend(self, *a): return True
    def vol(self, *a): return None
    def mom(self, *a): return None
    def hurst(self, *a): return None
    def feargreed(self, *a): return None
    def sweep(self, *a): return None
    def meta(self, *a): return None
    def micro(self, *a): return None
    def tree(self, *a): return None
    def size(self, *a): return None
    def has(self, *a): return False


class _Wants:
    """Every symbol is entry-grade."""
    name = "wants"
    weight = 1.0
    def reset(self): pass
    def evaluate(self, view):
        out = ModuleOutput()
        for s in view.candles:
            out.vote(s, conviction=0.9)
        return out


class _Vetoes:
    """A named gate that refuses the symbols it is given."""
    def __init__(self, name, symbols):
        self.name, self._symbols, self.weight = name, set(symbols), 1.0
    def reset(self): pass
    def evaluate(self, view):
        out = ModuleOutput()
        for s in view.candles:
            if s in self._symbols:
                out.vote(s, conviction=0.0, veto=True)
        return out


def _brain(modules, **kw):
    kw.setdefault("max_positions", 4)
    return EnsembleBrain(channels=_Ch(), modules=modules, position_fraction=1.0,
                         enter=0.5, exit_=0.1, min_hold=0, **kw)


def _tick(symbols, positions=None):
    return {"timestamp": "2025-06-02T00:00:00+00:00",
            "candles": {s: {"close": 100.0, "volume": 1e9} for s in symbols},
            "account": {"cash": 100_000.0, "equity": 100_000.0,
                        "initial_capital": 100_000.0, "positions": positions or {}}}


def test_a_refused_entry_names_the_gate_that_refused_it():
    b = _brain([_Wants(), _Vetoes("regime", ["BTCUSDT"]), _Vetoes("fractal", ["ETHUSDT"])])
    b.decide(_tick(["BTCUSDT", "ETHUSDT", "SOLUSDT"]))
    assert b.funnel["above_bar"] == 3
    assert b.funnel["vetoed"] == 2
    assert b.funnel["veto:regime"] == 1
    assert b.funnel["veto:fractal"] == 1
    assert b.funnel["eligible"] == 1


def test_two_gates_refusing_the_same_name_are_both_recorded():
    """Otherwise removing one gate looks like it should free the trade, and it does not."""
    b = _brain([_Wants(), _Vetoes("regime", ["BTCUSDT"]), _Vetoes("crowd", ["BTCUSDT"])])
    b.decide(_tick(["BTCUSDT"]))
    assert b.funnel["vetoed"] == 1, "the symbol is refused once"
    assert b.funnel["veto:regime"] == 1 and b.funnel["veto:crowd"] == 1, "by two gates"


def test_a_full_book_is_counted_as_capacity_not_as_an_opinion():
    """The one refusal that is not a judgement about the trade. It has to read
    differently from a veto, or 'add slots' and 'loosen the gates' look like the
    same fix for what are two entirely different problems."""
    held = {"BTCUSDT": {"entry_time": "2025-06-01T00:00:00+00:00", "quantity": 1.0}}
    b = _brain([_Wants()], max_positions=1)
    b.decide(_tick(["BTCUSDT", "ETHUSDT", "SOLUSDT"], positions=held))
    assert b.funnel["eligible"] == 2, "two names wanted in"
    assert b.funnel["book_full"] == 2, "and the book had no room for either"
    assert not b.funnel.get("vetoed"), "nobody objected to them"


def test_the_funnel_cannot_change_what_the_book_does():
    """The property that makes this safe to ship in the live path: counting happens
    beside the filter, never inside it. Same modules, same tick, same orders."""
    mods = [_Wants(), _Vetoes("regime", ["ETHUSDT"])]
    b = _brain(mods)
    tick = _tick(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    first = b.decide(tick)
    b.funnel.clear()          # wipe every counter mid-flight
    b.reset()
    second = b.decide(tick)
    assert [(o["symbol"], o["notional"]) for o in first.orders] == \
           [(o["symbol"], o["notional"]) for o in second.orders]
    assert "BTCUSDT" in {o["symbol"] for o in first.orders}
    assert "ETHUSDT" not in {o["symbol"] for o in first.orders}


def test_average_deployment_is_recoverable_from_the_funnel():
    """A year can go quiet because entries were refused, or because the regime scaled
    the money down to nothing. Those need telling apart, so the deployed fraction is
    accumulated per bar alongside the counts."""
    b = _brain([_Wants()])
    for _ in range(4):
        b.reset()
        b.decide(_tick(["BTCUSDT"]))
    assert b.funnel["bars"] == 4
    assert b.funnel["deploy_sum"] / b.funnel["bars"] == pytest.approx(1.0)


# --- the funnel has to SURVIVE the trip out of the backtest ---------------------------

def test_per_year_keeps_the_funnel_only_when_asked(monkeypatch):
    """per_year() filters each summary down to a fixed key list, and that filter
    silently swallowed the funnel on its first run: the report printed "0 signals
    cleared the bar" next to "512 trades" for the same year. Opt-in, like keep_equity -
    the autoloop writes every summary it takes to the ledger, so a field kept by
    default is kept thousands of times over."""
    from system006_oracle_net_15m import launch

    fake = {"return_pct": 1.0, "max_drawdown": 0.1, "trades": 7, "average_exposure": 0.05,
            "status": "complete", "stop_reason": None,
            "funnel": {"above_bar": 900, "vetoed": 880, "veto:regime": 880},
            "equity": [{"equity": 1.0}]}
    monkeypatch.setattr(launch, "year_window", lambda *a, **k: fake)

    plain = launch.per_year({}, [], [2025], "sig")
    assert "funnel" not in plain[2025], "nothing is paid for by default"
    assert "equity" not in plain[2025]

    kept = launch.per_year({}, [], [2025], "sig", keep_funnel=True)
    assert kept[2025]["funnel"]["veto:regime"] == 880
    assert "equity" not in kept[2025], "one opt-in must not drag the other along"

    both = launch.per_year({}, [], [2025], "sig", keep_funnel=True, keep_equity=True)
    assert "funnel" in both[2025] and "equity" in both[2025]


def test_a_window_summary_always_carries_its_funnel():
    """run_window attaches it unconditionally; only per_year's filter is opt-in. If
    this ever regresses to a getattr default, the funnel goes quiet without erroring -
    which is exactly how the first version failed."""
    import inspect

    from system006_oracle_net_15m import launch, strategy

    assert 'summary["funnel"]' in inspect.getsource(launch.run_window)
    assert hasattr(strategy.OracleNetBrain, "funnel"), (
        "launch reads brain.funnel through getattr with a default, so a missing "
        "property would read as an empty funnel rather than as a crash")
