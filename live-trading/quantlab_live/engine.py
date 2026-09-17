"""The swappable heart: an engine package in, a brain that decides live out.

Operator, 2026-09-17: *"when you have a better algorithm you simply change the engine,
but we keep trading... it has to be replaceable - the money-management functions, the
model that makes the decisions - and it has to manage the current portfolio as it is."*

An **engine package** is a directory under `live-trading/engines/<version>/` holding
everything a decision needs and nothing it does not:

    manifest.json      version, provenance, band, risk levers, what it scored
    config.json        the net's architecture and feature layout
    standardizer.json  the feature scaling that travels with the weights
    oracle_net*.pt     the weights (several files = a bagged ensemble)

`engines/current.json` names the live one. Promotion is a file write; the trader picks it
up between bars and the book never resets.

Three things this module refuses to do, each of which would quietly turn the live system
into a different one from the tested system:

* **It does not re-implement inference.** Signals come from `infer.export`, the same
  function the backtest and every experiment use, over the same catalogue candles.
* **It does not trade without the overlays a lever declares.** `Channels` makes a module
  abstain when its overlay is missing - excellent behaviour for research, a silent
  strategy change in production. `assert_feedable()` compares the manifest's levers
  against what is actually on disk and refuses to start otherwise.
* **It does not lose the brain's soft state.** Minimum-hold counters, trailing high-water
  marks and tranche counts live inside the ensemble object. A restart that dropped them
  would sell early and trail from the wrong level, so they are saved every bar and
  restored on load.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config


@dataclass(frozen=True)
class EnginePackage:
    """One promotable engine: the net, the band, the risk levers, and where it came from."""

    version: str
    path: Path
    manifest: dict[str, Any]

    @property
    def band(self) -> dict[str, Any]:
        return dict(self.manifest["band"])

    @property
    def risk(self) -> dict[str, Any]:
        return dict(self.manifest["risk"])

    @property
    def trend_span(self) -> int:
        return int(self.manifest.get("config", {}).get("trend_span", 5760))

    @property
    def needs_meta(self) -> bool:
        return self.risk.get("meta_margin") is not None

    @property
    def needs_money(self) -> bool:
        return float(self.risk.get("money_model") or 0) > 0

    @classmethod
    def load(cls, version: str) -> "EnginePackage":
        path = config.ENGINES / version
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"no engine package at {path}")
        return cls(version=version, path=path,
                   manifest=json.loads(manifest_path.read_text(encoding="utf-8")))

    @classmethod
    def current(cls) -> "EnginePackage":
        """Whatever `engines/current.json` points at, read fresh every time it is asked."""
        pointer = json.loads(config.CURRENT_ENGINE.read_text(encoding="utf-8"))
        return cls.load(pointer["version"])


def promote(version: str, source_model_dir: Path, best: dict[str, Any],
            provenance: str, metrics: dict[str, Any] | None = None) -> EnginePackage:
    """Build an engine package from a trained model directory and a `best.json` body.

    Copies rather than references: an engine that pointed at the laboratory's working
    files would change under the trader's feet the next time an experiment wrote there.
    A package is a photograph, and the manifest records what it was a photograph OF.
    """
    target = config.ENGINES / version
    target.mkdir(parents=True, exist_ok=True)
    source_model_dir = Path(source_model_dir)
    copied = []
    for pattern in ("config.json", "standardizer.json", "oracle_net*.pt", "model_card.json"):
        for src in sorted(source_model_dir.glob(pattern)):
            shutil.copy2(src, target / src.name)
            copied.append(src.name)
    manifest = {
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "system": "system006_oracle_net_15m",
        "provenance": provenance,
        "band": best["band"],
        "risk": best["risk"],
        "config": best.get("config", {}),
        "files": copied,
        "metrics": metrics or {},
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return EnginePackage(version=version, path=target, manifest=manifest)


def set_current(version: str, why: str) -> dict[str, Any]:
    """Point the trader at a package. The swap itself is one atomic file write."""
    EnginePackage.load(version)  # refuse to point at something that does not exist
    pointer = {"version": version, "since": datetime.now(timezone.utc).isoformat(), "why": why}
    config.ENGINES.mkdir(parents=True, exist_ok=True)
    tmp = config.CURRENT_ENGINE.with_suffix(".tmp")
    tmp.write_text(json.dumps(pointer, indent=1), encoding="utf-8")
    tmp.replace(config.CURRENT_ENGINE)
    return pointer


class LiveEngine:
    """Keeps one package's signals fresh and hands back a brain that decides on them."""

    def __init__(self, package: EnginePackage, symbols: list[str] | None = None,
                 data_root: str | None = None):
        from quantlab_catalog.paths import DATA_ROOT  # noqa: PLC0415

        self.package = package
        self.symbols = symbols or config.universe()
        self.data_root = data_root or str(DATA_ROOT)
        self.cache = config.STATE_DIR / "engine_cache" / package.version
        self.cache.mkdir(parents=True, exist_ok=True)
        self.signals_path = self.cache / "signals.npz"
        self.meta_path = self.cache / "meta.npz"
        self.money_path = self.cache / "moneymodel.npz"
        self.soft_state_path = config.STATE_DIR / "brain_state.json"
        self._brain = None
        self._refreshed_at: datetime | None = None
        self._overlays_at: datetime | None = None

    # -- keeping the channels current -----------------------------------------

    def refresh_signals(self, min_age_seconds: float = 0.0) -> dict[str, Any]:
        """Recompute the net's channels over catalogue history plus everything since.

        `Dataset.combined()` downloads and caches whatever candles are missing, so this
        is also how the newest bars reach the live layer: one loader, one cache, one
        definition of what a bar is - the same one the backtest reads.

        `min_age_seconds` skips the work when the file is younger than that. Startup
        refreshes in order to build the brain at all, and the first bar would otherwise
        repeat the same full export minutes later against the same candles.
        """
        from system006_oracle_net_15m import infer  # noqa: PLC0415

        if (min_age_seconds and self._refreshed_at is not None
                and (datetime.now(timezone.utc) - self._refreshed_at).total_seconds()
                < min_age_seconds):
            return {"skipped": "signals are younger than the window"}

        facts = infer.export(data_root=self.data_root, symbols=self.symbols,
                             model_dir=str(self.package.path),
                             out_path=str(self.signals_path),
                             trend_span=self.package.trend_span)
        self._refreshed_at = datetime.now(timezone.utc)
        return facts

    def refresh_overlays(self, bars: dict[str, list] | None = None) -> dict[str, Any]:
        """Rebuild the meta-label verdicts and the money-model sizing for the same bars.

        Both are functions of the signals file and the candles, and both are causal by
        construction (meta issues a verdict from a model trained only on candidates that
        had already resolved). They are the expensive half of a refresh, which is why the
        trader rebuilds them on a slower clock - except when the current bar is itself a
        candidate, where a missing verdict would change the decision.
        """
        from system006_oracle_net_15m import meta as metalabel  # noqa: PLC0415
        from system006_oracle_net_15m import moneymodel  # noqa: PLC0415
        from system006_oracle_net_15m.dataset import Dataset  # noqa: PLC0415

        band = self.package.band
        out: dict[str, Any] = {}
        if self.package.needs_meta:
            dataset = Dataset(data_root=self.data_root, symbols=self.symbols,
                              interval=config.INTERVAL)
            candidates = metalabel.gather_candidates(dataset, str(self.signals_path),
                                                     self.symbols,
                                                     enter=float(band["enter"]))
            verdicts, _doc = metalabel.build_verdicts(candidates)
            metalabel.write_meta(verdicts, str(self.meta_path))
            out["meta_symbols"] = len(verdicts)
        if self.package.needs_money:
            risk = self.package.risk
            overlay = moneymodel.build_sizing(
                str(self.signals_path), self.data_root,
                enter=float(band["enter"]), exit_=float(band["exit_"]),
                min_hold=int(band["min_hold"]),
                stop_loss=float(risk.get("stop_loss") or 0.0),
                trail_stop=float(risk.get("trail_stop") or 0.0),
                research=bars)
            moneymodel.write_sizing(overlay, str(self.money_path))
            out["money_symbols"] = len(overlay)
        self._overlays_at = datetime.now(timezone.utc)
        return out

    def latest_signal_stamp(self) -> datetime | None:
        """The newest bar the CHANNELS actually cover, across all symbols.

        The trader must decide on this bar and no later. A refresh takes minutes, so by
        the time it finishes the venue has closed one or two more candles, and a tick
        built from the newest CANDLE asks the channels for a timestamp they do not have.
        `Channels.prob` answers a missing timestamp with 0.0 - no conviction - so the
        live book read 0.000 on all fourteen symbols, every bar, and would never have
        bought anything for as long as it ran. Nothing raised; it simply never traded.
        """
        import numpy as np  # noqa: PLC0415

        if not self.signals_path.is_file():
            return None
        with np.load(self.signals_path) as z:
            newest = max((int(z[k][-1]) for k in z.files
                          if k.endswith("__epoch_ns") and len(z[k])), default=None)
        if newest is None:
            return None
        return datetime.fromtimestamp(newest / 1e9, tz=timezone.utc)

    def assert_feedable(self) -> None:
        """Refuse to trade a configuration whose overlays are not actually present."""
        missing = []
        if not self.signals_path.is_file():
            missing.append("signals")
        if self.package.needs_meta and not self.meta_path.is_file():
            missing.append("meta (meta_margin is set)")
        if self.package.needs_money and not self.money_path.is_file():
            missing.append("money model (money_model > 0)")
        if missing:
            raise RuntimeError(
                "the live engine cannot feed every lever this package declares: "
                + ", ".join(missing)
                + ". Trading now would silently run a DIFFERENT configuration, because a "
                  "missing overlay makes its module abstain rather than fail.")

    # -- the brain -------------------------------------------------------------

    def build_brain(self, trade_from: str | None = None):
        """One brain per engine version, carrying its soft state across restarts."""
        from system006_oracle_net_15m.strategy import OracleNetBrain  # noqa: PLC0415

        self.assert_feedable()
        band, risk = self.package.band, self.package.risk
        kwargs = dict(risk)
        kwargs.update(enter=float(band["enter"]), exit_=float(band["exit_"]),
                      min_hold=int(band["min_hold"]))
        if self.package.needs_meta:
            kwargs["meta_signals"] = str(self.meta_path)
        if self.package.needs_money:
            kwargs["size_signals"] = str(self.money_path)
        brain = OracleNetBrain(signals=str(self.signals_path),
                               trade_from=trade_from or config.CUTOVER.isoformat(),
                               model_tag=self.package.version, **kwargs)
        self._brain = brain
        self._restore_soft_state(brain)
        return brain

    def reload_channels(self, brain) -> None:
        """Point an EXISTING brain at the refreshed channels, keeping its state.

        Rebuilding the brain each bar would reset the minimum-hold counters and the
        trailing high-water marks - the live book would then behave like a strategy that
        forgets, every fifteen minutes, that it is already in a trade.
        """
        from system006_oracle_net_15m.channels import Channels  # noqa: PLC0415

        self.assert_feedable()
        brain._brain._channels = Channels.from_file(
            str(self.signals_path),
            meta_path=str(self.meta_path) if self.package.needs_meta else None,
            size_path=str(self.money_path) if self.package.needs_money else None)

    # -- soft state ------------------------------------------------------------

    def save_soft_state(self, brain) -> None:
        inner = brain._brain
        state = {
            "version": self.package.version,
            "at": datetime.now(timezone.utc).isoformat(),
            "equity_peak": getattr(inner, "_equity_peak", 0.0),
            "peak": {k: float(v) for k, v in getattr(inner, "_peak", {}).items()},
            "tranches": {k: int(v) for k, v in getattr(inner, "_tranches", {}).items()},
            "last_fill": {k: float(v) for k, v in getattr(inner, "_last_fill", {}).items()},
        }
        self.soft_state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.soft_state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        tmp.replace(self.soft_state_path)

    def _restore_soft_state(self, brain) -> None:
        if not self.soft_state_path.is_file():
            return
        try:
            state = json.loads(self.soft_state_path.read_text(encoding="utf-8"))
        except ValueError:
            return
        inner = brain._brain
        inner._equity_peak = float(state.get("equity_peak") or 0.0)
        inner._peak = {k: float(v) for k, v in (state.get("peak") or {}).items()}
        inner._tranches = {k: int(v) for k, v in (state.get("tranches") or {}).items()}
        inner._last_fill = {k: float(v) for k, v in (state.get("last_fill") or {}).items()}
