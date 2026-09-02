"""The autonomous experiment runner: the paired-test method, on a permanent loop.

The training loop (`quantlab_system06.autoloop`) searches genomes forever. This daemon
does the OTHER half of the work that was previously done by hand: it takes the queued
experiments in `rnd/program.jsonl`, runs each one as a PAIRED test on the champion
genome, and records an honest result. Between experiments it writes a mechanical review
of where the research stands, so a stall announces itself instead of being noticed weeks
later.

Every methodological guard this system paid to learn is built in rather than remembered:

  * PAIRED: one net is trained per seed and then scored once per arm, so seed variance
    cancels exactly. An unpaired headline of +0.1183 once collapsed to +0.0452 when
    measured this way.
  * POSITIVE CONTROL: any arm whose label contains [CONTROL] is checked against its known
    value; if the harness cannot reproduce it, the whole run is marked untrustworthy.
  * INERTNESS: an arm whose per-year returns are identical to baseline did NOT ENGAGE -
    a missing channel or an unmet precondition - and is reported that way, never as
    "no effect".
  * DRAWDOWN FLAGGED, FIXED IN ADVANCE: an arm reaching DD_FLAG is marked DEEP and its
    drawdown reported alongside its score. It is NOT discarded - the operator removed
    the hard cap on 2026-08-28, asking for the minimum drawdown to be sought rather
    than bounded. The line is still fixed before the scores are seen, because a line
    that moves afterwards reports nothing.
  * PER-YEAR STATUS AND DRAWDOWN are always recorded, so a mandate breach is read off
    rather than inferred from a badge.
  * JUDGE ON THE YEARS THAT MATTER: an experiment names `judge_on`, because the headline
    CAGR is dominated by 2021 while the binding constraint is the worst year.

Nothing here touches the live trading path: it trains, scores and writes notes. 2026 is
never scored - `launch.per_year` is called on RESEARCH_YEARS only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
RND = ROOT / "rnd"
PROGRAM = RND / "program.jsonl"
RESULTS = RND / "program_results.jsonl"
REVIEW = RND / "review.jsonl"
STOP = ROOT / "STOP"
HEARTBEAT = ROOT / "autotest_live.json"

# OPERATOR DECISION, 2026-08-28: drawdown is no longer a hard cap. His instruction was to
# seek the MINIMUM drawdown but set no ceiling - a genuinely winning strategy that needed
# 30% once is acceptable; maximise results first and reduce risk afterwards. So an arm that
# runs deep is FLAGGED and reported, never discarded, and the threshold below is a reporting
# line rather than a rejection. It is still fixed in advance, because a line that moves once
# the scores are visible reports nothing.
#
# The measured warning that travels with this, recorded rather than argued: configurations
# surviving only by sailing to a 24-25% drawdown were measured HERE to generalise worse out
# of sample, which is why fast_portfolio deliberately selects against a tighter 20% limit.
# Removing the cap is the operator's call and is executed; the effect will be watched for.
DD_FLAG = 0.24
DD_REJECT = None          # no hard rejection; kept as a name so older rows read consistently
IDLE_SLEEP = 900          # when the queue is empty
REVIEW_EVERY = 6 * 3600   # a mechanical review at least this often
# The positive control's expected delta depends on the SHIPPING CONFIG the arms are
# scored against, because a control arm measures a delta FROM that config. When the
# adopted config changed on 2026-08-29 to include money_model 0.5, the old money-0.5
# control became a no-op against itself: P20 measured -0.0034 where the stale table
# still expected +0.0228, and only the tolerance being wide enough to swallow it kept
# the run from reading as untrustworthy. A control that cannot fail is not a control.
# So: the money arm is now expected to be INERT (it is already in the shipping config),
# and the live control is a lever the shipping config does NOT contain - a deployment
# ceiling step, whose effect P11/P14 measured repeatedly on this instrument.
CONTROL_EXPECT = {
    "money 0.5 [CONTROL]": 0.0,      # inert since the adoption - it IS the shipping config
    "money 0.5": 0.0,
    "ceiling 0.70 [CONTROL]": 0.0407,  # P11: c0.50 -> c0.70 step measured on this path
}
CONTROL_TOL = 0.030       # the control may wander this far before the run is suspect


# The source this PROCESS is executing. Python binds imports at process start, so a
# file fixed on disk changes nothing until a restart - a trap this lab has paid for
# twice (P05 lost a whole experiment; P21 crashed twice on an already-fixed bug).
# Remembering to restart has failed as a control, so the runner publishes what it is
# actually running and staleness becomes visible instead of silent.
CODE_FINGERPRINT = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _read_program() -> list[dict]:
    if not PROGRAM.is_file():
        return []
    out = []
    for line in PROGRAM.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _write_program(rows: list[dict]) -> None:
    PROGRAM.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows) + "\n",
        encoding="utf-8")


def _set_status(exp_id: str, status: str, **fields) -> None:
    rows = _read_program()
    for r in rows:
        if r.get("id") == exp_id:
            r["status"] = status
            r.update(fields)
    _write_program(rows)


def unknown_levers(kwargs: dict) -> list[str]:
    """Lever names the brain would silently SWALLOW rather than act on.

    `OracleNetBrain.__init__` ends in `**_ignored`, so an unrecognised keyword produces
    no error and no effect - the arm simply equals baseline and reads INERT. Two ways
    that happens, and the second cost a full experiment before this guard existed:

      * a typo in a lever name;
      * a lever built AFTER this daemon started. Python imports a module once per
        process, so a long-running runner holds the code as it was at launch. P05 tested
        `trend_soft` three ways and all three came back INERT for exactly that reason -
        the lever existed on disk and did not exist in this process. Read carelessly,
        that would have refuted the operator's idea on the strength of a stale import.

    Checked against the LIVE signature, so it reports what THIS process would really do.
    """
    import inspect

    from quantlab_system06.strategy import OracleNetBrain

    accepted = set(inspect.signature(OracleNetBrain.__init__).parameters)
    return sorted(k for k in kwargs if k not in accepted)


def progress_beat(ev: dict, experiment: str, seed: int, last: list, every: float = 20.0) -> bool:
    """Heartbeat handler for `train`'s progress callback. Returns whether it wrote.

    ONE POSITIONAL DICT. `train._emit` calls `on_progress(ev)` and wraps it in a bare
    `except: pass`, so a callback with the wrong signature fails SILENTLY on every call -
    which is exactly what happened here: the first version was declared `_progress(**ev)`,
    raised TypeError each time, and the heartbeat sat frozen through a 25-minute training
    run while looking like a hang. Telemetry that cannot break training also cannot report
    that it is broken, so the shape is pinned by a test instead.
    """
    now_t = time.time()
    if now_t - last[0] < every:
        return False
    last[0] = now_t
    ep, eps = ev.get("epoch"), ev.get("epochs")
    stage = ev.get("stage") or "training"
    _beat("running",
          f"{experiment} seed {seed}: {stage}" + (f" epoch {ep}/{eps}" if ep else ""),
          experiment=experiment)
    return True


def _beat(state: str, detail: str = "", **extra) -> None:
    payload = {"state": state, "detail": detail, "heartbeat": _now(),
               "code": CODE_FINGERPRINT, **extra}
    try:
        HEARTBEAT.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# The mechanical review: does the research still look like it is going somewhere?

def review() -> dict:
    """A state-of-the-search assessment that needs no judgement, only arithmetic."""
    from quantlab_system06 import autoloop

    rows = []
    ledger = ROOT / "ledger.jsonl"
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    pinned = [r for r in rows
              if isinstance(r.get("config"), dict)
              and all(k in r["config"] for k in autoloop.BAND_KEYS)
              and isinstance(r.get("score"), float)]
    scores = [r["score"] for r in pinned]
    bar = autoloop._read_best_score()
    prior = autoloop._inflation_prior()
    trigger = (bar + prior) if bar is not None else None

    out = {
        "at": _now(),
        "iterations_total": len(rows),
        "iterations_current_regime": len(pinned),
        "bar": bar,
        "inflation_prior": round(prior, 4),
        "trigger_threshold": round(trigger, 4) if trigger is not None else None,
        "best_recent": max(scores) if scores else None,
        "mean_recent": round(statistics.mean(scores), 4) if scores else None,
        "stdev_recent": round(statistics.stdev(scores), 4) if len(scores) > 1 else None,
    }
    if scores and trigger is not None and len(scores) > 1 and out["stdev_recent"]:
        gap = (trigger - statistics.mean(scores)) / out["stdev_recent"]
        out["sigmas_to_trigger"] = round(gap, 1)
        # A search that must travel many sigmas is not going to arrive by drawing again.
        out["verdict"] = ("the search cannot reach the bar by sampling; improvement must come "
                          "from a better idea, not more draws" if gap > 3 else
                          "the bar is within reach of the current distribution")
    prog = _read_program()
    out["program"] = {s: sum(1 for r in prog if r.get("status") == s)
                      for s in {r.get("status") for r in prog}}
    _append(REVIEW, out)
    return out


# --------------------------------------------------------------------------- #
# One experiment: train once per seed, score every arm on that net.

def run_train_ab(exp: dict) -> dict:
    """A paired A/B over TRAINING variants (kind: "train_ab").

    The standard experiment shape trains ONE net per seed and scores many risk arms on
    it - which cannot express a change to training itself (a feature flag, a label
    change). Here `exp["train_variants"]` maps label -> extra train() kwargs; per seed,
    each variant trains its own net on the SAME seed and is scored on the champion's
    shipping risk config, so the pairing is across variants within a seed and seed
    variance cancels exactly as it does for risk arms. The first variant is the
    baseline. Costs one full train per variant per seed - the price of asking a
    training question honestly.
    """
    from quantlab_system06 import autoloop, infer, launch, moneymodel, train, universe
    from quantlab_system06 import meta as metalabel
    from quantlab_system06.dataset import Dataset

    # The cheap fail-fast guard runs BEFORE anything is loaded: a variant naming a
    # kwarg train() cannot see is the stale-import trap in a new coat, and it must
    # refuse loudly before a single bar is read, let alone a GPU hour spent.
    variants = exp["train_variants"]
    base_label = next(iter(variants))
    seeds = [int(s) for s in exp.get("seeds") or [77101, 77102]]
    import inspect as _inspect

    accepted = set(_inspect.signature(train.train).parameters)
    bad = {lbl: sorted(k for k in kw if k not in accepted)
           for lbl, kw in variants.items() if any(k not in accepted for k in kw)}
    if bad:
        raise RuntimeError(f"train() does not accept: {bad} - stale imports? restart the runner")

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, bd, risk = dict(best["config"]), best["band"], dict(best["risk"])
    enter, exit_, hold = float(bd["enter"]), float(bd["exit_"]), int(bd["min_hold"])

    symbols = universe.load()
    if not isinstance(symbols, list) or len(symbols) < 5:
        raise RuntimeError(f"degenerate universe: {symbols!r}")
    data_root = "trading-system/backtester/data"
    dataset = Dataset(data_root=data_root, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})
    if not rstamps:
        raise RuntimeError("no research bars")

    per_seed: dict[str, dict] = {}
    failed: dict[str, dict[str, str]] = {}
    for seed in seeds:
        for label, extra in variants.items():
            scratch = ROOT / f"_auto_{exp['id']}_{seed}_{abs(hash(label)) % 9973}"
            shutil.rmtree(scratch, ignore_errors=True)
            scratch.mkdir(parents=True, exist_ok=True)
            try:
                _beat("running", f"{exp['id']} seed {seed}: training [{label}]",
                      experiment=exp["id"])
                _last = [0.0]

                def _progress(ev, _e=exp["id"], _s=seed, _l=_last):
                    progress_beat(ev, _e, _s, _l)

                # The variant OVERRIDES the champion recipe rather than being passed
                # beside it. P21 died on exactly this: it varied `embargo`, which the
                # recipe already sets, and Python refused the duplicate keyword after
                # the data had loaded. Any recipe knob is a legitimate thing to A/B,
                # so the merge - not the call site - is where the variant belongs.
                call = dict(data_root=data_root, symbols=symbols,
                            threshold=cfg["threshold"], window=cfg["window"],
                            epochs=cfg["epochs"], lr=cfg["lr"], dropout=cfg["dropout"],
                            out_dir=str(scratch), seed=seed,
                            uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                            ensemble=int(cfg.get("ensemble", 1)),
                            embargo=int(cfg.get("embargo", 0)),
                            enter=enter, exit_=exit_, min_hold=hold,
                            on_progress=_progress)
                call.update(extra)
                train.train(**call)
                sig = str(scratch / "signals.npz")
                infer.export(data_root=data_root, symbols=symbols, model_dir=str(scratch),
                             out_path=sig, trend_span=int(cfg.get("trend_span", autoloop.TREND_SPAN)))
                band = {"enter": enter, "exit_": exit_, "min_hold": hold}
                cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
                verdicts, _doc = metalabel.build_verdicts(cand)
                metalabel.write_meta(verdicts, str(scratch / "meta.npz"))
                band["meta_signals"] = str(scratch / "meta.npz")
                kw = dict(risk)
                if float(kw.get("money_model") or 0) > 0:
                    overlay = moneymodel.build_sizing(
                        sig, data_root, enter=enter, exit_=exit_, min_hold=hold,
                        stop_loss=float(kw.get("stop_loss") or 0.0),
                        trail_stop=float(kw.get("trail_stop") or 0.0), research=rbars)
                    moneymodel.write_sizing(overlay, str(scratch / "moneymodel.npz"))
                    kw["size_signals"] = str(scratch / "moneymodel.npz")
                py = launch.per_year(rbars, rstamps, autoloop.RESEARCH_YEARS, sig,
                                     brain_kwargs={**band, **kw})
                cons = autoloop._consistency(py)
                per_seed.setdefault(label, {})[seed] = {
                    "score": cons["score"], "min_year": cons["min_year"], "cagr": cons["cagr"],
                    "all_positive": cons["all_positive"],
                    "annual": {int(y): round(float(py[y]["return_pct"]), 4) for y in sorted(py)
                               if (py[y] or {}).get("return_pct") is not None},
                    "stopped_years": [int(y) for y in sorted(py)
                                      if (py[y] or {}).get("status") == "stopped"],
                    "worst_drawdown": max((float((py[y] or {}).get("max_drawdown") or 0)
                                           for y in py), default=0.0),
                    "avg_exposure": round(statistics.mean(
                        [float((py[y] or {}).get("average_exposure") or 0.0) for y in py]), 4)
                    if py else 0.0,
                }
            except Exception as exc:  # noqa: BLE001 -- see the note below
                # One arm must not be able to destroy the arms that already ran.
                # P37 is the case that forced this: twelve trainings across three
                # seeds, and the widest variant sits close to the card's 8GB, so a
                # CUDA OOM in arm 4 of 12 would have thrown away the completed
                # baseline and 192-channel measurements with it. The failure is
                # RECORDED, never swallowed: the label keeps a `failed_seeds` entry,
                # the result carries `failed_arms`, and a partial arm reports the
                # seeds it actually has - a hole that is visible is a hole that can
                # be re-run, while a hole that is silent is a lie about coverage.
                failed.setdefault(label, {})[str(seed)] = f"{type(exc).__name__}: {exc}"[:400]
                _beat("running", f"{exp['id']} seed {seed}: arm [{label}] FAILED "
                                 f"({type(exc).__name__}) - continuing",
                      experiment=exp["id"])
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
                # Consecutive trainings share one process, so the caching allocator
                # carries the previous net's blocks into the next one's peak. Give
                # the wider variant the whole card rather than the remainder.
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:  # noqa: BLE001 -- housekeeping never breaks a run
                    pass

    summary = {}
    for label in variants:
        got = per_seed.get(label, {})
        if not got:
            continue
        deltas = [got[s]["score"] - per_seed[base_label][s]["score"]
                  for s in got if s in per_seed.get(base_label, {})]
        dds = [got[s]["worst_drawdown"] for s in got]
        stops = [y for s in got for y in got[s]["stopped_years"]]
        judge = exp.get("judge_on") or []
        focus = {}
        for y in judge:
            vals = [got[s]["annual"].get(int(y)) for s in got
                    if got[s]["annual"].get(int(y)) is not None]
            bvals = [per_seed[base_label][s]["annual"].get(int(y)) for s in got
                     if per_seed[base_label][s]["annual"].get(int(y)) is not None]
            if vals and bvals and len(vals) == len(bvals):
                focus[str(y)] = round(statistics.mean(vals) - statistics.mean(bvals), 4)
        summary[label] = {
            "paired_delta": round(statistics.median(deltas), 4) if deltas else None,
            "avg_exposure": round(statistics.mean(
                [got[s]["avg_exposure"] for s in got]), 4),
            "worst_drawdown": round(max(dds), 4),
            "mandate_breaches": sorted(set(stops)),
            "inert": all(got[s]["annual"] == per_seed[base_label][s]["annual"]
                         for s in got) and label != base_label,
            "deep_drawdown": (max(dds) >= DD_FLAG) or bool(stops),
            "judge_on_delta": focus,
            "scores": {str(s): round(got[s]["score"], 4) for s in got},
            "seeds_scored": len(got),
            "failed_seeds": failed.get(label, {}),
        }
    for label, errs in failed.items():
        # An arm that failed on EVERY seed has no summary row at all, so it would
        # simply be absent from the table - which reads as "not tried" rather than
        # "tried and died". Give it a row that says so.
        if label not in summary:
            summary[label] = {"paired_delta": None, "avg_exposure": 0.0,
                              "worst_drawdown": 0.0, "mandate_breaches": [],
                              "inert": False, "deep_drawdown": False,
                              "judge_on_delta": {}, "scores": {},
                              "seeds_scored": 0, "failed_seeds": errs}
    return {"id": exp["id"], "agenda": exp.get("agenda"), "at": _now(),
            "seeds": seeds, "judge_on": exp.get("judge_on"),
            "control": None, "summary": summary,
            "failed_arms": failed,
            "trustworthy": None,
            "note": "train_ab: no [CONTROL] arm exists at this shape - the baseline "
                    "variant plays that role, and its per-seed scores should match the "
                    "champion-genome plain scores already on record (~+0.072-0.074 on "
                    "seeds 77101/77102), which is the reconciliation to check."}


def run_experiment(exp: dict) -> dict:
    if exp.get("kind") == "train_ab" or exp.get("train_variants"):
        return run_train_ab(exp)
    from quantlab_system06 import autoloop, infer, launch, moneymodel, train, universe
    from quantlab_system06 import meta as metalabel
    from quantlab_system06.dataset import Dataset

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, bd, risk = dict(best["config"]), best["band"], dict(best["risk"])
    enter, exit_, hold = float(bd["enter"]), float(bd["exit_"]), int(bd["min_hold"])

    symbols = universe.load()
    if not isinstance(symbols, list) or len(symbols) < 5:
        raise RuntimeError(f"degenerate universe: {symbols!r}")
    data_root = "trading-system/backtester/data"
    dataset = Dataset(data_root=data_root, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})
    if not rstamps:
        raise RuntimeError("no research bars")

    arms = exp["arms"]
    base_label = next(iter(arms))
    seeds = [int(s) for s in exp.get("seeds") or [77101, 77102]]
    per_seed: dict[str, dict] = {}

    # Refuse to spend GPU hours proving that a lever this process cannot see does
    # nothing. Checked BEFORE training, against the live signature.
    bad = {label: unknown_levers(kw) for label, kw in arms.items() if unknown_levers(kw)}
    if bad:
        raise RuntimeError(
            "levers not accepted by the brain IN THIS PROCESS: "
            + "; ".join(f"{lbl} -> {ks}" for lbl, ks in bad.items())
            + ". Either the name is wrong, or the lever was built after this daemon "
              "started and the runner is holding stale imports - restart it.")

    for seed in seeds:
        scratch = ROOT / f"_auto_{exp['id']}_{seed}"
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True, exist_ok=True)
        try:
            _beat("running", f"{exp['id']} seed {seed}: training", experiment=exp["id"])

            # Beat DURING training too. A training run takes tens of minutes, and a
            # heartbeat that freezes for that long is indistinguishable from a hang -
            # which defeats the purpose of having one on a daemon meant to run unattended
            # for days. Throttled so it costs nothing.
            _last = [0.0]

            def _progress(ev, _exp=exp["id"], _seed=seed, _last=_last):
                progress_beat(ev, _exp, _seed, _last)

            train.train(data_root=data_root, symbols=symbols, threshold=cfg["threshold"],
                        window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"],
                        dropout=cfg["dropout"], out_dir=str(scratch), seed=seed,
                        uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                        ensemble=int(cfg.get("ensemble", 1)),
                        embargo=int(cfg.get("embargo", 0)),
                        enter=enter, exit_=exit_, min_hold=hold,
                        on_progress=_progress)
            sig = str(scratch / "signals.npz")
            infer.export(data_root=data_root, symbols=symbols, model_dir=str(scratch),
                         out_path=sig, trend_span=int(cfg.get("trend_span", autoloop.TREND_SPAN)))
            band = {"enter": enter, "exit_": exit_, "min_hold": hold}
            cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
            verdicts, _doc = metalabel.build_verdicts(cand)
            metalabel.write_meta(verdicts, str(scratch / "meta.npz"))
            band["meta_signals"] = str(scratch / "meta.npz")
            overlay = moneymodel.build_sizing(
                sig, data_root, enter=enter, exit_=exit_, min_hold=hold,
                stop_loss=float(risk.get("stop_loss") or 0.0),
                trail_stop=float(risk.get("trail_stop") or 0.0), research=rbars)
            moneymodel.write_sizing(overlay, str(scratch / "moneymodel.npz"))

            base_annual = None
            for label, extra in arms.items():
                kw = dict(extra)
                if "money_model" in kw:
                    kw["size_signals"] = str(scratch / "moneymodel.npz")
                _beat("running", f"{exp['id']} seed {seed}: {label}", experiment=exp["id"])
                py = launch.per_year(rbars, rstamps, autoloop.RESEARCH_YEARS, sig,
                                     brain_kwargs={**band, **risk, **kw})
                cons = autoloop._consistency(py)
                annual = {int(y): round(float(py[y]["return_pct"]), 4) for y in sorted(py)
                          if (py[y] or {}).get("return_pct") is not None}
                rec = {
                    "score": cons["score"], "min_year": cons["min_year"], "cagr": cons["cagr"],
                    "all_positive": cons["all_positive"], "annual": annual,
                    "stopped_years": [int(y) for y in sorted(py)
                                      if (py[y] or {}).get("status") == "stopped"],
                    "worst_drawdown": max((float((py[y] or {}).get("max_drawdown") or 0)
                                           for y in py), default=0.0),
                    # How much capital was actually AT RISK. Recorded because the single
                    # most consequential finding of this project was invisible without it:
                    # the champion returns roughly 500% on the money it risks and risks
                    # under 1% of the account, so a return figure alone says almost
                    # nothing about whether a configuration is good or merely absent.
                    "avg_exposure": round(statistics.mean(
                        [float((py[y] or {}).get("average_exposure") or 0.0) for y in py]), 4)
                    if py else 0.0,
                    "exposure_by_year": {int(y): round(float((py[y] or {}).get("average_exposure") or 0.0), 4)
                                         for y in sorted(py)},
                }
                if base_annual is None:
                    base_annual = annual
                    rec["inert"] = False
                else:
                    rec["inert"] = (annual == base_annual)
                per_seed.setdefault(label, {})[seed] = rec
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    # --- fold the seeds into paired verdicts ------------------------------------
    summary = {}
    for label in arms:
        got = per_seed.get(label, {})
        if not got:
            continue
        deltas = [got[s]["score"] - per_seed[base_label][s]["score"]
                  for s in got if s in per_seed.get(base_label, {})]
        dds = [got[s]["worst_drawdown"] for s in got]
        stops = [y for s in got for y in got[s]["stopped_years"]]
        inert = all(got[s]["inert"] for s in got)
        judge = exp.get("judge_on") or []
        focus = {}
        for y in judge:
            vals = [got[s]["annual"].get(int(y)) for s in got
                    if got[s]["annual"].get(int(y)) is not None]
            bvals = [per_seed[base_label][s]["annual"].get(int(y)) for s in got
                     if per_seed[base_label][s]["annual"].get(int(y)) is not None]
            if vals and bvals and len(vals) == len(bvals):
                focus[str(y)] = round(statistics.mean(vals) - statistics.mean(bvals), 4)
        # Flagged, not rejected: the operator removed the hard cap on 2026-08-28. A deep
        # arm still shows its drawdown and its mandate stops in every report, so the
        # cost is visible and the choice stays with him.
        deep = (max(dds) >= DD_FLAG) or bool(stops)
        exposures = [got[s]["avg_exposure"] for s in got if "avg_exposure" in got[s]]
        summary[label] = {
            "paired_delta": round(statistics.median(deltas), 4) if deltas else None,
            "avg_exposure": round(statistics.mean(exposures), 4) if exposures else None,
            "worst_drawdown": round(max(dds), 4),
            "mandate_breaches": sorted(set(stops)),
            "inert": inert,
            "deep_drawdown": deep,
            "judge_on_delta": focus,
            "scores": {str(s): round(got[s]["score"], 4) for s in got},
        }

    # --- an arm that never traded is a FAULT, not a verdict ----------------------
    # P33 asked for a lever whose data channel had never been built. The book failed
    # every year, and the table reported a -99 delta: a missing file wearing the
    # clothes of a catastrophic refutation. Zero exposure with zero drawdown cannot
    # happen to a working book, so it is flagged as a fault and the delta suppressed.
    for label, row in summary.items():
        if label.startswith("baseline"):
            continue
        if (row.get("avg_exposure") or 0) <= 0 and (row.get("worst_drawdown") or 0) <= 0:
            row["fault"] = ("the book never traded - a missing channel or a total veto, "
                            "NOT a measured effect; the delta is meaningless and is suppressed")
            row["paired_delta"] = None

    # --- was the harness itself trustworthy? -------------------------------------
    control = None
    for label, expected in CONTROL_EXPECT.items():
        if label in summary and summary[label]["paired_delta"] is not None:
            got_d = summary[label]["paired_delta"]
            control = {"arm": label, "expected": expected, "measured": got_d,
                       "ok": abs(got_d - expected) <= CONTROL_TOL}
            break
    return {"id": exp["id"], "agenda": exp.get("agenda"), "at": _now(),
            "seeds": seeds, "judge_on": exp.get("judge_on"),
            "control": control, "summary": summary,
            "trustworthy": (control["ok"] if control else None)}


def recover_orphans() -> list[str]:
    """Return rows left mid-flight by a previous process to the queue.

    A row is marked `running` while it executes. If the daemon is restarted - which
    happens whenever a lever is built, since Python holds imports for the life of a
    process - that row stays `running` forever and the runner, which only picks up
    `queued` rows, skips it silently for good. Recovering at startup is what makes the
    restart-to-refresh-code cycle safe.
    """
    rows = _read_program()
    freed = [r["id"] for r in rows if r.get("status") == "running"]
    if freed:
        for r in rows:
            if r.get("status") == "running":
                r["status"] = "queued"
                r["recovered_at"] = _now()
        _write_program(rows)
    return freed


def main() -> int:
    print("autotest: the paired-test method, running forever", flush=True)
    orphans = recover_orphans()
    if orphans:
        print(f"recovered {len(orphans)} experiment(s) orphaned by a restart: "
              f"{', '.join(orphans)}", flush=True)
    last_review = 0.0
    while True:
        if STOP.exists():
            _beat("stopped", "STOP file present")
            time.sleep(60)
            continue
        try:
            if time.time() - last_review > REVIEW_EVERY:
                _beat("reviewing", "mechanical state-of-the-search review")
                r = review()
                last_review = time.time()
                print(f"review: {r.get('verdict', '')} "
                      f"(bar {r.get('bar')}, {r.get('iterations_current_regime')} rows)", flush=True)

            queued = [r for r in _read_program() if r.get("status") == "queued"]
            queued.sort(key=lambda r: r.get("priority", 99))
            if not queued:
                _beat("idle", "no queued experiments; waiting for the agenda to be extended")
                time.sleep(IDLE_SLEEP)
                continue

            exp = queued[0]
            print(f"\n=== running {exp['id']} ({exp.get('agenda')}) ===", flush=True)
            _set_status(exp["id"], "running", started_at=_now())
            result = run_experiment(exp)
            _append(RESULTS, result)
            verdict = []
            for label, s in result["summary"].items():
                if s["inert"]:
                    verdict.append(f"{label}: DID NOT ENGAGE")
                elif s["deep_drawdown"]:
                    verdict.append(f"{label}: {s['paired_delta']:+.4f} "
                                   f"(DEEP dd {s['worst_drawdown']:.1%})")
                else:
                    verdict.append(f"{label}: {s['paired_delta']:+.4f}")
            _set_status(exp["id"], "done", finished_at=_now(),
                        verdict="; ".join(verdict),
                        trustworthy=result.get("trustworthy"))
            print("  " + "\n  ".join(verdict), flush=True)
        except Exception as exc:  # noqa: BLE001 -- a failed experiment must never stop the daemon
            print(f"autotest error: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            try:
                _set_status(exp["id"], "failed", error=f"{type(exc).__name__}: {exc}")  # noqa
            except Exception:  # noqa: BLE001
                pass
            _beat("error", f"{type(exc).__name__}: {exc}")
            time.sleep(300)


if __name__ == "__main__":
    raise SystemExit(main())
