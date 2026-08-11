"""The brain registry: how a new strategy becomes launchable.

An agent that writes a new strategy needs one thing to happen automatically --
for the orchestrator to be able to find it by name and run it. That is all this
is: a name, a constructor, and a description.

    from quantlab_trading.brains import register, get, available

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
        raise KeyError(
            f"no brain named {name!r}. Available: {', '.join(sorted(_REGISTRY)) or 'none'}"
        )
    return entry


def available() -> list[dict[str, str]]:
    return [
        {"name": entry.name, "description": entry.description.strip().split("\n")[0]}
        for entry in sorted(_REGISTRY.values(), key=lambda e: e.name)
    ]


def build(name: str, **parameters: Any) -> Any:
    return get(name).build(**parameters)


def _register_builtins() -> None:
    """Registered on import so the registry is never empty in a fresh process.

    `regime_system` is imported for its `@register` side effect: the operator's
    four-module system has to be launchable by name from a fresh process, and a
    strategy that exists but cannot be found is worse than one that does not
    exist, because nobody knows it is missing.
    """
    from .runner import MandateBrain

    if "mandate" not in _REGISTRY:
        register(
            "mandate",
            "Trend participation above the 50 and 200 day averages, with the "
            "drawdown mandate enforced against the deposit.",
        )(MandateBrain)
    from . import regime_system  # noqa: F401
    from . import codex_regime_system  # noqa: F401


_register_builtins()
