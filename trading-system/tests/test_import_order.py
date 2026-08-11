"""Every module must be importable FIRST.

The brain registry is populated by a side effect at the foot of `brains.py`,
and `regime_system` imports `register` from `brains` near its top. That makes
registration run in the middle of `regime_system`'s own import whenever
`regime_system` is the first module touched -- so anything registered from
`_register_builtins` that needs a NAME out of `regime_system` (a subclass of
`FourModuleBrain`, say) raises ImportError on a partially initialised module.

This is invisible to an ordinary test. Once pytest has collected any module
that pulls `brains` or `grammar` in first, every later import finds a fully
built `sys.modules` entry and the cycle never fires. The loop's entry point
does not have that luck, and the failure surfaced only when the loop refused to
start: `cannot import name 'FourModuleBrain' from partially initialized module`.

So each import runs in its own interpreter, with nothing else imported before
it. That is the only arrangement in which the bug is reachable.
"""

import subprocess
import sys
import unittest

# Every public entry point into the package. A module added here that cannot be
# imported first is a module the loop may not be able to start from.
MODULES = (
    "quantlab_trading",
    "quantlab_trading.brains",
    "quantlab_trading.regime",
    "quantlab_trading.regime_system",
    "quantlab_trading.codex_regime_system",
    "quantlab_trading.grammar",
    "quantlab_trading.policy",
    "quantlab_trading.runner",
    "quantlab_trading.seeds",
    "quantlab_trading.space",
    "quantlab_trading.universe",
)


class TestEveryModuleCanBeTheFirstImport(unittest.TestCase):
    def test_each_module_imports_in_a_clean_interpreter(self):
        for module in MODULES:
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-c", f"import {module}"],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"importing {module} first fails:\n{result.stderr}",
                )

    def test_the_registry_is_complete_however_it_is_entered(self):
        """Sabotage: register a brain from `_register_builtins` again. The
        import above starts failing and so does this, because entering through
        `regime_system` leaves the registry short of the brains that never got
        to register."""
        expected = None
        for entry in ("quantlab_trading.regime_system", "quantlab_trading.brains"):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"import {entry}; "
                    "from quantlab_trading.brains import available; "
                    "print(','.join(sorted(b['name'] for b in available())))",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            found = result.stdout.strip()
            if expected is None:
                expected = found
            self.assertEqual(
                found, expected, f"entering via {entry} changed the registry"
            )
        self.assertTrue(expected)


if __name__ == "__main__":
    unittest.main()
