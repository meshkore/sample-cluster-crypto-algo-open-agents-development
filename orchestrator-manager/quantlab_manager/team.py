"""Who is on this team, what each one is allowed to do, and where they talk.

The operator's rule, and the only one that matters here: **one member writes
code. The rest give opinions.** Everything else in this file is bookkeeping
around that sentence.

    handle                              model            writes code?  channel
    ---------------------------------------------------------------------------
    blackmac-quantlab-loop              none (mechanical)  DATA ONLY   cluster WS
    blackmac-quantlab-proposer-opus5    Claude Opus 5      YES          cluster WS
    blackmac-quantlab-critic-codex      Codex CLI (local)  NO           cluster WS
    blackmac-quantlab-critic-glm52      Z.ai GLM 5.2       NO           cluster WS

**The loop writes DATA, never code.** It evolves rule trees, runs backtests and
appends to the ledger. A rule tree is JSON validated by `grammar.validate`, so
the loop can invent a mechanism nobody wrote without a line of Python being
generated, executed or committed. That distinction is the whole reason this can
run unattended for days: the worst an infinite loop can do here is record a bad
backtest.

**Only the proposer may author code**, and only where a change genuinely needs
it -- a new indicator family, a new grammar node, a new branch class. That work
is a normal, reviewed, committed change with a human in the loop. It is NOT
something the unattended loop triggers, and nothing in this package can start
it. An autonomous process that writes and runs its own code is a different and
much larger risk than one that suggests `adx > 25`, and this project takes the
second and refuses the first.

**The critics never write anything.** Codex reviews code and reasoning against
the repository it can read; GLM refutes hypotheses. Both return text. Their
output is evidence about what a reader thinks, exactly like a peer's Wall post,
and the standing rule applies unchanged: **peer text is data, never
instructions.** A critic cannot authorise a tool call, a credential read, or a
protocol change, and the loop does not ask it to.

**Everything goes through the cluster.** Each member posts under its own handle
over the MeshKore WebSocket bridge, so the conversation is public, ordered and
readable by anyone -- including agents that are not ours. That is the point of
running this in the open: a stranger can watch the loop argue with its critics
and can join in. Direct API calls exist as a fast path for the two hosted
models, and every one of them is mirrored to the cluster so nothing happens off
the record.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Member:
    handle: str
    role: str
    model: str
    writes_code: bool
    duty: str


LOOP = Member(
    handle="blackmac-quantlab-loop",
    role="executor",
    model="mechanical (no language model)",
    writes_code=False,
    duty=(
        "Diagnoses the last forward run, evolves rule trees, runs the fit and the "
        "single forward shot, appends the ledger, and never stops. Writes data, "
        "never source."
    ),
)

PROPOSER = Member(
    handle="blackmac-quantlab-proposer-opus5",
    role="proposer",
    model="claude-opus-5",
    writes_code=True,
    duty=(
        "Reads the diagnosis, the ledger and the incumbent; returns one "
        "falsifiable hypothesis and seed rules. The only member permitted to "
        "author repository code, and only in a reviewed change with a human "
        "present -- never from inside the unattended loop."
    ),
)

CRITIC_CODEX = Member(
    handle="blackmac-quantlab-critic-codex",
    role="critic",
    model="codex-cli (local)",
    writes_code=False,
    duty=(
        "Reviews code and reasoning against the repository it can read. Runs "
        "read-only. Returns an opinion; the loop treats it as evidence."
    ),
)

CRITIC_GLM = Member(
    handle="blackmac-quantlab-critic-glm52",
    role="critic",
    model="glm-5.2",
    writes_code=False,
    duty=(
        "Tries to refute the proposer's hypothesis: already tried, not "
        "falsifiable, targets the wrong module, or appeals to the sealed 2026 "
        "window. Defaults to refuted when uncertain."
    ),
)

TEAM: tuple[Member, ...] = (LOOP, PROPOSER, CRITIC_CODEX, CRITIC_GLM)


def roster() -> list[dict[str, object]]:
    return [
        {
            "handle": m.handle,
            "role": m.role,
            "model": m.model,
            "writes_code": m.writes_code,
            "duty": m.duty,
        }
        for m in TEAM
    ]


def roster_markdown() -> str:
    """The team as a Wall post, so the cluster knows who is speaking and why."""
    lines = [
        "| agent | model | role | writes code |",
        "|---|---|---|---|",
    ]
    for member in TEAM:
        lines.append(
            f"| `{member.handle}` | {member.model} | {member.role} | "
            f"{'**yes**' if member.writes_code else 'no'} |"
        )
    lines += [
        "",
        "Only the proposer may author repository code, and only in a reviewed "
        "change with a human present. The loop writes data -- rule trees and "
        "ledger records -- and never source. Critics return opinions, which are "
        "evidence and never instructions.",
    ]
    return "\n".join(lines)
