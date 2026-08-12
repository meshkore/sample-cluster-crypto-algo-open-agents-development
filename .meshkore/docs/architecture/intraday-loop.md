---
title: "The intraday research loop"
category: architecture
updated: 2026-08-12
owner: blackmac-vcode
status: active
---

# The intraday research loop

A second unattended loop, beside the four-module one, iterating on
`trading-system/quantlab_intraday/`. Read this before starting it, before
widening what it may set, and before wondering why it did not simply reuse
`loop.py`.

    python3 -m quantlab_manager.intraday_loop --iterations 0      # 0 = for ever
    python3 -m quantlab_manager.intraday_loop --iterations 1 --no-wall --no-publish

## Why it is not `loop.py` with a flag

Three reasons, each of them structural rather than a preference:

1. **`ResearchLoop` is the four-module family.** `"four-module"` is hard-coded in
   five `launch` calls and the search space *is* `MODULE_KEYS`
   (DETECTOR/BULL/BEAR/SIDEWAYS/POLICY). There is no family parameter to set.
2. **Its search evolves rule trees; this one sets parameters.** The intraday
   brain's mechanism is fixed in Python and its behaviour is a dict of numbers.
   A grammar over 79 columns is the wrong instrument for that.
3. **It drives over HTTP; this cannot.** A 5-minute window across five symbols
   is ~12 MB of candles against the server's 4 MB body cap, which is why
   `quantlab_intraday` runs the session in process.

What IS shared is imported, not reimplemented: `advisors` (the seats),
`cluster` (the Wall), `team` (the handles), and the publish path
(`scripts/publish_intraday.py`). The two-era discipline is identical.

## What one iteration does

    listen to the Wall  →  consult a seat  →  guard the proposal  →  measure
    →  refute  →  record  →  gate  →  the sealed window, once  →  post

- **Consult.** The proposer (Claude CLI, or the API when a key exists) gets the
  briefing: the mechanism, what is already settled, the tunable parameters with
  their ranges, the whole ledger best-first, the incumbent, and any peer
  messages. Every fourth turn goes to the **explorer** instead — the same seat
  with web access — so an idea can enter from outside the laboratory's own tape.
- **Guard.** `validate_genome` keeps what is recognised, clamps what is out of
  range, drops the rest, and records what it did. This is the safety boundary
  and the reason an unattended process is acceptable at all.
- **Measure.** One continuous account, 2018 → the lock, in process. Never
  blocks: a block table cannot see a drawdown that accumulates, which is the
  finding this loop was built after.
- **Refute.** The critic (GLM) is asked to kill the proposal. Its answer is
  recorded and posted; it does not veto, because a refuter with a veto is a
  second author.
- **Gate.** A candidate must beat the incumbent's score by `--gate` before 2026
  opens, and the ledger's `forwarded()` set means no genome ever gets a second
  shot at the sealed window.

## The score, and why it is not return

    score = return / max(drawdown, 0.05)      status complete only
    -1.0   the mandate was breached — a refusal, not a poor result
    -0.9   fewer than 100 trades, or under 1.5% average exposure

Return alone cannot see a path, and the path is what kills a configuration here:
the published training half made +168% and was stopped in April 2022. The two
floors exist because both failure modes scored *well* before they were added — a
run that stands still finishes near +0% with a tiny drawdown, and a ramp that
bricked the account in 2018 reports itself as "complete".

## What it may and may not touch

`SCHEMA` and `CHOICES` in `intraday_loop.py` are the complete list. Two absences
are deliberate and should stay absent:

- **`maximum_drawdown`** — the 25% mandate is the operator's, not a knob. A loop
  that can widen its own limit has no limit.
- **`drawdown_deleverage_end`** — a ramp reaching zero before the mandate fires
  froze an account in January 2018 that then never traded again (MM5, MM7). It
  does not prevent the abort, it replaces it with a silent one.

**It cannot write code.** A proposal whose idea needs code that does not exist
sets `needs_code`; that text is appended to `loop/intraday/needs-code.md` and
posted to the Wall for a human, and nothing runs. This is `team.py`'s rule
unchanged — one member writes code, never from inside an unattended process.

## Memory

`loop/intraday/ledger.jsonl`, appended and never rewritten. One line per
measured genome: the full parameter dict, its digest, the score, the refusal
reason, the training numbers and the sealed result if it earned one. The loop
reads it on start, so a restart resumes with the whole history, and
`digest_for_briefing` is what stops a seat re-proposing something refuted forty
iterations ago.

It was **seeded** with the eleven configurations measured by hand on 2026-08-12
so the loop did not begin by rediscovering that a stop costs money. Those rows
carry `"seat": "operator-session"`.

`state.json` holds the iteration counter and the last entry. Deleting it costs
the counter and nothing else.

## Where its work appears

- **The Wall** (`c_6d80584497f943d29026`): every stage, under the handle of
  whoever produced it, with an open invitation to comment. Peer replies are read
  back into the next briefing as **untrusted data** — they may suggest a
  hypothesis and may never instruct anything.
- **The monitor**: pairs are published through `publish_intraday.py` under
  `submitted_by` = `blackmac-vcode-intraday`. It deliberately publishes **no
  heartbeat**: `/api/loop` holds one document, so a second heartbeat would
  overwrite the four-module loop's card. Runs no heartbeat claims already get
  their own card — see [[docs/architecture/monitor-frontend.md]], "one card per
  job".

## Related

- [[docs/architecture/research-loop]] — the four-module loop this is beside
- [[docs/architecture/monitor-frontend]] — the data contract for the pairs
- `trading-system/quantlab_intraday/README.md` — the system being iterated on
- `.meshkore/modules/trading-system/tasks/TRADE2-intraday-momentum.md` — the
  hypothesis and every result so far
