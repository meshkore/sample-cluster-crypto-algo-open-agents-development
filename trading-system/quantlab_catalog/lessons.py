"""Every transferable rule this laboratory has paid for, in one document.

Operator, 2026-09-09: *"as soon as a new strategy is generated, that you can consult
everything that has been done already"*, and earlier: *"cuando empecemos una nueva
estrategia lo primero que le vamos a decir es lee las estrategias anteriores"*.

Reading seven `SUMMARY.md` files is not that. A new system needs the LAWS - the things
that are true regardless of which hypothesis it is testing - and it needs them before it
writes any code, because most of them were bought with a sealed year that cannot be
bought twice.

So this collects section 6 of every system into one ordered document, with the system
that paid for each rule attached to it. Generated, never hand-edited: the per-system
`context.json` stays the single source of truth, and `test_lessons_current` fails if this
file drifts from it. A summary of the record that can disagree with the record is worse
than no summary, because it is the one people actually read.

    python -m quantlab_catalog.lessons          # rewrite the document
    python -m quantlab_catalog.lessons --check  # fail if it is stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .paths import REPO_ROOT

TRADING = REPO_ROOT / "trading-system"
OUT = REPO_ROOT / ".meshkore" / "context" / "LESSONS.md"

# Reading order, most-earned first. A champion's rules were paid for with sealed years;
# a frozen workshop's were paid for with a refutation, which is cheaper but still real;
# a blank system's are the method it inherits rather than anything it discovered.
RANK = {"champion": 0, "workshop": 1, "frozen": 2, "blank": 3}

HEAD = """# What this laboratory has already learned

*Generated from every system's `docs/context.json` by
`python -m quantlab_catalog.lessons`. Do not edit by hand — edit the system's own
record and regenerate, or the two will disagree and this is the one people read.*

**Read this before opening a new system.** Almost every rule below was bought with a
measurement that cost real time, and several were bought with a sealed year — a
resource that does not regenerate. Re-deriving them is the most expensive way to spend
a week that this laboratory offers.

"""

FOOT = """
---

## How to use this

A rule here is not advice, it is a **constraint that has already been tested**. If a new
hypothesis requires breaking one, that is allowed — but the break has to be argued
explicitly and measured, not walked past. The failure mode this document exists to
prevent is not disagreement; it is a system quietly re-running an experiment whose answer
is already written down.

The two rules that have cost the most, and that everything else tends to reduce to:

1. **Training return does not rank forward return.** System 04 measured +495.35% in
   training — the best figure ever produced here — and −5.81% on the sealed year.
2. **Price the odds before spending a sealed reading.** Three candidates were approved
   out of sample and lost the sealed year. The diagnosis was never "the edge is fake"; it
   was that a spread straddling 1.0 cannot be settled by a single year, and nobody
   computed the spread first.
"""


def collect() -> list[dict]:
    """Every documented system with its rules, ordered for reading."""
    out = []
    for ctx in sorted(TRADING.glob("systems/system*/docs/context.json")):
        doc = json.loads(ctx.read_text(encoding="utf-8"))
        if not doc.get("rules"):
            continue
        out.append({
            "id": doc.get("id") or ctx.parents[1].name,
            "name": doc.get("name") or "",
            "status": doc.get("status") or "undeclared",
            "rules": list(doc["rules"]),
            "package": ctx.parents[1].name,
        })
    out.sort(key=lambda d: (RANK.get(d["status"], 9), d["id"]))
    return out


def render(systems: list[dict]) -> str:
    total = sum(len(s["rules"]) for s in systems)
    parts = [HEAD, f"**{total} rules from {len(systems)} systems.**\n"]
    for s in systems:
        parts.append(f"\n## {s['name']}\n")
        parts.append(f"`{s['id']}` · {s['status']} · "
                     f"[its full record](../../trading-system/systems/{s['package']}/docs/SUMMARY.md)\n\n")
        for i, rule in enumerate(s["rules"], 1):
            parts.append(f"{i}. {rule}\n")
    parts.append(FOOT)
    return "".join(parts)


def build() -> str:
    return render(collect())


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = build()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != text:
            print(f"STALE: {OUT} does not match the systems' own records. "
                  f"Run: python -m quantlab_catalog.lessons")
            return 1
        print(f"current: {OUT}")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    systems = collect()
    print(f"wrote {OUT} - {sum(len(s['rules']) for s in systems)} rules from "
          f"{len(systems)} systems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
