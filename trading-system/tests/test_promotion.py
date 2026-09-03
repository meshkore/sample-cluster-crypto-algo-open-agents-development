"""Promotion must survive re-seeding: a champion is a median, never a single lucky draw."""

from __future__ import annotations

import pytest

from quantlab_system06.autoloop import _promotion_survives, PROMOTE_MARGIN, VERIFY_SEEDS


def test_no_incumbent_promotes_on_any_finite_median():
    assert _promotion_survives([-0.20, -0.15, -0.18], bar=None) is True


def test_empty_or_all_failed_never_promotes():
    assert _promotion_survives([], bar=-0.10) is False
    assert _promotion_survives([None, None], bar=-0.10) is False


def test_a_lucky_single_draw_does_not_promote():
    """The real case: the iter-42 champion drew +0.086 while its genome re-runs near -0.10.

    Under the old rule (`score > bar + margin`) that single draw was promoted and set a bar
    nothing cleared for 94 iterations. The median of the re-runs must refuse it.
    """
    lucky, reruns = 0.0864, [-0.1054, -0.0900]
    bar = -0.0700
    assert lucky > bar + PROMOTE_MARGIN                      # the old rule would promote
    assert _promotion_survives([lucky] + reruns, bar) is False


def test_a_genuinely_better_genome_promotes():
    assert _promotion_survives([0.05, 0.045, 0.048], bar=-0.02) is True


def test_median_ignores_one_bad_seed():
    """Two good runs and one poor one still promote — the median is the estimate."""
    assert _promotion_survives([0.05, 0.048, -0.20], bar=-0.02) is True


def test_margin_is_respected():
    """Stated relative to PROMOTE_MARGIN, so tuning the margin cannot silently break this."""
    bar = 0.00
    inside = bar + PROMOTE_MARGIN * 0.5
    clears = bar + PROMOTE_MARGIN * 1.5
    assert _promotion_survives([inside] * 3, bar) is False
    assert _promotion_survives([clears] * 3, bar) is True


def test_margin_is_scaled_to_measured_noise():
    """The bar must sit at the scale of selection noise (stdev ~0.052), not below it."""
    assert PROMOTE_MARGIN >= 0.04


def test_failed_verifications_are_not_counted_as_zero():
    """A failed re-run must not be read as a score of 0.0, which would flatter a candidate."""
    assert _promotion_survives([-0.30, None, None], bar=-0.10) is False


def test_a_failed_verification_blocks_promotion_fail_closed():
    """The subtle one: dropping a failed run collapses the median onto the lucky draw.

    A candidate that clears the bar on its own draw but whose verification runs did NOT
    complete must NOT promote. Filtering the Nones out would leave a one-element list whose
    median is the single draw - silently restoring the very behaviour this rule removes.
    """
    lucky, bar = 0.20, -0.1054
    assert lucky > bar + PROMOTE_MARGIN            # it clears on its own draw
    assert _promotion_survives([lucky, None, None], bar) is False
    assert _promotion_survives([lucky, -0.30, None], bar) is False


def test_verification_is_enabled():
    assert VERIFY_SEEDS >= 2


def test_verification_scores_the_shipping_config_not_a_fresh_search(monkeypatch):
    """Verification must re-run the WINNING config, never re-search the grid.

    Re-searching would hand each verification its own best-of-grid selection - exactly the
    advantage the guard exists to remove - and would measure a candidate differently from
    the incumbent bar, which is one configuration's reproducible median.
    """
    from quantlab_system06 import autoloop

    calls = {"select": 0, "per_year": 0, "kwargs": None}

    def fake_select(*a, **k):
        calls["select"] += 1
        return {"score": 0.5}, {}, {}, []

    def fake_per_year(bars, stamps, years, signals, brain_kwargs=None, **k):
        calls["per_year"] += 1
        calls["kwargs"] = dict(brain_kwargs or {})
        return {2018: {"return_pct": 0.10}, 2019: {"return_pct": 0.20}}

    monkeypatch.setattr(autoloop.train, "train", lambda **k: {"enter": 0.8, "exit": 0.2, "min_hold": 16})
    monkeypatch.setattr(autoloop.infer, "export", lambda **k: None)
    monkeypatch.setattr(autoloop, "_select_risk_years", fake_select)
    monkeypatch.setattr(autoloop.launch, "per_year", fake_per_year)

    risk = {"max_positions": 2, "position_fraction": 0.15, "meta_margin": 0.0}
    score = autoloop._score_genome({"threshold": 0.03, "window": 96, "epochs": 1, "lr": 1e-3,
                                    "dropout": 0.1}, seed=7, data_root="d", symbols=["A"],
                                   rbars={}, rstamps=[], dataset=None, grid=[],
                                   scratch=autoloop.ROOT / "_verify_test", risk=risk)
    assert calls["per_year"] == 1, "must score the given config"
    assert calls["select"] == 0, "must NOT re-search the grid"
    assert score is not None
    # The winning risk levers reach the backtest, including zero-valued ones.
    assert calls["kwargs"]["meta_margin"] == 0.0
    assert calls["kwargs"]["max_positions"] == 2


