"""Regression guard: the ensemble's decisions are frozen against a golden fixture.

The fixture was captured from the modular ensemble at the moment it was proven —
scripted (this file, 9 configs across the whole risk-layer space) and on real-data
backtests — to be byte-identical to the retired `OracleNetBrain` monolith. Every
later phase adds modules; with their new levers OFF, the decisions here must not
move. If a change is intentional, regenerate with `REGEN_GOLDEN=1 pytest`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from quantlab_system06.channels import Channels
from quantlab_system06.orchestrator import build_ensemble

SYMBOLS = ["AAA", "BBB", "CCC"]
START = datetime(2024, 1, 1, tzinfo=timezone.utc)
BAR = timedelta(minutes=15)
NBARS = 10
GOLDEN = Path(__file__).parent / "fixtures" / "ensemble_golden.json"

CONFIGS = {
    "vanilla": {},
    "stop_loss": {"stop_loss": 0.15},
    "trail_stop": {"trail_stop": 0.10},
    "vol_target": {"vol_scale": 1.5, "vol_floor": 0.4},
    "mom_gate": {"mom_gate": 0.5},
    "breadth_gate": {"breadth_gate": 0.5},
    "regime_deploy": {"regime_deploy": 0.6},
    "regime_persist": {"regime_deploy": 0.6, "regime_persist": 96},
    "combined": {"stop_loss": 0.2, "trail_stop": 0.12, "vol_scale": 1.5,
                 "mom_gate": 0.4, "breadth_gate": 0.4, "regime_deploy": 0.7,
                 "regime_persist": 48},
}
BASE = dict(position_fraction=0.9, max_positions=5, enter=0.5, exit_=0.5, min_hold=1)


def _ns(moment: datetime) -> int:
    naive = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return int(np.datetime64(naive, "ns").astype("int64"))


def _write_signals(path) -> None:
    times = [START + i * BAR for i in range(NBARS)]
    ns = np.array([_ns(t) for t in times], dtype="int64")
    prob = {"AAA": [0.9] * NBARS, "BBB": [0.9] * NBARS,
            "CCC": [0.2, 0.2, 0.8, 0.8, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1]}
    trend = {"AAA": [1] * NBARS, "BBB": [0] * NBARS,
             "CCC": [1, 1, 1, 1, 1, 1, 0, 1, 1, 1]}
    vol = {"AAA": [2.0] * NBARS, "BBB": [1.0] * NBARS, "CCC": [0.5] * NBARS}
    mom = {"AAA": [0.1] * NBARS, "BBB": [0.2] * NBARS, "CCC": [-0.1] * NBARS}
    payload = {}
    for s in SYMBOLS:
        payload[f"{s}__epoch_ns"] = ns
        payload[f"{s}__prob"] = np.array(prob[s], dtype=np.float16)
        payload[f"{s}__trend"] = np.array(trend[s], dtype=np.int8)
        payload[f"{s}__vol"] = np.array(vol[s], dtype=np.float16)
        payload[f"{s}__mom"] = np.array(mom[s], dtype=np.float16)
    np.savez(path, **payload)


def _tick(i: int, equity: float, positions: dict, closes: dict | None = None) -> dict:
    moment = START + i * BAR
    candles = {s: {"close": (closes or {}).get(s, 100.0 + i)} for s in SYMBOLS}
    return {"timestamp": moment.isoformat(), "candles": candles,
            "account": {"equity": equity, "cash": equity, "initial_capital": 100_000.0,
                        "positions": positions}}


def _held(entry_bar: int, unreal: float = 0.0) -> dict:
    return {"entry_price": 100.0, "entry_time": (START + entry_bar * BAR).isoformat(),
            "unrealised_pct": unreal}


def _scenario() -> list[dict]:
    return [
        _tick(0, 100_000.0, {}),
        _tick(1, 100_000.0, {"AAA": _held(0)}, {"AAA": 120.0}),
        _tick(2, 100_000.0, {"AAA": _held(0)}, {"AAA": 100.0}),
        _tick(3, 100_000.0, {"AAA": _held(0, unreal=-0.2)}),
        _tick(4, 100_000.0, {"AAA": _held(0), "CCC": _held(2)}),
        _tick(6, 100_000.0, {"AAA": _held(0), "CCC": _held(2)}),
        _tick(7, 100_000.0, {"AAA": _held(0)}),
        _tick(8, 70_000.0, {"AAA": _held(0)}),
    ]


def _run(signals_path, cfg) -> list[dict]:
    ens = build_ensemble(Channels.from_file(signals_path), **cfg)
    ens.reset()
    trace = []
    for tick in _scenario():
        d = ens.decide(tick)
        trace.append({"orders": d.orders, "stop": d.stop})
    return trace


@pytest.fixture()
def signals(tmp_path):
    path = tmp_path / "signals.npz"
    _write_signals(path)
    return str(path)


def test_matches_golden(signals):
    if os.environ.get("REGEN_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        out = {name: _run(signals, {**BASE, **extra}) for name, extra in CONFIGS.items()}
        GOLDEN.write_text(json.dumps(out, indent=1))
        pytest.skip(f"regenerated {GOLDEN}")
    golden = json.loads(GOLDEN.read_text())
    for name, extra in CONFIGS.items():
        trace = _run(signals, {**BASE, **extra})
        assert trace == golden[name], f"[{name}] decisions drifted from golden"


def test_vetoed_symbol_never_enters(signals):
    ens = build_ensemble(Channels.from_file(signals), **BASE)
    ens.reset()
    for tick in _scenario():
        bought = {o["symbol"] for o in ens.decide(tick).orders if o["side"] == "BUY"}
        assert "BBB" not in bought
