import unittest

from quantlab import redact


class ScrubTest(unittest.TestCase):
    def test_the_incident_that_prompted_this_module(self):
        """The exact line that leaked: vendor, billing status, account link."""
        leaked = (
            "Claude Sonnet 5 critic failed. Local summary: You've hit your "
            "monthly spend limit · raise it at claude.ai/settings/usage"
        )
        scrubbed = redact.scrub(leaked)
        self.assertNotIn("monthly spend", scrubbed)
        self.assertNotIn("claude.ai/settings", scrubbed)
        self.assertIn("[redacted]", scrubbed)
        self.assertIn("[redacted: account link]", scrubbed)

    def test_billing_phrases_are_caught(self):
        for phrase in (
            "you have hit your spend limit for this month",
            "usage limit reached, please upgrade",
            "quota exceeded for this billing period",
            "insufficient credits to continue",
            "rate limit exceeded, retry later",
            "check your subscription for details",
        ):
            self.assertFalse(redact.is_clean(phrase), phrase)

    def test_account_and_console_urls_are_caught(self):
        self.assertIn(
            "[redacted: account link]", redact.scrub("see claude.ai/settings/usage")
        )
        self.assertIn(
            "[redacted: account link]",
            redact.scrub("visit console.anthropic.com/billing"),
        )

    def test_a_local_macos_path_no_longer_names_the_account(self):
        """/Users/<name>/... IS the operator's account name on this OS."""
        scrubbed = redact.scrub(
            'Traceback: File "/Users/ricartjuncadella/project/x.py", line 12'
        )
        self.assertNotIn("ricartjuncadella", scrubbed)
        self.assertIn("[redacted: local path]", scrubbed)

    def test_credential_shaped_strings_are_caught(self):
        self.assertIn(
            "[redacted: credential]",
            redact.scrub("token: sk-ant-api03-abcdefghijklmnop"),
        )
        self.assertIn(
            "[redacted: credential]",
            redact.scrub("Authorization: Bearer abcdefghijklmnopqrstuvwx"),
        )
        self.assertIn(
            "[redacted: credential]", redact.scrub("api_key=abcdef0123456789")
        )

    def test_email_addresses_are_caught(self):
        self.assertIn(
            "[redacted: email]", redact.scrub("contact operator@example.com for help")
        )

    def test_ordinary_research_vocabulary_is_never_touched(self):
        """ "credit", "limit" and "rate" are this laboratory's own words."""
        clean = (
            "Position size stayed under the risk limit; drawdown de-leverage "
            "held it near the minimum credit floor. Win rate improved with a "
            "lower rate of false breakouts."
        )
        self.assertTrue(redact.is_clean(clean))
        self.assertEqual(redact.scrub(clean), clean)

    def test_scrubbing_is_idempotent(self):
        text = "hit your monthly spend limit, see claude.ai/settings/usage"
        once = redact.scrub(text)
        self.assertEqual(redact.scrub(once), once)


if __name__ == "__main__":
    unittest.main()
