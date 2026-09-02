"""The autonomous improvement loop: never stops, always searching for a better net.

It runs a complete dataset once, then iterates: sample a configuration, train the
pooled model, score it, keep it if it is the best so far, write the result to a
ledger, and go again — for a time budget or until a stop file appears. It is
built to run unattended for hours, so every iteration is wrapped: one bad config
logs a failure and the loop continues rather than dying.

THE ONE RULE THAT MATTERS: **selection is on validation, never on 2026.** The
laboratory forbids the sealed window from ever being an optimisation input, so
the loop's `score` is the model's edge over buy-and-hold on the held-out
validation slice inside the research era. The 2026 portfolio backtest is run for
the current champion and written down as an out-of-sample READOUT — it never
enters the score, and a config is never chosen because it did well in 2026.

The search space lives in `research/system06/search.json` so a supervising agent
can steer it between iterations — add a threshold, widen the window, propose a new
idea — without stopping the loop. The champion's artifacts are promoted to
`research/system06/` so the monitor's model card always shows the current best.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import torch

from . import fast_portfolio, infer, launch, moneymodel, prepare, train, universe
from . import meta as metalabel
from .dataset import Dataset

ROOT = Path("research/system06")
LEDGER = ROOT / "ledger.jsonl"
BEST = ROOT / "best.json"
SEARCH = ROOT / "search.json"
STOP = ROOT / "STOP"
# The genome search and the experiment runner both train on the SAME 8GB card, and the
# only brake that existed stopped both at once. Two trainings sharing that card do not
# halve each other's speed - they spill past the VRAM and one epoch stretches from
# thirty seconds to half an hour. A per-daemon flag is what lets the machine be given
# to whichever job matters most without shutting the other work down.
STOP_SELF = ROOT / "STOP_AUTOLOOP"
SCRATCH = ROOT / "_candidate"
LIVE = ROOT / "live.json"                 # real-time heartbeat the monitor polls
CURVES = ROOT / "champion_curves.json"    # per-year equity curves of the champion
KNOW_DIR = ROOT / "knowledge"             # the world-ideas notebook (ideas.jsonl / sources.jsonl)

# The starting search space. A supervising agent edits search.json to steer this;
# these are only the defaults for the first run.
DEFAULT_SEARCH = {
    # Only the knobs that need a GPU retrain are sampled here. The anti-churn band
    # (enter/exit/min_hold) is the toll lever, but it applies to the trained net's
    # probabilities with no retrain — so train() sweeps the WHOLE band grid on
    # validation for every model and keeps the toll-optimal one. Searching it here
    # would waste a full train on a single random band; letting train() optimise it
    # turns each GPU train into a full band sweep instead.
    "threshold": [0.02, 0.03, 0.05, 0.08],
    "window": [48, 64, 96, 128],
    "epochs": [20, 30, 40],
    "lr": [1e-3, 5e-4],
    "dropout": [0.1, 0.2, 0.3],
    # The trend filter's timescale (bars at 15m). It gates ENTRIES to uptrends, so a
    # LONGER span keeps the book flat through a bear market — the direct lever for
    # surviving 2018/2022 in the black, which the consistency law now demands.
    # 2880=30d, 5760=60d, 8640=90d, 11520=120d. Re-exported per iteration (no retrain).
    "trend_span": [2880, 5760, 8640, 11520],
    # Sample-uniqueness weighting (idea from Lopez de Prado): 0 = off, 1 = weight the
    # loss so each oracle swing counts equally. An anti-overfitting lever aimed at the
    # generalization gap the sealed 2026 readout exposed. A/B-tested by the loop.
    "uniqueness_weighting": [0, 1],
    # Bagged ensemble (idea ensemble-bagging): number of seed-varied nets to average.
    # Reduces variance -> better generalization + steadier years. Costs N x train time,
    # so keep N small and weight the sample toward 1.
    "ensemble": [1, 1, 1, 3],
    # Purged-CV embargo (bars) at the train/val split (idea purged-cv): drop leaky
    # boundary samples so the validation the loop selects on is honest — aimed at the
    # sealed-2026 generalization gap. 0=off, 288=3d, 960=10d at 15m.
    "embargo": [0, 288, 960],
    # The band is auto-optimised inside train(); the risk layer (positions, stops)
    # is gridded on the per-year sweep by _select_risk_years — neither is sampled here.
    #
    # BUT the band sweep is itself a 72-way maximisation on validation (4 enters x 3
    # exits x 6 holds), i.e. the SECOND nested best-of selection A43 exposed: with
    # smoothed probabilities its choice swung between min_hold 96 and 288 and the
    # resulting scores spread five times wider. Declaring `band_enter`/`band_exit`/
    # `band_hold` in search.json PINS the band per genome instead, converting a hidden
    # free maximum into an explicit searched dimension that is recorded, reproducible
    # and subject to the same seed-verified promotion as everything else. Absent from
    # the space (the default), train() sweeps as before — so this is opt-in and the
    # current behaviour is unchanged until the measurement justifies switching.
}

# The genome keys that pin the anti-churn band. All three must be present for the
# pin to apply; any missing one leaves train() free to sweep, since a partially
# pinned band is not a reproducible band.
BAND_KEYS = ("band_enter", "band_exit", "band_hold")


def _pinned_band(cfg: dict) -> dict:
    """train() kwargs pinning the band, or {} when the genome does not pin it."""
    if not all(k in cfg and cfg[k] is not None for k in BAND_KEYS):
        return {}
    return {"enter": float(cfg["band_enter"]), "exit_": float(cfg["band_exit"]),
            "min_hold": int(cfg["band_hold"])}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hypothesis(cfg: dict, risk: tuple | None = None) -> str:
    """One human line describing the algorithm this iteration is testing."""
    span = int(cfg.get("trend_span", TREND_SPAN))
    days = max(1, span // 96)
    parts = [f"TCN · window {cfg.get('window')} · threshold {cfg.get('threshold')}",
             f"epochs {cfg.get('epochs')} · lr {cfg.get('lr')} · dropout {cfg.get('dropout')}",
             f"trend filter {days}d"]
    if risk:
        parts.append(f"risk {risk[0]} pos × {risk[1]} · stop {risk[2]} · trail {risk[3]}")
    return " · ".join(parts)


def _ideas_index() -> dict:
    """Read the world-ideas notebook so a live rationale can cite the ACTUAL study behind
    each lever this iteration exercises. Returns {idea_id: idea_dict}; empty if unreadable
    (the rationale then falls back to hard-coded citations, so the loop never depends on it)."""
    idx: dict[str, dict] = {}
    path = KNOW_DIR / "ideas.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if d.get("id"):
                    idx[d["id"]] = d
            except ValueError:
                continue
    return idx


def _rationale(cfg: dict) -> dict:
    """Explain WHY this iteration exists — the reasoning the operator asked to see instead of
    a bare iteration counter. For every lever the sampled config exercises it returns the
    technique, its setting (ON/OFF/size), the STUDY it comes from (grounded in ideas.jsonl so
    the citation is the real one the loop is learning from), the hypothesis, and what we expect
    to find. `focus` is the headline experiment of this attempt (the paper-idea being A/B-tested,
    else the trend timescale). This is the small, structured 'what it's based on' block the live
    view renders under the training telemetry."""
    ideas = _ideas_index()
    span = int(cfg.get("trend_span", TREND_SPAN))
    days = max(1, span // 96)
    uniq = float(cfg.get("uniqueness_weighting", 0.0)) > 0
    emb = int(cfg.get("embargo", 0))
    ens = int(cfg.get("ensemble", 1))

    def source(idea_id: str, fallback: str) -> str:
        return (ideas.get(idea_id) or {}).get("source") or fallback

    levers = [
        {"key": "oracle", "active": True, "kind": "base",
         "label": "Cloning a long-only perfect-hindsight oracle",
         "setting": f"causal TCN · {cfg.get('window')}-candle window · threshold {cfg.get('threshold')}",
         "source": "System's founding hypothesis (zigzag oracle · max-trades)",
         "hypothesis": "A network that imitates an oracle's perfect entries/exits learns the "
                       "MECHANISM of a swing, not the price of any single coin.",
         "expects": "Buy/sell signals that generalize across the 14 pooled cryptos."},
        {"key": "trend", "active": True, "kind": "risk",
         "label": f"{days}-day trend filter",
         "setting": f"{days}d · {span} 15m candles",
         "source": "Consistency law (operator, 2026-08-19) — a direct survival lever in bear years",
         "hypothesis": f"Entering only in a {days}d+ uptrend keeps the book flat in broad bear "
                       "markets (2018, 2022), the consistency law's open problem.",
         "expects": "Raise the WORST year; less loss in bear years."},
        {"key": "uniqueness", "active": uniq, "kind": "training",
         "label": "Sample-uniqueness weighting",
         "setting": "ON — every swing weighted equally" if uniq else "OFF — control (unweighted)",
         "source": source("sample-uniqueness", "Lopez de Prado, Advances in Financial ML (ch. 4)"),
         "hypothesis": "Windows overlap heavily (one label per candle); weighting each swing equally "
                       "(1/leg-duration) avoids overfitting the redundant long legs.",
         "expects": "Less overfitting; higher worst year without hurting the sealed 2026 readout."},
        {"key": "embargo", "active": emb > 0, "kind": "validation",
         "label": "Purged validation + embargo",
         "setting": (f"ON — {emb} candles ({max(1, emb // 96)}d) of purge/embargo" if emb > 0
                     else "OFF — control (no purge)"),
         "source": source("purged-cv", "Lopez de Prado, Advances in Financial ML (ch. 7)"),
         "hypothesis": "The oracle labels are computed over the WHOLE series, so train bars next to "
                       "the cut 'see' the future through the pivots; purging + embargoing them gives an "
                       "honest validation to select on.",
         "expects": "Close the gap between internal validation and the sealed 2026 readout."},
        {"key": "ensemble", "active": ens > 1, "kind": "architecture",
         "label": "Network committee (bagging)",
         "setting": (f"ON — {ens} networks averaged" if ens > 1 else "OFF — single network"),
         "source": source("ensemble-bagging", "Lopez de Prado — bagging in finance; variance reduction (ML)"),
         "hypothesis": "Averaging N networks with different seeds cuts VARIANCE — the direct enemy "
                       "of year-to-year consistency.",
         "expects": "More stable years; less dependence on a single network's luck."},
    ]

    # The headline: the paper-idea being A/B-tested this attempt (ensemble > embargo > uniqueness),
    # else the trend timescale — so the UI leads with the TECHNIQUE, not the iteration number.
    focus = None
    for key in ("ensemble", "embargo", "uniqueness"):
        lever = next((l for l in levers if l["key"] == key and l["active"]), None)
        if lever:
            focus = lever["label"]
            break
    if focus is None:
        focus = next(l for l in levers if l["key"] == "trend")["label"]
    active_ideas = sum(1 for l in levers if l["active"] and l["kind"] not in ("base", "risk"))
    return {"focus": focus, "levers": levers, "active_ideas": active_ideas}


# The last-published live state, kept in memory so a background heartbeat thread can
# keep the timestamp fresh through long blocking stages (dataset build, a slow year)
# without the monitor ever deciding the loop died.
_LIVE_STATE: dict = {"running": False}


def _flush_live(state: dict) -> None:
    import os
    try:
        tmp = LIVE.with_name("live.json.tmp")
        tmp.write_text(json.dumps(state, default=str))
        os.replace(tmp, LIVE)
    except OSError:
        pass


def _write_live(base: dict, phase: str, phase_detail: str = "", **extra) -> None:
    """Publish the loop's live state atomically. The monitor polls this to show what
    is happening RIGHT NOW — training, exporting, which year is being backtested."""
    state = {**base, "running": True, "phase": phase, "phase_detail": phase_detail,
             "heartbeat": _now(), **extra}
    if base.get("started_epoch") is not None:
        state["elapsed_s"] = round(time.time() - base["started_epoch"], 1)
    _LIVE_STATE.clear()
    _LIVE_STATE.update(state)
    _flush_live(state)


def _idle_live(iteration: int, best_score, reason: str = "idle") -> None:
    """Mark the loop as not currently training (between iterations / stopped)."""
    state = {"running": False, "phase": reason, "iteration": iteration,
             "bar_score": best_score, "heartbeat": _now()}
    _LIVE_STATE.clear()
    _LIVE_STATE.update(state)
    _flush_live(state)


def _heartbeat_loop(stop_event) -> None:
    """Keep live.json's heartbeat fresh every few seconds while the loop is running,
    so a long stage never reads as a dead process."""
    while not stop_event.is_set():
        if _LIVE_STATE.get("running"):
            _LIVE_STATE["heartbeat"] = _now()
            if _LIVE_STATE.get("started_epoch") is not None:
                _LIVE_STATE["elapsed_s"] = round(time.time() - _LIVE_STATE["started_epoch"], 1)
            _flush_live(dict(_LIVE_STATE))
        stop_event.wait(6.0)


def _load_search() -> dict:
    if SEARCH.is_file():
        try:
            return {**DEFAULT_SEARCH, **json.loads(SEARCH.read_text())}
        except (OSError, ValueError):
            pass
    ROOT.mkdir(parents=True, exist_ok=True)
    SEARCH.write_text(json.dumps(DEFAULT_SEARCH, indent=2))
    return dict(DEFAULT_SEARCH)


def _sample(space: dict, rng: random.Random) -> dict:
    return {key: rng.choice(values) for key, values in space.items()}


EXPLORE_RATE = 0.20   # fraction of iterations that ignore history and sample fresh (exploration)
# Lowered 0.35 -> 0.20 on measured evidence. Pinned-era scores average -0.095 with a
# standard deviation of 0.039, while the promotion trigger sits at +0.116 — five and a
# half standard deviations away — so a randomly drawn genome essentially never clears it,
# and the space is 2,048 combinations against roughly ninety minutes an evaluation.
# Exploration is what you do when you have no good point; the champion IS a good point,
# and the elite pool now always carries it, so effort is better spent mutating its
# neighbourhood than sampling a space where nothing else has come close. Kept at 0.20
# rather than dropped to zero because a local optimum is still only local.
# REVERSAL CONDITION, stated so this is falsifiable: if the elite pool converges on a
# single genome and scores plateau without any candidate approaching the trigger, this is
# too low and should go back up — the search would then be exploiting a dead end.


# How many rows of the CURRENT regime must exist before the elite pool restricts itself
# to them. Below this the pool reads every row: a projected genome contributes only genes,
# never a score, so borrowing older NN backbones is safe while band genes are still scarce.
MIN_REGIME_ELITES = 4


def _incumbent_genome(space: dict, best_path: Path | None = None) -> dict | None:
    """The champion as a breeding parent, or None if its record cannot fill the space.

    The champion's band lives under `band` (it predates band genes), so it is folded back
    into genome form here. Returns None unless every gene of the current space is present,
    because a partial parent would be completed with random genes and would then not be
    the champion at all.
    """
    path = best_path or BEST
    try:
        best = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cfg = best.get("config")
    if not isinstance(cfg, dict):
        return None
    genome = dict(cfg)
    band = best.get("band")
    if isinstance(band, dict):
        genome.setdefault("band_enter", band.get("enter"))
        genome.setdefault("band_exit", band.get("exit_"))
        genome.setdefault("band_hold", band.get("min_hold"))
    projected = {g: genome[g] for g in space if genome.get(g) is not None}
    if set(projected) != set(space):
        return None
    # A gene value outside the declared space would make the parent unbreedable.
    if any(projected[g] not in space[g] for g in space):
        return None
    return projected


def _top_configs(space: dict, k: int = 6, ledger_path: Path | None = None) -> list[dict]:
    """The best historical NN genomes by consistency score, read from the ledger — the gene
    pool the evolutionary sampler breeds from. Each genome is projected onto the CURRENT
    search space's genes (an old config with a since-retired gene still breeds cleanly), and
    identical genomes are de-duplicated keeping the best-scoring. Empty on a cold start.

    Elites are ranked WITHIN the current selection regime. Band-swept scores and band-pinned
    scores are not comparable — sweeping bought roughly the median band, so swept rows score
    systematically differently from pinned ones — and ranking across both would let the older
    regime's rows own the gene pool permanently, so no pinned genome could ever become a
    parent. That is the same error as debiasing with the wrong regime's data or comparing
    against a bar measured another way. Below the minimum count the pool falls back to all
    rows, which is safe because a projected genome contributes only genes, never a score.

    The incumbent champion is always a parent when its genome covers the space: it is by
    definition the best REPRODUCIBLE point known, and after a regime change the ledger may
    hold no pinned row good enough to seed the search with.
    """
    path = ledger_path or LEDGER
    if not path.is_file():
        return []
    pinned_now = all(g in space for g in BAND_KEYS)
    scored: list[tuple[float, dict]] = []
    same_regime: list[tuple[float, dict]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            cfg, score = r.get("config"), r.get("score")
            if isinstance(cfg, dict) and isinstance(score, (int, float)):
                projected = {g: cfg[g] for g in space if g in cfg}
                scored.append((float(score), projected))
                if all(g in cfg for g in BAND_KEYS) == pinned_now:
                    same_regime.append((float(score), projected))
    except OSError:
        return []
    if len(same_regime) >= MIN_REGIME_ELITES:
        scored = same_regime
    scored.sort(key=lambda t: t[0], reverse=True)
    incumbent = _incumbent_genome(space)
    if incumbent is not None:
        scored.insert(0, (float("inf"), incumbent))
    seen: set = set()
    top: list[dict] = []
    for _s, c in scored:
        key = tuple(sorted(c.items()))
        if key in seen:
            continue
        seen.add(key)
        top.append(c)
        if len(top) >= k:
            break
    return top


def _evolve(space: dict, rng: random.Random, ledger_path: Path | None = None) -> dict:
    """Evolutionary sampler (idea `genetic-search`, Holland 1975): breed the next NN genome
    from the best historical configs instead of sampling uniformly at random — natural
    selection converges on a rugged fitness surface far faster than random search, which
    matters here because the space is ~10^4 combos and each evaluation costs a GPU train.

    With probability EXPLORE_RATE it EXPLORES (pure random) so the search never collapses
    onto a local optimum; otherwise it EXPLOITS: pick an elite parent, optionally cross it
    with a second elite (uniform crossover), then mutate 1-2 genes by resampling them from
    the search space. It always returns a genome with EXACTLY the current space's genes and
    valid values, and falls back to pure random when there is no history — so a cold start
    behaves like the old uniform search and the loop can never stall on this path."""
    if rng.random() < EXPLORE_RATE:
        return _sample(space, rng)
    top = _top_configs(space, ledger_path=ledger_path)
    if not top:
        return _sample(space, rng)
    child = dict(rng.choice(top))
    if len(top) > 1 and rng.random() < 0.5:                 # uniform crossover with a 2nd elite
        other = rng.choice(top)
        for g in space:
            if g in other and rng.random() < 0.5:
                child[g] = other[g]
    for g in rng.sample(list(space), k=min(2, len(space))):  # mutate 1-2 genes
        child[g] = rng.choice(space[g])
    return {g: child.get(g, rng.choice(space[g])) for g in space}  # complete & valid genome


def _genome_key(cfg: dict) -> tuple:
    """Canonical identity of a genome, for duplicate detection."""
    return tuple(sorted(cfg.items()))


def _evolve_fresh(space: dict, rng: random.Random, seen: set,
                  ledger_path: Path | None = None, tries: int = 8) -> dict:
    """`_evolve`, but never a genome this RUN has already evaluated.

    The training seed is fixed per run, so re-evaluating an identical genome re-trains
    the IDENTICAL net — pure waste (observed: a full ~1.5h iteration duplicated bit for
    bit). As evolution converges on the elites, duplicates get ever more likely. Resample
    up to `tries` times; if the pool is that collapsed, force-mutate genes one by one
    until the genome is new. Records the returned genome in `seen`."""
    cfg = _evolve(space, rng, ledger_path=ledger_path)
    for _ in range(tries):
        if _genome_key(cfg) not in seen:
            break
        cfg = _evolve(space, rng, ledger_path=ledger_path)
    genes = list(space)
    for _ in range(1000):                               # force novelty gene by gene, bounded
        if _genome_key(cfg) not in seen:
            break
        g = rng.choice(genes)
        options = [v for v in space[g] if v != cfg.get(g)]
        if options:
            cfg = {**cfg, g: rng.choice(options)}
    # A truly exhausted space (practically impossible at ~10^4 genomes vs ~100
    # iterations/run) falls through with a duplicate rather than stalling the loop.
    seen.add(_genome_key(cfg))
    return cfg


def _read_best_score() -> float | None:
    """The bar a candidate must clear — re-read each iteration so an externally promoted
    (or cross-run) champion raises it and the loop never regresses.

    Prefers `reproducible_bar`: the champion's MEDIAN over its verification re-runs, which
    is the same quantity a candidate's re-runs produce. Falling back to the headline `score`
    would compare a candidate's reproducible median against an incumbent's single lucky
    draw — the asymmetry that let one draw block the search for 94 iterations.
    """
    if BEST.is_file():
        try:
            best = json.loads(BEST.read_text())
        except (OSError, ValueError):
            return None
        bar = best.get("reproducible_bar")
        return bar if isinstance(bar, (int, float)) else best.get("score")
    return None


def _append_ledger(record: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def _promote(scratch: Path) -> None:
    """Copy the champion's artifacts to research/system06/ so the monitor shows it.
    Ensemble members are oracle_net.pt + oracle_net_1.pt ...; stale members from a
    previous (larger) champion are cleared first so infer never averages the wrong set."""
    net_files = sorted(scratch.glob("oracle_net*.pt"))
    for stale in list(ROOT.glob("oracle_net*.pt")):
        stale.unlink(missing_ok=True)
    for src in net_files:
        shutil.copy2(src, ROOT / src.name)
    # meta.npz travels with signals.npz: the champion's meta verdicts are keyed to its
    # signals, so a promoted champion must carry both or the meta filter would read stale
    # verdicts against fresh signals.
    for name in ("standardizer.json", "config.json", "model_card.json", "signals.npz", "meta.npz"):
        src = scratch / name
        if src.is_file():
            shutil.copy2(src, ROOT / name)
    best_dir = ROOT / "best"
    best_dir.mkdir(parents=True, exist_ok=True)
    for stale in list(best_dir.glob("oracle_net*.pt")):
        stale.unlink(missing_ok=True)
    for src in net_files:
        shutil.copy2(src, best_dir / src.name)
    for name in ("standardizer.json", "config.json", "model_card.json"):
        src = scratch / name
        if src.is_file():
            shutil.copy2(src, best_dir / name)


def _stamp_card(scratch: Path, brain_kwargs: dict, consistency: dict, annual: dict) -> None:
    """Fold the winning risk layer + the Jan->Dec grid into the model card the monitor
    reads. `annual` is {year: {return_pct, max_drawdown, status, ...}} for 2018..2026
    (2026 sealed readout). `consistency` carries worst_year / cagr / all_positive."""
    card_path = scratch / "model_card.json"
    try:
        card = json.loads(card_path.read_text())
    except (OSError, ValueError):
        card = {}
    fw = annual.get(2026, {})
    card["risk_layer"] = {k: brain_kwargs.get(k) for k in
                          ("enter", "exit_", "min_hold", "max_positions",
                           "position_fraction", "stop_loss", "trail_stop",
                           "vol_scale", "breadth_gate", "regime_deploy")}
    # Surface any active module lever (meta / money / microstructure / consensus) too.
    # PRESENCE, not truthiness: `meta_margin: 0.0` is an ACTIVE meta filter (accept any
    # trade with non-negative expected net), and 0.0 is falsy. Recording it by truthiness
    # silently dropped it from the champion's card, so the champion could not be rebuilt
    # from its own record — a config that scored +0.086 replayed as -0.076 without it.
    card["risk_layer"].update({k: brain_kwargs[k] for k in MODULE_LEVERS if k in brain_kwargs})
    # The new headline evidence: consistency across independent calendar years.
    card["annual_returns"] = {str(y): annual[y].get("return_pct") for y in sorted(annual)}
    card["annual_detail"] = {str(y): annual[y] for y in sorted(annual)}
    card["consistency"] = consistency                  # worst_year / cagr / all_positive
    card["selection_years"] = list(RESEARCH_YEARS)     # which years selected (2026 excluded)
    card["forward_2026"] = {k: fw.get(k) for k in      # sealed readout only
                            ("return_pct", "max_drawdown", "trades", "average_exposure", "status")}
    card["incumbent_2026"] = 0.0505
    card_path.write_text(json.dumps(card, indent=2, default=str))


# A small, fixed grid of risk-management configs, applied to a trained net's
# signals with no retrain. This is the survival layer that lets a long-only crypto
# basket clear the 25% peak-to-trough mandate: concentration + trailing stop +
# (optional) hard stop. Selected on the recent PRE-2026 validation window, never
# on 2026. (max_positions, position_fraction, stop_loss, trail_stop)
RISK_GRID = [
    (5, 0.6, 0.0, 0.20),
    (5, 0.7, 0.0, 0.20),
    (5, 0.5, 0.0, 0.20),
    (5, 0.6, 0.12, 0.20),
    (4, 0.6, 0.0, 0.18),
    (3, 0.7, 0.10, 0.20),
    # Lower-exposure survivors, so the validation window can clear the mandate
    # rather than always tripping the 25% stop.
    (3, 0.4, 0.0, 0.15),
    (4, 0.4, 0.10, 0.15),
    (3, 0.5, 0.08, 0.15),
]
RISK_FILE = ROOT / "risk_grid.json"
TREND_SPAN = 2880  # 30 days at 15m — the regime timescale, not a whippy fast MA
PROMOTE_MARGIN = 0.05  # ~1 sigma of MEASURED selection noise (stdev 0.0516 over 136
#                        iterations). The old 0.02 sat far below the noise, so the bar could
#                        not tell a better strategy from a luckier one. A candidate must now
#                        clear the bar by a full sigma before we spend seeds verifying it.
# Seed-robust promotion. Measured on 136 completed iterations, the selected score has a
# standard deviation of ~0.052 — more than twice PROMOTE_MARGIN — so a single draw cannot
# tell a better strategy from a luckier one. The iter-42 champion scored +0.086 (the sample
# maximum, ~3 sigma above the mean) yet its OWN genome re-run under another seed scored
# -0.105. Enshrining that draw set a bar nothing could clear for 94 iterations. So a
# candidate that clears the bar on one draw is now RE-RUN under extra seeds and promoted on
# the MEDIAN, which is what makes the number reproducible rather than lucky.
VERIFY_SEEDS = 3       # extra seeds a promotion candidate must survive (0 = off)
# Raised 2 -> 3 on MEASURED evidence, not taste. Four fixed-config re-runs of the champion
# genome (band and risk pinned, research years) scored +0.0000, +0.0057, +0.0724, +0.0738:
# a range of 0.074 and a standard deviation of 0.041. An earlier reading of only the first
# two put the spread at 0.006 and was badly optimistic — they happened to be adjacent seeds
# that landed together. With variance that large a two-sample "median" is really a mean of
# two draws, which one outlier can carry; three gives a genuine median that an outlier
# cannot. Verification fires on roughly one iteration in a hundred, so the extra train is
# cheap against the cost of enshrining another lucky draw.

# The iteration's reported score is the MAX over the risk grid, and picking the best of
# ten configurations on the same eight years that score them inflates it — measured at
# +0.0765 on average across 125 full sweeps (median +0.0720, stdev 0.043). Left
# uncorrected, 26% of historical iterations would trigger a verification (~2 GPU-hours
# each) and essentially all get refused, because their reproducible medians sit near
# -0.10. The trigger therefore compares the DEBIASED score against the bar. Once enough
# per-iteration `grid_inflation` rows accumulate in the ledger, the measured median of
# those replaces this constant, so the correction tracks the live grid rather than a
# frozen estimate.
GRID_INFLATION_PRIOR = 0.0765
MIN_INFLATION_ROWS = 8


def _inflation_prior(ledger_path: Path | None = None, pinned: bool = True) -> float:
    """Median per-iteration grid inflation, measured in the CURRENT selection regime.

    `pinned` says whether the loop now pins the band per genome. Rows from the other
    regime are EXCLUDED rather than pooled: band-swept iterations and band-pinned ones
    do not measure the same quantity — pinning shifted the score level by about 0.10 and
    cut run-to-run spread roughly twentyfold — so averaging across the two would correct
    a pinned candidate by a number partly derived from swept ones. That is the same
    error as comparing a candidate against a bar measured a different way, which this
    system has now produced three times (see the `bar-must-measure-what-candidates-
    measure` note); the cure is to make the estimate regime-matched, not merely recent.

    Falls back to GRID_INFLATION_PRIOR until MIN_INFLATION_ROWS rows of the CURRENT
    regime exist, and on any read error — the trigger must never take the loop down.
    That constant was itself measured under band sweeping, so while the fallback is in
    force the correction is regime-mismatched; it is a stand-in until pinned rows
    accumulate, which is why the threshold is low enough to cross within a day's work.
    """
    path = ledger_path or LEDGER
    try:
        vals: list[float] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001 -- one bad row must not disable the prior
                continue
            cfg = row.get("config")
            row_pinned = isinstance(cfg, dict) and all(k in cfg for k in BAND_KEYS)
            if row_pinned != pinned:
                continue
            gi = row.get("grid_inflation")
            if isinstance(gi, (int, float)) and gi == gi:
                vals.append(float(gi))
        if len(vals) >= MIN_INFLATION_ROWS:
            med = _median(vals)
            if med is not None:
                return float(med)
    except Exception:  # noqa: BLE001
        pass
    return GRID_INFLATION_PRIOR


def _is_candidate(score: float, bar: float | None, inflation: float) -> bool:
    """The cheap trigger for spending verification seeds on a genome.

    `score` is a max-of-grid and is optimistic by the measured selection inflation, so
    it must clear the bar AFTER subtracting that inflation. No margin here: the margin
    is enforced by `_promotion_survives` on the reproduced MEDIAN — the one measurement
    with no maximisation inside it — and demanding it twice would double-count."""
    if bar is None:
        return True
    if score is None or score != score:
        return False
    return (score - inflation) > bar


def _median(scores: list) -> float | None:
    """Median of the finite scores, or None if any is missing (see `_promotion_survives`)."""
    if not scores or any(x is None or x != x for x in scores):
        return None
    finite = sorted(float(x) for x in scores)
    mid = len(finite) // 2
    return finite[mid] if len(finite) % 2 else 0.5 * (finite[mid - 1] + finite[mid])


def _promotion_survives(scores: list[float], bar: float | None, margin: float = PROMOTE_MARGIN) -> bool:
    """Promote on the MEDIAN of a genome's scores, never on a single lucky draw.

    `scores` holds the candidate's own score plus one per verification seed. A missing bar
    (no incumbent yet) promotes on any finite median.

    FAIL CLOSED: a None means a verification run did not complete, and dropping it would
    quietly collapse the median back onto the single lucky draw this rule exists to refuse —
    silently restoring the bug rather than reporting it. So any failed verification blocks
    the promotion; the candidate simply gets another chance on a later iteration.
    """
    if not scores:
        return False
    if any(x is None or x != x for x in scores):
        return False
    finite = [float(x) for x in scores]
    finite.sort()
    mid = len(finite) // 2
    median = finite[mid] if len(finite) % 2 else 0.5 * (finite[mid - 1] + finite[mid])
    if bar is None:
        return True
    return median > bar + margin

# THE SELECTION LAW (operator, 2026-08-19): judge the algorithm the way money is
# actually invested — Jan 1 to Dec 31, EVERY year. Consistency over explosiveness.
# Each research year 2018..2025 is an independent account (see launch.year_window).
# 2026 stays SEALED: a per-year readout only, never in the score.
RESEARCH_YEARS = tuple(range(2018, 2026))   # 2018..2025 — the selection years
CAGR_WEIGHT = 0.10  # score = worst_year + CAGR_WEIGHT*cagr; the floor is the law,
#                     profit is only the tie-breaker among similar floors.


# The positional risk-grid schema (legacy list rows), in order. A row may also be a
# DICT naming any brain lever directly — the future-proof form, since the module levers
# (meta_margin, money_kelly, money_pyramid, micro_gate, consensus_k) outgrew a positional
# list. Both forms are normalised to a brain_kwargs partial by `_row_to_kwargs`.
POSITIONAL_LEVERS = ["max_positions", "position_fraction", "stop_loss", "trail_stop",
                     "vol_scale", "breadth_gate", "regime_deploy", "regime_persist"]
MODULE_LEVERS = ["meta_margin", "money_kelly", "money_pyramid", "micro_gate", "consensus_k",
                 "mom_gate", "martingale", "hurst_gate", "feargreed", "horserace", "sweep", "tree_weight", "edge_monitor",
                 "money_model", "trend_soft", "dd_sizer",
                 # The drawdown abort. Part of the STRATEGY (it halts the account for the
                 # year), and since the operator removed the hard 25% policy (2026-08-28)
                 # it is a swept lever like any other. Caught missing here PROACTIVELY:
                 # P11 measured ceiling 0.90 + cap 0.60 at +0.1166, and a grid row carrying
                 # max_drawdown would have been silently stripped by _row_to_kwargs -
                 # the row would have run at cap 0.25 and quietly measured the wrong thing.
                 "max_drawdown",
                 # A65: the extreme-fear veto, from the REAL Fear & Greed index. First
                 # lever in this list whose information does NOT derive from price.
                 "fng_min",
                 # Progressive entries (pyramiding into strength).
                 "scale_in",
                 # Seasoning: a symbol must have its OWN history before it is tradable.
                 "min_age_days", "scale_enter",
                 # A70: the second non-price input.
                 "activity_min",
                 # A71: fund accepted trades in proportion to certainty.
                 "conviction_sizing"]
KNOWN_LEVERS = set(POSITIONAL_LEVERS) | set(MODULE_LEVERS)


def _row_to_kwargs(row) -> dict:
    """Normalise a risk-grid row (positional list OR named dict) to a brain_kwargs partial."""
    if isinstance(row, dict):
        return {k: v for k, v in row.items() if k in KNOWN_LEVERS}
    return {POSITIONAL_LEVERS[i]: row[i] for i in range(min(len(row), len(POSITIONAL_LEVERS)))}


def _load_risk_grid() -> list:
    """Risk configs, steerable live via risk_grid.json.

    Each row is either a legacy positional list [maxpos, frac, stop, trail, (vol_scale),
    (breadth_gate), (regime_deploy), (regime_persist)] or a named dict of any brain lever
    (e.g. {"max_positions":2, "position_fraction":0.15, "meta_margin":0.0}). Dict rows are
    how the module levers — meta, money, microstructure, consensus — are explored.
    """
    if RISK_FILE.is_file():
        try:
            rows = json.loads(RISK_FILE.read_text())
            grid = [r for r in rows
                    if (isinstance(r, list) and len(r) in (4, 5, 6, 7, 8)) or (isinstance(r, dict) and r)]
            if grid:
                return grid
        except (OSError, ValueError):
            pass
    return RISK_GRID


def _consistency(per_year: dict[int, dict]) -> dict:
    """Score a per-calendar-year record for CONSISTENCY.

    score = worst_year + CAGR_WEIGHT * cagr. Maximising this maximises the floor —
    the guaranteed 12-month return "invest whenever you like, you still finish up".
    `all_positive` (every year > 0 and no year tripped the 25% mandate) is the badge
    that marks a genuine winner; the loop still promotes the best score so progress
    toward that badge is always visible.
    """
    rows = [v for v in per_year.values() if v and v.get("return_pct") is not None]
    rets = [float(v["return_pct"]) for v in rows]
    if not rets:
        return {"score": -99.0, "all_positive": False, "min_year": None,
                "cagr": None, "stopped": False, "n": 0}
    min_year = min(rets)
    stopped = any(v.get("status") == "stopped" for v in rows)
    growth = 1.0
    for r in rets:
        growth *= (1.0 + r)
    cagr = growth ** (1.0 / len(rets)) - 1.0
    return {"score": min_year + CAGR_WEIGHT * cagr,
            "all_positive": (min_year > 0) and not stopped,
            "min_year": min_year, "cagr": cagr, "stopped": stopped, "n": len(rets)}


def _score_genome(cfg: dict, seed: int, data_root: str, symbols: list[str],
                  rbars, rstamps, dataset, grid: list, scratch: Path,
                  risk: dict | None = None) -> float | None:
    """Train `cfg` under `seed` and return the consistency score it reproduces.

    A compact replay of one iteration, used ONLY to verify a promotion candidate: train,
    export, rebuild the meta channel if it is needed, then score.

    `risk` is the candidate's WINNING risk configuration. Passing it scores that one
    configuration — the exact pair (genome, risk) that would ship — instead of re-searching
    the whole grid. That matters twice over. Re-searching would hand every verification its
    own best-of-ten selection, the very advantage this guard exists to strip out, and it
    would measure the candidate differently from the incumbent bar, which is a single
    configuration's reproducible median. It is also roughly ten times cheaper. With `risk`
    None the old behaviour (search the grid) is kept for callers that want it.

    Returns None if anything fails — a verification that cannot run must never promote by
    default, and must never take the loop down either. 2026 is untouched throughout.
    """
    try:
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True, exist_ok=True)
        metrics = train.train(
            data_root=data_root, symbols=symbols, threshold=cfg["threshold"],
            window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"], dropout=cfg["dropout"],
            out_dir=str(scratch), seed=seed,
            uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
            ensemble=int(cfg.get("ensemble", 1)), embargo=int(cfg.get("embargo", 0)),
            market_features=bool(cfg.get("market_features", 0)),
            # A pinned band must be pinned HERE too. If verification re-swept the band it
            # would hand every re-run its own 72-way maximum — reintroducing selection
            # optimism into the one measurement that exists to be free of it, exactly the
            # bug that made verification re-search the risk grid.
            **_pinned_band(cfg))
        band = {"enter": metrics["enter"], "exit_": metrics["exit"], "min_hold": metrics["min_hold"]}
        sig = str(scratch / "signals.npz")
        infer.export(data_root=data_root, symbols=symbols, model_dir=str(scratch),
                     out_path=sig, trend_span=int(cfg.get("trend_span", TREND_SPAN)))
        if any("meta_margin" in _row_to_kwargs(r) for r in grid):
            try:
                cand = metalabel.gather_candidates(dataset, sig, symbols, enter=band["enter"])
                verdicts, _doc = metalabel.build_verdicts(cand)
                metalabel.write_meta(verdicts, str(scratch / "meta.npz"))
                band["meta_signals"] = str(scratch / "meta.npz")
            except Exception:  # noqa: BLE001 -- meta is optional; those rows just abstain
                pass
        # The shipping config's learned sizing must be rebuilt here as well, from THIS
        # re-run's own signals. Without it the Sizing module would find no channel and
        # abstain, so the verification would score a strategy WITHOUT sizing while the
        # candidate had it — measuring a different thing than the number it is compared
        # against. That is the recurring bug class, so it FAILS CLOSED: if the config
        # calls for sizing and the channel cannot be built, the verification reports
        # None and blocks promotion rather than quietly measuring something else.
        needs_sizing = (float((risk or {}).get("money_model") or 0) > 0 if risk is not None
                        else any(float(_row_to_kwargs(r).get("money_model") or 0) > 0 for r in grid))
        if needs_sizing:
            stops = risk if risk is not None else next(
                (_row_to_kwargs(r) for r in grid
                 if float(_row_to_kwargs(r).get("money_model") or 0) > 0), {})
            try:
                overlay = moneymodel.build_sizing(
                    sig, data_root,
                    enter=float(band["enter"]), exit_=float(band["exit_"]),
                    min_hold=int(band["min_hold"]),
                    stop_loss=float(stops.get("stop_loss") or 0.0),
                    trail_stop=float(stops.get("trail_stop") or 0.0),
                    research=rbars)
                moneymodel.write_sizing(overlay, str(scratch / "moneymodel.npz"))
                band["size_signals"] = str(scratch / "moneymodel.npz")
            except Exception:  # noqa: BLE001
                if risk is not None:
                    return None      # fail closed: never verify a different strategy
        if risk is None:
            cons, _bk, _py, _sweep = _select_risk_years(rbars, rstamps, sig, band, grid)
        else:
            bk = {**band, **{k: v for k, v in risk.items()
                             if k not in ("meta_signals", "size_signals")}}
            if "meta_signals" in band:
                bk["meta_signals"] = band["meta_signals"]
            if "size_signals" in band:
                bk["size_signals"] = band["size_signals"]
            per_year = launch.per_year(rbars, rstamps, RESEARCH_YEARS, sig, brain_kwargs=bk)
            cons = _consistency(per_year)
        return float(cons["score"])
    except Exception:  # noqa: BLE001 -- a failed verification blocks promotion, nothing worse
        return None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _select_risk_years(bars, stamps, signals: str, band: dict,
                       risk_grid: list[tuple], publish=None) -> tuple[dict, dict, dict[int, dict]]:
    """Run the independent per-year sweep (2018..2025) for every risk config and keep
    the most CONSISTENT. Returns (consistency, brain_kwargs, per_year, sweep) — `sweep`
    is EVERY config's per-year outcome so the ledger records the whole grid, not just the
    winner. 2026 never enters here. The score is exactly what the instrument produces.

    `publish(risk_idx, risk_total, risk_tuple, years_done, current_year)` is called as
    each year runs so the monitor can show the backtest sweeping year by year, live."""
    best: tuple[dict, dict, dict[int, dict]] | None = None
    sweep: list[dict] = []   # EVERY config's outcome, so the ledger shows the whole grid,
    #                          not just the winner (the blind spot that made vol/breadth
    #                          verdicts guesswork — now every risk lever is judged on its
    #                          own faithful per-year result).
    total = len(risk_grid)
    for ri, row in enumerate(risk_grid):
        kw = _row_to_kwargs(row)
        bk = {**band, **kw}
        mp, pf = bk.get("max_positions"), bk.get("position_fraction")
        done: dict[int, float] = {}

        def on_year(year, result, i, n, _risk=(mp, pf, bk.get("stop_loss"), bk.get("trail_stop")), _ri=ri):
            if result is not None and result.get("return_pct") is not None:
                done[int(year)] = round(float(result["return_pct"]), 4)
            if publish:
                publish(_ri, total, _risk, dict(done), int(year))

        try:
            py = launch.per_year(bars, stamps, RESEARCH_YEARS, signals,
                                 brain_kwargs=bk, on_year=on_year)
        except Exception:  # noqa: BLE001 -- a bad risk cfg just drops out of the grid
            continue
        cons = _consistency(py)
        # Log the positional levers (the dashboard reads these keys) plus any active
        # module lever, so every config's contribution is judged on its own per-year result.
        record = {lever: bk.get(lever, 0.0) for lever in POSITIONAL_LEVERS}
        record.update({k: kw[k] for k in MODULE_LEVERS if k in kw})
        record.update({
            "score": round(cons["score"], 4), "min_year": cons["min_year"],
            "cagr": cons["cagr"], "all_positive": cons["all_positive"],
            "annual": {str(y): round(float(py[y]["return_pct"]), 4)
                       for y in sorted(py) if py[y].get("return_pct") is not None},
        })
        sweep.append(record)
        if best is None or cons["score"] > best[0]["score"]:
            best = (cons, bk, py)
    if best is None:
        raise RuntimeError("no risk config produced a per-year backtest")
    return (*best, sweep)


def _champion_curves(bars, stamps, dataset: Dataset, signals: str, brain_kwargs: dict) -> None:
    """On promotion, save each calendar year's equity curve (2018..2026) so the monitor
    can draw the real path of the champion year by year. 2026 from the combined data."""
    curves: dict[str, list] = {}
    for y in RESEARCH_YEARS:
        try:
            r = launch.year_window(bars, stamps, y, signals, brain_kwargs=brain_kwargs)
            if r is not None:
                curves[str(y)] = r.get("equity", [])
        except Exception:  # noqa: BLE001
            continue
    try:
        cbars = dataset.combined()
        cstamps = sorted({b.timestamp for series in cbars.values() for b in series})
        r26 = launch.year_window(cbars, cstamps, 2026, signals, brain_kwargs=brain_kwargs)
        if r26 is not None:
            curves["2026"] = r26.get("equity", [])
    except Exception:  # noqa: BLE001
        pass
    try:
        CURVES.write_text(json.dumps(curves, default=str))
    except OSError:
        pass


def _annual_grid(bars, stamps, dataset: Dataset, signals: str,
                 per_year_research: dict[int, dict], brain_kwargs: dict) -> dict:
    """The full Jan->Dec grid the monitor shows: 2018..2025 from research (reuse the
    selection sweep) plus the SEALED 2026 year from the combined dataset (readout)."""
    grid = {int(y): v for y, v in per_year_research.items()}
    try:
        cbars = dataset.combined()
        cstamps = sorted({b.timestamp for series in cbars.values() for b in series})
        r26 = launch.year_window(cbars, cstamps, 2026, signals, brain_kwargs=brain_kwargs)
        if r26 is not None:
            grid[2026] = {k: r26.get(k) for k in launch.PER_YEAR_KEYS}
    except Exception as exc:  # noqa: BLE001
        grid[2026] = {"error": str(exc)}
    return grid


def run(hours: float = 24.0, seed: int = 0, data_root: str = "backtester/data",
        skip_prepare: bool = False) -> None:
    symbols = universe.load()
    print(f"autoloop starting: {len(symbols)} symbols, budget {hours}h", flush=True)
    if skip_prepare:
        # Panels are cached on disk and build_matrix warms any that are missing
        # lazily, so a warm restart can skip the ~15-minute prepare pass entirely.
        print("skip-prepare: assuming indicator panels are already warm", flush=True)
    else:
        prepare.prepare(symbols, data_root=data_root)  # complete dataset, once

    dataset = Dataset(data_root, symbols=symbols)
    _idle_live(0, None, reason="preparing")   # UI shows life the instant the loop starts
    _LIVE_STATE["running"] = True             # keep the heartbeat thread bumping during prepare
    hb_stop = threading.Event()
    hb_thread = threading.Thread(target=_heartbeat_loop, args=(hb_stop,), daemon=True)
    hb_thread.start()
    # Research bars are static across iterations — load once and reuse for every
    # per-calendar-year sweep. (2026 combined bars are fetched only on a promotion.)
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})
    print(f"research bars {rstamps[0].date()} -> {rstamps[-1].date()} "
          f"({len(rstamps)} stamps); selecting on years {RESEARCH_YEARS[0]}..{RESEARCH_YEARS[-1]}", flush=True)
    deadline = time.time() + hours * 3600
    # Read the bar through _read_best_score so it is the champion's REPRODUCIBLE median,
    # not its headline draw. Reading `score` directly here silently pinned the bar to a
    # lucky max-of-grid number (+0.0675 while the reproducible bar was -0.0885), which no
    # candidate could clear — the exact stall the verified-promotion regime exists to end.
    best_score = _read_best_score()

    iteration = 0
    seen_genomes: set = set()   # genomes evaluated THIS run (train seed is fixed per run,
    #                             so a repeat genome would re-train the identical net)
    while time.time() < deadline and not STOP.exists() and not STOP_SELF.exists():
        iteration += 1
        rng = random.Random((seed << 20) ^ iteration)
        space = _load_search()
        cfg = _evolve_fresh(space, rng, seen_genomes)   # evolutionary search, never a duplicate
        started = time.time()
        rationale = _rationale(cfg)   # WHY this attempt: technique · study · hypothesis · expectation
        record = {"iteration": iteration, "at": _now(), "config": cfg, "rationale": rationale}
        live_base = {"iteration": iteration, "config": cfg, "hypothesis": _hypothesis(cfg),
                     "rationale": rationale, "started_at": _now(), "started_epoch": started,
                     "bar_score": best_score}
        try:
            if SCRATCH.exists():
                shutil.rmtree(SCRATCH, ignore_errors=True)
            # 1) Train the net; the anti-churn band is auto-optimised on val inside.
            #    A throttled callback republishes rich training telemetry (epoch, batch,
            #    live loss, dataset shape) so the monitor shows the net actually forming.
            _write_live(live_base, "training", "starting training")
            _last_emit = [0.0]

            def _train_progress(ev, _lb=live_base, _le=_last_emit):
                stage = ev.get("stage")
                nowt = time.time()
                force = bool(ev.get("epoch_done")) or stage in ("building", "evaluating")
                if not force and nowt - _le[0] < 1.2:
                    return
                _le[0] = nowt
                if stage == "building":
                    _write_live(_lb, "training", ev.get("msg", "building dataset"),
                                train={"substage": "building", "dataset": ev.get("dataset")})
                elif stage == "evaluating":
                    _write_live(_lb, "training", "validating + sweeping anti-churn bands",
                                train={"substage": "evaluating", "loss_curve": ev.get("loss_curve"),
                                       "dataset": ev.get("dataset")})
                else:
                    ep, eps = ev.get("epoch"), ev.get("epochs")
                    b, bs = ev.get("batch"), ev.get("batches")
                    _write_live(_lb, "training", f"epoch {ep}/{eps} · batch {b}/{bs}",
                                train={"substage": "training", "epoch": ep, "epochs": eps,
                                       "batch": b, "batches": bs, "loss": ev.get("loss"),
                                       "loss_curve": ev.get("loss_curve"), "dataset": ev.get("dataset"),
                                       "samples_done": ev.get("samples_done"),
                                       "samples_total": ev.get("samples_total")})

            metrics = train.train(
                data_root=data_root, symbols=symbols,
                threshold=cfg["threshold"], window=cfg["window"],
                epochs=cfg["epochs"], lr=cfg["lr"], dropout=cfg["dropout"],
                out_dir=str(SCRATCH), seed=seed, on_progress=_train_progress,
                uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                ensemble=int(cfg.get("ensemble", 1)),
                embargo=int(cfg.get("embargo", 0)),
                market_features=bool(cfg.get("market_features", 0)),
                **_pinned_band(cfg),
            )
            band = {"enter": metrics["enter"], "exit_": metrics["exit"], "min_hold": metrics["min_hold"]}
            # 2) Export full signals, then SELECT the risk layer by REAL validation
            #    backtests over a small safe grid — no fast-sim proxy, so the score is
            #    exactly what the instrument produces. Every candidate is scored the
            #    honest way; 2026 is never touched here.
            sig = str(SCRATCH / "signals.npz")
            trend_span = int(cfg.get("trend_span", TREND_SPAN))
            live_base["hypothesis"] = _hypothesis(cfg)
            _write_live(live_base, "exporting", "exporting signals · scoring the trend filter")
            infer.export(data_root=data_root, symbols=symbols, model_dir=str(SCRATCH),
                         out_path=sig, trend_span=trend_span)
            # 2a) META (optional): if any grid row explores the meta filter, rebuild the
            #     verdict channel FROM THE FRESH SIGNALS at this net's own enter, so the
            #     verdicts never drift from the signals they judge. Honest walk-forward,
            #     2026 sealed inside meta.build_verdicts. A failure just disables meta this
            #     cycle (those configs abstain) — it never stops the loop.
            grid = _load_risk_grid()
            if any("meta_margin" in _row_to_kwargs(r) for r in grid):
                meta_path = str(SCRATCH / "meta.npz")
                try:
                    _write_live(live_base, "meta", "building meta-label verdicts (walk-forward)")
                    cand = metalabel.gather_candidates(dataset, sig, symbols, enter=band["enter"])
                    verdicts, _mdoc = metalabel.build_verdicts(cand)
                    metalabel.write_meta(verdicts, meta_path)
                    band["meta_signals"] = meta_path
                except Exception as exc:  # noqa: BLE001 -- meta is optional; failure disables it
                    print(f"iter {iteration}: meta build failed ({exc}); meta configs abstain", flush=True)
            # 2a-bis) MONEY MODEL (optional), same discipline as meta: rebuild the learned
            #     size-multiplier channel FROM THIS NET'S OWN SIGNALS. The first version
            #     shipped a channel built from the CHAMPION's signals, so every candidate
            #     was sized by a model trained on a different net's trades — a handicap that
            #     could only understate the lever. The exit rules used to simulate the
            #     training trades are taken from the money_model row itself, so the model
            #     learns the outcomes of the very rules it will size. Walk-forward and
            #     embargoed inside build_sizing; the sealed window is scored by a
            #     research-only fit. A failure just disables it this cycle (those rows
            #     abstain) — it never stops the loop.
            money_rows = [_row_to_kwargs(r) for r in grid]
            money_rows = [kw for kw in money_rows if float(kw.get("money_model") or 0) > 0]
            if money_rows:
                size_path = str(SCRATCH / "moneymodel.npz")
                try:
                    _write_live(live_base, "sizing", "training the money-management model (walk-forward)")
                    overlay = moneymodel.build_sizing(
                        sig, data_root,
                        enter=float(band["enter"]), exit_=float(band["exit_"]),
                        min_hold=int(band["min_hold"]),
                        stop_loss=float(money_rows[0].get("stop_loss") or 0.0),
                        trail_stop=float(money_rows[0].get("trail_stop") or 0.0),
                        research=rbars)
                    moneymodel.write_sizing(overlay, size_path)
                    band["size_signals"] = size_path
                except Exception as exc:  # noqa: BLE001 -- optional; failure disables it
                    print(f"iter {iteration}: sizing build failed ({exc}); money_model rows abstain",
                          flush=True)
            # 2b) SELECT on CONSISTENCY: independent per-calendar-year backtests (2018..
            #    2025) for every risk config; keep the one whose WORST year is highest.
            #    2026 is never touched here. The score is exactly what the instrument
            #    produces, so it is cross-net comparable and honest.
            def _publish(ri, rt, risk, years_done, cur_year):
                _write_live(live_base, "backtesting",
                            f"backtesting {cur_year} · risk config {ri + 1}/{rt}",
                            partial={"risk": list(risk), "years": years_done,
                                     "current_year": cur_year})

            cons, brain_kwargs, per_year, sweep = _select_risk_years(
                rbars, rstamps, sig, band, grid, publish=_publish)
            record["sweep"] = sweep   # every risk config's per-year, for honest lever A/Bs
            score = cons["score"]
            # The reported score is the MAX over the risk grid, chosen on the same years
            # that score it. Measured across 125 sweeps that inflates by about +0.077 versus
            # the median configuration on the same net. Recording the median (and the gap)
            # costs nothing and gives every iteration an uninflated number to judge by.
            grid_scores = [r.get("score") for r in sweep
                           if isinstance(r.get("score"), (int, float))]
            grid_median = _median(grid_scores) if grid_scores else None
            record["grid_median"] = grid_median
            record["grid_inflation"] = (score - grid_median) if grid_median is not None else None
            # The champion on disk is authoritative, in BOTH directions. Only ever raising
            # the bar meant a corrected (lower, reproducible) bar could never take effect,
            # so a stale high number outlived the evidence that disproved it.
            disk_best = _read_best_score()
            if disk_best is not None:
                best_score = disk_best
            # A single draw only makes a candidate; reproducible RE-RUNS make a champion.
            # The candidate's own score is a max over the risk grid and is used only as a
            # cheap TRIGGER for who deserves verifying — DEBIASED by the measured grid
            # inflation, since the bar it is compared against is a fixed-config median
            # that carries no selection optimism. The decision is then made purely on
            # the re-runs, which score the winning configuration alone — the same quantity
            # the bar holds — so both sides of the comparison measure the same thing.
            # Estimate the correction from iterations run the SAME way this one was:
            # pooling band-swept and band-pinned rows would debias a pinned candidate
            # with a number partly measured under sweeping.
            pinned_now = all(k in space for k in BAND_KEYS)
            inflation = _inflation_prior(pinned=pinned_now)
            record["trigger"] = {"inflation_prior": round(inflation, 4),
                                 "debiased_score": round(score - inflation, 4),
                                 "regime": "pinned" if pinned_now else "swept"}
            candidate = _is_candidate(score, best_score, inflation)
            verify_scores = []
            if candidate and VERIFY_SEEDS > 0:
                for k in range(VERIFY_SEEDS):
                    vseed = seed + 1000 * (k + 1)
                    _write_live(live_base, "verifying",
                                f"re-running this genome under seed {vseed} "
                                f"({k + 1}/{VERIFY_SEEDS}) before promoting")
                    vscore = _score_genome(cfg, vseed, data_root, symbols, rbars, rstamps,
                                           dataset, grid, ROOT / f"_verify_{k}",
                                           risk=brain_kwargs)
                    verify_scores.append(vscore)
                    print(f"    verify seed {vseed}: "
                          f"{'failed' if vscore is None else format(vscore, '+.4f')}", flush=True)
                record["verify_scores"] = verify_scores
                record["reproducible_score"] = _median(verify_scores)
            improved = (_promotion_survives(verify_scores, best_score) if VERIFY_SEEDS > 0
                        else _promotion_survives([score], best_score))
            if candidate and not improved:
                print(f"    NOT promoted: single draw {score:+.4f} did not survive re-seeding "
                      f"{[None if v is None else round(v, 4) for v in verify_scores]}", flush=True)
            record["consistency"] = cons
            record["annual"] = {str(y): round(float(per_year[y]["return_pct"]), 4)
                                for y in sorted(per_year)
                                if per_year[y].get("return_pct") is not None}
            record["annual_detail"] = {str(y): per_year[y] for y in sorted(per_year)}
            record["band"] = band
            record["risk"] = {k: brain_kwargs.get(k) for k in ("max_positions", "position_fraction", "stop_loss", "trail_stop")}
            # Surface any active optional lever (vol/breadth/regime + the module levers).
            # Recorded by PRESENCE, not truthiness — see `_stamp_card`: a 0.0 threshold
            # (meta_margin) is an active lever, and dropping it makes the row unreplayable.
            for lever in ("vol_scale", "breadth_gate", "regime_deploy", *MODULE_LEVERS):
                if lever in brain_kwargs:
                    record["risk"][lever] = brain_kwargs[lever]
            record["score"] = score
            record["net_val"] = {k: metrics.get(k) for k in ("accuracy", "net_return", "buy_hold", "avg_trades")}
            grid_str = " ".join(f"{y}:{per_year[y]['return_pct']:+.0%}" for y in sorted(per_year)
                                if per_year[y].get("return_pct") is not None)
            print(f"iter {iteration}: score {score:+.3f} "
                  f"(worst {float(cons['min_year'] or 0):+.1%} cagr {float(cons['cagr'] or 0):+.1%} "
                  f"{'ALL+' if cons['all_positive'] else 'neg'}, "
                  f"risk {record['risk']['max_positions']}/{record['risk']['position_fraction']}/"
                  f"{record['risk']['stop_loss']}/{record['risk']['trail_stop']}, band {band['enter']}/{band['exit_']}/{band['min_hold']}) "
                  f"[{grid_str}]  {'** NEW BEST' if improved else ''}", flush=True)

            # --- the 2026 READOUT for EVERY iteration (operator, 2026-08-29) ----------
            # He is right that the forward year is the only untrained evidence of quality,
            # and a published card without it says nothing about what matters. So every
            # candidate now carries its 2026 figure.
            #
            # The seal is preserved by ORDER, not by good intentions: this runs AFTER
            # `score`, `cons`, `verify_scores` and `improved` are all decided and written
            # above, so no branch below can change what was selected. Nothing downstream
            # of here reads `forward_2026` for scoring - `_consistency`, `_is_candidate`,
            # `_promotion_survives` and `_select_risk_years` all operate on RESEARCH_YEARS
            # only, and `test_forward_readout_never_reaches_selection` pins that.
            try:
                cbars_ro = dataset.combined()
                cstamps_ro = sorted({b.timestamp for s in cbars_ro.values() for b in s})
                r26_ro = launch.year_window(cbars_ro, cstamps_ro, 2026, sig,
                                            brain_kwargs=brain_kwargs)
                record["forward_2026"] = {k: r26_ro.get(k) for k in launch.PER_YEAR_KEYS}
            except Exception as exc:  # noqa: BLE001 - a readout must never stop the loop
                record["forward_2026"] = {"error": str(exc)}

            if improved:
                # Full Jan->Dec grid including the SEALED 2026 readout (never scored).
                _write_live(live_base, "promoting", "new best · sealing 2026 & saving curves",
                            partial={"risk": [brain_kwargs.get(k) for k in
                                     ("max_positions", "position_fraction", "stop_loss", "trail_stop")],
                                     "years": record["annual"]})
                annual = _annual_grid(rbars, rstamps, dataset, sig, per_year, brain_kwargs)
                record["portfolio"] = {"annual": {str(y): annual[y] for y in sorted(annual)}}
                # The new bar is what this champion REPRODUCES, not the draw that won it.
                best_score = record.get("reproducible_score", score) or score
                _stamp_card(SCRATCH, brain_kwargs, cons, annual)
                _promote(SCRATCH)
                _champion_curves(rbars, rstamps, dataset, sig, brain_kwargs)  # real charts
                fw = annual.get(2026, {})
                BEST.write_text(json.dumps({
                    "score": score, "config": cfg, "band": band, "risk": record["risk"],
                    "rationale": rationale,
                    "score_metric": "worst calendar-year return + 0.10*CAGR "
                                    "(each year 2018..2025 an independent account; 2026 sealed)",
                    "consistency": cons, "net_val": record["net_val"],
                    # The bar future candidates must clear: this champion's REPRODUCIBLE
                    # median over its verification re-runs, not the single draw above.
                    "reproducible_bar": record.get("reproducible_score"),
                    "verify_scores": record.get("verify_scores"),
                    "annual_returns": {str(y): annual[y].get("return_pct") for y in sorted(annual)},
                    "annual_detail": {str(y): annual[y] for y in sorted(annual)},
                    "forward_2026": fw, "at": _now(), "iteration": iteration,
                }, indent=2, default=str))
                print(f"    promoted. worst year {float(cons['min_year'] or 0):+.1%}, "
                      f"cagr {float(cons['cagr'] or 0):+.1%}, all-positive={cons['all_positive']}; "
                      f"2026 readout {fw.get('return_pct')} @ dd {fw.get('max_drawdown')}", flush=True)
        except Exception:  # noqa: BLE001 -- one bad config must not stop the loop
            record["error"] = traceback.format_exc().splitlines()[-1]
            print(f"iter {iteration}: FAILED {record['error']}", flush=True)
        finally:
            record["seconds"] = round(time.time() - started, 1)
            _append_ledger(record)
            _idle_live(iteration, best_score, reason="between-iterations")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    hb_stop.set()
    _idle_live(iteration, best_score, reason="stopped")
    print(f"autoloop stopped after {iteration} iterations "
          f"({'stop file' if STOP.exists() or STOP_SELF.exists() else 'budget reached'})", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--data-root", default="backtester/data")
    parser.add_argument("--skip-prepare", action="store_true",
                        help="skip the panel-warming pass (panels already cached)")
    args = parser.parse_args(argv)
    run(hours=args.hours, seed=args.seed, data_root=args.data_root, skip_prepare=args.skip_prepare)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
