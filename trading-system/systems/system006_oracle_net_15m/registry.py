"""The architecture registry: one ID per trading-system ARCHITECTURE, with its record.

Operator, 2026-08-30: when the architecture changes - not merely the values of the
levers - the system gets a NEW ID, and to that ID we attach the source it runs, an
explanation, an architecture diagram, and every backtest that belongs to it. All of
it in one place, so the infinite loop has a memory of what was tried, what was
dropped, and how each thing behaved.

## What counts as a new architecture

The line has to be sharp or the registry fills with noise. Here it is STRUCTURE, not
magnitude:

  * NEW ID: a module joins or leaves the decision path; the labeller changes; the
    feature set changes; the data topology changes (universe identity, timeframe);
    the pipeline gains or loses a stage.
  * SAME ID, new config: any numeric lever moves (deployment ceiling, meta margin,
    stop, money-model strength...). Those are configurations OF an architecture and
    are recorded as such, because that is what they are.

So `regime_deploy 0.35 -> 0.50` keeps the ID; switching the labeller or adding the
seasoning gate mints a new one.

## Layout, all under research/system06/registry/

  architectures.jsonl        one row per architecture, newest last
  <ARCH-ID>/explain.md       what it is, why it exists, what changed from its parent
  <ARCH-ID>/diagram.mmd      the decision path as a diagram (mermaid, renders anywhere)
  <ARCH-ID>/code.json        module set, levers, labeller, features, git commit
  <ARCH-ID>/backtests.jsonl  every measurement attached to this architecture

Nothing here decides anything; it records. That separation is deliberate - a registry
that could influence selection would be another way for the sealed year to leak in.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06/registry")
INDEX = ROOT / "architectures.jsonl"

# The structural axes. A change in any of these mints a new ID; a change in a numeric
# lever does not. Kept explicit rather than inferred, so the rule is auditable.
STRUCTURAL_KEYS = ("modules", "labeller", "features", "universe_id", "timeframe", "pipeline")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001 - a registry entry must never fail on git
        return None


def fingerprint(spec: dict) -> str:
    """A stable hash of the STRUCTURAL part of a spec (values deliberately ignored)."""
    core = {k: spec.get(k) for k in STRUCTURAL_KEYS}
    core["modules"] = sorted(core.get("modules") or [])
    core["features"] = sorted(core.get("features") or [])
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def read_index() -> list[dict]:
    if not INDEX.is_file():
        return []
    rows = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def find_by_fingerprint(fp: str) -> dict | None:
    for row in read_index():
        if row.get("fingerprint") == fp:
            return row
    return None


def next_id() -> str:
    n = len(read_index()) + 1
    return f"ARCH-{n:04d}"


def diagram(spec: dict) -> str:
    """The decision path as mermaid - drawn from the spec, so it cannot drift."""
    mods = spec.get("modules") or []
    lines = ["flowchart TD",
             f'  D["Market data · {spec.get("timeframe", "?")} · '
             f'{spec.get("universe_size", "?")} assets"] --> F["Features: {spec.get("features_label", "causal price/vol/trend")}"]',
             f'  F --> N["{spec.get("model", "neural net")} — scores EVERY asset each bar"]',
             '  N --> C["Conviction 0–1 per asset"]']
    prev = "C"
    for i, m in enumerate(m for m in mods if m not in ("oracle-nn",)):
        node = f"M{i}"
        lines.append(f'  {prev} --> {node}["{m}"]')
        prev = node
    lines += [f'  {prev} --> R["Rank by conviction · scarce slots to the highest"]',
              '  R --> S["Position sizing"]',
              '  S --> X["Exits: stops, trail, conviction, mandate"]',
              '  X --> P["Portfolio · long-only spot"]']
    return "\n".join(lines)


def register(spec: dict, *, explanation: str, parent: str | None = None,
             note: str = "") -> dict:
    """Register `spec` as an architecture, or return the existing row if unchanged.

    Idempotent by fingerprint: calling it twice for the same structure does not mint
    a second ID, so the loop can call it on every cycle without polluting the record.
    """
    fp = fingerprint(spec)
    existing = find_by_fingerprint(fp)
    if existing:
        return existing

    arch_id = next_id()
    folder = ROOT / arch_id
    folder.mkdir(parents=True, exist_ok=True)
    row = {"id": arch_id, "fingerprint": fp, "created_at": _now(), "parent": parent,
           "title": spec.get("title") or arch_id, "status": spec.get("status", "candidate"),
           "git_commit": _git_commit(), "note": note,
           "structure": {k: spec.get(k) for k in STRUCTURAL_KEYS}}
    (folder / "code.json").write_text(json.dumps(
        {"spec": spec, "fingerprint": fp, "git_commit": row["git_commit"]},
        indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (folder / "diagram.mmd").write_text(diagram(spec), encoding="utf-8")
    (folder / "explain.md").write_text(
        f"# {arch_id} — {row['title']}\n\n"
        f"*Registered {row['created_at']}*"
        + (f" · parent **{parent}**" if parent else " · first architecture on record")
        + f" · code `{row['git_commit'] or 'unknown'}`\n\n{explanation.strip()}\n\n"
        "## Structure\n\n"
        + "\n".join(f"- **{k}**: {spec.get(k)}" for k in STRUCTURAL_KEYS)
        + "\n\n## Diagram\n\nSee `diagram.mmd` (mermaid).\n\n"
        "## Backtests\n\nEvery measurement attached to this architecture is appended to "
        "`backtests.jsonl`, newest last.\n", encoding="utf-8")
    (folder / "backtests.jsonl").touch()
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    with INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row


def attach_backtest(arch_id: str, record: dict) -> None:
    """Attach one measurement to an architecture. Never overwrites; append-only."""
    folder = ROOT / arch_id
    if not folder.is_dir():
        raise ValueError(f"unknown architecture {arch_id!r}")
    row = {"at": _now(), **record}
    with (folder / "backtests.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def backtests(arch_id: str) -> list[dict]:
    p = ROOT / arch_id / "backtests.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def set_status(arch_id: str, status: str, reason: str = "") -> None:
    """Mark an architecture active / superseded / rejected, keeping the reason."""
    rows = read_index()
    for r in rows:
        if r.get("id") == arch_id:
            r["status"] = status
            r["status_reason"] = reason
            r["status_at"] = _now()
    INDEX.write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows)
                     + "\n", encoding="utf-8")


def summary() -> list[dict]:
    """Index rows plus their measurement counts - what the dashboard publishes."""
    out = []
    for r in read_index():
        bt = backtests(r["id"])
        sealed = [b for b in bt if b.get("sealed_2026") is not None]
        out.append({**r, "backtest_count": len(bt),
                    "best_sealed_2026": max((b["sealed_2026"] for b in sealed), default=None),
                    "median_sealed_2026": (sorted(b["sealed_2026"] for b in sealed)[len(sealed) // 2]
                                           if sealed else None)})
    return out
