"""System 10 overfit (audit 2.2): CSCV PBO on noise ~ 0.5, on one superior strategy ~ 0; nested
selection never reads the year it chooses for; the release gate reads only a fresh cache."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np

from system010_conditioned_rl import overfit as O


def test_pbo_pure_noise_is_about_half():
    rng = np.random.default_rng(1)
    pbos = [O.cscv_pbo(rng.normal(0, 1, (240, 100)), 16, max_combos=2000, seed=s)["pbo"] for s in range(5)]
    assert 0.35 < float(np.mean(pbos)) < 0.65


def test_pbo_one_superior_strategy_is_about_zero():
    rng = np.random.default_rng(2)
    M = rng.normal(0, 1, (240, 100))
    M[:, 7] += 1.0                               # Sharpe ~1 per period vs 0 for the rest
    assert O.cscv_pbo(M, 16, max_combos=2000)["pbo"] < 0.02


def test_law_vec_equals_search_law():
    from system010_conditioned_rl import search as S
    rng = np.random.default_rng(3)
    for k in (1, 2, 3, 4):
        R, D = rng.normal(0.2, 0.3, (50, k)), rng.uniform(0, 0.4, (50, k))
        got = O.law_vec(R, D)
        for i in range(50):
            ys = {2022 + j: {"return": R[i, j]} for j in range(k)}
            assert abs(got[i] - S.law(ys, D[i].max())) < 1e-9


def _rows(n=40, seed=4):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        years = {str(y): {"return": float(rng.normal(0.2, 0.3)), "max_dd": float(rng.uniform(0.05, 0.24)),
                          "q": float(rng.normal()), "trades": 100} for y in O.YEARS}
        av = {str(y): {"day_share": 0.9, "longest_gap_days": 5} for y in range(2019, 2026)}
        out.append({"id": f"c{i}", "cfg": {"size_down": 1.0}, "eligible": True, "years": years,
                    "availability": {"per_year": av}})
    return out


def test_nested_never_reads_the_year_it_chooses_for():
    rows = _rows()
    for N in O.NESTED_YEARS:
        view = O.past_view(rows, N)
        assert all(max(v["years"]) < N and max(v["availability"]) < N for v in view)
        pick = O.choose(view)
        # rewrite year N and later in every row: the choice for N must not move
        poisoned = json.loads(json.dumps(rows))
        for i, r in enumerate(poisoned):
            for y in r["years"]:
                if int(y) >= N:
                    r["years"][y].update({"return": 10.0 * (i % 3), "max_dd": 0.9, "trades": 0})
            for y in r["availability"]["per_year"]:
                if int(y) >= N:
                    r["availability"]["per_year"][y]["day_share"] = 0.0
        assert O.choose(O.past_view(poisoned, N)) == pick
        assert O.nested(poisoned)["picks"][str(N)]["id"] == pick


def test_nested_curve_reads_the_chosen_rows():
    rows = _rows()
    res = O.nested(rows)
    by = {r["id"]: r for r in rows}
    for N, p in res["picks"].items():
        assert p["return"] == by[p["id"]]["years"][N]["return"]
    assert set(res["curve"]["years"]) == {str(y) for y in O.NESTED_YEARS}


def test_deflated_sharpe_falls_with_more_trials():
    r = np.random.default_rng(5).normal(0.02, 0.05, 48)
    srs = np.random.default_rng(6).normal(0, 0.15, 500)
    a, b = O.deflated_sharpe(r, srs, 10)["dsr"], O.deflated_sharpe(r, srs, 5000)["dsr"]
    assert 0 <= b < a <= 1


def test_monthly_compounds_daily_by_calendar_month():
    from system010_conditioned_rl import search as S
    ns = np.arange(np.datetime64("2023-01-01"), np.datetime64("2024-01-01"), np.timedelta64(15, "m"))
    ns = ns.astype("datetime64[ns]").astype("int64")
    world = SimpleNamespace(per={"A": {"ns": ns, "year": np.full(len(ns), 2023)}})
    daily = [0.01] * 365
    m = S.monthly(world, 2023, daily)
    assert len(m) == 12 and abs(m[0] - (1.01 ** 31 - 1)) < 1e-4 and abs(m[1] - (1.01 ** 28 - 1)) < 1e-4
    assert S.monthly(world, 2023, daily[:-1]) is None


def test_release_gate_reads_a_fresh_cache_only(tmp_path, monkeypatch):
    from system010_conditioned_rl import search as S
    f = tmp_path / "overfit.json"
    monkeypatch.setattr(S, "OVERFIT", f)
    assert S.overfit_refusal() is None                          # missing: never blocks
    at = lambda h: (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()  # noqa: E731
    f.write_text(json.dumps({"at": at(1), "pbo": 0.67, "pbo_basis": "yearly"}))
    assert S.overfit_refusal()
    f.write_text(json.dumps({"at": at(1), "pbo": 0.4}))
    assert S.overfit_refusal() is None
    f.write_text(json.dumps({"at": at(48), "pbo": 0.9}))       # stale: never blocks
    assert S.overfit_refusal() is None
    f.write_text("{not json")
    assert S.overfit_refusal() is None
