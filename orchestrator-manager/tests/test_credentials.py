"""Keys reach the agent's environment and never the repository.

`.meshkore/credentials/` is gitignored; `service._environment` reads from it and
injects into the LaunchAgent's environment dictionary. Nothing in this project
writes a key into the tree, a log, or a cluster post.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from quantlab_manager.advisors import _provider_message
from quantlab_manager.service import _environment


class TestCredentialsReachTheAgentAndNotTheRepository(unittest.TestCase):
    def test_the_refuter_key_is_injected_when_the_file_exists(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            credentials = workspace / ".meshkore" / "credentials"
            credentials.mkdir(parents=True)
            (credentials / "zai-api-key").write_text("a-key\n")

            environment = _environment(workspace, workspace / "runtime")

        self.assertEqual(environment["ZAI_API_KEY"], "a-key")

    def test_no_key_file_is_a_supported_state_not_a_crash(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            environment = _environment(workspace, workspace / "runtime")

        self.assertNotIn("ZAI_API_KEY", environment)

    def test_an_empty_key_file_is_not_injected_as_an_empty_key(self):
        # An empty value would make `Advisor.available` False anyway, but it
        # would be reported as "configured" rather than as absent.
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            credentials = workspace / ".meshkore" / "credentials"
            credentials.mkdir(parents=True)
            (credentials / "zai-api-key").write_text("   \n")

            environment = _environment(workspace, workspace / "runtime")

        self.assertNotIn("ZAI_API_KEY", environment)


class TestTheProviderGetsToSayWhatWentWrong(unittest.TestCase):
    def test_an_empty_account_is_not_reported_as_a_rate_limit(self):
        """Z.ai answers a fresh, VALID key with HTTP 429 and `1113 Insufficient
        balance`. Flattened to "out of tokens", that reads as something waiting
        will fix. It is not: the loop rests thirty minutes, retries, rests
        again, for ever, and every iteration records "resting" as the reason.
        """
        body = (
            '{"error":{"code":"1113","message":"Insufficient balance or no '
            'resource package. Please recharge."}}'
        )
        message = _provider_message(body)
        self.assertIn("1113", message)
        self.assertIn("Insufficient balance", message)

    def test_other_envelopes_and_plain_text_still_yield_something(self):
        self.assertEqual(_provider_message('{"message":"nope"}'), "nope")
        self.assertEqual(_provider_message("upstream exploded"), "upstream exploded")
        self.assertEqual(_provider_message(""), "no detail")
        self.assertEqual(_provider_message("{not json"), "{not json")

    def test_a_body_that_echoes_the_request_is_not_reproduced_whole(self):
        # Error bodies sometimes echo the request, and the request carries the
        # briefing. When a message exists it is returned INSTEAD of the payload.
        body = json.dumps(
            {
                "error": {"code": "400", "message": "bad request"},
                "request": {"messages": [{"content": "the whole briefing"}]},
            }
        )
        self.assertNotIn("briefing", _provider_message(body))


if __name__ == "__main__":
    unittest.main()
