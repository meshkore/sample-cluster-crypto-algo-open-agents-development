import json
import os
import threading
import unittest
from unittest.mock import patch

from quantlab.config import Settings
from quantlab.public_mirror import PublicStatePublisher
from quantlab.public_state import compact_public_snapshot


class PublicStateTest(unittest.TestCase):
    def test_snapshot_is_bounded_and_redacted(self):
        source = {
            "current_strategy": {
                "assets": [{"symbol": str(i)} for i in range(501)],
                "trades": [{"sequence": i} for i in range(501)],
                "equity_curve": [{"equity": i} for i in range(1000)],
            },
            "development": {"log_path": "/private/log", "summary": "safe"},
            "activity": {"token": "must-not-leak", "message": "safe"},
        }
        result = compact_public_snapshot(source)
        strategy = result["current_strategy"]
        self.assertEqual(len(strategy["assets"]), 500)
        self.assertEqual(len(strategy["trades"]), 500)
        self.assertEqual(len(strategy["equity_curve"]), 720)
        self.assertNotIn("development", result)
        self.assertNotIn("token", result["activity"])
        self.assertEqual(result["project"]["source"], "local-mac")

    def test_publisher_sends_bearer_token(self):
        settings = Settings(
            autonomous={
                "public_mirror": {
                    "enabled": True,
                    "url": "https://mirror.example",
                    "token_env": "MIRROR_TEST_TOKEN",
                }
            }
        )
        publisher = PublicStatePublisher(
            settings, lambda: {"loop": {"state": "RUNNING"}}, threading.Event()
        )

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        with (
            patch.dict(os.environ, {"MIRROR_TEST_TOKEN": "test-token"}),
            patch(
                "quantlab.public_mirror.urlopen", return_value=Response()
            ) as open_request,
        ):
            self.assertTrue(publisher.publish_once())
        request = open_request.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        body = json.loads(request.data)
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["state"]["loop"]["state"], "RUNNING")

    def test_disabled_publisher_does_not_open_network(self):
        publisher = PublicStatePublisher(
            Settings(autonomous={"public_mirror": {"enabled": False}}),
            lambda: {},
            threading.Event(),
        )
        with patch("quantlab.public_mirror.urlopen") as open_request:
            self.assertFalse(publisher.publish_once())
        open_request.assert_not_called()
