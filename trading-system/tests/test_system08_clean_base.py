"""System 08 inherits a base, not a burden.

Operator, 2026-09-09: *"no quiero arrastrar basura, quiero un sistema limpio totalmente
funcional para empezar lo nuevo, no quiero arrastrar nada disfuncional, ni pesos, ni
lacras, ni lastres... aprovechar el sistema de back testing, de adquisicion de datos, de
normalizacion de datos, todo lo que ya tenemos descargado y operativo."*

Those are two requirements pulling in opposite directions, and the only way to satisfy
both is to say exactly which parts are inherited and prove the rest is not reachable.
So this file is the definition, executable:

  INHERITED, because it is shared, tested and general
    quantlab_catalog          data acquisition, the 2026 lock, the external series
    quantlab_catalog.transforms   causal normalisation, fitted on nothing
    quantlab_backtester       execution, costs, the ledger, shorts, forced exits

  NOT INHERITED, deliberately
    system006_oracle_net_15m         its net, its features, its thresholds, its overlays
    the classical TA panel    ~91 indicator columns - real and shared, and precisely
                              the "bag of indicators" the alpha specification rejects.
                              Available if a hypothesis ever asks for it; never a
                              default, and never imported just because it exists.

The last test is the one that matters. A dependency on system 06 would not announce
itself - it would arrive as one convenient import, and six months later the "clean"
system would be unable to run without the thing it was supposed to replace.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
SYSTEM08 = REPO / "trading-system" / "system008_residual_momentum_ls"


def test_system08_does_not_import_system06_anywhere():
    """The whole definition of a clean start, checked by parsing rather than by grep."""
    offenders = []
    for py in sorted(SYSTEM08.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if "system06" in name or "system0" in name.replace("system08", ""):
                    offenders.append(f"{py.name}:{node.lineno} -> {name}")
    assert not offenders, (
        f"system 08 reached into an older system: {offenders}. The inheritance is the "
        f"catalogue and the backtester; everything else is a fresh start or it is not "
        f"a fresh start at all.")


def test_the_inherited_base_is_importable_and_real():
    import quantlab_catalog as cat
    from quantlab_backtester.ledger import AccountLedger
    from quantlab_catalog import transforms

    assert callable(cat.load_universe) and callable(cat.research)
    assert callable(transforms.rolling_z) and callable(transforms.robust_z)
    assert AccountLedger(initial_capital=1.0).equity == 1.0


def test_a_new_system_can_go_from_candles_to_a_normalised_feature_without_system06():
    """The round trip the operator asked for, end to end, on real downloaded data."""
    import quantlab_catalog as cat
    from quantlab_catalog import transforms

    symbols = cat.load_universe()[:1]
    bars = cat.research(symbols)[symbols[0]]
    assert len(bars) > 10_000, "the catalogue returned a suspiciously short history"
    assert max(b.timestamp for b in bars).year == 2025, "the 2026 lock did not hold"

    close = np.array([b.close for b in bars[-5_000:]], dtype=float)
    ret = transforms.log_change(close, 1)
    z = transforms.rolling_z(ret[1:], 96)
    pct = transforms.rolling_percentile(np.abs(ret[1:]), 96)

    assert np.isfinite(z[200:]).all(), "the normalised feature has holes in it"
    assert np.isfinite(pct[200:]).all()
    assert 0.0 <= np.nanmin(pct) and np.nanmax(pct) <= 1.0
    # A z-score of a return series should be centred and of order one. If this drifts
    # far from that, the transform is describing something other than what it claims.
    assert abs(np.nanmean(z[200:])) < 0.5
    assert 0.5 < np.nanstd(z[200:]) < 2.0


def test_the_engine_the_new_system_inherits_can_carry_a_short():
    from quantlab_backtester.ledger import AccountLedger

    led = AccountLedger(initial_capital=10_000.0)
    led.record_sell(datetime(2026, 1, 1, tzinfo=timezone.utc), "BTCUSDT",
                    price=100.0, proceeds=1000.0, fee=0.0, reason="SHORT",
                    quantity=10.0)
    led.mark("BTCUSDT", 90.0)
    assert led.equity == pytest.approx(10_100.0)
    assert led.gross_exposure == pytest.approx(900.0 / 10_100.0)


def test_no_dead_experiment_directories_remain_under_system06():
    """8.15 GB of scratch nets were cleared on 2026-09-09. This keeps them cleared.

    They were regenerable from config, code and data, and every RESULT they produced is
    recorded in rnd/ and in the summary - so what was deleted was weight, not evidence.
    The champion's own artefacts stay, and the golden test depends on them.
    """
    root = REPO / "research" / "system06"
    if not root.is_dir():
        pytest.skip("system 06 is not on this machine")
    # __pycache__ is Python's, not ours, and is regenerated on every import.
    scratch = [p.name for p in root.iterdir()
               if p.is_dir() and p.name.startswith("_") and p.name != "__pycache__"]
    assert not scratch, (
        f"experiment scratch directories are back: {scratch}. They are regenerable and "
        f"each one costs about 110 MB; if one is needed for a study, it belongs in the "
        f"study's own working directory rather than beside the champion.")
    for artefact in ("best.json", "signals.npz", "model_card.json"):
        assert (root / artefact).is_file(), (
            f"{artefact} is missing - the champion's own artefacts are NOT scratch and "
            f"the golden reproduction test depends on them")
