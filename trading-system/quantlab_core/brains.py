"""The brain registry: how a new strategy becomes launchable.

An agent that writes a new strategy needs one thing to happen automatically --
for the orchestrator to be able to find it by name and run it. That is all this
is: a name, a constructor, and a description.

    from quantlab_core.brains import register, get, available

    @register("my-idea", "buys breakouts above the 55-day high")
    class MyBrain:
        def decide(self, tick) -> Decision: ...

Registering is the ONLY step between writing a brain and having the whole
laboratory able to launch it, backtest it, persist it under an id and show it on
the monitor. There is deliberately no configuration file to edit and no list to
append to somewhere else -- a second place to update is a second place to
forget, and a strategy that exists but cannot be found is worse than one that
does not exist, because nobody knows it is missing.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import sys
import warnings
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class BrainEntry:
    name: str
    description: str
    factory: Callable[..., Any]

    def build(self, **parameters: Any) -> Any:
        return self.factory(**parameters)


_REGISTRY: dict[str, BrainEntry] = {}


def register(name: str, description: str = "") -> Callable[[type], type]:
    """Class decorator. Returns the class unchanged so it stays importable."""

    def decorate(factory):
        key = name.strip().lower()
        if not key:
            raise ValueError("a brain needs a name")
        existing = _REGISTRY.get(key)
        if existing is not None and existing.factory is not factory:
            # Silently replacing would mean two agents' strategies quietly
            # became one, and the loser would still appear to have been tested.
            raise ValueError(
                f"a different brain is already registered as {key!r}: "
                f"{existing.factory.__module__}.{existing.factory.__qualname__}"
            )
        _REGISTRY[key] = BrainEntry(key, description or factory.__doc__ or "", factory)
        return factory

    return decorate


def get(name: str) -> BrainEntry:
    key = name.strip().lower()
    entry = _REGISTRY.get(key)
    if entry is None:
        _discover_systems()
        entry = _REGISTRY.get(key)
    if entry is None:
        raise KeyError(
            f"no brain named {name!r}. Available: {', '.join(sorted(_REGISTRY)) or 'none'}"
        )
    return entry


def available() -> list[dict[str, str]]:
    _discover_systems()
    return [
        {"name": entry.name, "description": entry.description.strip().split("\n")[0]}
        for entry in sorted(_REGISTRY.values(), key=lambda e: e.name)
    ]


def build(name: str, **parameters: Any) -> Any:
    return get(name).build(**parameters)


def _register_builtins() -> None:
    """The one brain the shared runtime owns.

    `MandateBrain` lives in `runner.py`, which is part of this package, so
    registering it here couples nothing. Everything else is a SYSTEM and is
    found by `_discover_systems` below.
    """
    from .runner import MandateBrain

    if "mandate" not in _REGISTRY:
        register(
            "mandate",
            "Trend participation above the 50 and 200 day averages, with the "
            "drawdown mandate enforced against the deposit.",
        )(MandateBrain)


_SYSTEM = re.compile(r"^system\d{3}_[a-z0-9_]+$")

# `trading-system/systems/`, found from this file rather than from a working
# directory. This package sits at `trading-system/quantlab_core/`, so the folder
# is its sibling. Reading a sibling's NAME is not a dependency on it -- nothing
# here imports a system, and the registry still holds no list of which exist.
_SYSTEMS_DIR = Path(__file__).resolve().parent.parent / "systems"
_discovered = False


def _discover_systems() -> None:
    """Import every numbered system package, for its `@register` side effects.

    This used to be one hard-coded `from . import regime_system` at the foot of
    this file, which meant the shared runtime imported a strategy -- the exact
    coupling the folder split exists to prevent, and a cycle that once stopped
    the loop from starting at all (`cannot import name 'FourModuleBrain' from
    partially initialized module`).

    A system is now found by the shape of its name on `sys.path`, so adding one
    is adding a folder and nothing else. Discovery is lazy and runs once: it is
    triggered by `available()`, and by `get()` only when the name asked for is
    not already registered, so a process that imports its own strategy directly
    never pays for importing anyone else's.

    A system that cannot be imported is a warning, not a crash. The alternative
    is that one system with a missing optional dependency makes every other
    system unlaunchable on that machine.
    """
    global _discovered
    if _discovered:
        return
    _discovered = True  # set first: a failing import must not be retried forever

    # Two sources, because neither alone is enough. `iter_modules` walks the
    # real directories on `sys.path` and misses an editable install, whose
    # packages arrive through a meta-path finder it never asks. The folder scan
    # covers that, and covers a checkout nobody has installed at all.
    names = {m.name for m in pkgutil.iter_modules() if _SYSTEM.match(m.name)}
    if _SYSTEMS_DIR.is_dir():
        names |= {
            p.name for p in _SYSTEMS_DIR.iterdir()
            if p.is_dir() and _SYSTEM.match(p.name) and (p / "__init__.py").exists()
        }
        if names and str(_SYSTEMS_DIR) not in sys.path:
            sys.path.append(str(_SYSTEMS_DIR))

    for name in sorted(names):
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - see the docstring
            warnings.warn(
                f"system {name} could not be imported and its brains are "
                f"not registered: {exc.__class__.__name__}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )


_register_builtins()
