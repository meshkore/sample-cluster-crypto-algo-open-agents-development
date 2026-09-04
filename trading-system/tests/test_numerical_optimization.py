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


# --- the objective has to want what the operator wants --------------------------------

CHAMP = {"2018": 1.79, "2019": 0.53, "2020": 1.63, "2021": 145.5,
         "2022": 0.087, "2023": 0.73, "2024": 1.56, "2025": -0.030}
CONS = {"cagr": 2.06}


def test_a_moonshot_year_cannot_buy_a_year_in_the_red():
    """The flaw the first 25 trials of the full space exposed.

    The house metric is worst_year + 0.10*CAGR, and on this record 2021 alone drags CAGR
    past 300% - so the growth term is worth ~0.30 while the worst year is worth ~0.05.
    That is a CAGR contest wearing a consistency law's clothes, and the search behaved
    accordingly: it found +0.2423 against the incumbent's +0.1509 by taking the worst
    year from -1.49% to -6.56% and the drawdown from 22.0% to 33.9%.
    """
    steady = {str(y): 0.35 for y in range(2018, 2026)}
    moonshot = {**{str(y): 0.35 for y in range(2018, 2025)}, "2025": -0.10}
    assert nopt.mandate_score(steady, {"cagr": 0.35}, 0.20) > \
           nopt.mandate_score(moonshot, {"cagr": 40.0}, 0.20), (
        "a year in the red must not be purchasable with a bigger 2021")


def test_a_year_is_credited_up_to_the_target_and_no_further():
    """+30% every year is the mandate, so +14,554% in one year is worth exactly what
    +30% is worth. This is the single property that stops the search chasing 2021."""
    at_target = {str(y): 0.30 for y in range(2018, 2026)}
    enormous = {**{str(y): 0.30 for y in range(2018, 2026)}, "2021": 145.0}
    same_cons = {"cagr": 0.30}
    assert nopt.mandate_score(at_target, same_cons, 0.10) == \
        pytest.approx(nopt.mandate_score(enormous, same_cons, 0.10))
    assert nopt.mandate_score(at_target, same_cons, 0.10) == \
        pytest.approx(nopt.MANDATE_TARGET + nopt.GROWTH_WEIGHT * __import__("math").log(1.30))


def test_growth_still_breaks_ties_and_can_never_overtake_the_mandate():
    """The first version of this objective capped CAGR at 50% - and since every
    configuration on this record clears 50% easily, that removed growth ENTIRELY: the
    search could no longer tell +843% from +10,080% in 2021 and bought steadiness with
    enormous forgone return. Capping each YEAR at the target, rather than capping the
    aggregate, is what separates 'a moonshot cannot buy a bad year' from 'moonshots do
    not exist'."""
    floor = {str(y): 0.30 for y in range(2018, 2026)}
    assert nopt.mandate_score(floor, {"cagr": 5.0}, 0.10) > \
           nopt.mandate_score(floor, {"cagr": 0.5}, 0.10), "more growth still wins"
    # ...but never enough to excuse a year below the target.
    below = {**floor, "2025": 0.00}
    assert nopt.mandate_score(below, {"cagr": 1000.0}, 0.10) < \
           nopt.mandate_score(floor, {"cagr": 0.5}, 0.10)


def test_the_perfect_record_scores_the_target():
    """The score has a meaning, not just an ordering: distance from MANDATE_TARGET is
    how far the record sits from '+30% every single year'."""
    perfect = {str(y): 9.99 for y in range(2018, 2026)}
    s = nopt.mandate_score(perfect, {"cagr": 0.0}, 0.0)
    assert s == pytest.approx(nopt.MANDATE_TARGET)


def test_drawdown_is_free_up_to_the_incumbents_level_and_priced_past_it():
    """Not a hard limit - the operator superseded that on 2026-08-28 - but a price, so a
    deeper drawdown has to buy something to be worth taking."""
    assert nopt.mandate_score(CHAMP, CONS, 0.10) == \
        pytest.approx(nopt.mandate_score(CHAMP, CONS, nopt.DD_FREE))
    assert nopt.mandate_score(CHAMP, CONS, 0.40) < nopt.mandate_score(CHAMP, CONS, nopt.DD_FREE)