def test_verification_failure_returns_none_not_a_score(monkeypatch):
    """A verification that blows up must report None so the fail-closed rule can refuse."""
    from quantlab_system06 import autoloop

    def boom(**k):
        raise RuntimeError("gpu fell over")

    monkeypatch.setattr(autoloop.train, "train", boom)
    out = autoloop._score_genome({"threshold": 0.03, "window": 96, "epochs": 1, "lr": 1e-3,
                                  "dropout": 0.1}, seed=7, data_root="d", symbols=["A"],
                                 rbars={}, rstamps=[], dataset=None, grid=[],
                                 scratch=autoloop.ROOT / "_verify_test", risk={"max_positions": 2})
    assert out is None


def test_median_helper_matches_the_rule():
    from quantlab_system06.autoloop import _median
    assert _median([0.1, 0.2, 0.3]) == 0.2
    assert _median([0.1, 0.3]) == pytest.approx(0.2)
    assert _median([]) is None
    assert _median([0.1, None]) is None      # incomplete evidence has no median


def test_bar_prefers_the_reproducible_median_over_the_headline(tmp_path, monkeypatch):
    """The bar must be the same QUANTITY a candidate's re-runs produce.

    Comparing a candidate's reproducible median against an incumbent's single lucky draw is
    the asymmetry that let one draw block the search for 94 iterations.
    """
    import json as _json
    from quantlab_system06 import autoloop

    best = tmp_path / "best.json"
    best.write_text(_json.dumps({"score": 0.0864, "reproducible_bar": -0.0635}))
    monkeypatch.setattr(autoloop, "BEST", best)
    assert autoloop._read_best_score() == -0.0635

    best.write_text(_json.dumps({"score": 0.0864}))       # older record, no bar recorded
    assert autoloop._read_best_score() == 0.0864          # falls back to the headline


def test_the_bar_is_the_reproducible_median_end_to_end(tmp_path, monkeypatch):
    """The whole regime rests on which NUMBER becomes the bar.

    Reading `score` directly pinned the bar to a lucky max-of-grid draw (+0.0675 while the
    reproducible bar was -0.0885), so no candidate could ever clear it and verification
    never fired — the stall this machinery exists to end. The bar must come from
    _read_best_score, and the disk must be authoritative in BOTH directions so a corrected
    (lower) bar can actually take effect.
    """
    import json as _json
    from quantlab_system06 import autoloop

    best = tmp_path / "best.json"
    monkeypatch.setattr(autoloop, "BEST", best)

    best.write_text(_json.dumps({"score": 0.0675, "reproducible_bar": -0.0885}))
    bar = autoloop._read_best_score()
    assert bar == -0.0885

    # A candidate at -0.0128 (a real observed iteration) must qualify against the
    # reproducible bar, and must NOT qualify against the headline.
    candidate = -0.0128
    assert candidate > bar + PROMOTE_MARGIN
    assert not (candidate > 0.0675 + PROMOTE_MARGIN)

    # A corrected, LOWER bar on disk must replace a higher one held in memory.
    stale_memory = 0.0675
    disk = autoloop._read_best_score()
    assert disk is not None and disk < stale_memory


def test_grid_median_and_inflation_are_recorded():
    """Every iteration should carry an UNINFLATED number beside its best-of-grid score.

    Across 125 measured sweeps the max exceeded the same net's median configuration by
    about 0.077 - roughly half the gap between a champion's headline and what it
    reproduces. Recording the median costs nothing and makes that inflation visible
    per iteration instead of only in aggregate.
    """
    from quantlab_system06.autoloop import _median

    sweep = [{"score": -0.20}, {"score": -0.14}, {"score": -0.05}]
    grid_scores = [r["score"] for r in sweep]
    grid_median = _median(grid_scores)
    best = max(grid_scores)
    assert grid_median == -0.14
    assert best - grid_median == pytest.approx(0.09)


