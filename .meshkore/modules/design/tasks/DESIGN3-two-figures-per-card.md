---
id: DESIGN3
title: "Show training and 2026 forward on every card in the rail"
status: done
priority: high
owner: master
category: design
initiative: public-state-mirror
created: 2026-08-11
updated: 2026-08-11
tags: [ui, monitor, forward, training, public]
depends_on: [DESIGN2]
blocks: []
---

## Scope

Every card in the left rail carried exactly one percentage and no statement of
which of the laboratory's two eras it measured. The rail therefore read:

    loop-086-sideways-2026        0.27%   143 trades · 1.49% max DD
    loop-085-sideways-training    8.42%   2265 trades · 8.63% max DD

Both figures are true and only the first is evidence. Nothing on either card
said so, and stacked in a column ordered by time the pair reads as one strategy
getting eight times worse rather than as a fit and its forward test.

## Delivered

- Each card in the rail — champion, live, archive — now shows both halves of its
  hypothesis: `TRAINING` on the left and `2026 FORWARD` on the right, larger,
  because the sealed window is the only number the laboratory is trying to move.
  Order is fixed by era, never by which half the card itself is, so two cards
  can be compared without first reading their labels.
- Trades and max drawdown moved out of the meta line and under the figure that
  earned them. With two returns on a card the old line was unattributable.
- The half the card actually opens is tinted in the accent colour; a hypothesis
  appears twice in a chronological archive, once per run.
- A hypothesis with no twin says why — `no run before 2026 recorded`, or
  `2026 never opened on it`, which is the honest answer for a fit that broke its
  drawdown budget and never earned a forward evaluation.
- The running-iteration card carries the same two figures. This needed the loop
  to publish them: `_beat` recorded only the `backtest` stage, so the forward
  result never reached the heartbeat at all. The loop now emits `trained` after
  the accepted genome's training run and carries trades/drawdown on `forward`,
  and `_beat` keeps both in a `pair` object that is cleared on `begin`.
- Until the search accepts a genome there is no training result, so that figure
  falls back to the last backtest of the search and is labelled as such rather
  than passed off as the iteration's result. 2026 stays empty until the window
  is opened.

## Acceptance criteria

- No percentage in the rail is unlabelled as to its era.
- The 2026 figure is visually dominant on every card that has one.
- A missing half states why it is missing and never renders as 0.00%.
- The running iteration shows the same two figures as an archived card.
