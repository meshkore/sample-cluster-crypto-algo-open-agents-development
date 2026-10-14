# System 10 - summary

Conditions + an AI exit + signal-strength sizing, chosen by a 24/7 walk-forward search. Design:
`.meshkore/context/system10-design.md`. Operating notes and the decision log:
`research/system10/README.md`.

| module | role |
|---|---|
| `search.py` | the World (bars, features), the gate, the selector, the AI exit, trials, releases, the model card |
| `../../../research/system10/tools/conditions.py` | the book (`book_year`): fills, costs, money management |
| `bandit.py` | the small nets the selector and the exit fit |
| `evaluator.py` | reads the newest release on 2026 every hour |
| `paper.py` | paper-trades the pinned release on live bars ($50,000 from 2026-10-13) |
| `status.py` | the Live tab's status, every 10 s |
| `review.py`, `pivots.py` | health every 15 min, daily stall gate, 8-hour and weekly reports |
| `strategy.py` | the registered brain (abstains; the paper book is the live path) |
| `features.py`, `region.py` | the feature registry and the oracle helpers `conditions.py` reads |
