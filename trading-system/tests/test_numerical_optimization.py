"""The threshold optimiser: the held-out years must not be able to leak into the search.

Operator request (2026-09-04): stop moving one threshold at a time and let a numerical
optimiser search the combinations - "instead of moving the conviction threshold digit by
digit, a function that gets close to the winning formulas without trying them all". That
is TPE, and the implementation is tools/numerical_optimization.py.

The power is exactly why the guards are here. Eleven dimensions of continuous thresholds
against eight years of history is the most efficient overfitting machine this project has
ever built, and it has already been fooled four times by far weaker selection. What makes
the study mean anything is a split the search cannot cross:

    FIT       2018-2023   the objective is computed on these
    HOLDOUT   2024-2025   recorded on every trial, used for nothing

These tests pin that separation. They are cheap, they do not touch market data, and they
fail if anyone ever "just adds the holdout to the objective to squeeze more out of it".
"""

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "nopt", REPO / "research/system06/tools/numerical_optimization.py")
nopt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nopt)


def test_the_two_halves_never_overlap():
    assert not (set(nopt.FIT_YEARS) & set(nopt.HOLDOUT_YEARS))
    assert max(nopt.FIT_YEARS) < min(nopt.HOLDOUT_YEARS), (
        "the held-out half must be LATER in time - testing on years that precede the "
        "fitted ones is a different and much weaker claim")


def test_2025_is_held_out_even_though_it_is_the_year_we_want_to_fix():
    """The costly, deliberate choice. 2025 is the failing year and the temptation is to
    optimise on it directly; doing so is precisely how we would fool ourselves about
    having repaired it. 2022 is the other quiet year and stays in the fit half, so a
    threshold set that genuinely understands quiet markets is still findable."""
    assert 2025 in nopt.HOLDOUT_YEARS
    assert 2022 in nopt.FIT_YEARS


def test_the_sealed_year_is_nowhere_in_the_study():
    src = (REPO / "research/system06/tools/numerical_optimization.py").read_text(
        encoding="utf-8")
    assert 2026 not in nopt.FIT_YEARS and 2026 not in nopt.HOLDOUT_YEARS
    assert "launch.forward" not in src and "forward(" not in src, (
        "a search this powerful has no business near the sealed window, not even for "
        "a readout")


def test_the_objective_returns_the_fit_score_and_nothing_else():
    """The single line that could silently destroy the design is the objective's return
    value. Anything blended with the held-out score turns the holdout into a selection
    input while every label in the file still says otherwise."""
    import inspect

    src = inspect.getsource(nopt.main)
    body = src.split("def objective(trial):")[1].split("study.optimize")[0]
    returns = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("return ")]
    assert returns == ['return r["fit"]'], returns


def test_the_shipped_point_is_chosen_on_the_fit_score(monkeypatch):
    """Selecting the best HELD-OUT trial at the end would leak the holdout just as
    thoroughly as optimising on it, and would look perfectly reasonable in a report."""
    import inspect

    src = inspect.getsource(nopt.main)
    assert "best = max(comp, key=lambda t: t.value)" in src
    assert 'key=lambda t: t.user_attrs.get("holdout")' not in src


def test_realism_and_the_mandate_are_not_in_the_search_space():
    """min_notional and max_participation are statements about what the market can
    absorb, and max_drawdown is the mandate. Optimising them would be optimising our
    own honesty rather than the strategy. `enter` IS searched now, deliberately - v1
    pinned it on two single-lever refutations, which is exactly the kind of reasoning
    this study exists to distrust."""
    for forbidden in ("min_notional", "max_participation", "max_drawdown", "bar_seconds"):
        assert forbidden not in nopt.SPACE, f"{forbidden} must never be searched"
    assert "enter" in nopt.SPACE, "the operator asked for the conviction bar by name"


def test_the_search_covers_the_whole_decision_tree():
    """Operator, 2026-09-04: every module of the decision tree has parameters, and all
    of those combinations are what the search is for. So the space is checked against
    the brain's own signature rather than against a list somebody remembered to update -
    a lever that exists and is never searched is a lever nobody will think to add."""
    import inspect

    from quantlab_system06.strategy import OracleNetBrain

    NOT_SEARCHABLE = {
        "self", "signals", "trade_from", "model_tag", "bar_seconds", "_ignored",
        "meta_signals", "micro_signals", "tree_signals", "size_signals",  # file paths
        "max_drawdown",                                    # the mandate
        "min_notional", "max_participation",               # market realism, not knobs
        "activity_min",                                    # no on-chain channel on disk
    }
    levers = set(inspect.signature(OracleNetBrain.__init__).parameters) - NOT_SEARCHABLE
    missing = levers - set(nopt.SPACE)
    assert not missing, (
        f"the brain accepts these and the search never varies them: {sorted(missing)}")


