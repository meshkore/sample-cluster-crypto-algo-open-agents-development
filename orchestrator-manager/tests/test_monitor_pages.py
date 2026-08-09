"""What the monitor daemon will serve, and what it will not.

The monitor runs on the operator's machine, next to their credentials and the
research database. It serves pages by an ALLOW-LIST rather than by resolving a
path under a directory, because "serve whatever is under this folder" turns one
traversal slip into "serve whatever is on this disk".

All sabotage-verified.
"""

import unittest

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
