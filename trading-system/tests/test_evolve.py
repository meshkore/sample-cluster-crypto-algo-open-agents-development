"""Evolutionary search: bred genomes are always complete & valid; cold start = random."""

from __future__ import annotations

import json
import random
from pathlib import Path

from system006_oracle_net_15m.autoloop import _evolve, _top_configs, _sample

SPACE = {
    "threshold": [0.02, 0.03, 0.05, 0.08],
    "window": [48, 64, 96, 128],
    "epochs": [20, 30, 40],
    "trend_span": [2880, 5760, 8640, 11520],
    "ensemble": [1, 1, 1, 3],
}


def _valid(cfg: dict) -> bool:
    return set(cfg) == set(SPACE) and all(cfg[g] in SPACE[g] for g in SPACE)


def test_evolve_cold_start_falls_back_to_random(tmp_path):
    empty = tmp_path / "nonexistent.jsonl"
    rng = random.Random(0)
    for _ in range(50):
        cfg = _evolve(SPACE, rng, ledger_path=empty)
        assert _valid(cfg)


def test_evolve_always_complete_and_valid_with_history(tmp_path):
    # A ledger with a few scored genomes (plus a legacy gene that must be projected out).
    lp = tmp_path / "ledger.jsonl"
    rows = [
        {"iteration": 1, "score": 0.08, "config": {"threshold": 0.03, "window": 96, "epochs": 40,
                                                    "trend_span": 2880, "ensemble": 1, "legacy_gene": 7}},
        {"iteration": 2, "score": -0.05, "config": {"threshold": 0.02, "window": 64, "epochs": 30,
                                                    "trend_span": 5760, "ensemble": 3}},
        {"iteration": 3, "score": 0.02, "config": {"threshold": 0.05, "window": 128, "epochs": 20,
                                                   "trend_span": 8640, "ensemble": 1}},
        {"iteration": 4, "error": "boom"},              # malformed rows must be ignored
        {"iteration": 5, "score": None, "config": {}},
    ]
    lp.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    top = _top_configs(SPACE, ledger_path=lp)
    assert top, "should find elite configs"
    assert all("legacy_gene" not in c for c in top)      # retired gene projected out
    assert all(set(c) <= set(SPACE) for c in top)

    rng = random.Random(1)
    seen_values = {g: set() for g in SPACE}
    for _ in range(300):
        cfg = _evolve(SPACE, rng, ledger_path=lp)
        assert _valid(cfg)                                # never emits a broken genome
        for g in SPACE:
            seen_values[g].add(cfg[g])
    # Exploration means the sampler still reaches values beyond the elite genomes.
    assert len(seen_values["threshold"]) >= 2


def test_top_configs_ranks_by_score(tmp_path):
    lp = tmp_path / "ledger.jsonl"
    rows = [
        {"score": -0.20, "config": {"threshold": 0.02, "window": 48, "epochs": 20, "trend_span": 2880, "ensemble": 1}},
        {"score": 0.09, "config": {"threshold": 0.03, "window": 96, "epochs": 40, "trend_span": 2880, "ensemble": 1}},
        {"score": 0.01, "config": {"threshold": 0.05, "window": 64, "epochs": 30, "trend_span": 5760, "ensemble": 3}},
    ]
    lp.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    top = _top_configs(SPACE, k=2, ledger_path=lp)
    assert len(top) == 2
    assert top[0]["window"] == 96 and top[0]["threshold"] == 0.03   # best score first


def test_evolve_fresh_never_repeats(tmp_path):
    from system006_oracle_net_15m.autoloop import _evolve_fresh, _genome_key
    lp = tmp_path / "ledger.jsonl"
    lp.write_text(json.dumps({"score": 0.05, "config": {"threshold": 0.03, "window": 96,
                                                        "epochs": 40, "trend_span": 2880,
                                                        "ensemble": 1}}) + "\n")
    rng = random.Random(7)
    seen: set = set()
    genomes = [_evolve_fresh(SPACE, rng, seen, ledger_path=lp) for _ in range(60)]
    keys = [_genome_key(g) for g in genomes]
    assert len(keys) == len(set(keys)), "duplicate genome evaluated twice in one run"
    for g in genomes:
        assert set(g) == set(SPACE) and all(g[k] in SPACE[k] for k in SPACE)