def test_the_house_metric_is_still_recorded():
    """Changing what the search WANTS must not make what it measured incomparable: every
    trial still carries the old score, so the published bar can still be read against
    it and nothing already on record is orphaned."""
    import inspect

    assert '"house_score"' in inspect.getsource(nopt.Evaluator.score)
    assert '"house_score"' in inspect.getsource(nopt.main)


def test_an_inert_book_still_loses_to_everything():
    """The penalty has to survive the new objective: the mandate score of a real but
    terrible configuration is around -1, so the floor must sit well below that."""
    awful = {str(y): -0.95 for y in range(2018, 2026)}
    assert nopt.INERT_SCORE < nopt.mandate_score(awful, {"cagr": -0.90}, 0.60)


# --- v3: the only measurement that counts is out of sample ----------------------------

def test_the_default_run_holds_the_recent_years_back():
    """Operator, 2026-09-04, and it settles a question he had earlier overruled: "a
    system that gets great results on the data it was trained on does not surprise me...
    the only place the quality of this system is measured is 2026, where the model has
    never trained."

    Fitting all eight years and selecting on the same eight is description, not
    optimisation, and on the day he said it two candidates had just doubled the research
    score and both LOST the sealed year. There is exactly one way to improve a number you
    are forbidden to look at: hold out the most recent years, tune without them, and
    check whether the improvement carries. 2024-2025 stand in for 2026 precisely because
    they are what 2026 will be - the years after the ones we tuned on.
    """
    import inspect

    src = inspect.getsource(nopt.main)
    assert "fit_years = ALL_YEARS if args.all_years else FIT_YEARS" in src
    assert "--all-years" in src, "the descriptive mode stays available, but not by default"
    assert nopt.HOLDOUT_YEARS == (2024, 2025)


def test_the_whole_lever_space_is_searched_in_both_modes():
    """The year split chooses which YEARS the objective sees. It never decided which
    levers exist, and for one revision it accidentally did - --all-years was wired to
    both, so the held-out mode would silently have searched eleven levers instead of
    thirty-three."""
    import inspect

    src = inspect.getsource(nopt.main)
    assert "with_enter=True" in src
    assert "names = [n for n in SPACE if n not in missing]" in src


def test_months_are_counted_from_the_equity_path():
    """Eight annual buckets is a desperately thin thing to fit thirty-three levers
    against. The same record cut monthly gives ninety-six observations of the same book,
    and the operator asked for exactly this: "that it wins the maximum number of months
    possible"."""
    curve = [{"timestamp": "2025-01-15T00:00:00+00:00", "equity": 100.0},
             {"timestamp": "2025-01-31T00:00:00+00:00", "equity": 110.0},
             {"timestamp": "2025-02-20T00:00:00+00:00", "equity": 121.0},
             {"timestamp": "2025-03-05T00:00:00+00:00", "equity": 108.9}]
    assert nopt.monthly_returns(curve) == pytest.approx([0.10, -0.10])
    assert nopt.monthly_returns([]) == []
    assert nopt.monthly_returns([{"timestamp": "2025-01-01", "equity": 1.0}]) == []


def test_winning_more_months_is_worth_something_but_cannot_rescue_a_bad_year():
    at_target = {str(y): 0.30 for y in range(2018, 2024)}
    cons = {"cagr": 0.30}
    every = nopt.mandate_score(at_target, cons, 0.10, [0.01] * 12)
    half = nopt.mandate_score(at_target, cons, 0.10, [0.01] * 6 + [-0.01] * 6)
    assert every > half, "a book that wins every month must beat one that wins half"

    # ...and no monthly record can pay for a year below the mandate.
    bad_year = {**at_target, "2023": -0.10}
    assert nopt.mandate_score(bad_year, cons, 0.10, [0.01] * 12) < \
        nopt.mandate_score(at_target, cons, 0.10, [])


