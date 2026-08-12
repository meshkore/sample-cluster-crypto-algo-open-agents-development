"""The laboratory's diary: what was tried, by which system, and how it went.

Three records already exist and none of them answers the question a person
actually asks.

- `hypotheses.jsonl` is the VERDICT. One line per iteration, machine-shaped,
  and it says nothing about what the iteration did to reach it.
- `journal/H-*.jsonl` is the WORK. Every stage, generation and backtest of one
  hypothesis, append-only -- and unreadable, because it is a thousand JSON
  events describing an hour.
- `.meshkore/log/<date>.md` is the DAY, written by hand, and per-machine.

What is missing is the thing between them: a readable account of each
hypothesis, and an index that groups them BY TRADING SYSTEM. That grouping is
not cosmetic. This laboratory now runs more than one system -- the four-module
daily brain and the intraday second system -- and a flat list of `H-L001..107`
silently implies they are one line of research. They are not; they have
different tapes, different bar intervals and different failure modes, and a
result from one is not evidence about the other.

Everything here is DERIVED. The diary is regenerated from the ledger and the
journals and never written to by hand, so it cannot drift from the record it
describes: if the two disagree, the diary is wrong by construction and one
regeneration fixes it. Nothing in this module mutates its inputs.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
import json

# Which system a record belongs to when it does not say.
#
# Every ledger record written before the field existed came from the daily
# four-module brain, because it was the only system that existed. Guessing
# forward would be a lie; guessing backward is simply the history.
DEFAULT_SYSTEM = "four-module"

# `piece` values the four-module loop rotates through. A record naming one of
# these is that system's, whatever else it carries.
FOUR_MODULE_PIECES = {
    "policy",
    "detector",
    "bull",
    "bear",
    "sideways",
    "loop",
    "universe",
}


def system_of(record: dict[str, Any]) -> str:
    """Which trading system this hypothesis belongs to.

    An explicit `system` field wins. Failing that, an explicit strategy family
    wins. Failing both, a recognised four-module `piece` decides it, and the
    remainder falls back to the default rather than inventing a new system for
    every unfamiliar `piece` -- an index that grows a section per typo is worse
    than one that occasionally files a record under the wrong heading.
    """
    for key in ("system", "strategy_family", "family"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    piece = str(record.get("piece") or "").lower()
    if piece in FOUR_MODULE_PIECES:
        return DEFAULT_SYSTEM
    return DEFAULT_SYSTEM


def read_ledger(path: Path | str) -> list[dict[str, Any]]:
    """Every record, oldest first. A corrupt line is skipped, never fatal."""
    records: list[dict[str, Any]] = []
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return records
    for line in lines:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def read_journal(journal_dir: Path | str, identifier: str) -> list[dict[str, Any]]:
    """One hypothesis's events, oldest first. Missing is empty, not an error."""
    events: list[dict[str, Any]] = []
    try:
        lines = (Path(journal_dir) / f"{identifier}.jsonl").read_text().splitlines()
    except OSError:
        return events
    for line in lines:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _verdict(record: dict[str, Any]) -> str:
    raw = str(record.get("verdict") or "").upper()
    return raw if raw else "OPEN"


def _one_line(record: dict[str, Any], limit: int = 120) -> str:
    """The claim, on one line, for the index."""
    text = " ".join(str(record.get("statement") or "").split())
    if not text:
        return "(no statement recorded)"
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _stage_summary(events: Iterable[dict[str, Any]]) -> list[tuple[str, int]]:
    """How many events of each stage, in the order the stages first appeared.

    Order matters more than count here: it is what shows whether an iteration
    walked the loop or bounced between two boxes.
    """
    order: list[str] = []
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        stage = str(event.get("stage") or event.get("node") or "").strip()
        if not stage:
            continue
        if stage not in counts:
            order.append(stage)
        counts[stage] += 1
    return [(stage, counts[stage]) for stage in order]