def test_trigger_debiases_the_max_of_grid():
    """The trigger compares score MINUS the measured grid inflation against the bar.

    A max-of-grid at -0.01 looks like it clears a -0.0885 bar by a mile, but after
    subtracting the 0.0765 the max-selection contributes it sits at -0.0865 - a
    marginal, honest pass. At -0.02 the debiased value falls below the bar and the
    verification (~2 GPU-hours) must not be spent: 26% of historical iterations
    triggered under the old rule and essentially all were refused on re-seeding.
    """
    from quantlab_system06.autoloop import _is_candidate

    bar, inflation = -0.0885, 0.0765
    assert _is_candidate(-0.01, bar, inflation) is True
    assert _is_candidate(-0.02, bar, inflation) is False
    # No incumbent: anything qualifies (first champion must be creatable).
    assert _is_candidate(-0.50, None, inflation) is True
    # A missing/NaN score must never trigger.
    assert _is_candidate(float("nan"), bar, inflation) is False


def test_inflation_prior_reads_the_ledger_median(tmp_path):
    """Once enough rows carry grid_inflation, the live median replaces the constant."""
    import json as _json

    from quantlab_system06.autoloop import (
        GRID_INFLATION_PRIOR, MIN_INFLATION_ROWS, _inflation_prior,
    )

    ledger = tmp_path / "ledger.jsonl"
    # Rows carry no band genes, so they belong to the SWEPT regime - read them as such.
    # Too few rows: fall back to the measured aggregate.
    ledger.write_text("\n".join(
        _json.dumps({"grid_inflation": 0.05}) for _ in range(MIN_INFLATION_ROWS - 1)
    ), encoding="utf-8")
    assert _inflation_prior(ledger, pinned=False) == GRID_INFLATION_PRIOR

    # Enough rows: the ledger median wins; None/garbage rows are ignored, not fatal.
    rows = [_json.dumps({"grid_inflation": v})
            for v in (0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12)]
    rows.insert(3, _json.dumps({"grid_inflation": None}))
    rows.append("{not json")
    ledger.write_text("\n".join(rows), encoding="utf-8")
    assert _inflation_prior(ledger, pinned=False) == pytest.approx(0.085)

    # A missing ledger must never take the loop down.
    assert _inflation_prior(tmp_path / "absent.jsonl", pinned=False) == GRID_INFLATION_PRIOR
    assert _inflation_prior(tmp_path / "absent.jsonl") == GRID_INFLATION_PRIOR


def test_trigger_margin_is_not_double_counted():
    """The margin belongs to the promotion decision (on the reproduced median), not the
    trigger. A candidate whose debiased score clears the bar by less than the margin
    must still be ALLOWED to verify - refusing it there would demand margin twice."""
    from quantlab_system06.autoloop import PROMOTE_MARGIN, _is_candidate

    bar, inflation = -0.0885, 0.0765
    score = bar + inflation + PROMOTE_MARGIN / 2  # debiased: inside the margin
    assert _is_candidate(score, bar, inflation) is True


def test_pinned_band_requires_all_three_keys():
    """A partially pinned band is NOT a reproducible band, so it must not pin at all."""
    from quantlab_system06.autoloop import _pinned_band

    assert _pinned_band({"threshold": 0.02}) == {}
    assert _pinned_band({"band_enter": 0.75, "band_exit": 0.25}) == {}
    assert _pinned_band({"band_enter": 0.75, "band_exit": 0.25, "band_hold": None}) == {}
    assert _pinned_band({"band_enter": 0.75, "band_exit": 0.25, "band_hold": 96}) == {
        "enter": 0.75, "exit_": 0.25, "min_hold": 96
    }


def test_pinned_band_maps_to_train_kwargs_exactly():
    """The keys must match train.train's signature, or the pin silently does nothing."""
    import inspect

    from quantlab_system06 import train
    from quantlab_system06.autoloop import _pinned_band

    pinned = _pinned_band({"band_enter": 0.65, "band_exit": 0.35, "band_hold": 192})
    params = inspect.signature(train.train).parameters
    assert set(pinned) <= set(params), f"unknown train kwargs: {set(pinned) - set(params)}"
    assert isinstance(pinned["min_hold"], int)