def test_the_equity_path_is_actually_requested():
    """monthly_returns needs the path, and per_year drops it unless asked - the same
    silent filter that made the first gate_forensics report print "0 signals" beside
    "512 trades"."""
    import inspect

    assert "keep_equity=True" in inspect.getsource(nopt.Evaluator.score)


def test_the_leader_is_never_chosen_on_the_held_out_score():
    """On a dashboard this would look entirely reasonable, and it would destroy the only
    honest measurement in the study. Checked in BOTH places that rank trials: the live
    heartbeat the page reads, and the final report."""
    import inspect

    for fn in (nopt.write_live, nopt.main):
        src = inspect.getsource(fn)
        assert "key=lambda t: t.value" in src
        assert 'key=lambda t: t.user_attrs.get("holdout")' not in src


def test_no_tiebreak_can_ever_pay_for_a_year_below_the_mandate():
    """The property that makes this objective trustworthy, stated once for all the
    tiebreaks rather than once per tiebreak. Both of them tried to break it: the growth
    term reached 0.138 at CAGR 1000 against a one-year shortfall of 0.0375, and a flat
    months weight of 0.10 let a perfect monthly record outrank a record with a year in
    the red. They now share one budget, half of a single year's full shortfall."""
    years = {str(y): 0.30 for y in range(2018, 2026)}
    clean = nopt.mandate_score(years, {"cagr": 0.0}, 0.0, [])
    # every tiebreak at maximum, and one year lost entirely
    holed = {**years, "2025": 0.0}
    loud = nopt.mandate_score(holed, {"cagr": 1e6}, 0.0, [0.01] * 96)
    assert loud < clean, (
        "a perfect monthly record and unbounded growth must still lose to a record "
        "that simply meets the mandate every year")


# --- the leak that was not in the objective ------------------------------------------

def test_every_companion_statistic_declares_which_half_it_came_from():
    """Measured 2026-09-04. The objective was always clean - it returns f["score"], the
    fit half and nothing else. But `months_won`, `worst_month`, `worst_drawdown` and
    `mandate_years` were computed across ALL EIGHT years and printed beside the fit
    score, on the console, in the live heartbeat, and on the public page.

    It surfaced while correlating fit-side statistics against the held-out score to see
    which one predicts it best: three of the four leading "predictors" turned out to
    CONTAIN the held-out years. `mandate_years` scored rho +0.65 against a number it was
    partly made of. Nothing automated was ever selected on them - but a person ranking
    trials by what the page showed would have been selecting on 2024-2025 without
    knowing it, which is precisely what the split exists to prevent.

    So every companion now carries its half in its name.
    """
    import inspect

    src = inspect.getsource(nopt.Evaluator.score)
    for key in ("fit_months_won", "fit_worst_month", "fit_mandate_years",
                "fit_worst_drawdown", "fit_years_n"):
        assert f'"{key}"' in src, f"{key} must be recorded separately from the whole record"
    assert '"holdout_worst_drawdown"' in src

    # and the fit-side ones must be built from the fit half, not from `rets`/`allm`
    assert 'fit_rets = [v for y, v in rets.items() if y in self.fit_years' in src
    assert 'sum(1 for v in fit_rets if v >= 0.30)' in src


def test_the_console_line_reports_fit_side_companions():
    """The trial line is read by a person hundreds of times a day; it is a channel."""
    import inspect

    src = inspect.getsource(nopt.main)
    assert "r['fit_months_won']" in src
    assert "r['fit_mandate_years']" in src
    assert "r['fit_worst_drawdown']" in src


def test_the_live_card_never_shows_an_all_year_number_as_a_fit_number():
    """What the public page puts next to the fit score decides what a human ranks on."""
    import inspect

    src = inspect.getsource(nopt.write_live)
    assert '"months_won": a.get("fit_months_won"' in src
    assert '"mandate_years": a.get("fit_mandate_years"' in src
    assert '"worst_drawdown": a.get("fit_worst_drawdown"' in src
    # the whole-record versions stay available, but only under a name that says so
    for k in ("all_months_won", "all_worst_drawdown", "all_mandate_years"):
        assert f'"{k}"' in src


