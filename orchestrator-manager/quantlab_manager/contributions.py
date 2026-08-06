"""Intake and security review for outside contributions.

Anyone may propose code. Nothing they propose runs, and nothing reaches `main`,
until it has passed this gate. The gate is deliberately two layers, because a
reviewer that can be argued with is not a security control:

1. :func:`screen` — deterministic rules over the diff itself. They read no
   prose, so a persuasive pull-request description cannot move them. Any hit is
   a BLOCK and the reviewing agent is never even asked.
2. A dedicated review agent, which only ever sees a diff written to a file and
   framed as untrusted, and which cannot merge, push or execute anything.

The verdict gates the merge; it does not perform it. Merging stays an operator
action on purpose: an automated approval path is the one component whose
failure mode is unbounded.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from quantlab_backtester.models import utc_now


APPROVE = "APPROVE"
REVISE = "REVISE"
BLOCK = "BLOCK"
VERDICTS = (APPROVE, REVISE, BLOCK)

# A contribution larger than this is not reviewable in one pass, and an
# enormous diff is itself a way to hide one bad line.
MAXIMUM_DIFF_BYTES = 400_000
MAXIMUM_FILES = 60


class Rule:
    """One deterministic screening rule."""

    def __init__(self, name: str, why: str, paths: str = "", added: str = ""):
        self.name = name
        self.why = why
        self.paths = re.compile(paths) if paths else None
        self.added = re.compile(added, re.IGNORECASE) if added else None


# Ordered by how badly the project loses if the rule is wrong.
RULES = (
    Rule(
        "secrets",
        "touches credentials, tokens or runtime state that must never travel",
        paths=r"(^|/)(\.meshkore/credentials|\.env|credentials|secrets)(/|$)"
        r"|token|\.pem$|\.key$|id_rsa",
    ),
    Rule(
        "execution-capability",
        "introduces order placement, wallets or exchange secrets, which this "
        "project may never contain",
        added=r"\b(place_order|create_order|new_order|withdraw|private_key|"
        r"api_secret|secret_key|wallet)\b",
    ),
    Rule(
        "shorting",
        "introduces short exposure, and the laboratory is long-only",
        added=r"\b(short|sell_short|go_short|borrow)\b\s*[=(:]",
    ),
    Rule(
        "shell-out",
        "adds process execution or dynamic evaluation",
        added=r"\b(subprocess\.|os\.system|os\.popen|eval\(|exec\(|"
        r"__import__\(|pickle\.loads|child_process)",
    ),
    Rule(
        "network",
        "adds outbound network access, which a strategy never needs",
        added=r"\b(urllib\.request|requests\.|httpx\.|socket\.|fetch\(|"
        r"XMLHttpRequest|websocket)",
    ),
    Rule(
        "infrastructure",
        "changes the daemon, deployment, service or CI surface",
        paths=r"(^|/)(service\.py|public_mirror\.py|cloudflare/|\.github/|"
        r"scripts/)|Dockerfile|wrangler",
    ),
    Rule(
        "dependencies",
        "adds or changes dependencies, which is a supply-chain decision",
        paths=r"(^|/)(pyproject\.toml|requirements.*\.txt|package(-lock)?\.json)$",
    ),
    Rule(
        "gate-tampering",
        "modifies the security gate, the champion ranking or the criteria that "
        "judge it",
        paths=r"(^|/)(contributions\.py|champion\.py|inbox\.py|SYSTEM_CRITERIA\.md)$",
    ),
)


def changed_paths(diff: str) -> list[str]:
    return sorted(
        {match.group(1) for match in re.finditer(r"^\+\+\+ b/(.+)$", diff, re.M)}
    )


def added_lines(diff: str) -> str:
    return "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def screen(diff: str) -> list[dict[str, str]]:
    """Deterministic findings. A non-empty result is an automatic BLOCK."""
    paths = changed_paths(diff)
    additions = added_lines(diff)
    findings: list[dict[str, str]] = []
    if len(diff.encode("utf-8", "ignore")) > MAXIMUM_DIFF_BYTES:
        findings.append(
            {
                "rule": "size",
                "why": "the diff is too large to review in one pass",
                "evidence": f"{len(diff)} bytes",
            }
        )
    if len(paths) > MAXIMUM_FILES:
        findings.append(
            {
                "rule": "size",
                "why": "too many files changed for one contribution",
                "evidence": f"{len(paths)} files",
            }
        )
    for rule in RULES:
        if rule.paths:
            hits = [path for path in paths if rule.paths.search(path)]
            if hits:
                findings.append(
                    {
                        "rule": rule.name,
                        "why": rule.why,
                        "evidence": ", ".join(hits[:5]),
                    }
                )
                continue
        if rule.added:
            match = rule.added.search(additions)
            if match:
                findings.append(
                    {
                        "rule": rule.name,
                        "why": rule.why,
                        "evidence": match.group(0)[:120],
                    }
                )
    return findings


def parse_verdict(output: str) -> tuple[str, str]:
    """Read the reviewer's verdict, defaulting to the safe answer.

    An agent that rambles, crashes or answers in prose does not get to imply
    approval: anything we cannot read as an explicit APPROVE is a REVISE.
    """
    block = re.search(r"```json\s*(\{.*?\})\s*```", output, re.S)
    if block:
        try:
            payload = json.loads(block.group(1))
            verdict = str(payload.get("verdict", "")).upper()
            if verdict in VERDICTS:
                return verdict, str(payload.get("summary", ""))[:2000]
        except ValueError:
            pass
    match = re.search(r"^\s*VERDICT:\s*(\w+)", output, re.M | re.I)
    if match and match.group(1).upper() in VERDICTS:
        return match.group(1).upper(), output.strip()[-2000:]
    return REVISE, "No explicit verdict was returned, so the contribution is held."


class ContributionGate:
    """Discovers pull requests, screens them and records review verdicts."""

    def __init__(self, memory: Any, root: Path, gh: Optional[str] = None):
        self.memory = memory
        self.root = root
        self.gh = gh or "gh"

    # -- github --------------------------------------------------------------

    def _gh(self, *args: str, timeout: int = 60) -> Optional[str]:
        try:
            completed = subprocess.run(
                [self.gh, *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return completed.stdout if completed.returncode == 0 else None

    def available(self) -> bool:
        return self._gh("auth", "status", timeout=20) is not None

    def open_pull_requests(self) -> list[dict[str, Any]]:
        raw = self._gh(
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "30",
            "--json",
            "number,title,author,headRefOid,url,changedFiles,additions,deletions",
        )
        if not raw:
            return []
        try:
            return json.loads(raw)
        except ValueError:
            return []

    def diff(self, number: int) -> Optional[str]:
        return self._gh("pr", "diff", str(number), timeout=120)

    # -- persistence ---------------------------------------------------------

    def record(self, pull: dict[str, Any]) -> None:
        author = (pull.get("author") or {}).get("login") or "unknown"
        now = utc_now()
        with self.memory.transaction() as db:
            db.execute(
                """INSERT INTO contributions(number,title,author,head_sha,url,
                     files_changed,additions,deletions,state,first_seen,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,'OPEN',?,?)
                   ON CONFLICT(number) DO UPDATE SET
                     title=excluded.title,head_sha=excluded.head_sha,
                     files_changed=excluded.files_changed,
                     additions=excluded.additions,deletions=excluded.deletions,
                     updated_at=excluded.updated_at""",
                (
                    int(pull["number"]),
                    str(pull.get("title", ""))[:400],
                    author[:120],
                    str(pull.get("headRefOid", ""))[:64],
                    str(pull.get("url", ""))[:400],
                    int(pull.get("changedFiles") or 0),
                    int(pull.get("additions") or 0),
                    int(pull.get("deletions") or 0),
                    now,
                    now,
                ),
            )

    def reviewed(self, number: int, head_sha: str) -> bool:
        """True when this exact revision already has a verdict.

        Keyed on the head sha so that pushing new commits re-opens the gate:
        approving a pull request is approving a revision, not a title.
        """
        with self.memory.session() as db:
            return (
                db.execute(
                    """SELECT 1 FROM contribution_reviews
                       WHERE number=? AND head_sha=? LIMIT 1""",
                    (number, head_sha),
                ).fetchone()
                is not None
            )

    def save_review(
        self,
        number: int,
        head_sha: str,
        reviewer: str,
        verdict: str,
        findings: list[dict[str, str]],
        summary: str,
    ) -> None:
        with self.memory.transaction() as db:
            db.execute(
                """INSERT INTO contribution_reviews
                     (number,head_sha,reviewer,verdict,findings_json,summary,reviewed_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    number,
                    head_sha,
                    reviewer,
                    verdict,
                    json.dumps(findings, sort_keys=True),
                    summary[:4000],
                    utc_now(),
                ),
            )
            db.execute(
                """UPDATE contributions SET verdict=?,blocked_reason=?,updated_at=?
                   WHERE number=?""",
                (
                    verdict,
                    "; ".join(f"{f['rule']}: {f['why']}" for f in findings)[:1000]
                    or None,
                    utc_now(),
                    number,
                ),
            )

    def pending(self) -> list[dict[str, Any]]:
        with self.memory.session() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT number,title,author,head_sha,url,verdict,blocked_reason
                       FROM contributions WHERE state='OPEN' ORDER BY number"""
                )
            ]

    def summary(self) -> dict[str, Any]:
        with self.memory.session() as db:
            rows = [
                dict(row)
                for row in db.execute(
                    """SELECT c.number,c.title,c.author,c.url,c.verdict,
                              c.blocked_reason,r.summary,r.reviewed_at
                       FROM contributions c
                       LEFT JOIN contribution_reviews r
                         ON r.number=c.number AND r.head_sha=c.head_sha
                       WHERE c.state='OPEN' ORDER BY c.number DESC LIMIT 10"""
                )
            ]
        return {
            "open": len(rows),
            "awaiting_review": sum(1 for row in rows if not row["verdict"]),
            "blocked": sum(1 for row in rows if row["verdict"] == BLOCK),
            "approved": sum(1 for row in rows if row["verdict"] == APPROVE),
            "pull_requests": rows,
        }
