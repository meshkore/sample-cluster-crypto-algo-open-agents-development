# Generation five — meta-labelled ITSM

**Written by hand, unlike generation 4.** The loop is stopped, and this folder is
open because the operator chose the hypothesis. `strategy.py` here is therefore
lint-checked and reviewed like any other module — but the folder still obeys the
generation contract: it is a **workshop** until an attempt beats the best sealed
2026 result on record, at which point it freezes exactly as it stands and
`quantlab_system06/` opens.

## The hypothesis

The incumbent (`intraday-itsm-30d`, +5.05% sealed 2026, 24 trades) buys every
1.5% morning move at 06:00 UTC and holds three days. It has no stop, no trail and
no trend filter — every one of its 24 exits was the timer. It has edge and no
discretion.

Generation 5 adds discretion and nothing else: a model predicts which of those
entries resolve upward, and the ones it declines are not taken. This is
meta-labelling (López de Prado, *AFML* ch. 3) — the primary model picks the side,
the secondary picks the size, and here the sizes are one and zero.

**Why a filter and not another signal.** Every previous attempt traded *more*.
Generation 4 went from 24 trades to 65, paid 4.9% of capital in toll, and its
gross return was −0.87%. At a 30 bps round trip an extra trade is a certain cost
against an uncertain gain, so a filter is the only change that can improve the
return and the bill at the same time.

## Measured, 2026-08-13

| | training | sealed 2026 |
|---|---|---|
| **generation 5** | **+149.29%**, DD 22.65%, 287 trades, **completed** | **−1.03%**, DD 7.47%, 7 trades |
| incumbent | +168.19%, DD 25.04%, 388 trades, **ABORTED 2022-04-08** | +5.05%, DD 7.88%, 24 trades |
| buy & hold | — | −35.58% |

Pair `eff92b31de88cadb`. **Not promoted**: −1.03% does not beat +5.05%, so this
folder stays a workshop.

**The claim that survived.** The filter halves the trade count in the overlapping
years (161 against 318 across 2019–2021), holds the drawdown under the mandate,
and the run therefore lives through the whole research era instead of dying in
April 2022. Trades per year: 2019: 28, 2020: 57, 2021: 76, 2022: 30, 2023: 22,
2024: 43, 2025: 31 — including the 45 months the incumbent has never been
measured on at all. That is the first rule in this laboratory to finish the
training era inside the 25% mandate.

**The claim that failed.** On the sealed year the filter's discrimination
inverts. It approved 7 of the incumbent's setups and among them kept the single
worst trade of the year (SOL −10.74%), while declining the July SOL entry that
was the incumbent's best (+10.83%). Predicted before the run from the verdict
table alone — keeps 6 worth −389, drops 18 worth +5,438 — and the run confirmed
it. Per-trade t is −0.26 on 7 trades, so the forward number is not evidence of
anything on its own; what it is not, is an improvement.

**Two caveats on the training half.** It begins in **2019**, not 2018, because
the table's first 2,000 candidates fund fold 0's training block and earlier bars
get no honest verdict — so the span is not like-for-like with the incumbent's.
And the toll was **29.4% of capital** across 287 trades (pre-cost +178.68%).

## What the numbers must clear

| | training | sealed 2026 |
|---|---|---|
| incumbent | +168.19% **aborted at 25.04% DD** | +5.05%, 24 trades, t = +0.74 |
| generation 4 | +495.35%, 20.91% DD | −5.81%, 65 trades |
| buy & hold | — | **−35.58%** |

Two cautions that belong on the card rather than in a commit message. The
incumbent's *training* half breached the 25% mandate, so it is not a legitimately
promotable system by this laboratory's own rule. And its sealed result carries
t = +0.74 over 24 trades — indistinguishable from zero. Beating +5.05% is
therefore necessary and nowhere near sufficient; the training era has to hold up
block by block and stay inside the mandate.

## How it is wired

- **The primary is the champion by composition, not by copy.** `strategy.py`
  instantiates `intraday-momentum` with the recorded genome and vetoes entries,
  so "generation 5 minus the filter" *is* the champion and the run measures one
  variable.
- **Verdicts are precomputed** by `python3 -m quantlab_ml.meta`, using the same
  `quantlab_ml.dataset.build` call that trained the model. A brain recomputing 46
  features live would be a second implementation of that arithmetic, and drift
  would feed the model garbage while every metric read normally.
- **Research verdicts come from the purged walk-forward** — a fold model that
  never saw the bar it judges. Only sealed rows are scored by the model fitted on
  all history before the lock.
- **A missing verdict is a refusal.** Bars before the first walk-forward test
  block have no honest verdict, and letting them trade unfiltered would produce a
  card describing no strategy at all.

## Reproducing

```sh
python3 -m quantlab_ml.meta --out research/agent_runs/meta/itsm-h6.json

python3 orchestrator-manager/scripts/publish_intraday.py --phase training \
    --brain meta-labelled-itsm --brain-module quantlab_system05.strategy \
    --set verdict_table=research/agent_runs/meta/itsm-h6.json
python3 orchestrator-manager/scripts/publish_intraday.py --phase forward \
    --brain meta-labelled-itsm --brain-module quantlab_system05.strategy \
    --set verdict_table=research/agent_runs/meta/itsm-h6.json
```

Both halves must carry identical `--set` flags. `trade_from` is the only thing
either phase may differ on, and the publisher sets it.
