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

from . import fast_portfolio, infer, launch, prepare, train, universe
from . import meta as metalabel
from .dataset import Dataset

ROOT = Path("research/system06")
LEDGER = ROOT / "ledger.jsonl"
BEST = ROOT / "best.json"
SEARCH = ROOT / "search.json"
STOP = ROOT / "STOP"
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
}


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
    else the trend timescale). This is the small, structured 'en qué nos basamos' block the live
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
         "label": "Clonación de un oráculo long-only de visión perfecta",
         "setting": f"TCN causal · ventana {cfg.get('window')} velas · umbral {cfg.get('threshold')}",
         "source": "Hipótesis fundacional del sistema (oráculo zigzag · máx-operaciones)",
         "hypothesis": "Una red que imita las entradas/salidas perfectas de un oráculo aprende el "
                       "MECANISMO de un swing, no el precio de una cripto concreta.",
         "expects": "Señales de compra/venta que generalizan entre las 14 criptos agrupadas."},
        {"key": "trend", "active": True, "kind": "riesgo",
         "label": f"Filtro de tendencia a {days} días",
         "setting": f"{days}d · {span} velas de 15m",
         "source": "Ley de consistencia (operador, 2026-08-19) — palanca directa de supervivencia en años bajistas",
         "hypothesis": f"Entrar solo con una tendencia alcista de {days}d+ mantiene el libro plano en "
                       "mercados bajistas amplios (2018, 2022), el problema abierto de la ley de consistencia.",
         "expects": "Subir el PEOR año; menos pérdida en los años bajistas."},
        {"key": "uniqueness", "active": uniq, "kind": "entrenamiento",
         "label": "Ponderación por unicidad de muestra",
         "setting": "ON — cada swing pesa igual" if uniq else "OFF — control (sin ponderar)",
         "source": source("sample-uniqueness", "Lopez de Prado, Advances in Financial ML (cap. 4)"),
         "hypothesis": "Las ventanas se solapan mucho (una etiqueta por vela); pesar cada swing por igual "
                       "(1/duración del tramo) evita sobreajustar los tramos largos redundantes.",
         "expects": "Menos sobreajuste; peor año más alto sin dañar el readout sellado de 2026."},
        {"key": "embargo", "active": emb > 0, "kind": "validación",
         "label": "Validación purgada + embargo",
         "setting": (f"ON — {emb} velas ({max(1, emb // 96)}d) de purga/embargo" if emb > 0
                     else "OFF — control (sin purga)"),
         "source": source("purged-cv", "Lopez de Prado, Advances in Financial ML (cap. 7)"),
         "hypothesis": "Las etiquetas del oráculo se calculan sobre TODA la serie, así que las barras de "
                       "train pegadas al corte 'ven' el futuro por los pivotes; purgarlas + embargar da una "
                       "validación honesta sobre la que seleccionar.",
         "expects": "Cerrar la brecha entre la validación interna y el readout sellado de 2026."},
        {"key": "ensemble", "active": ens > 1, "kind": "arquitectura",
         "label": "Comité de redes (bagging)",
         "setting": (f"ON — {ens} redes promediadas" if ens > 1 else "OFF — 1 sola red"),
         "source": source("ensemble-bagging", "Lopez de Prado — bagging en finanzas; reducción de varianza (ML)"),
         "hypothesis": "Promediar N redes con semillas distintas reduce la VARIANZA — el enemigo directo "
                       "de la consistencia año a año.",
         "expects": "Años más estables; menos dependencia de la suerte de una sola red."},
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
    active_ideas = sum(1 for l in levers if l["active"] and l["kind"] not in ("base", "riesgo"))
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


def _read_best_score() -> float | None:
    """Current champion score on disk — re-read each iteration so an externally
    promoted (or cross-run) champion raises the bar and the loop never regresses."""
    if BEST.is_file():
        try:
            return json.loads(BEST.read_text()).get("score")
        except (OSError, ValueError):
            return None
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
    card["risk_layer"].update({k: brain_kwargs[k] for k in MODULE_LEVERS if brain_kwargs.get(k)})
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
PROMOTE_MARGIN = 0.02  # a candidate must beat the bar by this to replace the champion

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
MODULE_LEVERS = ["meta_margin", "money_kelly", "money_pyramid", "micro_gate", "consensus_k"]
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
    best_score = None
    if BEST.is_file():
        try:
            best_score = json.loads(BEST.read_text()).get("score")
        except (OSError, ValueError):
            best_score = None

    iteration = 0
    while time.time() < deadline and not STOP.exists():
        iteration += 1
        rng = random.Random((seed << 20) ^ iteration)
        space = _load_search()
        cfg = _sample(space, rng)
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
            _write_live(live_base, "training", "arrancando el entrenamiento")
            _last_emit = [0.0]

            def _train_progress(ev, _lb=live_base, _le=_last_emit):
                stage = ev.get("stage")
                nowt = time.time()
                force = bool(ev.get("epoch_done")) or stage in ("building", "evaluating")
                if not force and nowt - _le[0] < 1.2:
                    return
                _le[0] = nowt
                if stage == "building":
                    _write_live(_lb, "training", ev.get("msg", "construyendo dataset"),
                                train={"substage": "building", "dataset": ev.get("dataset")})
                elif stage == "evaluating":
                    _write_live(_lb, "training", "validando + barriendo bandas anti-churn",
                                train={"substage": "evaluating", "loss_curve": ev.get("loss_curve"),
                                       "dataset": ev.get("dataset")})
                else:
                    ep, eps = ev.get("epoch"), ev.get("epochs")
                    b, bs = ev.get("batch"), ev.get("batches")
                    _write_live(_lb, "training", f"época {ep}/{eps} · batch {b}/{bs}",
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
            # Honour a higher bar on disk (manual promotion / another run).
            disk_best = _read_best_score()
            if disk_best is not None and (best_score is None or disk_best > best_score):
                best_score = disk_best
            improved = best_score is None or score > best_score + PROMOTE_MARGIN
            record["consistency"] = cons
            record["annual"] = {str(y): round(float(per_year[y]["return_pct"]), 4)
                                for y in sorted(per_year)
                                if per_year[y].get("return_pct") is not None}
            record["annual_detail"] = {str(y): per_year[y] for y in sorted(per_year)}
            record["band"] = band
            record["risk"] = {k: brain_kwargs.get(k) for k in ("max_positions", "position_fraction", "stop_loss", "trail_stop")}
            # Surface any active optional lever (vol/breadth/regime + the module levers).
            for lever in ("vol_scale", "breadth_gate", "regime_deploy", *MODULE_LEVERS):
                if brain_kwargs.get(lever):
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

            if improved:
                # Full Jan->Dec grid including the SEALED 2026 readout (never scored).
                _write_live(live_base, "promoting", "new best · sealing 2026 & saving curves",
                            partial={"risk": [brain_kwargs.get(k) for k in
                                     ("max_positions", "position_fraction", "stop_loss", "trail_stop")],
                                     "years": record["annual"]})
                annual = _annual_grid(rbars, rstamps, dataset, sig, per_year, brain_kwargs)
                record["portfolio"] = {"annual": {str(y): annual[y] for y in sorted(annual)}}
                best_score = score
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
          f"({'stop file' if STOP.exists() else 'budget reached'})", flush=True)


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
