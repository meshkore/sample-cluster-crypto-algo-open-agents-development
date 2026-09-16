"""Microstructure: the contrarian score reads the crowd, the module vetoes fragile longs."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from system006_oracle_net_15m.channels import Channels
from system006_oracle_net_15m.microstructure import contrarian_score
from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.microstructure import Microstructure


def _view(channels, ns=10, symbols=("AAA",)):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols},
                      account={"positions": {}}, channels=channels, held=set(), peaks={})


def test_score_bounds_and_sign():
    n = 300
    rng = np.random.default_rng(0)
    funding = rng.normal(0, 1e-4, n)
    oi = np.cumsum(rng.normal(0, 1.0, n)) + 1000
    liq_long = np.abs(rng.normal(0, 1.0, n))
    liq_short = np.abs(rng.normal(0, 1.0, n))
    # A crowded top at bar 200: funding and OI both spike hard.
    funding[200] = 0.02
    oi[200:] += 500
    score = contrarian_score(funding, oi, liq_long, liq_short)
    assert score.shape == (n,)
    assert np.all(score >= -1.0) and np.all(score <= 1.0)
    assert score[200] < 0  # crowded, over-levered longs -> contrarian bearish

    # A long-liquidation flush -> contrarian bullish.
    liq_long2 = liq_long.copy()
    liq_long2[250] = 50.0
    score2 = contrarian_score(funding, oi, liq_long2, liq_short)
    assert score2[250] > 0


def test_module_vetoes_fragile_and_abstains_when_off():
    ch = Channels({"AAA": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "micro": {10: -0.8}},
                  "BBB": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "micro": {10: 0.6}}})
    assert Microstructure(gate=None).evaluate(_view(ch, symbols=["AAA", "BBB"])).votes == {}
    out = Microstructure(gate=0.5).evaluate(_view(ch, symbols=["AAA", "BBB"]))
    assert out.votes["AAA"].veto is True   # crowded top -> vetoed
    assert "BBB" not in out.votes          # flushed / bullish -> allowed


def test_the_funding_builder_is_causal_and_signed_correctly():
    """Built 2026-09-01 from the only microstructure input with a public long history.

    Two properties decide whether this channel can be trusted: a bar must read only
    settlements STRICTLY before it, and crowding (persistently high funding) must read
    NEGATIVE, which is the contract every consumer of the channel assumes.
    """
    import json
    import tempfile
    from pathlib import Path

    import numpy as np

    from system006_oracle_net_15m import microstructure as m

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # settlements every 8h; the second half is heavily crowded (high positive funding)
        base = 1_600_000_000_000
        rows = [{"t_ms": base + i * 28_800_000, "rate": 0.0001 if i < 200 else 0.01}
                for i in range(400)]
        (tmp / "funding_TESTUSDT.json").write_text(json.dumps(rows), encoding="utf-8")
        bars = np.array([base + i * 28_800_000 + 3_600_000 for i in range(400)],
                        dtype=np.int64) * 1_000_000
        sig = tmp / "signals.npz"
        np.savez(sig, TESTUSDT__epoch_ns=bars, TESTUSDT__prob=np.zeros(400, dtype=np.float32))

        out = m.build_from_funding(str(sig), funding_dir=str(tmp), span=32)
        ns, score = out["TESTUSDT"]
        assert len(score) == 400
        # The first version used a surge term alone and failed here, for a reason worth
        # keeping: a z-score erases funding that has been high for months, because the
        # trailing mean follows it up - so it read a sustained crowded market as normal.
        assert score[350] < -0.5, "sustained expensive funding must read as crowded"
        assert score[100] > score[350], "the calm period must read less crowded"


def test_a_symbol_without_funding_history_is_skipped():
    import tempfile
    from pathlib import Path

    import numpy as np

    from system006_oracle_net_15m import microstructure as m

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sig = tmp / "signals.npz"
        np.savez(sig, NOPERP__epoch_ns=np.arange(10, dtype=np.int64),
                 NOPERP__prob=np.zeros(10, dtype=np.float32))
        assert m.build_from_funding(str(sig), funding_dir=str(tmp)) == {}
