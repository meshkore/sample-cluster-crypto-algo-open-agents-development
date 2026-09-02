"""Render the whole idea backlog as one readable document. Nothing is ever dropped.

    PYTHONPATH=trading-system python research/system06/tools/build_ideas_index.py

Operator, 2026-09-02: *"no pierdas memoria de las ideas que te doy, hay que explorarlas
todas, hay que documentarlo todo, hay que tener como una especie de diario o de lista
de todas las ideas que hay que aplicar, probar, cómo, cuándo, dónde"*.

The memory already exists and is append-only by rule (`rnd/agenda.jsonl` - an idea is
killed with a measured result, never deleted). What was missing is a way to READ it.
This renders every idea, grouped by what is happening to it, with the four things the
operator asked for on each: what it is, why, how it gets tested, and what would kill
it. Regenerated on demand; the JSONL stays the source of truth.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RND = Path("research/system06/rnd")
OUT = Path("research/system06/IDEAS.md")

# Reading order: what is live first, what is proven next, what was measured and closed
# last - a closed idea is still worth reading, because it is why we do not retry it.
GROUPS = [
    ("queued", "🔜 En cola — se probarán a continuación"),
    ("running", "▶ En marcha o a medio medir"),
    ("proposed", "💡 Propuestas — esperando su turno"),
    ("win", "✅ Ganadoras — medidas y adoptadas"),
    ("win-conditional", "✅ Ganadoras con condiciones"),
    ("stage3b-pass", "✅ Pasaron su fase"),
    ("built", "🔧 Construidas, pendientes de medición"),
    ("measured", "📏 Medidas"),
    ("stage1-inconclusive", "❓ No concluyentes — el test no respondía a la pregunta"),
    ("shelved", "⏸ Aparcadas"),
    ("loss", "❌ Refutadas — medidas y cerradas, con su resultado"),
]


def main() -> int:
    rows = [json.loads(l) for l in
            (RND / "agenda.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    by_status = defaultdict(list)
    for r in rows:
        by_status[r.get("status", "proposed")].append(r)

    prog = [json.loads(l) for l in
            (RND / "program.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    by_agenda = defaultdict(list)
    for p in prog:
        if p.get("agenda"):
            by_agenda[p["agenda"]].append(p)

    parts = [
        "# Diario de ideas — system 06",
        "",
        f"*Generado {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC desde "
        "`rnd/agenda.jsonl`, que es la fuente de verdad y sólo crece: una idea se cierra "
        "con un resultado medido, nunca se borra.*",
        "",
        f"**{len(rows)} ideas** en el registro. "
        + " · ".join(f"{len(by_status[k])} {k}" for k, _ in GROUPS if by_status.get(k)),
        "",
        "Cada ficha lleva lo que el operador pidió: qué es, por qué, **cómo** se prueba, "
        "**qué la mataría**, y el resultado si ya se midió.",
        "",
    ]

    for status, title in GROUPS:
        items = by_status.get(status) or []
        if not items:
            continue
        prio = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda r: (prio.get(r.get("priority"), 9), r.get("id", "")))
        parts += [f"## {title}", ""]
        for r in items:
            head = f"### {r['id']} — {r.get('title', '')}"
            if r.get("priority") == "critical":
                head += "  ⭐"
            parts.append(head)
            meta = [r.get("world"), r.get("kind"), r.get("priority"),
                    f"creada {r.get('created_at', '?')}"]
            parts.append("*" + " · ".join(str(m) for m in meta if m) + "*")
            parts.append("")
            for label, key in (("Por qué", "rationale"), ("Qué esperamos", "expect"),
                               ("Cómo se prueba", "impl"), ("Qué la mataría", "kill"),
                               ("Resultado", "result")):
                if r.get(key):
                    parts.append(f"**{label}.** {r[key]}")
                    parts.append("")
            runs = by_agenda.get(r["id"]) or []
            if runs:
                parts.append("**Experimentos.** "
                             + "; ".join(f"`{p['id']}` ({p.get('status')})" for p in runs))
                parts.append("")
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"{len(rows)} ideas -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
