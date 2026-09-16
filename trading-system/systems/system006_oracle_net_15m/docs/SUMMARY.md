# System 06 — the oracle-taught net

*Opened 2026-08-18. Status: **champion**. Sealed 2026: **+25.71%** at 22.13% drawdown,
90 trades.*

**Read this before opening a new system.** It is the compressed record of what was
measured here, and above all of what was measured and **refused** — twenty-odd ideas that
looked good and were not. That list is the expensive part; the code can be re-read, the
refusals cannot be re-derived without spending the weeks again.

---

## 1. Hypothesis

A perfect-hindsight oracle can mark, after the fact, every clean up-swing in a price
series. A network trained to *imitate those marks causally* — using only bars it could
have seen — learns the **mechanism of a swing** rather than the price of any coin. Pooled
across many cryptos, that mechanism should generalise, because it is the same crowd
behaving the same way on fourteen different tickers.

The claim is not "the net predicts price". It is "the net recognises the shape of a swing
early enough to be paid for it, after costs".

## 2. What it is

A causal TCN (dilated 1-D convolutions, 3×192 channels, ~262k parameters) over a 96-bar
window of 15-minute candles, 44 engineered features per bar, trained on 14 pooled USDT
pairs to clone a zigzag oracle's long-only entries and exits. Its **receptive field is 15
bars** — it structurally cannot see the whole window, and that turned out to be a feature.

Its conviction feeds a decision tree of independent modules — trend filter, stops,
breadth, regime-scaled deployment, meta-labelling veto, learned sizing, Fear & Greed —
each of which can be switched off. Long-only, spot, research-only. **Nine of thirty-three
available levers are set; the rest have never earned their place.**

**Data consumed** (all from the shared catalogue — see `.meshkore/context/data-catalogue.md`):
15m candles for 14 symbols, 2017-08 → 2025-12-31 for research and 2026 sealed; Binance
perp funding; alternative.me Fear & Greed; blockchain.info on-chain series; FRED macro.

## 3. What helped

| change | measured effect | evidence |
|---|---|---|
| **The oracle-clone labelling** | the founding mechanism; 66.8% validation accuracy imitating the oracle | model card |
| **The risk layer as a whole** | the breakthrough. Without it the held-out half collapses to −0.1011 from +0.1572, 2025 goes to −31.2% on 21,008 trades | A119/A120 `risk_layer_off` |
| **60-day trend filter** (`trend_span` 5760) | keeps the book flat in broad bear markets. Removing it costs −0.0491 fit, −0.1395 held-out, +5.6pp drawdown | A119 |
| **Meta-labelling veto** (`meta_margin`) | the drawdown halver. Removing it doubles drawdown 19.1% → 38.1% and takes 2025 to −31.4% | A119 |
| **Regime-scaled deployment + 2-position cap** | the two levers that buy the moonshots. Removing either cuts 2021 from +14,554% to ~+720% but also halves drawdown — a genuine trade-off, not free | A119 |
| **Width-192 channels** | adopted 2026-09-02 as the current champion architecture | ARCH-0005 |
| **Sample-uniqueness weighting** | one label per candle means windows overlap heavily; weighting each swing equally reduces overfitting to long legs | López de Prado ch. 4 |
| **Execution realism** (`min_notional`, `max_participation`) | after the 2021 audit found $45M orders in single 15-minute NEAR candles once the account had compounded to $122M. Not a performance lever — an honesty one | 2021 audit |
| **The 2-of-2 walk-forward rule** | *the single most valuable thing built here.* Stopped four candidates that each won one exam and lost the next, before any of them cost a sealed reading | A106/A112/A113, A110/A110b, A96/A96b |

## 4. What hurt

**Longer than the list above, and that is the honest shape of research.** Every row below
looked good on the evidence available when it was tried.

