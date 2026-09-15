---
id: S9V2-5
title: "Give the model a world and a memory: regional macro, cycle state, player tiers, relative target"
status: active
priority: high
owner: win-opus-5
category: trading-system
initiative: system-nine-reality-alignment
created: 2026-09-15
updated: 2026-09-15
tags: [system09, v2, macro, regions, inflation, cohorts, target, regime]
depends_on: [S9V2-1, S9V2-2]
blocks: [S9V2-4]
---

## Why, in one paragraph

The model forecast a rise on 250 days out of 250. The operator's diagnosis was that the input
vector is wrong, and he is half right: the *target* is wrong first. It is the raw forward
return, whose mean across 2017-2025 is strongly positive, so a model with weak features
minimises its loss by predicting the era's drift. But his second point stands on its own - the
model cannot see the world (inflation differs by continent, regulation by jurisdiction, wealth
by region), it cannot see the trend it is dragging (every row is an independent day), and it
sees each class of participant as one lump when a $100M whale and a $2M whale are different
animals.

## The order, and why this order

| # | Task | Why here |
|---|---|---|
| **T1** | **Relative target.** Predict excess over the universe's own mean, plus a separate market-direction head. | Removes the always-up bias *by construction* rather than by hoping features fix it. Nothing else can be measured cleanly until this is done - every IC above is contaminated by the drift. |
| **T2** | **Cycle state.** Fear & Greed (in the catalogue, never used), distance from the all-time high, drawdown depth AND duration, volatility regime, and 30/90-day deltas of the ledger and macro blocks. | "The trend we are dragging", in the operator's words. Cheap, and it is the missing half of why the model cannot tell a bear from a bull. |
| **T3** | **The world by region.** Inflation for the US, euro area, China, Japan, India, Brazil, UK; policy rates where published; regional currencies; a regulatory-event calendar. | An investor in Shanghai and one in Frankfurt face different rules and different real rates. One global CPI cannot represent that, and the boundary flow into crypto is precisely where it shows. |
| **T4** | **Player tiers.** Split each class into size bands with their own balances, flows and dry powder reported separately. | The operator: *"unos operan con cifras del orden de 100 millones y otros no pasan de 2"*. A class average hides the participant who actually moves. |
| **T5** | **Retrain and measure**, research years + the held-back 2025, with the strict-addition test per block. | So each of T1-T4 is priced individually rather than shipped as a bundle nobody can decompose. |
| **T6** | **One sealed reading** at the milestone, never as a selection input. | The operator wants 2026 to improve. It can only mean something if the improving happens somewhere else. |

## The discipline, stated once

The operator asked not to stop until the 2026 number beats the last one. Taken literally that
is fitting the sealed window, which this laboratory has already paid for four times. So:
iteration happens on the research years and on a held-back year; 2026 is read at milestones
and reported with its sample size; and a configuration is never chosen because 2026 liked it.

## Done when

Each of T1-T4 has a measured effect on the held-back year, and the best configuration by that
measure gets one sealed reading.
