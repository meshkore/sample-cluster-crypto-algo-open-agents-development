"""Two models in the loop: one proposes, one tries to kill it. Both emit data.

The mechanical loop can already invent mechanisms -- the grammar composes rule
trees and the search breeds them. What it cannot do is *read*: it has no way to
notice that a shape it is about to try was refuted eleven iterations ago for a
reason nobody encoded, or that the thing failing looks like a documented
pathology with a name.

So there are two advisors, and the operator's naming makes their jobs legible on
the cluster:

    blackmac-quantlab-proposer-opus5   Anthropic Claude Opus 5   proposes
    blackmac-quantlab-critic-glm52     Z.ai GLM 5.2              refutes

The proposer reads the diagnosis, the ledger and the incumbent, and returns a
hypothesis: which module to work on, seed rules to put in the population, and a
falsifiable claim. The critic reads the same briefing plus the proposal and
tries to refute it -- has this been tried, is the claim actually falsifiable, is
the rule reading a column that will be `None` for the whole window. A proposal
the critic kills never costs a backtest.

**What an advisor may return, and why that is the whole safety story.** JSON,
matching one schema, validated before use: module names checked against a fixed
set, rule trees checked by `grammar.validate`, everything else discarded. An
advisor cannot write a file, run a command, install anything, reach a
credential, or put a single line of Python into this repository. It contributes
*candidates* to a search that then has to earn its result against the same four
folds as everything else. That is deliberate: an unattended loop that could
write and execute its own code is a different and much larger risk than an
unattended loop that can suggest `adx > 25`.

**Absence is normal.** With no API key configured, `advise()` returns None and
the loop runs on its mechanical proposer. Every iteration records which advisors
answered, so a run of the ledger says honestly whether a model was involved.
"""

from __future__ import annotations

from typing import Any
import json
import os
import time
import urllib.error
import urllib.request

from quantlab_trading import grammar

REVIEWER_SYSTEM = """You are the code reviewer in an open crypto quant research
loop. You can READ this repository. You never change it: you return an opinion
and someone else decides.

Return JSON only:

{"concerns": ["<specific, checkable objection with a file reference>", ...],
 "lookahead_risk": true|false,
 "blocking": true|false,
 "note": "<one paragraph a maintainer can act on>"}

Look for: a decision that reads a bar it should not be able to see; a test that
would pass against deliberately broken code; a parameter fitted on the sealed
2026 window; an invented rule that cannot be true because the columns it reads
never fill together. Say so plainly if you find nothing."""

PROPOSER_HANDLE = "blackmac-quantlab-proposer-opus5"
CRITIC_HANDLE = "blackmac-quantlab-critic-glm52"

VALID_MODULES = ("BULL", "SIDEWAYS", "BEAR", "DETECTOR")

# How long a provider sits out after it says it has run out. The operator's
# number, and it matches how these quotas actually refill: a rolling window,
# not a per-request limit, so retrying in ten seconds burns the retry too.
COOLDOWN_SECONDS = 30 * 60

# What "out of credit" looks like across providers. Matched on the response
# body as well as the status, because a 400 carrying "insufficient balance" is
# the same event as a 429 and must not be mistaken for a bad request we could
# fix by asking differently.
EXHAUSTED_MARKERS = (
    "rate_limit",
    "rate limit",
    "quota",
    "insufficient",
    "credit",
    "billing",
    "overloaded",
    "usage limit",
    "too many requests",
)


def looks_exhausted(status: int | None, body: str) -> bool:
    if status in (429, 402):
        return True
    text = (body or "").lower()
    return any(marker in text for marker in EXHAUSTED_MARKERS)


PROPOSER_SYSTEM = """You are the proposer in an open crypto quant research loop.
You receive a diagnosis of the last forward run, the ledger of hypotheses already
tried, and the incumbent configuration. You return ONE falsifiable hypothesis
about which of four modules to improve and how.

You do not write code. You return JSON only, matching this schema:

{"module": "BULL|SIDEWAYS|BEAR|DETECTOR",
 "claim": "<one falsifiable sentence: what you expect to measure>",
 "kill_condition": "<what result would refute it>",
 "seed_rules": [<expression tree>, ...],
 "reasoning": "<why, referencing the diagnosis or the ledger>"}

An expression tree is built only from these nodes:
  {"t":"col","name":<served column>}   {"t":"px","name":"open|high|low|close|volume"}
  {"t":"num","v":<number>}             {"t":"mul","a":<value>,"b":<value>}
  {"t":"gt","a":<value>,"b":<value>}   {"t":"lt","a":<value>,"b":<value>}
  {"t":"cross_up","a":<value>,"b":<value>}  {"t":"cross_down",...}
  {"t":"and","xs":[...]}  {"t":"or","xs":[...]}  {"t":"not","x":...}

Rules are capped at 24 nodes. A term comparing a field with itself is rejected.
Prefer two or three joined comparisons: a large rule that fits four folds is an
overfit, not a mechanism.

Do not repeat a hypothesis in the ledger. Say so explicitly if the evidence
suggests the previous direction should be abandoned rather than deepened."""