def test_inflation_prior_never_mixes_selection_regimes(tmp_path):
    """Band-swept and band-pinned iterations do NOT measure the same quantity.

    Pinning shifted the score level by ~0.10 and cut spread ~20x, so pooling the two
    would debias a pinned candidate with a number partly derived from swept rows -
    the same class of error as comparing against a bar measured a different way.
    """
    import json as _json

    from quantlab_system06.autoloop import (
        GRID_INFLATION_PRIOR, MIN_INFLATION_ROWS, _inflation_prior,
    )

    def swept(gi):
        return _json.dumps({"config": {"threshold": 0.02}, "grid_inflation": gi})

    def pinned(gi):
        return _json.dumps({"config": {"band_enter": 0.75, "band_exit": 0.25,
                                       "band_hold": 96}, "grid_inflation": gi})

    ledger = tmp_path / "ledger.jsonl"

    # Plenty of SWEPT rows, no pinned ones: a pinned loop must NOT borrow them.
    ledger.write_text("\n".join(swept(0.20) for _ in range(MIN_INFLATION_ROWS + 4)),
                      encoding="utf-8")
    assert _inflation_prior(ledger, pinned=True) == GRID_INFLATION_PRIOR
    # ...while a swept loop legitimately uses them.
    assert _inflation_prior(ledger, pinned=False) == pytest.approx(0.20)

    # Enough of BOTH: each regime uses only its own rows, never the other's.
    rows = [swept(0.20) for _ in range(MIN_INFLATION_ROWS)]
    rows += [pinned(v) for v in (0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09)]
    ledger.write_text("\n".join(rows), encoding="utf-8")
    assert _inflation_prior(ledger, pinned=True) == pytest.approx(0.055)
    assert _inflation_prior(ledger, pinned=False) == pytest.approx(0.20)


def test_inflation_prior_requires_every_band_key_to_count_a_row_as_pinned():
    """A half-declared band is not a pinned regime - it matches _pinned_band's rule."""
    import json as _json

    from quantlab_system06.autoloop import BAND_KEYS, _pinned_band

    partial = {"band_enter": 0.75, "band_exit": 0.25}
    assert not all(k in partial for k in BAND_KEYS)
    assert _pinned_band(partial) == {}
    _json.dumps(partial)  # the row shape used by the prior stays serialisable


def _mini_space():
    return {"threshold": [0.02, 0.03], "band_enter": [0.65, 0.75],
            "band_exit": [0.25, 0.35], "band_hold": [16, 96]}


def test_incumbent_is_always_a_breeding_parent(tmp_path):
    """After a regime change the ledger may hold no pinned row worth breeding from, so
    the champion - the best REPRODUCIBLE point known - must seed the pool itself."""
    import json as _json

    from quantlab_system06.autoloop import _incumbent_genome

    best = tmp_path / "best.json"
    # The champion predates band genes: its band lives under `band` and must be folded in.
    best.write_text(_json.dumps({
        "config": {"threshold": 0.03},
        "band": {"enter": 0.75, "exit_": 0.25, "min_hold": 16},
    }), encoding="utf-8")
    genome = _incumbent_genome(_mini_space(), best)
    assert genome == {"threshold": 0.03, "band_enter": 0.75,
                      "band_exit": 0.25, "band_hold": 16}


def test_incumbent_is_refused_when_it_cannot_fill_the_space(tmp_path):
    """A partial parent would be completed with RANDOM genes and would not be the
    champion at all, so it must be refused outright rather than half-used."""
    import json as _json

    from quantlab_system06.autoloop import _incumbent_genome

    best = tmp_path / "best.json"
    best.write_text(_json.dumps({"config": {"threshold": 0.03}}), encoding="utf-8")
    assert _incumbent_genome(_mini_space(), best) is None          # no band at all

    # A gene value outside the declared space makes the parent unbreedable.
    best.write_text(_json.dumps({
        "config": {"threshold": 0.03},
        "band": {"enter": 0.85, "exit_": 0.25, "min_hold": 16},    # 0.85 not in space
    }), encoding="utf-8")
    assert _incumbent_genome(_mini_space(), best) is None

    assert _incumbent_genome(_mini_space(), tmp_path / "absent.json") is None


def test_elite_pool_does_not_let_the_old_regime_own_the_gene_pool(tmp_path, monkeypatch):
    """Swept and pinned scores are not comparable. If ranked together, the higher-scoring
    regime keeps every elite slot and no genome of the current regime can ever breed.
    """
    import json as _json

    from quantlab_system06 import autoloop

    monkeypatch.setattr(autoloop, "BEST", tmp_path / "no_best.json")   # isolate the incumbent
    space = _mini_space()
    ledger = tmp_path / "ledger.jsonl"

    rows = []
    # Swept rows scoring WELL (the old regime flattered itself).
    for _ in range(6):
        rows.append(_json.dumps({"config": {"threshold": 0.02}, "score": 0.20}))
    # Pinned rows scoring lower, but they are the only ones carrying band genes.
    for hold in (16, 96, 16, 96):
        rows.append(_json.dumps({
            "config": {"threshold": 0.03, "band_enter": 0.75,
                       "band_exit": 0.35, "band_hold": hold},
            "score": -0.10}))
    ledger.write_text("\n".join(rows), encoding="utf-8")

    top = autoloop._top_configs(space, ledger_path=ledger)
    assert top, "the pool must not be empty"
    # Every parent carries band genes: the swept rows, despite scoring higher, are excluded.
    assert all("band_hold" in c for c in top), top


