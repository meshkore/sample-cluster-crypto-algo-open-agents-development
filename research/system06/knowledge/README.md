# system06 · continuous-learning notebook

The trading loop trains and backtests. This folder is the **other half**: a running
memory of what the world already knows about ML-for-trading, and which of those ideas
we have folded into our own system. The point rjj set: *we cannot live on four of my
ideas — we must feed on the world's ideas, apply what fits, and keep improving.*

## How it works (the honest architecture)

The autoloop is a plain Python process — it cannot browse the web or reason over a
paper. The **supervising agent** (Claude) is the research engine. On every supervision
cycle (~45 min, which is roughly one training iteration), while the GPU trains, the
agent:

1. **Reads** — searches papers (arXiv, SSRN), quant blogs (Hudson & Thames, Alpha
   Architect, QuantStrategy), Medium, and YouTube transcripts for ML-for-trading
   techniques relevant to *our* system: a behaviour-cloning causal-TCN oracle, 15m
   bars, 14 pooled cryptos, **long-only**, judged on **positive-every-calendar-year**
   consistency. Sources logged to `sources.jsonl`.
2. **Extracts** — turns each source into concrete, testable ideas mapped to one of our
   levers: **label**, **feature/normalisation**, **risk/sizing**, **selection**,
   **architecture**, **data**. Logged to `ideas.jsonl` with an application note.
3. **Applies** — converts the most promising idea into a real change (code behind an
   off-by-default flag, a new search-space entry, or a new risk-grid dimension) and
   lets the loop's own per-year metric decide if it helps. No idea is "believed" — it
   is A/B tested against the incumbent, and the ledger is the judge.
4. **Records the verdict** — the idea's `status` moves proposed → testing → applied /
   rejected, with the measured effect on the worst-year / score. Negative results are
   kept: knowing an idea did *not* help is knowledge too.

## The rules that never bend (from CLAUDE.md)

- **Long-only.** We buy low and sell high; we never short. Long spot buys with no
  credit are the trades market-makers cannot squeeze, and we can sit in a position for
  as long as we like. Every idea must respect this.
- **2026 is sealed.** Never an optimisation input. Ideas are selected on 2018–2025
  per-year consistency only.
- **25% peak-to-trough mandate.** Any idea that survives only by nearing the cliff is
  overfit and is rejected.
- Research-only software: no live orders, wallets, or exchange secrets — ever.

## Files

- `ideas.jsonl` — one idea per line: `{id, title, lever, source, summary, application,
  status, priority, added, result}`. The backlog + verdicts.
- `sources.jsonl` — one source per line: what was read, when, key takeaways.

The monitor (`dashboard.html`) reads `ideas.jsonl` and shows an **Aprendizaje** panel:
what we have learned, what is being tested, what has been applied.
