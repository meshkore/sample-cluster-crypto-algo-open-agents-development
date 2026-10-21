# System 10 - summary

Conditions + an AI exit + signal-strength sizing, chosen by a 24/7 walk-forward search. Design:
`.meshkore/context/archive/system10-design.md`. Operating notes and the decision log:
`research/system10/README.md`.

| module | role |
|---|---|
| `search.py` | the World (bars, features), the gate, the selector, the AI exit, trials, releases, the model card |
| `../../../research/system10/tools/conditions.py` | the book (`book_year`): fills, costs, money management |
| `bandit.py` | the small nets the selector and the exit fit |
| `evaluator.py` | reads the newest release on 2026 every hour |
| `paper.py` | paper-trades the pinned release on live bars ($50,000 from 2026-10-13; stopped 2026-10-21) |
| `status.py` | the Live tab's status, every 10 s |
| `review.py`, `pivots.py` | health every 15 min, daily stall gate, 8-hour and weekly reports |
| `strategy.py` | the registered brain (abstains; the paper book is the live path) |
| `features.py`, `region.py` | the feature registry and the oracle helpers `conditions.py` reads |

## 1. Hypothesis
Conditions taken from the oracle's best trades, plus an AI selector and exit with stakes sized by signal strength, can make money in EVERY unseen year with max drawdown ≤ 25%.

## 2. What it is
The walk-forward search above. The paper book traded the pinned release (33: momentum boost) from 2026-10-13 to 2026-10-21; a BingX mirror follows it, shadow unless the operator arms it.

## 3. What helped
Signal-strength sizing; 5 small slots; drawdown-scaled stakes; momentum boost (2× stake for the top-5 coins by 90-day return).

## 4. What hurt
Every RL variant, the GPU forecaster, the account stop, market-health halts (decision log in `research/system10/README.md`).

## 5. What is still open
`research/system10/IMPROVEMENTS.md`.

## 6. Rules learned
Choose on ≤ 2025 only; 2026 is read, never used to choose. Selection law (2026-10-15): regular floor of the worst years + recent years weighted more − drawdown; one boom year cannot win.