def test_verify_seeds_gives_a_genuine_median_not_a_mean_of_two():
    """Measured champion re-runs span 0.074 with stdev 0.041 (seeds 91001/91002/77101/77102).

    Under variance that large a two-sample "median" is really the mean of two draws, which
    a single outlier carries; an odd count gives a median an outlier cannot move. This is
    the evidence-based response to the spread - NOT loosening the promotion margin.
    """
    from quantlab_system06.autoloop import VERIFY_SEEDS, _median

    assert VERIFY_SEEDS >= 3, "an even seed count cannot produce an outlier-proof median"
    assert (VERIFY_SEEDS + 1) % 2 == 0, "candidate score + VERIFY_SEEDS runs should be odd"

    # One wild draw must not drag the verdict: with three runs the median ignores it.
    assert _median([0.07, 0.072, 0.40]) == 0.072
    # ...whereas a two-sample "median" is dragged half way to the outlier.
    assert _median([0.072, 0.40]) == pytest.approx(0.236)


def test_the_drawdown_cap_is_a_grid_lever_and_survives_row_normalisation():
    """P11 measured ceiling 0.90 + cap 0.60 at +0.1166 - the best delta ever recorded.

    A grid row expressing that configuration must reach the brain intact. Before this,
    max_drawdown was absent from KNOWN_LEVERS and _row_to_kwargs would have silently
    STRIPPED it: the row would have run at the default 0.25 abort and measured the wrong
    strategy while looking exactly like the right one - the same name-vs-behaviour trap
    that has now appeared four times, caught proactively this once.
    """
    from quantlab_system06.autoloop import MODULE_LEVERS, _row_to_kwargs

    assert "max_drawdown" in MODULE_LEVERS
    row = {"max_positions": 2, "position_fraction": 0.15, "regime_deploy": 0.9,
           "max_drawdown": 0.6, "meta_margin": 0.005}
    kw = _row_to_kwargs(row)
    assert kw.get("max_drawdown") == 0.6, "the cap must survive normalisation"
    assert kw.get("regime_deploy") == 0.9


def test_the_heartbeat_publishes_each_finished_year_s_equity_PATH(monkeypatch):
    """The monitor draws a real equity chart, so it needs the shape, not the endpoints.

    Operator, 2026-09-03: "yo me imaginaba un grafico de bolsa en el que se ve dia a dia
    como va subiendo y bajando el equity". A dot per year cannot show that. So
    _select_risk_years asks per_year to RETAIN the equity curve and hands each finished
    year's path to publish(), thinned to ~90 points so a nine-year heartbeat stays a few
    kilobytes rather than a few hundred.

    Two things are pinned here because either one silently empties the chart: that
    keep_equity is actually requested (without it launch.per_year drops the curve and
    the page falls back to straight lines forever), and that the path is thinned rather
    than shipped whole.
    """
    from quantlab_system06 import autoloop, launch

    seen = {}

    def fake_per_year(bars, stamps, years, signals, brain_kwargs=None,
                      on_year=None, keep_equity=False):
        seen["keep_equity"] = keep_equity
        out = {}
        for i, y in enumerate(years):
            res = {"return_pct": 0.1, "max_drawdown": 0.05, "trades": 5,
                   "average_exposure": 0.06, "status": "complete", "stop_reason": None,
                   # what launch.run_window hands back: already capped near 500 points
                   "equity": [{"equity": 100000.0 + j} for j in range(500)]}
            out[y] = res
            if on_year:
                on_year(y, res, i, len(years))
        return out

    published = []
    monkeypatch.setattr(launch, "per_year", fake_per_year)
    autoloop._select_risk_years(
        {}, [], "sig", {"enter": 0.75}, [(2, 0.15, 0.08, 0.12)],
        publish=lambda ri, rt, risk, done, cur, curves=None: published.append(
            (dict(done), {k: list(v) for k, v in (curves or {}).items()})))

    assert seen.get("keep_equity") is True, \
        "per_year must be asked to keep the curve, or there is no path to publish"
    done, curves = published[-1]
    assert set(curves) == set(done), "every finished year must carry its path"
    for year, path in curves.items():
        assert 60 <= len(path) <= 120, f"{year}: path not thinned ({len(path)} points)"
        assert all(isinstance(v, float) for v in path), "path is equity values, not dicts"