def test_a_lever_with_no_overlay_file_is_dropped_rather_than_searched_blind():
    """meta, money-model, microstructure and the tree voter each need a channel file. If
    one is absent the brain ignores that lever in silence, and the search would spend
    trials on a knob connected to nothing and record the result as a refutation. That is
    the P46 `band_enter` failure with four more chances to happen."""
    for lever, filename in nopt.NEEDS_FILE.items():
        assert lever in nopt.SPACE
        assert filename.endswith(".npz")


def test_every_searched_threshold_is_a_lever_the_brain_actually_takes():
    """The failure this repeats: P46 was queued naming `band_enter`, a lever that does
    not exist, and the brain would have ignored it silently while the arm read as a
    measured refutation. A search space has the same exposure, eleven times over."""
    import inspect

    from quantlab_system06.strategy import OracleNetBrain

    class _T:
        def suggest_int(self, name, *a, **k): return 1
        def suggest_float(self, name, *a, **k): return 0.0
    accepted = set(inspect.signature(OracleNetBrain.__init__).parameters)
    unknown = set(nopt._space(_T(), {})) - accepted
    assert not unknown, f"the brain would silently ignore: {sorted(unknown)}"


def test_the_champion_point_lands_inside_every_range():
    """Trial 0 is the incumbent, enqueued verbatim so later numbers have something real
    to beat in the same units. If a range excluded the shipping value the anchor would
    be a different strategy, and every comparison in the report would be meaningless."""
    best = __import__("json").loads(
        (REPO / "research/system06/best.json").read_text(encoding="utf-8"))
    point = nopt._champion_point_full(best["risk"], best["band"], list(nopt.SPACE))
    assert set(point) == set(nopt.SPACE), "the anchor must fill exactly the searched space"
    for k, v in point.items():
        _kind, lo, hi, _log = nopt.SPACE[k]
        assert lo <= v <= hi, f"the shipping {k}={v} sits outside the search range {lo}..{hi}"

    # The finding this test happens to expose, pinned so it stays visible: of the
    # thirty-odd knobs the brain accepts, the shipping champion actually uses nine.
    live = {k for k, v in point.items() if v and k not in ("vol_floor", "consensus_k")}
    assert len(live) <= 12, (
        f"the incumbent uses {len(live)} levers: {sorted(live)} - the rest have sat at "
        f"zero since they were written, each switched off by an experiment that tested "
        f"it alone against a book tuned for its absence")


def test_rank_correlation_is_the_honest_shape():
    assert nopt._spearman([1, 2, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4, 5, 6, 7, 8]) == \
        pytest.approx(1.0)
    assert nopt._spearman([1, 2, 3, 4, 5, 6, 7, 8], [8, 7, 6, 5, 4, 3, 2, 1]) == \
        pytest.approx(-1.0)
    assert nopt._spearman([1, 2, 3], [1, 2, 3]) is None, (
        "too few trials to claim a correlation at all")


def test_a_book_that_never_trades_scores_worse_than_any_real_configuration():
    """The flaw that nearly wasted a night of compute, caught six trials in.

    The objective is worst_year + 0.10*CAGR. A configuration that trades badly scores
    NEGATIVE; one that never trades at all scores exactly 0.0. So without a penalty,
    paralysis outranks imperfection and TPE converges on a book that does nothing - and
    every trial still costs a full eight-year backtest to discover it. Measured, not
    imagined: the first six trials of the 33-lever space all returned 0.0% in all eight
    years, because random draws kept asking for more module agreement than this ensemble
    can produce.
    """
    assert nopt.INERT_SCORE < -1.0, (
        "must be unreachable by any real configuration - the worst plausible year is "
        "around -100%, so a penalty near zero would still leave paralysis competitive")


def test_consensus_cannot_ask_for_agreement_that_does_not_exist():
    """`backers` counts modules casting a DIRECTIONAL vote above the entry bar. In this
    ensemble that is the net, plus the tree voter when it is switched on. Asking three
    to agree asks for a third opinion nobody holds, and the book simply never enters -
    which reads as a refuted configuration rather than an impossible one."""
    _kind, lo, hi, _log = nopt.SPACE["consensus_k"]
    assert (lo, hi) == (1, 2)


def test_the_inert_flag_is_recorded_not_just_penalised():
    """A penalised trial and a genuinely terrible trial must stay distinguishable in the
    study, or the leaderboard's tail becomes unreadable and the search's own failure
    mode gets mistaken for a finding about trading."""
    import inspect

    src = inspect.getsource(nopt.Evaluator.score)
    assert '"inert": trades == 0' in src
    assert '"trades": trades' in src
    obj = inspect.getsource(nopt.main)
    assert '"inert"' in obj and '"all_positive"' in obj, (
        "both must be written as user attributes, or the report cannot tell an inert "
        "trial from a losing one after the fact")
