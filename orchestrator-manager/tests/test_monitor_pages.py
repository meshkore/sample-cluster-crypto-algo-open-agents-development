"""What the monitor daemon will serve, and what it will not.

The monitor runs on the operator's machine, next to their credentials and the
research database. It serves pages by an ALLOW-LIST rather than by resolving a
path under a directory, because "serve whatever is under this folder" turns one
traversal slip into "serve whatever is on this disk".

All sabotage-verified.
"""

import json
import math
import unittest

from quantlab_manager import monitor_server
from quantlab_manager.monitor_server import STATIC_PAGES, monitor_root, static_page


class TestStaticPages(unittest.TestCase):
    def test_the_pages_that_exist_are_the_pages_that_are_served(self):
        root = monitor_root()
        self.assertIsNotNone(root, "monitor/public not found beside the packages")
        for route, filename in STATIC_PAGES.items():
            self.assertTrue(
                (root / filename).exists(), f"{route} -> missing {filename}"
            )

    def test_the_loop_page_is_reachable_and_is_a_whole_document(self):
        page = static_page("loop.html")
        self.assertIsNotNone(page)
        self.assertIn("<!doctype html>", page.lower())
        self.assertIn("</html>", page.lower())
        self.assertIn("never-ending", page.lower() + page)

    def test_a_traversal_attempt_is_not_a_route(self):
        """Sabotage: replace the allow-list with `root / requested_path`. These
        then resolve to real files outside `monitor/public/`."""
        for attempt in ("../../CLAUDE.md", "/etc/passwd", "..%2F..%2Fsecrets"):
            self.assertNotIn(attempt, STATIC_PAGES)

    def test_an_unknown_page_returns_nothing_rather_than_guessing(self):
        self.assertIsNone(static_page("does-not-exist.html"))


if __name__ == "__main__":
    unittest.main()


class NonFiniteNumbersTest(unittest.TestCase):
    """`/api/loop` returned 500 for hours because one rejected candidate sat in
    the heartbeat.

    `objective()` returns `-math.inf` for a candidate it rejects and the loop
    puts that straight into `recent[].fit_score`. JSON has no representation of
    it: `allow_nan=False` raises, `allow_nan=True` emits a bare `-Infinity` that
    `JSON.parse` refuses. The monitor showed nothing about the loop while the
    loop was running perfectly well.
    """

    def test_a_rejected_score_becomes_null_rather_than_breaking_the_payload(self):
        beat = {"recent": [{"fit_score": -math.inf, "id": "H-L111"}]}
        cleaned = monitor_server.finite(beat)
        self.assertIsNone(cleaned["recent"][0]["fit_score"])
        self.assertEqual(cleaned["recent"][0]["id"], "H-L111")

    def test_the_result_is_strictly_serialisable(self):
        # The assertion that matters: `allow_nan=False` is what the daemon uses,
        # and it must not raise. Sabotage: return `value` unchanged from
        # `finite` and this raises ValueError exactly as production did.
        payload = {"a": [float("inf"), -math.inf, float("nan")], "b": {"c": 1.5}}
        text = json.dumps(monitor_server.finite(payload), allow_nan=False)
        self.assertEqual(json.loads(text), {"a": [None, None, None], "b": {"c": 1.5}})

    def test_finite_numbers_and_other_types_are_untouched(self):
        payload = {"n": 1.5, "i": 3, "s": "x", "b": True, "z": None, "l": [1, "y"]}
        self.assertEqual(monitor_server.finite(payload), payload)
