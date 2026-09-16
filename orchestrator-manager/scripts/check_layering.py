#!/usr/bin/env python3
"""Enforce the folder contract: the instrument must not know about strategies.

The whole value of the split is that a contributed strategy cannot reach into
sizing, costs or scoring. That property is one careless import away from being
false, and nothing about a passing test suite would reveal it -- the tests would
go green and the numbers would quietly stop being comparable.

    python orchestrator-manager/scripts/check_layering.py

Three layers, and one exception that is deliberate:

    backtester/           the frozen instrument. Imports nothing above it.
    trading-system/       quantlab_core, quantlab_catalog, quantlab_ml (shared),
                          plus systems/systemNNN_* (one hypothesis each).
    orchestrator-manager/ the lab. May compose everything.

THE EXCEPTION IS LINEAGE. A generation that branches from an earlier one may
import it, and only it -- system 005 is system 002's entries filtered by a
second model, and refusing the import would mean copying the parent's money
management into the child, where it could drift and quietly stop being the same
measurement. Every such edge is listed in LINEAGE below with the reason. An
import between two systems that is NOT in that table is a violation, because it
would let one system's edit change another system's recorded result.

Exit status is 1 on the first violation, so this belongs in CI and in the L1
pre-commit gate.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# The repository root: this file sits at <root>/orchestrator-manager/scripts/.
# It used to be `parent.parent`, which pointed at `orchestrator-manager/` and
# made every folder below resolve to a path that does not exist -- the check
# had been finding zero files and printing "layering ok" for weeks.
ROOT = Path(__file__).resolve().parents[2]
SYSTEMS_DIR = ROOT / "trading-system" / "systems"

# Shared packages, each with the folder its source sits in.
SHARED = {
    "quantlab_backtester": ROOT / "backtester",
    "quantlab_core": ROOT / "trading-system",
    "quantlab_catalog": ROOT / "trading-system",
    "quantlab_ml": ROOT / "trading-system",
    "quantlab_manager": ROOT / "orchestrator-manager",
}

# Every numbered system, discovered rather than listed: a new system is a new
# folder and nothing else, and a list here would be a second place to forget.
SYSTEMS = {
    p.name: SYSTEMS_DIR
    for p in sorted(SYSTEMS_DIR.iterdir())
    if p.is_dir() and p.name.startswith("system") and (p / "__init__.py").exists()
}

PACKAGES = {**SHARED, **SYSTEMS}

# What a system may import besides its own modules.
SYSTEM_ALLOWANCE = {"quantlab_backtester", "quantlab_core", "quantlab_catalog", "quantlab_ml"}

# The branch table: child -> the parent it is a generation of, and why.
LINEAGE = {
    "system004_llm_written_rules": (
        "system002_intraday_momentum_5m",
        "generation four writes strategies against generation two's harness",
    ),
    "system005_meta_label_filter": (
        "system002_intraday_momentum_5m",
        "generation five is generation two's entries, filtered by a second model",
    ),
    "system007_capitulation_dip": (
        "system006_oracle_net_15m",
        "007 is measured as a combine with 006, so it reads 006's signal directly",
    ),
}

ALLOWED: dict[str, set[str]] = {
    "quantlab_backtester": set(),
    "quantlab_core": {"quantlab_backtester"},
    "quantlab_catalog": {"quantlab_backtester"},
    "quantlab_ml": {"quantlab_backtester", "quantlab_core", "quantlab_catalog"},
    "quantlab_manager": set(PACKAGES) - {"quantlab_manager"},
}
for name in SYSTEMS:
    parent = LINEAGE.get(name, (None, None))[0]
    ALLOWED[name] = SYSTEM_ALLOWANCE | ({parent} if parent else set())

REASON = {
    "quantlab_backtester": (
        "the backtester is the frozen instrument and must decide nothing; if it "
        "imports a strategy or the manager, results stop being comparable"
    ),
    "quantlab_core": (
        "the shared runtime may use the data contract but must not depend on any "
        "strategy, or a strategy could not be scored in isolation"
    ),
    "quantlab_catalog": "the data catalogue serves data and decides nothing",
    "quantlab_ml": "the learning library is shared by several systems and must not prefer one",
    "quantlab_manager": "the manager may compose everything",
}
_SYSTEM_REASON = (
    "a system may import the shared packages and the one generation it branched "
    "from (see LINEAGE); any other system import would let one hypothesis change "
    "another hypothesis's recorded result"
)


def imported_packages(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # a broken file is a different failure
        print(f"cannot parse {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
        return set()
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
    return found & set(PACKAGES)


def main() -> int:
    violations = []
    for package, folder in PACKAGES.items():
        # Only the shipped package is bound by the rule. Tests may cross layers,
        # because an integration test that could not compose them would be
        # testing nothing.
        for path in sorted((folder / package).rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            for imported in imported_packages(path):
                if imported != package and imported not in ALLOWED[package]:
                    violations.append((path.relative_to(ROOT), package, imported))

    if not violations:
        print(f"layering ok: {len(SYSTEMS)} systems, {len(SHARED)} shared packages")
        return 0

    print("LAYERING VIOLATIONS\n", file=sys.stderr)
    for path, package, imported in violations:
        print(f"  {path}", file=sys.stderr)
        print(f"    {package} must not import {imported}", file=sys.stderr)
        print(f"    {REASON.get(package, _SYSTEM_REASON)}", file=sys.stderr)
    print(f"\n{len(violations)} violation(s). See CONTRACT.md.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
