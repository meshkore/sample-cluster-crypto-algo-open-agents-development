"""Shared test isolation.

System 10's switch files live in research/system10/ (FREEZE_PAPER_SWAPS, ENABLE_MEASURED_BAND,
ENABLE_NESTED_ELIGIBILITY, ENABLE_BOOK_RELEASES). Since 2026-10-15 some are ON in the real
repo, and tests that did not patch them read the live state. Every test starts with each flag
pointed at a fresh, absent path under tmp_path; a test that needs a flag sets it itself
(monkeypatch.setattr(..., tmp_path / NAME) and writes the file), as they already do.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _system010_flags_off(tmp_path, monkeypatch):
    try:
        from system010_conditioned_rl import overfit as O
        from system010_conditioned_rl import paper as P
        from system010_conditioned_rl import search as S
    except Exception:  # noqa: BLE001 - suites that cannot import system 10 are unaffected
        yield
        return
    off = tmp_path / "_flags_off"
    for mod in (P, O, S):
        for name in dir(mod):
            if name.endswith("FLAG"):
                monkeypatch.setattr(mod, name, off / name)
    yield