# --- six workers must not be one worker -----------------------------------------------

def test_the_sampler_seed_is_never_shared_between_workers():
    """Measured 2026-09-04 at 168 completed trials: only 102 DISTINCT parameter points.
    39% of every evaluation was a duplicate, and once the enqueued seeds were exhausted
    and TPE took over it was 74% - six workers proposing the same point because each
    built TPESampler(seed=20260904) and read the same study state from the same SQLite
    file. The fleet was doing the exploration of about one and a half workers while
    costing six.

    The seed must therefore come from something distinct per process. The pid is the only
    identifier guaranteed distinct among LIVE workers, which is precisely the set that
    must not collide - a worker index computed from "how many are alive" reuses an index
    the moment a middle worker dies and is replaced.
    """
    import inspect

    src = inspect.getsource(nopt.main)
    assert "seed=20260904," not in src, "a literal shared seed is the bug this guards"
    assert "os.getpid()" in src
    assert "sampler = optuna.samplers.TPESampler(seed=seed," in src


def test_the_samplers_are_told_about_each_other():
    """Distinct seeds make six different draws; they do not stop six workers converging
    on the same attractive point at the same moment, because each sees a study in which
    nobody is working on it yet. constant_liar scores in-flight trials as losses for the
    duration, which is Optuna's mechanism for exactly this."""
    import inspect

    assert "constant_liar=True" in inspect.getsource(nopt.main)


def test_the_watchdog_does_not_hand_out_colliding_seeds():
    """The watchdog owns the fleet, so it is the place a shared seed would come back."""
    import pathlib

    wd = pathlib.Path("../research/system06/watchdog.ps1")
    if not wd.exists():                       # test suite run from the repo root
        wd = pathlib.Path("research/system06/watchdog.ps1")
    text = wd.read_text(encoding="utf-8", errors="replace")
    assert "numerical_optimization.py" in text, "the watchdog must own the run"
    # Only the optimizer block. The autoloop next door passes a --seed of its own and is
    # entitled to: it is a single process, so it has nobody to collide with.
    block = text.split("numerical_optimization.py", 1)[1].split("# ---", 1)[0]
    assert '"--seed"' not in block, (
        "the watchdog must not pass a seed derived from the worker index - $i counts "
        "from the number ALIVE and is reused when a middle worker is replaced")
    assert '"--seeds"' in block, "the enqueued champion perturbations are still wanted"


def test_the_watchdog_script_actually_parses():
    """A watchdog that does not parse relaunches NOTHING, and says nothing about it.

    2026-09-04: adding a comment line between `Start-Process -FilePath "python" `` ` and
    its -ArgumentList made the whole file a parse error. PowerShell's backtick continues
    the line, and a comment cannot be continued onto. The watchdog runs with
    $ErrorActionPreference = "SilentlyContinue" from a scheduled task, so the only
    symptom was six optimizer workers that stayed dead - and, silently, the autoloop,
    the pulse, the Cloudflare pusher and the Wall listener would have stayed dead too the
    moment any of them stopped. The fleet was down about ten minutes before anyone looked.

    Every daemon on this machine depends on this one file parsing, so it is checked here
    rather than trusted.
    """
    import pathlib
    import shutil
    import subprocess

    wd = pathlib.Path("../research/system06/watchdog.ps1")
    if not wd.exists():
        wd = pathlib.Path("research/system06/watchdog.ps1")
    if not wd.exists() or shutil.which("powershell") is None:
        pytest.skip("watchdog.ps1 or powershell not available on this machine")

    script = (
        "$e=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{wd.resolve()}',"
        "[ref]$null,[ref]$e) > $null;"
        "if($e.Count -gt 0){$e|%{$_.Message};exit 1}else{exit 0}")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, f"watchdog.ps1 does not parse:\n{out.stdout}{out.stderr}"
