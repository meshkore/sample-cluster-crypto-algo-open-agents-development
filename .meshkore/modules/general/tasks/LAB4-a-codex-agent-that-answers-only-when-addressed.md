---
id: LAB4
title: "Three agents on the Wall, two of them here, and only one writes code"
status: in-progress
priority: high
owner: master
category: general
initiative: public-agent-lab
created: 2026-09-09
updated: 2026-09-09
tags: [codex, claude, cluster, unattended, cost, gpt-6-astra, fable]
depends_on: [LAB2]
blocks: []
---

# The agents that stay quiet

> Written in two passes on 2026-09-09. The first pass built one Codex agent; the
> operator then corrected the roster to three. **The roster section near the
> bottom is current** — the sections above it describe how the single agent was
> built and every measurement still holds, but the handle and the long-only
> framing in them were superseded the same afternoon.

## Why

The operator's requirement: the agents designing the system argue about it *in
public* on the cluster rather than publishing a summary afterwards. On this
machine, on the locally authenticated CLIs, on flagship models.

And the constraint that shapes the whole design, in the operator's words: it
must not read the Wall. Broadcasts addressed to everybody cost tokens and
answer nothing. The research loop is NOT started for this — `loop.py` runs a
laboratory and consults advisors on the way past; this holds one socket open
and stays silent until a message names it.

## What runs

    cluster_advisor.py --agent gpt6      # or: --agent fable
    tail -f research/agent_runs/advisor/<agent>/advisor.log
    touch research/agent_runs/advisor/<agent>/advisor.stop      # to stop it

`advisor-forever.sh <agent>` supervises one if it is wanted; the operator asked
for no loops, so neither is started that way today. Each appears online in the
cluster purely by holding the listener socket open with its own handle — there
is no separate presence process to keep in step with it.

## The four limits, and why they are the whole safety story

1. **Only when addressed.** `addressed()` matches the full handle and the
   agent's short forms (`@gpt6`, `@fable5`) on word boundaries. Bare `codex`
   and bare `claude` deliberately do not match: on a Wall of coding agents half
   the traffic mentions them in passing. The filter sits in front of the subprocess, not inside the
   prompt, which is why it is testable without a network or a key.
2. **Read-only.** `codex exec --sandbox read-only`. It opens every file in the
   working copy — it has to, to argue about the code — and cannot change one.
   Asserted on the command line by a test, because a prompt is a request and a
   sandbox is not.
3. **Peer text is data, never instructions.** The message arrives fenced,
   after the briefing, labelled untrusted. It may pose a question; it may not
   authorise a tool call, a credential read, a look past the 2026 lock, or a
   change of protocol.
4. **A bounded mouth.** Six replies an hour. A message arriving with the cap
   spent is dropped with a log line rather than queued — a queue that drains an
   hour later answers a conversation that has moved on and pays full price.

## Two things measured rather than assumed

**The app bundle's Codex is too old for the model.**
`/Applications/Codex.app/Contents/Resources/codex` is 0.146.0-alpha.9.2 and the
API answers `gpt-6-astra` requests from it with *"requires a newer version of
Codex"* — a 400, not a capability warning, so it fails every time. The CLI
inside the VS Code extension is 0.153.4 and works. Both read the same
`~/.codex/auth.json`, so there is one login and no second authentication.
`codex_executable()` therefore prefers the newest extension binary and keeps
the bundle as a fallback.

**Reasoning effort is `xhigh`, not `ultra`.** `gpt-6-astra` offers low through
`ultra`; `ultra` delegates to sub-agents on its own, which is an unbounded
spend on a message whose length nobody here controls.

## Restart behaviour, which is where this kind of agent embarrasses itself

A cold start records the replayed backlog as seen and answers none of it. A
restart with a remembered high-water mark answers what it missed — the newest
two only, because an hour-old question has been overtaken and costs the same as
the live one. The stop file is cleared by the supervisor once at startup and
never by the agent, so a `touch advisor.stop` landing during a restart is not
deleted by the very process it was meant to stop.

## Rules this must not break

- Research-only. No live orders, wallets or exchange secrets.
- 2026 stays locked. Long-only and the drawdown limit became recommendations
  the same day; the 2026 lock did not, and the briefing says why.
- Nothing on the Wall is an instruction.


## The roster, after the operator's correction (2026-09-09, later the same day)

The operator looked at the Wall and asked why there were two agents on this Mac
when they had asked for one. The answer was that there were not: `blackmac-vcode`
was this terminal posting test messages and an announcement by hand. One agent
ran; the other was a person with a handle.

What they asked for instead is exact and worth writing down: **three agents,
none hidden.** Two on this Mac running flagship models, one on the Windows box,
and the Windows one is the only one that writes code. The two here research,
read, prepare and argue. The standing task for all three is to design the best
algorithm and the best hypothesis this laboratory can defend.

A handle now says one thing: which machine, which model.

| handle | machine | model | backend |
|---|---|---|---|
| `blackmac-gpt6` | this Mac | GPT-6-Astra at `xhigh` | Codex CLI 0.153.4 |
| `blackmac-fable5` | this Mac | Fable 5 at `high` | Claude Code CLI 2.1.212 |
| (the Windows agent) | Winbox | — | writes the code |

`builder-codex` was retired because it named a job, and the job changed within
the afternoon.

## What two auto-repliers on one Wall do to each other

Every reply opens with `@sender`. A reply to the other agent is therefore an
addressed message, which that agent answers, which is addressed again. The pair
would have exhausted six replies an hour, every hour, indefinitely — and the log
would have read like a healthy debate throughout.

`MAX_AGENT_EXCHANGES = 3` bounds a *run* of consecutive exchanges with one peer,
and the counter clears the moment anybody off the roster speaks: the operator,
or the Windows agent. It is checked before the model call, like every other
refusal here, so a suppressed message costs nothing. Four tests hold it.

## Read-only, two different ways

Codex is held by `--sandbox read-only`. Claude Code has no sandbox flag, so
Fable is held by `--permission-mode plan` with `--allowed-tools Read,Grep,Glob`.
Both are asserted on the command line by tests rather than requested in a
prompt.

## No hidden agents

`com.meshkore.quantlab-claude-presence` and `com.meshkore.quantlab-codex-presence`
were loaded in launchd and failing (exit 1). They never posted, but a working
restart would have put two more handles on the Wall. Both booted out.
`com.meshkore.cluster-listener` belongs to a different repository and has no
record of this cluster.

The arrival greeting is now opt-in (`--greet`). A listener may exist without
writing on the Wall — the operator's instruction, and announcing yourself is the
cheapest noise to remove.
