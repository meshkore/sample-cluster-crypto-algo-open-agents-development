"""What may never reach the public Wall.

Every message this laboratory posts passes through
``AutonomousService.cluster_update``. That is the one choke point, so this
module scrubs there rather than trusting every call site to remember —
the same principle as the Wall rate limiter and the contribution screen:
a leak requires the one shared function to be wrong, not fourteen call
sites to all stay careful forever.

The incident that prompted this: a reviewer's CLI call failed on a billing
limit, and the failure handler echoed the raw local error text straight to
the public cluster — vendor name, billing status, and a link to the
account's own settings page, all in one line anyone connected could read.

Scope, deliberately narrow. This is not a topic filter — "credit", "limit"
and "rate" are ordinary words in this laboratory's own research vocabulary
(risk limit, drawdown limit, minimum credit floor) and a blanket ban on them
would mangle legitimate prose for no safety gain. What is scrubbed is
specific and unambiguous: account/billing URLs, credential-shaped tokens,
local filesystem paths (which embed the operator's account name on a Mac),
email addresses, and the exact phrases a CLI billing failure actually uses.
"""

from __future__ import annotations

import re


def _pattern(expr: str, flags: int = re.IGNORECASE) -> re.Pattern:
    return re.compile(expr, flags)


# Ordered by how much it discloses if one is missed. Each replacement names
# what was removed rather than leaving a blank, so a reader (and whoever
# reviews daemon_events) can tell a redaction happened from a truncation.
#
# The billing phrases are one alternation with one replacement, not several
# rules run in sequence: a replacement text that itself contains a trigger
# word ("billing status" contains "billing") would otherwise get re-matched
# and re-wrapped by a later rule on the same pass, mangling the output every
# time scrub() runs — caught by the idempotence test below.
_BILLING_PHRASES = _pattern(
    r"\b(monthly spend|spend limit|usage limit|quota exceeded|"
    r"insufficient credits?|rate limit exceeded|billing|invoice|subscription)\b"
)

_RULES: tuple[tuple[re.Pattern, str], ...] = (
    # The exact shape of a CLI billing/quota failure — the leak that
    # prompted this module. Exact phrases, not bare "credit" or "limit",
    # which are ordinary trading vocabulary here. The replacement names no
    # category word from the trigger list itself ("billing", "spend") —
    # scrubbing a second time must not re-match what the first pass wrote.
    (_BILLING_PHRASES, "[redacted]"),
    # Account/console URLs — unambiguous, never legitimate research content.
    (_pattern(r"claude\.ai/settings\S*"), "[redacted: account link]"),
    (_pattern(r"console\.anthropic\.com\S*"), "[redacted: account link]"),
    (_pattern(r"platform\.openai\.com\S*"), "[redacted: account link]"),
    # Credential-shaped strings.
    (_pattern(r"sk-[a-zA-Z0-9_-]{10,}"), "[redacted: credential]"),
    (_pattern(r"bearer\s+[a-zA-Z0-9._-]{10,}"), "[redacted: credential]"),
    (_pattern(r"\bapi[_-]?key\b\s*[:=]\s*\S+"), "[redacted: credential]"),
    (_pattern(r"gh[pousr]_[A-Za-z0-9]{20,}"), "[redacted: credential]"),
    # Local filesystem paths. On this machine /Users/<name>/... IS the
    # operator's account name — the single most direct "who owns this"
    # leak available, and the one a stack trace hands out for free.
    (_pattern(r"/Users/[^/\s]+(?:/\S*)?"), "[redacted: local path]"),
    (_pattern(r"/home/[^/\s]+(?:/\S*)?"), "[redacted: local path]"),
    (_pattern(r"C:\\Users\\[^\\\s]+(?:\\\S*)?"), "[redacted: local path]"),
    # Email addresses.
    (_pattern(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[redacted: email]"),
)


def scrub(text: str) -> str:
    """Replace anything on the denylist. Idempotent and safe on clean text."""
    result = text
    for pattern, replacement in _RULES:
        result = pattern.sub(replacement, result)
    return result


def is_clean(text: str) -> bool:
    """True when scrubbing would not have changed anything."""
    return scrub(text) == text
