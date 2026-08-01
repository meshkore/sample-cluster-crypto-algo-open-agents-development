---
id: DESIGN2
title: "Make the best-strategy view obvious in the monitor header"
status: done
priority: high
owner: codex-lead
category: design
initiative: public-state-mirror
created: 2026-08-01
updated: 2026-08-01
tags: [ui, navigation, public, champion]
depends_on: [DESIGN1]
blocks: []
---

## Scope

A visitor landing on the live monitor could not tell that a best-strategy view
existed. The header read `Current` / `Best forward`, which names an internal
phase rather than the thing a reader wants: the best result so far.

## Delivered

- The header tabs are now `Active testing strategy` and `★ Best strategy`,
  wider, higher contrast, with the champion tab in its own lime/cyan active
  state so the two views read as distinct destinations.
- The command deck gained a fifth card, `★ best strategy`, showing the current
  champion label, its evidence class and score. The card is a button that opens
  the best-strategy view, giving a second, larger entry point.
- The best-strategy view now opens with a champion banner: label, evidence
  badge, the ranking rule in plain language, ranking score, evaluations beaten,
  publication time and the strategy it replaced.
- The view renders the champion's full evidence — equity chart, scorecard,
  Phase-1 record, latest trades, signal criteria, execution and money
  management, per-asset results and trade ledger.
- When nothing is eligible yet the view states that explicitly instead of
  rendering an empty screen.

## Acceptance criteria

- Both views are reachable and labelled without reading documentation.
- The best-strategy view never renders blank while data exists.
- Evidence class is always visible next to the champion label.
