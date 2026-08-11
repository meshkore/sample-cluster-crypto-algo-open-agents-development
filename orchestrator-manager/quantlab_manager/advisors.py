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
REVIEWER_HANDLE = "blackmac-quantlab-critic-codex"

# Where the Codex CLI lives when nobody says otherwise. The Homebrew symlink
# `/opt/homebrew/bin/codex` points into the app bundle's `MacOS/` and does not
# execute; the binary that does is under `Resources/`.
CODEX_DEFAULT = "/Applications/Codex.app/Contents/Resources/codex"

VALID_MODULES = ("BULL", "SIDEWAYS", "BEAR", "DETECTOR", "POLICY")

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


def _provider_message(body: str) -> str:
    """The human-readable half of an error body, without the envelope.

    Providers disagree about the shape -- `{"error": {"message": ...}}`,
    `{"message": ...}`, or plain text -- so this tries each and falls back to
    the raw body rather than losing it. Never returns the whole payload when a
    message exists: an error body can echo the request, and the request carries
    the briefing.
    """
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return (body or "").strip()[:200] or "no detail"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            code = error.get("code")
            text = str(error["message"])[:200]
            return f"{code} {text}" if code else text
        if payload.get("message"):
            return str(payload["message"])[:200]
    return (body or "").strip()[:200] or "no detail"


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

{"module": "BULL|SIDEWAYS|BEAR|DETECTOR|POLICY",
 "claim": "<one falsifiable sentence: what you expect to measure>",
 "kill_condition": "<what result would refute it>",
 "seed_rules": [<expression tree>, ...],
 "reasoning": "<why, referencing the diagnosis or the ledger>"}

Answer about the module the briefing names as `target_module`. A proposal about
a different one is recorded as advice for that module and does not become this
iteration's hypothesis.

Two modules take no trades under their own name and have no rule trees, so send
them an empty `seed_rules` and put the work in the claim:

  DETECTOR decides which branch owns a symbol on a bar -- including
  `regime_scope`, which is `market` (one regime for everything) or `asset`
  (each symbol routed by its own detector).
  POLICY is money management: risk_per_trade, risk_distance_pct, stop_loss_pct,
  take_profit_pct, maximum_position_fraction, maximum_concurrent_assets,
  maximum_holding_days. This is where position sizing, the exit asymmetry and
  how much of the book one idea may hold get decided.

An expression tree is built only from these nodes:
  {"t":"col","name":<served column>}   {"t":"px","name":"open|high|low|close|volume"}
  {"t":"num","v":<number>}             {"t":"mul","a":<value>,"b":<value>}
  {"t":"gt","a":<value>,"b":<value>}   {"t":"lt","a":<value>,"b":<value>}
  {"t":"cross_up","a":<value>,"b":<value>}  {"t":"cross_down",...}
  {"t":"and","xs":[...]}  {"t":"or","xs":[...]}  {"t":"not","x":...}

Rules are capped at 24 nodes. A term comparing a field with itself is rejected,
and so is any comparison between two parts of the SAME bar -- low <= close <=
high by definition, so `high > close` is not a signal. Prefer two or three
joined comparisons: a large rule that fits four folds is an overfit, not a
mechanism.

THIS SYSTEM IS LONG ONLY. There is no shorting, no leverage, no margin. An entry
rule is a condition to BUY; an exit rule is a condition to SELL what is already
held. "BEAR" does not mean "go short in a bear market" -- it is the module that
decides whether and what to hold long WHILE the market falls, and its recorded
finding is that buying dips there loses money (RSI-30 bounces return -0.20% over
the next 20 bars in a bear regime against +2.26% in a bull one; H-REGIME-001
bought them and returned -8.46%). A proposal phrased as shorting, covering, or
selling short will be executed as its exact opposite: your entry becomes a BUY.

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

