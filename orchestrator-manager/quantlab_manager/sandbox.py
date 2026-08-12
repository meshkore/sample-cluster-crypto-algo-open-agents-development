"""The boundary that makes an unattended code-writing loop acceptable.

Until now this project refused outright to let the loop author source: `team.py`
said "one member writes code, and never from inside an unattended process". The
operator has lifted that, with a condition — *the loop may write code, as long as
it cannot damage the systems that already work*. This file is that condition,
made mechanical.

**The model never receives a tool.** It returns Python as a JSON string, exactly
as the proposer returns a parameter dict, and THIS module decides whether those
bytes are ever written and where. So there is no file-writing agent to contain:
there is a text generator and a gate. The distinction matters because a tool-using
agent has to be sandboxed at the operating system, while a string has to pass a
parser.

**The gate is a whitelist, not a blacklist.** Every import is checked against a
list of modules a strategy legitimately needs; anything else is refused. Every
name is checked against a list of builtins that cannot reach outside the process.
A blacklist of "dangerous" names is the classic wrong answer here — it fails open
on the one spelling nobody thought of, and `getattr(__builtins__, "e" + "val")`
is the whole genre.

**Three things are structurally impossible for generated code**, not by policy but
because the names do not resolve:

- **Touching the filesystem.** No `open`, no `os`, no `pathlib`, no `shutil`. So
  generated code cannot edit the systems that already work — the operator's
  actual requirement — and cannot rewrite this gate either.
- **Reaching the network.** No `socket`, `urllib`, `http`, `requests`, `subprocess`.
  This is also how the project's standing rule that there is never live-order,
  wallet or exchange-secret capability stops being a promise and starts being a
  property: the code has no way to send anything anywhere.
- **Escaping the whitelist at runtime.** No `eval`, `exec`, `compile`,
  `__import__`, `globals`, `getattr`, and no dunder attribute access — because
  `().__class__.__bases__[0].__subclasses__()` is a complete escape from every
  restriction above and reads like ordinary punctuation.

**The gate runs before the import.** Importing a module executes it, so a check
performed after the import has already lost. Everything here is AST-only and
touches nothing.

**A static gate cannot bound behaviour, only capability.** Generated code may
still loop for ever or allocate until the machine complains. That is handled
where it belongs — `verify()` runs the candidate in a separate process with a
timeout — and it is worth being explicit that these are two different guarantees:
the parser decides what the code may REACH, the subprocess decides how long it
may RUN.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# Where generated systems live. One folder per champion generation: the loop
# works inside the current one until something beats the sealed incumbent, and
# only then does the next open. Nothing here may be written outside this tree.
WORKSHOP = ROOT / "trading-system"
WORKSHOP_PREFIX = "quantlab_system"

# What a strategy is allowed to import. Read access to the existing systems is
# deliberately granted -- importing a module is not mutating it, and a new idea
# that cannot reuse the money management or the indicator context would be
# rewritten badly from scratch every time.
ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "__future__",
        "collections",
        "collections.abc",
        "dataclasses",
        "datetime",
        "enum",
        "functools",
        "itertools",
        "math",
        "statistics",
        "typing",
        "numpy",
        "quantlab_backtester.indicators",
        "quantlab_trading.brains",
        "quantlab_trading.policy",
        "quantlab_trading.runner",
        "quantlab_intraday.context",
        "quantlab_intraday.moneymanagement",
    }
)

# Builtins a strategy may name. Everything absent from this set is refused,
# including every builtin that opens a file, starts a process, or reaches the
# interpreter's own machinery.
ALLOWED_BUILTINS: frozenset[str] = frozenset(
    {
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "print",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "type",
        "zip",
        "True",
        "False",
        "None",
        "Exception",
        "ValueError",
        "KeyError",
        "TypeError",
        "IndexError",
        "ZeroDivisionError",
        "ArithmeticError",
        "RuntimeError",
        "NotImplementedError",
        "StopIteration",
        "property",
        "staticmethod",
        "classmethod",
        "super",
        "object",
        "__name__",
        "__doc__",
    }
)

# Attribute names that are an escape hatch out of everything above. `__class__`
# leads to `__bases__` leads to `__subclasses__` leads to every loaded class in
# the process, including the ones that open files.
FORBIDDEN_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "__class__",
        "__bases__",
        "__base__",
        "__subclasses__",
        "__mro__",
        "__globals__",
        "__code__",
        "__closure__",
        "__func__",
        "__self__",
        "__builtins__",
        "__import__",
        "__dict__",
        "__getattribute__",
        "__reduce__",
        "__reduce_ex__",
        "__init_subclass__",
        "__loader__",
        "__spec__",
        "__module__",
        "__wrapped__",
        "__defaults__",
        "__kwdefaults__",
    }
)

MAXIMUM_SOURCE_BYTES = 120_000


@dataclass
class Verdict:
    """Whether these bytes may be written, and every reason they may not."""

    ok: bool
    refusals: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    registered: list[str] = field(default_factory=list)

    def document(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "refusals": self.refusals,
            "imports": sorted(set(self.imports)),
            "registered": self.registered,
        }


def _module_root(name: str) -> str:
    return name.split(".")[0]


def _import_allowed(name: str) -> bool:
    """Allowed if the module itself, or a package it lives under, is listed.

    `numpy.linalg` is allowed by `numpy`; `os.path` is not allowed by anything.
    Checked by dotted PREFIX rather than by `startswith` on the raw string,
    because `numpy_evil` starts with `numpy` and is a different package.
    """
    if name in ALLOWED_IMPORTS:
        return True
    parts = name.split(".")
    return any(".".join(parts[:i]) in ALLOWED_IMPORTS for i in range(1, len(parts)))


def inspect(source: str) -> Verdict:
    """Read the source without running it, and say whether it may be written.

    Refusals are collected rather than raised at the first one: a coder that is
    told all four of its mistakes fixes them in one pass, and one that is told
    only the first burns an iteration per mistake.
    """
    verdict = Verdict(ok=False)

    if len(source.encode("utf-8")) > MAXIMUM_SOURCE_BYTES:
        verdict.refusals.append(
            f"source is larger than {MAXIMUM_SOURCE_BYTES} bytes; a strategy this "
            "big is not a strategy"
        )
        return verdict

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        verdict.refusals.append(f"does not parse: {exc}")
        return verdict

    assigned: set[str] = set()
    for node in ast.walk(tree):
        # Names the module defines for itself are not builtins and must not be
        # judged against the builtin whitelist. Collected first, over the whole
        # tree, because Python is not read top to bottom -- a method may call a
        # helper defined below it.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(node.name)
            for argument in getattr(node, "args", ast.arguments()).args:
                assigned.add(argument.arg)
            for argument in getattr(node, "args", ast.arguments()).kwonlyargs:
                assigned.add(argument.arg)
            vararg = getattr(getattr(node, "args", None), "vararg", None)
            if vararg is not None:
                assigned.add(vararg.arg)
            kwarg = getattr(getattr(node, "args", None), "kwarg", None)
            if kwarg is not None:
                assigned.add(kwarg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            assigned.add(node.id)
        elif isinstance(node, ast.alias):
            assigned.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, (ast.comprehension,)):
            for name in ast.walk(node.target):
                if isinstance(name, ast.Name):
                    assigned.add(name.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            assigned.add(node.name)

    registered: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                verdict.imports.append(alias.name)
                if not _import_allowed(alias.name):
                    verdict.refusals.append(f"import of {alias.name!r} is not allowed")

        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module name to check and can reach a
            # sibling file this gate never saw.
            if node.level:
                verdict.refusals.append(
                    "relative imports are not allowed; name the module in full"
                )
                continue
            name = node.module or ""
            verdict.imports.append(name)
            if not _import_allowed(name):
                verdict.refusals.append(f"import of {name!r} is not allowed")
            if any(alias.name == "*" for alias in node.names):
                # Star imports make the name analysis below unsound: anything
                # could now be in scope and every unknown name would have to be
                # given the benefit of the doubt.
                verdict.refusals.append("`import *` is not allowed")

        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES:
                verdict.refusals.append(
                    f"attribute {node.attr!r} is an escape from this whitelist"
                )

        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in assigned and node.id not in ALLOWED_BUILTINS:
                verdict.refusals.append(f"name {node.id!r} is not available here")

        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            verdict.refusals.append("`global`/`nonlocal` are not allowed")

        elif isinstance(node, ast.Call):
            decorated = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None
            )
            if decorated == "register" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    registered.append(first.value)

    verdict.registered = registered
    if not registered:
        verdict.refusals.append(
            "nothing is registered; a strategy the laboratory cannot launch by "
            "name is not a strategy"
        )

    verdict.ok = not verdict.refusals
    return verdict


def workshop_path(generation: int, filename: str = "strategy.py") -> Path:
    """Where generation N's code lives. Computed here, never supplied by a model.

    A path that arrives from a model is a path that can be `../../`. The coder
    names a strategy; it does not name a location.
    """
    if generation < 4:
        # One, two and three are the systems that already exist and work.
        raise ValueError("generations below 4 are the existing systems")
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise ValueError(f"{filename!r} is not a plain file name")
    if not filename.endswith(".py"):
        raise ValueError("a strategy is a .py file")
    return WORKSHOP / f"{WORKSHOP_PREFIX}{generation:02d}" / filename


def inside_workshop(path: Path) -> bool:
    """True only for a real location under the workshop tree.

    `resolve()` before comparing, so a symlink planted inside the workshop that
    points at `trading-system/quantlab_intraday/` does not pass.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False
    try:
        relative = resolved.relative_to(WORKSHOP.resolve())
    except ValueError:
        return False
    return relative.parts and relative.parts[0].startswith(WORKSHOP_PREFIX)


