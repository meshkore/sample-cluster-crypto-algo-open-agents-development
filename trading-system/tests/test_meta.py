"""Meta-labelling: the gate module vetoes losers, and the walk-forward stays causal."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from system006_oracle_net_15m.channels import Channels
from system006_oracle_net_15m.dataset import LOCK
from system006_oracle_net_15m.meta import Candidates, build_verdicts
from system006_oracle_net_15m.modules.base import MarketView
from system006_oracle_net_15m.modules.meta import Meta


def _view(channels, ns, symbols):
    return MarketView(timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc), ns=ns,
                      candles={s: {"close": 100.0} for s in symbols}, account={"positions": {}},
                      channels=channels, held=set(), peaks={})


def test_meta_module_vetoes_below_margin_and_abstains_when_missing():
    table = {
        "AAA": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "meta": {10: 0.05}},   # win
        "BBB": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "meta": {10: -0.02}},  # loser
        "CCC": {"prob": {}, "trend": {}, "vol": {}, "mom": {}, "meta": {}},           # no verdict
    }
    ch = Channels(table)
    # Off (margin=None) -> abstains on everything.
    assert Meta(margin=None).evaluate(_view(ch, 10, ["AAA", "BBB", "CCC"])).votes == {}
    out = Meta(margin=0.0).evaluate(_view(ch, 10, ["AAA", "BBB", "CCC"]))
    assert out.votes["BBB"].veto is True     # expected net <= 0 -> vetoed
    assert "AAA" not in out.votes            # positive edge -> allowed
    assert "CCC" not in out.votes            # no verdict -> abstain (primary stands)


def test_meta_channel_roundtrips_through_npz(tmp_path):
    from system006_oracle_net_15m.meta import write_meta
    path = tmp_path / "meta.npz"
    write_meta({"AAA": {123: 0.04, 456: -0.01}}, str(path))
    ch = Channels.from_file  # noqa: F841  (documented below)
    from system006_oracle_net_15m.channels import load_meta
    got = load_meta(str(path))
    assert got["AAA"][123] == pytest.approx(0.04, abs=1e-6)
    assert got["AAA"][456] == pytest.approx(-0.01, abs=1e-6)


def _synthetic_candidates(n_research=1500, n_forward=300, seed=0):
    rng = np.random.default_rng(seed)
    n = n_research + n_forward
    lock_ns = int(np.datetime64(datetime.fromisoformat(LOCK).replace(tzinfo=None), "ns").astype("int64"))
    bar = 900 * 1_000_000_000
    # Research entries strictly before the lock, forward strictly after.
    entry = np.concatenate([
        lock_ns - (np.arange(n_research)[::-1] + 1) * bar,
        lock_ns + (np.arange(n_forward) + 1) * bar,
    ]).astype(np.int64)
    resolve = entry + 96 * bar
    feats = rng.normal(size=(n, 3))
    # A learnable label so XGBoost has real signal: sign of feature 0.
    y = np.where(feats[:, 0] > 0.3, 1, np.where(feats[:, 0] < -0.3, -1, 0)).astype(int)
    sym = np.array(["AAA" if i % 2 else "BBB" for i in range(n)])
    return Candidates(X=feats, y=y, ret=feats[:, 0] * 0.01, entry_ns=entry,
                      resolve_ns=resolve, sigma=np.full(n, 0.05), symbol=sym), n_research, n_forward


def test_walkforward_is_causal_and_seals_2026():
    cand, n_research, n_forward = _synthetic_candidates()
    verdicts, doc = build_verdicts(cand, folds=4, min_train_frac=0.2)
    all_ns = {ns for table in verdicts.values() for ns in table}

    # The earliest (train-only) research block gets NO verdict — the module abstains there.
    earliest = int(cand.entry_ns[:n_research].min())
    assert earliest not in all_ns
    assert doc["research"] == n_research and doc["forward"] == n_forward

    # Every sealed-2026 candidate is scored (by the final research model only).
    forward_ns = set(cand.entry_ns[n_research:].tolist())
    assert forward_ns.issubset(all_ns)
