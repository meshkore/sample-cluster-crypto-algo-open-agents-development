#!/usr/bin/env python3
"""Enforce the folder contract: the instrument must not know about strategies.

The whole value of the three-way split is that a contributed strategy cannot
reach into sizing, costs or scoring. That property is one careless import away
from being false, and nothing about a passing test suite would reveal it -- the
tests would go green and the numbers would quietly stop being comparable.

    python3 orchestrator-manager/scripts/check_layering.py

Exit status is 1 on the first violation, so this belongs in CI and in the L1
pre-commit gate.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACKAGES = {
    "quantlab_backtester": ROOT / "backtester",
    "quantlab_trading": ROOT / "trading-system",
    "quantlab_manager": ROOT / "orchestrator-manager",
}

# Who is allowed to import whom. Anything absent is forbidden.
ALLOWED = {
    "quantlab_backtester": set(),
    "quantlab_trading": {"quantlab_backtester"},
    "quantlab_manager": {"quantlab_backtester", "quantlab_trading"},
}

REASON = {
    "quantlab_backtester": (
        "the backtester is the frozen instrument and must decide nothing; if it "
        "imports a strategy or the manager, results stop being comparable"
    ),
    "quantlab_trading": (
        "the trading system may use the data contract but must not depend on the "
        "lab that runs it, or a strategy could not be scored in isolation"
    ),
    "quantlab_manager": "the manager may compose both",
}


def imported_packages(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
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
        source = folder / package
        for path in sorted(source.rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            for imported in imported_packages(path):
                if imported != package and imported not in ALLOWED[package]:
                    violations.append((path.relative_to(ROOT), package, imported))

    if not violations:
        print("layering ok: backtester imports nothing above it")
        return 0

    print("LAYERING VIOLATIONS\n", file=sys.stderr)
    for path, package, imported in violations:
        print(f"  {path}", file=sys.stderr)
        print(f"    {package} must not import {imported}", file=sys.stderr)
        print(f"    {REASON[package]}", file=sys.stderr)
    print(f"\n{len(violations)} violation(s). See CONTRACT.md.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
