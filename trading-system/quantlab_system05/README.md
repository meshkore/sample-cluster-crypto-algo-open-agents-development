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