def render_hypothesis(record: dict[str, Any], events: list[dict[str, Any]]) -> str:
    """One hypothesis as a page: the claim, the verdict, the work, the numbers."""
    identifier = str(record.get("id") or "?")
    lines = [
        f"# {identifier} — {_verdict(record)}",
        "",
        f"- **System**: {system_of(record)}",
        f"- **Iteration**: {record.get('iteration', '?')}",
        f"- **Piece**: {record.get('piece', '?')}",
        f"- **Recorded**: {record.get('at') or record.get('recorded') or '?'}",
        f"- **Consulted 2026**: {'yes' if record.get('opened_2026') else 'no'}",
    ]
    if record.get("commit"):
        lines.append(f"- **Commit**: {record['commit']}")
    lines += ["", "## Claim", "", str(record.get("statement") or "_none recorded_")]

    notes = str(record.get("notes") or "").strip()
    if notes:
        lines += ["", "## What was found", "", notes]

    metrics = record.get("metrics")
    if isinstance(metrics, dict) and metrics:
        lines += [
            "",
            "## Measurements",
            "",
            "```json",
            json.dumps(metrics, indent=1, sort_keys=True, default=str),
            "```",
        ]

    stages = _stage_summary(events)
    if stages:
        lines += [
            "",
            "## What the loop did",
            "",
            f"{len(events)} journal events across {len(stages)} stages, "
            "in the order they were first reached:",
            "",
        ]
        lines += [f"- `{stage}` × {count}" for stage, count in stages]
    elif not events:
        lines += [
            "",
            "## What the loop did",
            "",
            "_No journal for this hypothesis._ Records written by hand, and "
            "records from before the journal existed, have no event stream — "
            "the claim and the measurements above are the whole account.",
        ]

    return "\n".join(lines) + "\n"


def render_index(records: list[dict[str, Any]]) -> str:
    """Every hypothesis, grouped by system, newest first inside each."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[system_of(record)].append(record)

    lines = [
        "# Research diary",
        "",
        "Derived from `ledger/hypotheses.jsonl` and `journal/`. Regenerated by "
        "the loop after every iteration and by `quantlab diary`. Never edit a "
        "file in here — the next regeneration overwrites it.",
        "",
        f"{len(records)} hypotheses across {len(grouped)} trading "
        f"{'system' if len(grouped) == 1 else 'systems'}.",
        "",
    ]

    for system in sorted(grouped):
        entries = sorted(
            grouped[system],
            key=lambda r: (r.get("iteration") or 0, str(r.get("id") or "")),
            reverse=True,
        )
        tally: dict[str, int] = defaultdict(int)
        for record in entries:
            tally[_verdict(record)] += 1
        counted = ", ".join(
            f"{count} {name.lower()}" for name, count in sorted(tally.items())
        )
        lines += [
            f"## {system}",
            "",
            f"{len(entries)} hypotheses — {counted}.",
            "",
            "| hypothesis | iter | piece | verdict | claim |",
            "|---|---|---|---|---|",
        ]
        for record in entries:
            identifier = str(record.get("id") or "?")
            claim = _one_line(record).replace("|", "\\|")
            lines.append(
                f"| [{identifier}]({system}/{identifier}.md) "
                f"| {record.get('iteration', '?')} "
                f"| {record.get('piece', '?')} "
                f"| {_verdict(record)} | {claim} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def write(
    ledger_path: Path | str,
    journal_dir: Path | str,
    out_dir: Path | str,
) -> dict[str, Any]:
    """Regenerate the whole diary. Returns what it wrote.

    Idempotent and total: it rewrites every page from the record each time
    rather than appending, so a page can never hold a stale verdict from before
    a hypothesis was resolved.
    """
    records = read_ledger(ledger_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    written = 0
    systems: set[str] = set()
    for record in records:
        identifier = str(record.get("id") or "").strip()
        if not identifier:
            continue
        system = system_of(record)
        systems.add(system)
        page = out / system / f"{identifier}.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            render_hypothesis(record, read_journal(journal_dir, identifier))
        )
        written += 1

    (out / "INDEX.md").write_text(render_index(records))
    return {
        "hypotheses": written,
        "systems": sorted(systems),
        "index": str(out / "INDEX.md"),
    }