| idea | what happened | evidence |
|---|---|---|
| **Deep-field net** (receptive field 127) | won *every* research metric, then lost the sealed year: −18.04% vs +25.71%. Memorisation, not skill | A103 |
| **5-seed ensemble** | won exam 1 (+6.46% vs −6.54%), lost exams 2 and 3. 1-of-3 | A106/A112/A113 |
| **Recency-weighted training** | won unseen 2025 (+1.16% vs −6.54%), lost unseen 2024 by 30 points. 1-of-2 | A110/A110b |
| **Reference-market features** (VIX, NASDAQ, DXY, WTI, curve) | won exam 1 and *halved* the drawdown; lost unseen 2024 by nearly 40 points. 1-of-2 | A96/A96b |
| **Joint threshold search, 1,668 TPE trials** | only 1% beat the champion on fitted years, and the best of those gained +0.0160 on fit while losing −0.0154 out of sample | v1–v3 study |
| **The lean champion** (`min_hold` 1 + three dead levers removed) | beat the incumbent on *all six* fitted years, *both* held-out years, with a perfectly ordered response curve — then lost the sealed year by 37 points, −11.65% vs +25.71% | A120 |
| **`min_hold` 32** | replicated on 7 of 8 walk-forward boundaries; sealed 2026 +22.38% vs +25.71%. Closed | A123/A124 |
| **Shorts** | measured and declined: less raw material than longs in every year at tradeable scale, plus squeeze-tail and funding costs the long side does not pay | A63 |
| **Trailing stop, breadth gate, Fear & Greed veto** | measured as carrying nothing — removing them changes the fitted score by ≤0.0023. Still in the live path because the only test that removed them (with `min_hold`) lost the sealed year, so their removal has never been cleanly measured | A119 |
| **The 50% drawdown circuit breaker** | has never fired. Eight years identical with and without it. Kept as insurance, not as a contributor | A120 |
| **Vector memory, deep field, martingale** | retired on pre-registered kill criteria | rnd ledger |

## 5. What is still open

| question | why it stalled |
|---|---|
| **Shorter receptive fields** (7 vs 15 bars) | **running since 2026-09-16.** Reach and capacity had never been separable - dilations defaulted to 1,2,4 per block, so changing the reach meant adding blocks and parameters with it. `train(dilations=...)` now moves the reach alone, with the parameter count pinned at 255,937 for every arm: 7 and 9 bars against the shipping 15, four seeds, judged on 2022/2023/2025 | A111 / P54 |
| **Point-in-time macro** (Fed, CPI, payrolls) | needs ALFRED vintages; FRED alone is revised data and would leak | A87 |
| **Cross-asset corpus** (equities, FX, gold) | crypto is one risk factor sampled 27 times; independence is the scarce input | A95 |
| **Foundation / pretrained models** | contamination risk — a pretrained model may have seen 2026 | A97/A98 |
| **Can our instrument find a winner at all?** | three candidates approved by out-of-sample evidence have all lost the sealed year. See rule 2 below — the diagnosis is *underpowered*, not *broken*, but it is unresolved | open |

## 6. Rules learned — obey these without re-deriving them

1. **A candidate needs 2-of-2 walk-forward exams before a sealed reading.** Four
   candidates won one exam and lost the next. One exam year is a coin flip.
2. **Price the odds before spending a sealed reading.** Compute the candidate's per-year
   ratio against the incumbent across every walk-forward net-year and report
   min/q1/median/q3/max. **If the spread straddles 1.0, one year cannot settle it** — do
   not spend the reading. All three sealed losses here were staked on unpriced edges.
3. **"Held out" in a threshold study means held out from the *thresholds*, not the
   *net*.** The champion net trained through 2025, so 2024–2025 were never out-of-sample
   for it. Score net-sensitive levers on a walk-forward net or the number is fiction.
4. **A joint Bayesian search never measures one-lever neighbours of its own anchor.** Of
   1,607 TPE trials, the closest to "the champion with `min_hold` at 1" differed in 24 of
   the other 31 levers. Single-lever effects are invisible inside a 32-dimensional search;
   ablate separately.
5. **Check an "off" value against the code, never assume it.** `max_drawdown = 0.0` is
   the *tightest* brake, not the absent one — two ablation arms traded zero times and were
   reported as the most load-bearing modules in the system.
6. **Turnover levers fitted on the full record describe a market that no longer exists.**
   Fast rotation paid 2.97x in 2018 and 4.17x in 2021, then 1.12x in 2022 and 0.82x in
   2024. Our record is four-fifths pre-2022.
7. **Run every tool from the repo root with `PYTHONPATH=trading-system`.** Otherwise the
   universe silently degenerates to one symbol and results read ~24x too weak — as a
   refuted idea rather than a broken path. The catalogue now raises instead.
8. **Compare growth multiples, ratios of (1+r), never differences of percentages.** A year
   going +8.7% → +32.8% multiplied the account by 1.22, not by "+24 points".
9. **Trend-following gives up bull upside to avoid bear catastrophes.** The champion's
   worst year in nine is −2.96% against BTC's −72.77%; it also loses straight-line bull
   years. That is the bargain, not a defect — but it means the +30%-every-year mandate is
   not reachable by this book alone.
