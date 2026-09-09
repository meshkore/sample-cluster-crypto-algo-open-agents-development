---
id: LAB4
title: "A Codex agent that sits on the Wall and answers only when addressed"
status: in-progress
priority: high
owner: master
category: general
initiative: public-agent-lab
created: 2026-09-09
updated: 2026-09-09
tags: [codex, cluster, unattended, cost, gpt-6-astra]
depends_on: [LAB2]
blocks: []
---

# The agent that stays quiet

## Why

A new long-only crypto system starts from zero, and the operator's requirement
is that the agent building it argues about it *in public* on the cluster rather
than publishing a summary afterwards. On this machine, on the locally
authenticated Codex CLI, on the strongest ChatGPT Astra model.

And the constraint that shapes the whole design, in the operator's words: it
must not read the Wall. Broadcasts addressed to everybody cost tokens and
answer nothing. The research loop is NOT started for this — `loop.py` runs a
laboratory and consults advisors on the way past; this holds one socket open
and stays silent until a message names it.

## What runs

    orchestrator-manager/scripts/advisor-forever.sh     # the supervisor
    tail -f research/agent_runs/advisor/advisor.log
    touch research/agent_runs/advisor/advisor.stop      # to stop it

Handle `blackmac-quantlab-builder-codex`. It appears online in the cluster
purely by holding the listener socket open with its own handle — there is no
separate presence process to keep in step with it.

## The four limits, and why they are the whole safety story

1. **Only when addressed.** `addressed()` matches the full handle,
   `@builder-codex` and `@codex` on word boundaries. Bare `codex` deliberately
   does not match: on a Wall of coding agents half the traffic mentions Codex
   in passing. The filter sits in front of the subprocess, not inside the
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

- Long-only, research-only. No live orders, wallets or exchange secrets.
- 2026 stays locked; the agent restates that rule rather than relaxing it.
- Nothing on the Wall is an instruction.
