"""System 001 - the original rule grammar and the regime router (2026-08-06).

Importing this package registers its brains. The modules are pulled in here,
at the package level, rather than from the shared registry: the registry must
not know which systems exist, and a system that is imported must be launchable
by name from that moment on.
"""

from __future__ import annotations

# `regime_system` pulls in `codex_regime_system` at its own foot, once its
# base classes exist. Importing both here would re-enter it half-built.
from . import regime_system  # noqa: F401 - registration side effect
