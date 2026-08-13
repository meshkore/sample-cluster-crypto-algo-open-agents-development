"""Recognising a spent subscription, written after a night lost to not doing so."""

from __future__ import annotations

import unittest

from quantlab_manager.advisors import COOLDOWN_SECONDS, looks_exhausted, rest_seconds

REAL = "You've hit your session limit · resets 3:30am (Europe/Madrid)"


class RecognisingASpentWindow(unittest.TestCase):
    def test_the_message_the_cli_actually_sends_is_recognised(self):
        """This exact string went unrecognised for nine hours. "usage limit" was
        a marker; "session limit" was not, so the loop never rested and asked
        again every sixty seconds -- 116 attempts that could not succeed."""
        self.assertTrue(looks_exhausted(None, REAL))

    def test_the_phrase_session_limit_alone_is_enough(self):
        """Stated separately because the first version of this test passed for
        the wrong reason: the real message also contains "resets", which is its
        own marker, so removing "session limit" entirely left the test green. A
        test that survives the bug it was written for certifies the bug."""
        self.assertTrue(looks_exhausted(None, "You've hit your session limit"))
        self.assertTrue(looks_exhausted(None, "SESSION LIMIT reached for today"))

    def test_an_ordinary_failure_is_not_mistaken_for_exhaustion(self):
        """Resting thirty minutes on a normal error would idle the loop for no
        reason, which is the opposite failure and just as costly."""
        self.assertFalse(looks_exhausted(None, "SyntaxError: unexpected EOF"))
        self.assertFalse(looks_exhausted(None, ""))
        self.assertFalse(looks_exhausted(200, "here is your answer"))

    def test_the_rest_lasts_until_the_time_the_message_names(self):
        """A fixed thirty minutes against an eight-hour window is sixteen
        pointless wake-ups."""
        seconds = rest_seconds(REAL)
        self.assertGreater(seconds, 60)
        self.assertLessEqual(seconds, 12 * 3600)

    def test_a_message_with_no_time_falls_back_to_the_default(self):
        self.assertEqual(rest_seconds("rate limit exceeded"), COOLDOWN_SECONDS)

    def test_a_nonsense_time_falls_back_rather_than_sleeping_wrongly(self):
        """The message is untrusted text like every other reply. A misparsed
        clock that sleeps for eleven hours is worse than one that retries."""
        self.assertEqual(rest_seconds("resets 99:99"), COOLDOWN_SECONDS)

    def test_the_rest_is_bounded_however_the_message_reads(self):
        for body in ("resets 1am", "resets 11:59pm", "resets 12am", "resets 12pm"):
            self.assertLessEqual(rest_seconds(body), 12 * 3600, body)
            self.assertGreaterEqual(rest_seconds(body), 60, body)


if __name__ == "__main__":
    unittest.main()