def write(source: str, generation: int, filename: str = "strategy.py") -> Path:
    """Gate, then write. The only function in this project that commits model
    output to disk, and it refuses more often than it writes."""
    path = workshop_path(generation, filename)
    if not inside_workshop(path.parent / filename):
        raise ValueError(f"{path} is not inside the workshop")
    verdict = inspect(source)
    if not verdict.ok:
        raise PermissionError(
            "refused:\n" + "\n".join(f"  - {r}" for r in verdict.refusals)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    init = path.parent / "__init__.py"
    if not init.exists():
        init.write_text(
            f'"""Generation {generation}, written by the loop under '
            f'`quantlab_manager.sandbox`."""\n'
        )
    path.write_text(source)
    return path


PROTECTED = (
    "backtester",
    "trading-system/quantlab_trading",
    "trading-system/quantlab_intraday",
    "trading-system/quantlab_ml",
    "orchestrator-manager/quantlab_manager",
)


def modified(paths: tuple[str, ...] | list[str] | None = None) -> set[str]:
    """Which protected paths the working tree has dirty, right now."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", *(paths or PROTECTED)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        # An unanswerable question is not an all-clear.
        return {"<could not ask git>"}
    if result.returncode != 0:
        return {"<could not ask git>"}
    return {line[3:].strip() for line in result.stdout.splitlines() if line.strip()}


def untouched(baseline: set[str] | None = None) -> list[str]:
    """What the loop has dirtied SINCE it started. The operator's rule, checked.

    The gate above makes it impossible for GENERATED code to edit the working
    systems. This is the other half: evidence that the loop's own machinery has
    not either, taken from git rather than trusted.

    **Measured against a baseline, and that is not a loophole.** The question
    worth answering is "did this loop damage anything", not "is the repository
    pristine" — an operator half-way through an edit when the loop starts would
    otherwise stall it for hours, and a loop that cries wolf at its own author's
    unsaved work teaches everyone to ignore it. The baseline is taken once at
    startup and never refreshed, so anything the loop dirties afterwards shows
    up and stays showing up.
    """
    now = modified()
    return sorted(now - (baseline or set()))


def verify(timeout: float = 900.0, baseline: set[str] | None = None) -> dict[str, Any]:
    """Does the repository still work? Run in a subprocess, with a clock on it.

    This is where a generated strategy's BEHAVIOUR is bounded, as opposed to its
    capability: an import that never returns is a hang, not a security hole, and
    a timeout is the right answer to it rather than another parser rule.
    """
    checks: dict[str, Any] = {}
    commands = {
        "layering": [sys.executable, "orchestrator-manager/scripts/check_layering.py"],
        "tests": [sys.executable, "-m", "pytest", "trading-system/tests", "-q"],
    }
    for name, command in commands.items():
        try:
            result = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, timeout=timeout
            )
            checks[name] = {
                "ok": result.returncode == 0,
                "tail": (result.stdout or result.stderr).strip().splitlines()[-5:],
            }
        except subprocess.TimeoutExpired:
            checks[name] = {"ok": False, "tail": [f"timed out after {timeout:.0f}s"]}
        except (OSError, subprocess.SubprocessError) as exc:
            checks[name] = {"ok": False, "tail": [f"{type(exc).__name__}: {exc}"]}
    dirtied = untouched(baseline)
    checks["protected_paths_clean"] = {"ok": not dirtied, "tail": dirtied[:5]}
    checks["ok"] = all(c["ok"] for c in checks.values() if isinstance(c, dict))
    return checks
