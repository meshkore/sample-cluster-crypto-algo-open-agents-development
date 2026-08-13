"""The gate that lets the loop write code, attacked rather than demonstrated.

This is the file that decides whether an unattended process authoring Python is
acceptable, so a test suite that only shows it accepting good input is worthless.
Every test here is an ATTACK, and each names the specific bypass it exists to
close. If any of them starts passing for the wrong reason the loop's licence to
write code should be considered withdrawn.

The threat model is not a hostile intelligence. It is a capable model that has
been asked to write a trading strategy, is trying to be helpful, and reaches for
`open()` to cache a computation or `os` to find a data file -- and, once, will
produce something stranger because a token went the wrong way. The gate has to
refuse all of it without being asked twice.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from quantlab_manager import sandbox

GOOD = '''
"""A minimal strategy that passes the gate."""
from __future__ import annotations

from typing import Any

from quantlab_trading.brains import register
from quantlab_trading.runner import Decision


@register("generation-four-probe", "buys nothing, refuses nothing")
class Probe:
    def __init__(self, **params: Any):
        self.params = dict(params)

    def decide(self, tick: dict[str, Any]) -> Decision:
        decision = Decision()
        decision.note = "flat"
        return decision
'''


def refusals(source: str) -> str:
    return " | ".join(sandbox.inspect(source).refusals)


class TheGateAcceptsRealWork(unittest.TestCase):
    def test_an_ordinary_strategy_passes(self):
        """If the gate cannot pass this, it is not a gate, it is a wall."""
        verdict = sandbox.inspect(GOOD)
        self.assertTrue(verdict.ok, verdict.refusals)
        self.assertEqual(verdict.registered, ["generation-four-probe"])

    def test_numpy_and_the_existing_systems_may_be_imported(self):
        """Reading what already works is allowed; a strategy forced to rewrite
        the money management from scratch would rewrite it badly."""
        source = GOOD.replace(
            "from typing import Any",
            "from typing import Any\nimport numpy as np\n"
            "from quantlab_intraday.moneymanagement import position_notional",
        ).replace('decision.note = "flat"', "decision.note = str(np.mean([1.0]))")
        verdict = sandbox.inspect(source)
        self.assertTrue(verdict.ok, verdict.refusals)

    def test_every_refusal_is_reported_not_just_the_first(self):
        """A coder told all its mistakes fixes them in one pass. One told only
        the first burns an iteration per mistake."""
        source = GOOD.replace(
            "from typing import Any", "import os\nimport socket\nfrom typing import Any"
        )
        found = sandbox.inspect(source).refusals
        self.assertTrue(any("os" in r for r in found))
        self.assertTrue(any("socket" in r for r in found))


class TheFilesystemIsUnreachable(unittest.TestCase):
    """The operator's actual requirement: generated code must not be able to
    damage the systems that already work. It cannot edit what it cannot open."""

    def test_open_is_refused(self):
        source = GOOD.replace(
            'decision.note = "flat"', 'decision.note = open("/etc/passwd").read()'
        )
        self.assertIn("open", refusals(source))

    def test_os_is_refused(self):
        self.assertIn("os", refusals("import os\n" + GOOD))

    def test_pathlib_is_refused(self):
        self.assertIn("pathlib", refusals("from pathlib import Path\n" + GOOD))

    def test_shutil_is_refused(self):
        self.assertIn("shutil", refusals("import shutil\n" + GOOD))


class TheNetworkIsUnreachable(unittest.TestCase):
    """This is what makes 'no live-order, wallet or exchange-secret capability'
    a property of the code rather than a promise in a document."""

    def test_socket_is_refused(self):
        self.assertIn("socket", refusals("import socket\n" + GOOD))

    def test_urllib_is_refused(self):
        self.assertIn("urllib", refusals("from urllib.request import urlopen\n" + GOOD))

    def test_requests_is_refused(self):
        self.assertIn("requests", refusals("import requests\n" + GOOD))

    def test_subprocess_is_refused(self):
        self.assertIn("subprocess", refusals("import subprocess\n" + GOOD))


class TheWhitelistCannotBeEscapedAtRuntime(unittest.TestCase):
    """Static import rules are worth nothing if the code can assemble a name
    while it runs. Each of these is a complete bypass of everything above."""

    def test_eval_is_refused(self):
        source = GOOD.replace('decision.note = "flat"', 'decision.note = eval("1+1")')
        self.assertIn("eval", refusals(source))

    def test_exec_is_refused(self):
        source = GOOD.replace('decision.note = "flat"', 'exec("x = 1")')
        self.assertIn("exec", refusals(source))

    def test_dunder_import_is_refused(self):
        source = GOOD.replace(
            'decision.note = "flat"', '__import__("os").system("rm -rf /")'
        )
        self.assertTrue(refusals(source))

    def test_getattr_is_refused(self):
        """`getattr(x, "e" + "val")` defeats any check that reads names only."""
        source = GOOD.replace(
            'decision.note = "flat"', 'decision.note = getattr(tick, "keys")()'
        )
        self.assertIn("getattr", refusals(source))

    def test_the_subclasses_walk_is_refused(self):
        """`().__class__.__bases__[0].__subclasses__()` reaches every loaded
        class in the process, including the ones that open files. It reads like
        punctuation and is the single most important line in this file."""
        source = GOOD.replace(
            'decision.note = "flat"',
            "decision.note = str(().__class__.__bases__[0].__subclasses__())",
        )
        found = refusals(source)
        self.assertIn("__class__", found)

    def test_function_globals_is_refused(self):
        """A function's `__globals__` is its module namespace, which holds every
        import the module made -- including this gate's own, if it ever reached
        one."""
        source = GOOD.replace(
            'decision.note = "flat"', "decision.note = str(register.__globals__)"
        )
        self.assertIn("__globals__", refusals(source))

    def test_builtins_by_name_is_refused(self):
        source = GOOD.replace(
            'decision.note = "flat"', "decision.note = str(__builtins__)"
        )
        self.assertTrue(refusals(source))


class TheImportRuleIsPrefixNotSubstring(unittest.TestCase):
    def test_a_submodule_of_an_allowed_package_is_allowed(self):
        self.assertTrue(sandbox._import_allowed("numpy.linalg"))

    def test_a_package_that_merely_starts_with_an_allowed_name_is_refused(self):
        """`startswith` on the raw string is the natural way to write this and
        it lets `numpy_evil` through."""
        self.assertFalse(sandbox._import_allowed("numpy_evil"))
        self.assertFalse(sandbox._import_allowed("osmium"))
        self.assertFalse(sandbox._import_allowed("os"))
        self.assertFalse(sandbox._import_allowed("typing_extensions"))

    def test_relative_imports_are_refused(self):
        """A relative import names no module for the gate to check and can reach
        a sibling file that was never inspected."""
        self.assertIn("relative", refusals("from . import helper\n" + GOOD))

    def test_star_imports_are_refused(self):
        """A star import makes the name analysis unsound: anything could be in
        scope, so every unknown name would have to be given the benefit of the
        doubt."""
        self.assertIn("*", refusals("from math import *\n" + GOOD))


class TheDestinationIsNotNegotiable(unittest.TestCase):
    """The coder names a strategy. It never names a location."""

    def test_a_traversal_in_the_filename_is_refused(self):
        with self.assertRaises(ValueError):
            sandbox.workshop_path(4, "../../quantlab_intraday/momentum.py")

    def test_an_absolute_path_is_refused(self):
        with self.assertRaises(ValueError):
            sandbox.workshop_path(4, "/etc/crontab")

    def test_the_existing_systems_cannot_be_addressed_as_a_generation(self):
        for generation in (1, 2, 3, 0, -1):
            with self.assertRaises(ValueError):
                sandbox.workshop_path(generation)

    def test_generation_four_lands_in_its_own_folder(self):
        path = sandbox.workshop_path(4)
        self.assertTrue(sandbox.inside_workshop(path))
        self.assertEqual(path.parent.name, "quantlab_system04")

    def test_paths_outside_the_workshop_are_not_inside_it(self):
        for outside in (
            sandbox.ROOT / "backtester" / "x.py",
            sandbox.ROOT / "trading-system" / "quantlab_intraday" / "momentum.py",
            Path("/tmp/x.py"),
        ):
            self.assertFalse(sandbox.inside_workshop(outside), outside)


class WritingIsRefusedWhenTheGateRefuses(unittest.TestCase):
    def test_bad_source_never_reaches_the_disk(self):
        before = sandbox.workshop_path(9, "attack.py")
        with self.assertRaises(PermissionError):
            sandbox.write("import os\n" + GOOD, 9, "attack.py")
        self.assertFalse(before.exists(), "refused source was written anyway")

    def test_source_that_registers_nothing_is_refused(self):
        """A strategy the laboratory cannot launch by name is not a strategy,
        and would otherwise sit in the workshop looking like progress."""
        self.assertIn("registered", refusals("x = 1\n"))


class TheProtectedPathsAreCheckedAgainstGitNotTrusted(unittest.TestCase):
    def test_an_unanswerable_question_is_not_an_all_clear(self):
        """If git cannot be asked, `untouched` must not return an empty list --
        that would read as 'nothing was modified'."""
        original = sandbox.ROOT
        try:
            sandbox.ROOT = Path("/nonexistent-repository-path")
            self.assertTrue(sandbox.untouched())
        finally:
            sandbox.ROOT = original


if __name__ == "__main__":
    unittest.main()


class FalsePositivesThatCostANight(unittest.TestCase):
    """A gate that refuses correct code is as useless as one that permits bad
    code, and it fails silently: the coder is told a rule it is breaking, the
    rule does not exist, and it cannot possibly comply. In one night 17 of 173
    attempts died here. Each test names the construct that was refused."""

    def test_a_lambda_argument_is_in_scope(self):
        """Six strategies were refused for `item`. Argument collection was keyed
        on FunctionDef and ClassDef, and `ast.Lambda` is neither."""
        source = GOOD.replace(
            'decision.note = "flat"',
            "decision.note = str(sorted([1, 2], key=lambda item: -item))",
        )
        self.assertTrue(sandbox.inspect(source).ok, refusals(source))

    def test_a_lambda_with_several_arguments_is_in_scope(self):
        """Five died on `kv`."""
        source = GOOD.replace(
            'decision.note = "flat"',
            "decision.note = str(sorted([(1, 2)], key=lambda kv, n=0: kv[0] + n))",
        )
        self.assertTrue(sandbox.inspect(source).ok, refusals(source))

    def test_star_args_are_in_scope(self):
        source = GOOD.replace(
            "    def decide",
            "    def helper(self, *rest, **named):\n"
            "        return rest, named\n\n    def decide",
        )
        self.assertTrue(sandbox.inspect(source).ok, refusals(source))

    def test_catching_an_attribute_error_is_allowed(self):
        """Defensive code was being punished for existing."""
        source = GOOD.replace(
            'decision.note = "flat"',
            'try:\n            decision.note = "flat"\n'
            "        except AttributeError:\n            pass",
        )
        self.assertTrue(sandbox.inspect(source).ok, refusals(source))

    def test_hasattr_is_allowed_but_getattr_is_not(self):
        """`hasattr` returns a bool and hands back no object; `getattr` can
        retrieve one under a name assembled at runtime, which is the bypass."""
        ok = GOOD.replace(
            'decision.note = "flat"', 'decision.note = str(hasattr(tick, "keys"))'
        )
        self.assertTrue(sandbox.inspect(ok).ok, refusals(ok))
        bad = GOOD.replace(
            'decision.note = "flat"', 'decision.note = str(getattr(tick, "keys"))'
        )
        self.assertFalse(sandbox.inspect(bad).ok)
