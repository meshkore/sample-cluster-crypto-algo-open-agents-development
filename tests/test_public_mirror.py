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
                "assets": [{"symbol": str(i)} for i in range(900)],
                "trades": [{"sequence": i} for i in range(900)],
                "equity_curve": [{"equity": i} for i in range(2000)],
            },
            "development": {"log_path": "/private/log", "summary": "safe"},
            "activity": {"token": "must-not-leak", "message": "safe"},
        }
        result = compact_public_snapshot(source)
        strategy = result["current_strategy"]
        # Assert against the declared limits rather than repeating the numbers,
        # so trimming the payload cannot leave the contract silently stale.
        limits = result["limits"]
        self.assertEqual(len(strategy["assets"]), limits["assets"])
        self.assertEqual(len(strategy["trades"]), limits["trades"])
        self.assertEqual(len(strategy["equity_curve"]), limits["equity_points"])
        self.assertLessEqual(limits["trades"], 500)
        self.assertLessEqual(limits["equity_points"], 720)
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

    def test_runner_identity_defaults_from_hostname_and_travels_with_the_payload(self):
        """Several people can run the laboratory locally at once.

        Without any config, two machines already differ by hostname, which is
        what lets the edge keep their evidence apart without setup.
        """
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
        self.assertTrue(publisher.runner_id)
        self.assertNotEqual(publisher.runner_id, "default")

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        with (
            patch.dict(os.environ, {"MIRROR_TEST_TOKEN": "test-token"}),
            patch("quantlab.public_mirror.urlopen", return_value=Response()) as opened,
        ):
            self.assertTrue(publisher.publish_once())
        body = json.loads(opened.call_args.args[0].data)
        self.assertEqual(body["runner"]["id"], publisher.runner_id)
        self.assertEqual(body["state"]["runner"]["id"], publisher.runner_id)

    def test_explicit_runner_id_overrides_the_hostname_default(self):
        settings = Settings(
            autonomous={
                "public_mirror": {
                    "enabled": True,
                    "url": "https://mirror.example",
                    "token_env": "MIRROR_TEST_TOKEN",
                    "runner_id": "mac-2",
                    "runner_label": "Ricart's second machine",
                }
            }
        )
        publisher = PublicStatePublisher(settings, lambda: {}, threading.Event())
        self.assertEqual(publisher.runner_id, "mac-2")
        self.assertEqual(publisher.runner_label, "Ricart's second machine")

    def test_disabled_publisher_does_not_open_network(self):
        publisher = PublicStatePublisher(
            Settings(autonomous={"public_mirror": {"enabled": False}}),
            lambda: {},
            threading.Event(),
        )
        with patch("quantlab.public_mirror.urlopen") as open_request:
            self.assertFalse(publisher.publish_once())
        open_request.assert_not_called()

    def test_downloads_use_the_active_publish_cadence_not_the_idle_one(self):
        settings = Settings(
            autonomous={
                "public_mirror": {
                    "enabled": True,
                    "url": "https://mirror.example",
                    "interval_seconds": 15,
                    "idle_interval_seconds": 600,
                }
            }
        )
        publisher = PublicStatePublisher(settings, lambda: {}, threading.Event())
        self.assertEqual(
            publisher._interval({"activity": {"phase": "DOWNLOADING_DATA"}}), 15
        )
        self.assertEqual(
            publisher._interval({"activity": {"phase": "RESEARCHING"}}), 15
        )
        self.assertEqual(
            publisher._interval({"activity": {"phase": "BACKTESTING"}}), 15
        )
        self.assertEqual(publisher._interval({"activity": {"phase": "RESTING"}}), 600)