CRITIC_SYSTEM = """You are the critic in an open crypto quant research loop. You
receive a proposal and the same evidence the proposer had. Your job is to REFUTE
it, not to improve it. Default to refuted when uncertain.

Return JSON only:

{"refuted": true|false,
 "reasons": ["<specific, checkable objection>", ...],
 "already_tried": "<ledger id, or null>",
 "salvage": "<the narrowest change that would make it worth running, or null>"}

Refute if: the claim is not falsifiable; the ledger already contains it; the
rules read columns that cannot be true together; the proposal targets a module
the diagnosis does not implicate; or the reasoning appeals to the 2026 forward
window, which is sealed and must never be optimised against."""


class Advisor:
    """One model, one role, one HTTP call. No tools, no subprocess, no files."""

    def __init__(
        self,
        handle: str,
        endpoint: str,
        model: str,
        api_key: str | None,
        system: str,
        timeout: float = 120.0,
        style: str = "anthropic",
    ):
        self.handle = handle
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.system = system
        self.timeout = timeout
        self.style = style
        self.last_error: str | None = None
        # When this provider may be asked again. Tokens are finite and the loop
        # is not: an advisor that has run out sits out its window while the
        # mechanical loop keeps producing evidence without it.
        self.cooling_until: float = 0.0

    @property
    def cooling(self) -> bool:
        return time.time() < self.cooling_until

    @property
    def cooldown_remaining(self) -> int:
        return max(0, int(self.cooling_until - time.time()))

    def rest(self, seconds: float = COOLDOWN_SECONDS) -> None:
        self.cooling_until = time.time() + seconds

    @property
    def available(self) -> bool:
        return bool(self.api_key) and not self.cooling

    def ask(self, briefing: str) -> dict[str, Any] | None:
        """One turn. Returns parsed JSON, or None if the model is unreachable.

        Unreachable is not an error worth stopping for. The loop's whole point
        is that it does not stop, and an iteration with no advisor is an
        iteration driven by the mechanical proposer -- weaker, recorded as such,
        and still a real iteration.
        """
        if not self.available:
            self.last_error = "no api key configured"
            return None
        if self.style == "anthropic":
            payload = {
                "model": self.model,
                "max_tokens": 2000,
                "system": self.system,
                "messages": [{"role": "user", "content": briefing}],
            }
            headers = {
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
        else:
            payload = {
                "model": self.model,
                "max_tokens": 2000,
                "messages": [
                    {"role": "system", "content": self.system},
                    {"role": "user", "content": briefing},
                ],
            }
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.api_key}",
            }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={**headers, "User-Agent": "QuantLab-research-loop/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            self.last_error = f"HTTP {exc.code}: {detail}"
            if looks_exhausted(exc.code, detail):
                self.rest()
                self.last_error = (
                    f"out of tokens (HTTP {exc.code}); resting "
                    f"{COOLDOWN_SECONDS // 60} minutes"
                )
            return None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        self.last_error = None
        return _parse_json(_text_of(body))


def _text_of(body: dict) -> str:
    """Pull the text out of either provider's envelope."""
    if isinstance(body.get("content"), list):  # anthropic
        return "".join(
            part.get("text", "") for part in body["content"] if isinstance(part, dict)
        )
    choices = body.get("choices") or []  # openai-compatible
    if choices and isinstance(choices[0], dict):
        return (choices[0].get("message") or {}).get("content", "") or ""
    return ""


def _parse_json(text: str) -> dict[str, Any] | None:
    """Find the JSON object in a reply that may be wrapped in prose or a fence.

    Deliberately forgiving about the envelope and strict about the contents:
    what comes out of here is still validated field by field before anything
    uses it.
    """
    if not text:
        return None
    cleaned = text.strip()
    if "```" in cleaned:
        blocks = cleaned.split("```")
        for block in blocks:
            block = block.removeprefix("json").strip()
            if block.startswith("{"):
                cleaned = block
                break
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def validate_proposal(proposal: Any) -> dict[str, Any] | None:
    """Everything a model says, checked before anything acts on it.

    A proposal is a suggestion from an untrusted source. Every field is either
    recognised and kept or dropped -- there is no path by which unrecognised
    content reaches the search.
    """
    if not isinstance(proposal, dict):
        return None
    module = str(proposal.get("module", "")).upper()
    if module not in VALID_MODULES:
        return None
    rules = []
    for candidate in proposal.get("seed_rules") or []:
        try:
            rules.append(grammar.validate(candidate))
        except (grammar.GrammarError, TypeError, KeyError):
            # A rule the grammar rejects is dropped silently and the rest of the
            # proposal stands. One bad tree is not a reason to discard a good
            # hypothesis.
            continue
    return {
        "module": module,
        "claim": str(proposal.get("claim", ""))[:500],
        "kill_condition": str(proposal.get("kill_condition", ""))[:500],
        "reasoning": str(proposal.get("reasoning", ""))[:2000],
        "seed_rules": rules[:6],
    }


def validate_critique(critique: Any) -> dict[str, Any] | None:
    if not isinstance(critique, dict):
        return None
    reasons = [str(r)[:300] for r in (critique.get("reasons") or [])][:6]
    return {
        "refuted": bool(critique.get("refuted")),
        "reasons": reasons,
        "already_tried": (
            str(critique["already_tried"])[:60]
            if critique.get("already_tried")
            else None
        ),
        "salvage": str(critique["salvage"])[:500] if critique.get("salvage") else None,
    }


class CodexAdvisor:
    """The local reviewer. Reads the repository, writes nothing, answers in JSON.

    A subprocess rather than an HTTP call, because this one has to SEE the code
    to review it -- which is the operator's point: both local agents share the
    working copy, one is responsible for changing it and the other reads it and
    argues on the cluster.

    Three deliberate limits. It runs read-only, so a review cannot become an
    edit. It is bounded by a timeout, so a hung model cannot stall an iteration
    that has a backtest waiting. And its answer is parsed as JSON and validated
    like any other advisor's: a reviewer that could emit anything the loop then
    acted on would be a much larger thing than a reviewer.
    """

    handle = "blackmac-quantlab-critic-codex"

    def __init__(
        self,
        executable: str | None = None,
        repository: str | None = None,
        timeout: float = 240.0,
    ):
        self.executable = executable or os.environ.get(
            "QUANTLAB_CODEX",
            "/Applications/Codex.app/Contents/Resources/codex",
        )
        self.repository = repository or os.getcwd()
        self.timeout = timeout
        self.last_error: str | None = None
        self.cooling_until: float = 0.0

    @property
    def cooling(self) -> bool:
        return time.time() < self.cooling_until

    @property
    def cooldown_remaining(self) -> int:
        return max(0, int(self.cooling_until - time.time()))

    def rest(self, seconds: float = COOLDOWN_SECONDS) -> None:
        self.cooling_until = time.time() + seconds

    @property
    def available(self) -> bool:
        return (
            bool(self.executable)
            and os.path.exists(self.executable)
            and not self.cooling
        )

    def ask(self, briefing: str) -> dict[str, Any] | None:
        if not self.available:
            self.last_error = f"no codex executable at {self.executable}"
            return None
        import subprocess

        command = [
            self.executable,
            "exec",
            # Read-only, non-interactive, no approvals. A reviewer that can
            # write is not a reviewer.
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "-C",
            self.repository,
            "-",
        ]
        try:
            result = subprocess.run(
                command,
                input=f"{REVIEWER_SYSTEM}\n\nBRIEFING:\n{briefing}",
                text=True,
                capture_output=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "")[:400]
            self.last_error = detail
            if looks_exhausted(None, detail):
                self.rest()
                self.last_error = (
                    f"codex is out of credit; resting {COOLDOWN_SECONDS // 60} minutes"
                )
            return None
        self.last_error = None
        return _parse_json(result.stdout)


def validate_review(review: Any) -> dict[str, Any] | None:
    if not isinstance(review, dict):
        return None
    return {
        "concerns": [str(c)[:300] for c in (review.get("concerns") or [])][:8],
        "lookahead_risk": bool(review.get("lookahead_risk")),
        "blocking": bool(review.get("blocking")),
        "note": str(review.get("note", ""))[:1200],
    }


def from_environment() -> tuple[Advisor, Advisor]:
    """The operator's pair, configured from the environment and never from a file.

    Keys are read from the process environment so nothing here can leak one into
    the repository, a log, or a Wall post. Both are optional: the loop runs
    without either and records that it did.
    """
    proposer = Advisor(
        handle=PROPOSER_HANDLE,
        endpoint=os.environ.get(
            "QUANTLAB_PROPOSER_URL", "https://api.anthropic.com/v1/messages"
        ),
        model=os.environ.get("QUANTLAB_PROPOSER_MODEL", "claude-opus-4-5"),
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        system=PROPOSER_SYSTEM,
        style="anthropic",
    )
    critic = Advisor(
        handle=CRITIC_HANDLE,
        endpoint=os.environ.get(
            "QUANTLAB_CRITIC_URL", "https://api.z.ai/api/paas/v4/chat/completions"
        ),
        model=os.environ.get("QUANTLAB_CRITIC_MODEL", "glm-4.6"),
        api_key=os.environ.get("ZAI_API_KEY"),
        system=CRITIC_SYSTEM,
        style="openai",
    )
    return proposer, critic