THIS SYSTEM IS LONG ONLY: no shorting, no leverage, no margin. An entry rule
BUYS; an exit rule SELLS what is held. "BEAR" is the module deciding what to
hold long while the market falls, not a licence to go short.

Refute if: the claim is not falsifiable; the ledger already contains it; the
rules read columns that cannot be true together; the proposal targets a module
the diagnosis does not implicate; the reasoning appeals to the 2026 forward
window, which is sealed and must never be optimised against; or the proposal is
reasoned as a SHORT -- selling short, covering, profiting from a decline. That
last one is not a quibble about wording: the rule will be run as a long, so the
mechanism argued for is not the mechanism that would be tested."""


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
                # Keep what the PROVIDER said. This used to be flattened to
                # "out of tokens (HTTP 429)", and the two states that hides are
                # not the same problem: a rate limit clears by waiting, an
                # empty account never does. Z.ai answers a fresh, valid key
                # with 429 and `1113 Insufficient balance or no resource
                # package`, so the loop recorded "resting 30 minutes" and rested
                # for ever, and finding out why cost a hand-written curl.
                self.last_error = (
                    f"provider refused (HTTP {exc.code}): {_provider_message(detail)}"
                    f" -- resting {COOLDOWN_SECONDS // 60} minutes"
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
    rejected = []
    for candidate in proposal.get("seed_rules") or []:
        try:
            rules.append(grammar.validate(candidate))
        except (grammar.GrammarError, TypeError, KeyError) as exc:
            # A rule the grammar rejects is still dropped, and the rest of the
            # proposal still stands -- one bad tree is not a reason to discard a
            # good hypothesis. But it is no longer dropped SILENTLY: "the model
            # proposed nothing" and "the model proposed two rules the grammar
            # refused" looked identical from the outside, and telling them apart
            # is the difference between a resting advisor and a guard that has
            # quietly closed the grammar. A guard written this morning was too
            # broad by exactly one pair and nothing could have shown it.
            rejected.append(str(exc)[:200])
    return {
        "module": module,
        "claim": str(proposal.get("claim", ""))[:500],
        "kill_condition": str(proposal.get("kill_condition", ""))[:500],
        "reasoning": str(proposal.get("reasoning", ""))[:2000],
        "seed_rules": rules[:6],
        "rejected_rules": rejected[:6],
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
        self.executable = executable or os.environ.get("QUANTLAB_CODEX", CODEX_DEFAULT)
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


class ClaudeCliAdvisor:
    """The proposer, over the operator's own Claude Code subscription.

    There is no API key on this machine and there does not need to be: the CLI is
    already signed in, so the loop asks it the same way it asks Codex -- a
    subprocess, a briefing on stdin, JSON back.

    Three limits, and they are the reason this is a safe thing for an unattended
    loop to invoke:

    **No tools.** `--allowed-tools ""` grants none, so the model cannot read a
    file, run a command, or edit anything. It receives a briefing as text and
    answers as text. `--permission-mode plan` is belt and braces: even if a tool
    were somehow reachable, a write would need an approval nobody is there to
    give.

    **No session.** Each call is a fresh `-p` invocation with no resume, so one
    iteration cannot poison the next through accumulated context, and a briefing
    is the ONLY thing the model sees.

    **JSON or nothing.** The reply is parsed and then validated field by field
    like every other advisor's. What the loop acts on is a module name from a
    fixed set and rule trees the grammar accepted -- never text, never code.

    Cost is a subscription window rather than metered tokens, so exhaustion
    arrives as a refusal to answer. That is handled exactly like an HTTP 429:
    rest, record it, and keep iterating without this seat filled.
    """

    handle = PROPOSER_HANDLE

    def __init__(
        self,
        executable: str | None = None,
        model: str | None = None,
        system: str = PROPOSER_SYSTEM,
        timeout: float = 300.0,
    ):
        self.executable = executable or os.environ.get(
            "QUANTLAB_CLAUDE", os.path.expanduser("~/.local/bin/claude")
        )
        self.model = model or os.environ.get("QUANTLAB_PROPOSER_MODEL", "opus")
        self.system = system
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
            self.last_error = f"no claude cli at {self.executable}"
            return None
        import subprocess

        command = [
            self.executable,
            "-p",
            "--model",
            self.model,
            "--allowed-tools",
            "",
            "--permission-mode",
            "plan",
            "--output-format",
            "text",
            "--append-system-prompt",
            self.system,
        ]
        try:
            result = subprocess.run(
                command,
                input=briefing,
                text=True,
                capture_output=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            self.last_error = f"claude cli timed out after {self.timeout:.0f}s"
            return None
        except (OSError, subprocess.SubprocessError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "")[:400]
            self.last_error = detail
            if looks_exhausted(None, detail):
                self.rest()
                self.last_error = (
                    f"the Claude subscription window is spent; resting "
                    f"{COOLDOWN_SECONDS // 60} minutes"
                )
            return None
        parsed = _parse_json(result.stdout)
        if parsed is None and looks_exhausted(None, result.stdout):
            self.rest()
            self.last_error = (
                f"the Claude subscription window is spent; resting "
                f"{COOLDOWN_SECONDS // 60} minutes"
            )
            return None
        self.last_error = None if parsed else "reply was not JSON"
        return parsed


def validate_review(review: Any) -> dict[str, Any] | None:
    if not isinstance(review, dict):
        return None
    concerns = [str(c)[:300] for c in (review.get("concerns") or [])][:8]
    return {
        "concerns": concerns,
        "lookahead_risk": bool(review.get("lookahead_risk")),
        # A reviewer that names no concern cannot block. `{}` and
        # `{"blocking": true}` both parse, and either one would otherwise
        # silence the seed rules of every iteration for as long as it took
        # somebody to notice that the reason was always empty.
        "blocking": bool(review.get("blocking")) and bool(concerns),
        "note": str(review.get("note", ""))[:1200],
    }


def reviewer_from_environment() -> Any | None:
    """The local Codex reviewer, or nothing when it is not installed.

    Built separately from the pair above because it is the only member that
    reads the WORKING COPY. The proposer and the refuter argue about a
    hypothesis; this one opens the files and checks whether the hypothesis is
    even runnable against the code as it stands. In its first live round it
    found that the parameter being proposed would raise a `ValueError` on
    construction -- a thing no amount of reasoning about the idea would catch.

    Returns None rather than a disabled object when the executable is absent,
    so the loop's "is there a reviewer" question has one answer and not two.
    `QUANTLAB_CODEX=off` parks it without uninstalling anything.
    """
    executable = os.environ.get("QUANTLAB_CODEX", CODEX_DEFAULT)
    if not executable or executable.lower() in {"off", "none", "disabled"}:
        return None
    reviewer = CodexAdvisor(executable=executable)
    return reviewer if os.path.exists(reviewer.executable) else None


def from_environment() -> tuple[Any, Advisor]:
    """The operator's pair, configured from the environment and never from a file.

    The proposer prefers an API key when one exists and otherwise falls back to
    the Claude Code CLI already signed in on this machine -- which is the normal
    case here, because the operator has a subscription and no key. Both paths
    produce the same validated JSON, so nothing downstream knows or cares which
    one answered.

    Keys, when present, are read from the process environment so nothing can leak
    one into the repository, a log, or a Wall post.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    proposer: Any
    if key:
        proposer = Advisor(
            handle=PROPOSER_HANDLE,
            endpoint=os.environ.get(
                "QUANTLAB_PROPOSER_URL", "https://api.anthropic.com/v1/messages"
            ),
            model=os.environ.get("QUANTLAB_PROPOSER_MODEL", "claude-opus-4-5"),
            api_key=key,
            system=PROPOSER_SYSTEM,
            style="anthropic",
        )
    else:
        proposer = ClaudeCliAdvisor()
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
