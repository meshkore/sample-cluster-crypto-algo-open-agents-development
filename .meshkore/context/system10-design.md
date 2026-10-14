---
title: "System 10 - design"
updated: 2026-10-14
status: active
---

# System 10 - conditions, an AI exit and signal-strength sizing

Operating detail and the decision log: `research/system10/README.md`. The RL design this file
used to hold (2026-09-27) was tried and closed; it is in git tag `s10-before-cleanup`.

## 0. Status

Active, one line of work. Release 31: every unseen year 2022-2025 positive (worst +10.3%,
CAGR +30.8%, max DD 24.7%), 2026 forward +22.4% (DD 17.3%). Paper-traded with $50,000 from
2026-10-13. The search runs 24/7 on four workers.

## 1. Hypothesis

The edge is in **choosing the conditions** in which to trade, not in a cleverer learner: a
market gate decides when, a small selector decides which trade, a forecast of the next day's
return decides when to leave and how big to be. Money management, not the model, keeps the
drawdown under 25%.

## 2. Mechanism

Per 15-minute bar, 14 coins, long only:
1. **Gate** - BTC above / below its N-day average splits the market in two; per side, the share
   of coins in an uptrend (breadth) must clear a threshold.
2. **Selector** - per regime, four small nets trained on years < N score each opportunity.
3. **Exit and strength** - four regressors forecast the next day's return from 64 causal columns
   (the coin, BTC, 1h-1w views, lagged macro). Buy when >= +0.3%, sell when < -0.3%; stake =
   forecast / 1% of a slot (25-100%); every 4 h add a quarter slot if >= +0.6%, sell half if < 0.
4. **Book** - N slots, per-trade stop, trailing stop, max hold, stakes x0.75 in the falling
   regime and shrinking with drawdown (x max(0.25, 1 - DD / L)).

## 3. How it is chosen

Walk-forward: everything fitted on years < N, judged on N in 2022-2025, never on 2026. Score =
worst year + 0.1 x CAGR; eligible only with >= 70% tradeable days (gaps <= 40) and max DD <= 25%
every year. A new best must repeat on a second seed set before it is released. 2026 is read
every hour for the live release and drives nothing.
