"""Parsing the coder's reply, written after losing a real one.

The first coder call this laboratory ever made researched the open web for
twenty-two minutes, wrote a module, and was discarded with "reply was not JSON"
-- because the design asked it to embed a hundred lines of Python inside a JSON
string, which means escaping every newline and quote in the file. These tests
exist so that never silently happens again.
"""

from __future__ import annotations

import unittest

from quantlab_manager import coder

MODULE = '''"""A strategy with everything that breaks JSON escaping."""
from quantlab_trading.runner import Decision


class Brain:
    def decide(self, tick):
        d = Decision()
        d.note = "quotes \\" and a backslash \\\\ and a newline in a string"
        return d
'''


class SplittingTheReply(unittest.TestCase):
    def test_metadata_and_source_come_back_separately(self):
        reply = (
            '{"family": "gen04-idea", "hypothesis": "it works", "parameters": {"a": 1}}'
            f"\n{coder.SEPARATOR}\n{MODULE}"
        )
        out = coder.split_reply(reply)
        self.assertIsNotNone(out)
        self.assertEqual(out["family"], "gen04-idea")
        self.assertIn("class Brain", out["source"])

    def test_python_that_would_break_json_escaping_survives(self):
        """The actual failure. A module carrying quotes, backslashes and
        newlines is exactly what a model gets wrong when asked to escape it, and
        is ordinary Python."""
        reply = '{"family": "x"}' + f"\n{coder.SEPARATOR}\n{MODULE}"
        out = coder.split_reply(reply)
        self.assertIn('\\"', out["source"])
        self.assertIn("\n", out["source"])

    def test_a_fenced_module_is_unwrapped_anyway(self):
        """The briefing says no fence. A model that has just written Python
        reaches for one by habit, and refusing over it would throw away the
        work for a formatting nicety."""
        reply = f'{{"family": "x"}}\n{coder.SEPARATOR}\n```python\n{MODULE}```\n'
        out = coder.split_reply(reply)
        self.assertTrue(out["source"].startswith('"""'))
        self.assertNotIn("```", out["source"])

    def test_metadata_wrapped_in_prose_is_still_found(self):
        reply = (
            "Here is my proposal.\n"
            '```json\n{"family": "x", "hypothesis": "y"}\n```\n'
            f"{coder.SEPARATOR}\n{MODULE}"
        )
        out = coder.split_reply(reply)
        self.assertEqual(out["family"], "x")

    def test_a_reply_without_the_separator_is_refused(self):
        self.assertIsNone(coder.split_reply('{"family": "x", "source": "print(1)"}'))

    def test_a_reply_whose_metadata_is_not_json_is_refused(self):
        self.assertIsNone(coder.split_reply(f"no json here\n{coder.SEPARATOR}\ncode"))


class ValidatingTheProposal(unittest.TestCase):
    def test_a_complete_proposal_validates(self):
        out = coder.validate(
            {
                "family": "Gen04-Idea",
                "hypothesis": "h",
                "source": MODULE,
                "parameters": {"hold": 5, "bad key": 1, "obj": {"no": 1}},
                "sources": [{"title": "t", "url": "https://x", "claim": "c"}],
            }
        )
        self.assertEqual(out["family"], "gen04-idea")
        self.assertIn("hold", out["parameters"])
        self.assertNotIn("bad key", out["parameters"], "not an identifier")
        self.assertNotIn("obj", out["parameters"], "not a scalar")
        self.assertEqual(len(out["sources"]), 1)

    def test_a_proposal_without_source_is_refused(self):
        self.assertIsNone(coder.validate({"family": "x", "source": "   "}))

    def test_sources_given_as_bare_strings_still_count(self):
        out = coder.validate(
            {"family": "x", "source": MODULE, "sources": ["a paper I read"]}
        )
        self.assertEqual(out["sources"][0]["title"], "a paper I read")

    def test_missing_sources_is_an_empty_list_not_a_crash(self):
        out = coder.validate({"family": "x", "source": MODULE})
        self.assertEqual(out["sources"], [])


if __name__ == "__main__":
    unittest.main()
