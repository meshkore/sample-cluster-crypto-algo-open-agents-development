# Diario de ideas — system 06

*Generado 2026-09-03 01:37 UTC desde `rnd/agenda.jsonl`, que es la fuente de verdad y sólo crece: una idea se cierra con un resultado medido, nunca se borra.*

**88 ideas** en el registro. 9 queued · 16 running · 21 proposed · 9 win · 1 win-conditional · 1 stage3b-pass · 2 built · 2 measured · 1 stage1-inconclusive · 4 shelved · 22 loss

Cada ficha lleva lo que el operador pidió: qué es, por qué, **cómo** se prueba, **qué la mataría**, y el resultado si ya se midió.

## 🔜 En cola — se probarán a continuación

### A76-train-wide-trade-narrow — Train on MORE markets, keep trading the same fourteen  ⭐
*operator/data · training · critical · creada 2026-09-03*

**Por qué.** Operator, 2026-09-03: if the model needs more, train it on more data - other markets, even equities. The cheap half is already on disk: 27 symbols downloaded, 14 traded, so 13 unused series carry ~2.7M extra bars (+90% training data) at zero download cost.

The distinction that makes this NEW, because four experiments look like it and are not: A37/A40/A66/A68 all widened the TRADED universe and lost badly (median sealed 2026 -21%). None of them widened the TRAINING set while keeping the traded book narrow. Those are opposite claims - one says 'hold worse assets', this says 'learn from more examples of the same phenomenon and keep holding the good ones'. And it is exactly the textbook fix for the condition P35 proved we are in: underfitting.

**Qué esperamos.** If capacity was binding and data is now the next constraint, the walk-forward held-out column improves and the thin years improve most, since they are where the model has seen fewest analogues.

**Cómo se prueba.** Stage 1 (P43, cheap, no download): train on all 27 local symbols, export signals and trade the same 14. One paired train_ab. Stage 2, only if stage 1 pays: pull more crypto symbols. Stage 3, only if stage 2 pays: cross-asset (equity index futures, FX) as PRE-TRAINING with a crypto fine-tune, since microstructure and session structure differ and mixing them raw is more likely to blur the target than sharpen it.

**Qué la mataría.** No improvement in the walk-forward held-out median -> the model is not data-starved and the constraint is elsewhere. A LOSS would also be informative: it would mean the extra symbols carry a different phenomenon rather than more of ours, which argues against the cross-asset stage before it costs anything.

**Experimentos.** `P43-train-wide-trade-narrow` (queued)

### A78-the-book-cannot-express-the-signal — Two slots cannot carry a signal that fires on a fifth of all bars - and sqrt-impact now REWARDS spreading  ⭐
*measurement/portfolio · risk · critical · creada 2026-09-03*

**Por qué.** fit_diagnosis (2026-09-03): conviction >= 0.75 fires on 21.1% of validation bars and is right 77.1% of the time. The book holds at most TWO positions at ~25% of equity each and averages 1.9-6.5% exposure, so it expresses almost none of what its own model is saying. The ceiling measurement agrees from the other side: 0.49% capture in 2026.

And the cost model just changed the arithmetic in this idea's favour. Impact is charged as 60*sqrt(participation), so splitting one order across four names costs sqrt(1/4) = HALF the impact per unit of capital that one concentrated order pays. Concentration was chosen when our own volume was free; it is a different trade now that it is not.

**Qué esperamos.** More slots at smaller size raises exposure and total impact cost sublinearly while raising the number of 77%-precision signals acted on. The thin years should gain most - they are where the book sat in cash while signals existed.

**Cómo se prueba.** P44, paired risk arms on the same trained nets: max_positions 2 vs 3 vs 4 vs 6, and a deployment arm, judged on the score and the thin years with drawdown reported.

**Qué la mataría.** If more slots lowers the score, the signal's precision does not survive being acted on more often - which would mean the 77% is concentrated in the very top convictions and the book is already taking exactly those. That is a real and useful answer: it would send the work to the forecaster (A76 data, P39 capacity) and close portfolio structure.

**Experimentos.** `P44-more-slots` (queued)

### A02-breadth-fine-sweep — Fine-sweep breadth 0.20/0.25/0.30/0.35 for the exact sweet spot
*risk-lever · creada 2026-08-21*

**Por qué.** A/B showed a sweet spot near 0.30 and a cliff above. Sweep the neighbourhood on validation to pin the max-worst-year point.

**Qué esperamos.** a breadth value that maximizes worst-year with <5% CAGR cost

**Qué la mataría.** no value beats champion score

### A08-vol-target-refine — Refine volatility-targeted sizing (span, cap, floor)
*risk-lever · creada 2026-08-21*

**Por qué.** Vol-targeting sizes down in turbulence. Tune it to shave drawdown in 2018/2022 without dulling the bull.

**Qué esperamos.** lower max drawdown in bear years

**Qué la mataría.** CAGR cost exceeds drawdown benefit on validation

### A09-system07-mean-reversion — DISRUPTIVE (L5): system 07 = capitulation dip-buyer, complementary to system 06
*new-system · creada 2026-08-21*

**Por qué.** Four refutations show system 06 is near its ceiling for incremental rolling gains; raising combined reliability needs DIVERSIFICATION, not more surgery. system 06's 17 losing cohorts are bear-entries (2018/2022 bears, 2026 dip). A separate long-only mean-reversion system that buys CAPITULATION dips (the A06 feature) and exits into the bounce would earn EXACTLY in those periods, filling system 06's gaps. Kept fully separate (system 07), never touches system 06; a portfolio-level combine can then be rolling-tested.

**Qué esperamos.** system 07 is positive in the flat/bear years system 06 is weak (2018/2019/2022/2025), so a 50/50 combine raises the rolling 1-yr win rate above 82% without lowering median

**Qué la mataría.** capitulation dip-buying has no positive-carry edge after costs on validation (falling knives dominate)

**Resultado.** active lead; build incrementally: first an offline capitulation-dip backtest (entry=high capit score, exit=fixed horizon or bounce target) on research years to check for real edge BEFORE any system scaffolding

### A10-continuous-paper-research — Keep mining ML-for-trading papers each cycle for methods to A/B
*research · creada 2026-08-21*

**Por qué.** The continuous-research layer researches papers, extracts ideas, A/B-tests them. Feed the best into this agenda as concrete experiments.

**Qué esperamos.** a steady inflow of testable, paper-grounded hypotheses

**Qué la mataría.** n/a (ongoing)

### A14-maximize-rolling-1yr-winrate — NEW TARGET: maximize the rolling one-year-hold win rate (operator's stability criterion)
*risk-lever · creada 2026-08-21*

**Por qué.** Rolling analysis (92 monthly cohorts 2018..2026 incl sealed): champion/bare model wins 75/92 (82%), median +23.3%, worst -16%. The decision modules HURT rolling reliability (V2 69/92, V3/V4 68/92, worst -25%) even though V2 improved the single 2026 calendar year — whipsaws + reduced trading push more cohorts underwater. So the operator's ideal ('whenever you invest, up in a year') is currently best served by the bare champion, and the open problem is to push 82% toward 100% WITHOUT losing return.

**Qué esperamos.** a config/module that raises the 1-yr win rate above 82% while keeping median > +15%

**Qué la mataría.** nothing beats the bare champion's 82% on rolling holds

**Resultado.** baseline to beat: champion 75/92 (82%), median +23.3%, worst -16%

### A18-ensemble-of-champions — NEW: diversify across MODELS (ensemble of past champions), not across strategy types
*model-arch · creada 2026-08-21*

**Por qué.** System 07 failed because a dip-buyer loses in bears. The RIGHT diversification is across system-06 MODELS with different entry timing (trend_span/band): their bear-entry losing cohorts don't perfectly overlap, so a 1/N portfolio of a few diverse champions could raise the rolling win rate WITHOUT clipping any single model's bull (each keeps its full behavior). This is model-diversification, not a new loss-in-bears strategy.

**Qué esperamos.** a 1/N blend of 3-4 diverse configs has a higher worst-year / smoother per-year than the best single config; if so, higher rolling reliability

**Qué la mataría.** the diverse configs' losing years overlap too much (all crypto is one beta) so the blend doesn't smooth

**Resultado.** CHEAP first test: combine 3-4 diverse configs' RECORDED per-year returns from ledger.jsonl (1/N) and check if the blended worst-year beats the best single config — before spending on multi-signal exports.

### A19-cross-sectional-momentum — mom_gate seed was silently dropped — latent whitelist bug fixed; A19 pending next autoloop restart
*risk-lever · creada 2026-08-21*

**Por qué.** Discovered _row_to_kwargs strips any named-dict lever not in KNOWN_LEVERS; mom_gate AND martingale were missing from MODULE_LEVERS, so those grid rows silently ran as plain breadth+regime duplicates (mom_gate/martingale never actually tested). Fixed: added mom_gate, martingale to MODULE_LEVERS (full suite 334 pass). The RUNNING autoloop imported old code, so mom_gate activates only after the next autoloop restart (watchdog relaunches with the fixed, suite-verified code).

**Qué esperamos.** after restart, mom_gate (symbol selection) either helps worst-year/rolling or clips like the exposure cuts

**Qué la mataría.** clips returns / no improvement

**Resultado.** BUG FIXED (module levers now grid-testable via named rows). A19 test deferred to next autoloop restart; not restarting a productive engine for a long-shot.

## ▶ En marcha o a medio medir

### A30-horse-race-leadlag — Horse-race: cross-asset lead-lag cascade (buy the laggards when the pack is firing)
*market-microstructure/network · signal · high · creada 2026-08-25*

**Por qué.** OPERATOR IDEA (2026-08-25). A rally does not lift all coins at once or equally: early movers fire first, then BTC takes a leading role, then the rest of the alts catch up. So the market's global trend is observable in DETAIL as a cascade. If we trade ~50 coins and 25 are already exploding, the laggards have a high probability of making similar moves soon - a competitive, PREDICTIVE cross-asset edge the per-symbol oracle cannot see. Distinct from breadth (which only gates risk on/off): this is a per-symbol ENTRY/UPSIZE signal for laggards conditioned on pack heat + leader (BTC) state.

**Qué esperamos.** catch rotations early; add alpha in trending/rotational regimes incl 2026 where the defensive oracle sits flat

**Cómo se prueba.** Causal CROSS-SECTIONAL channel computed in infer across symbols per timestamp: pack_heat = fraction of the universe with a fresh breakout / strong short-horizon momentum; leader_state = BTC momentum/breakout; per-symbol laggard_gap = pack_heat high AND this symbol's own recent return << pack median. A HorseRace module upsizes / un-vetoes laggards when pack_heat>gate and leader is up. Needs a cross-symbol pass (unlike the per-symbol channels).

**Qué la mataría.** laggards keep lagging (no catch-up) / no edge vs the bare oracle on validation

**Resultado.** Implemented (safe size version): modules/horserace.py upsizes laggards (below-median momentum) when the pack runs (>=50% positive momentum) and BTC leads. horserace lever wired; grid rows horserace 0.5 and meta+horserace 0.5. 5 tests pass, full suite 349. Live in the grid, A/B vs the champion. Standalone-voter version (enter laggards the oracle misses) tracked under A33.

### A31-mm-liquidation-hunt — Market-maker liquidation-hunt / stop-sweep detection (wick-cleaning reversals)
*market-microstructure · signal · high · creada 2026-08-25*

**Por qué.** OPERATOR IDEA (2026-08-25). Operator visually recognises MM stop-hunts: a candle (in 1-2 timeframes) with long wicks up AND down - a two-sided liquidation sweep - after which price often reverses / changes trend. Two uses: (a) ride the post-sweep reversal, (b) ANTICIPATE when an MM is likely to run a sweep (from prior move, volume build-up, and TIME SINCE the last sweep) to avoid bad entries or pre-position. Complements the current system or stands alone.

**Qué esperamos.** better entries via post-liquidation bounces; fewer entries right before a sweep; a contrarian channel at capitulation wicks

**Cómo se prueba.** Causal per-symbol sweep_score from OHLC wick geometry (upper_wick+lower_wick relative to body/range) x volume spike x time-since-last-sweep (a refractory/pressure term). Extends A06 capitulation.py (one-sided) to the TWO-SIDED sweep. A module: post-sweep contrarian entry or a short veto before likely sweeps.

**Qué la mataría.** no measurable reversal edge after costs; sweeps not separable from ordinary volatility

**Resultado.** Implemented (observational half): infer._causal_sweep = causal two-sided wick-sweep score (both wicks x volume z-spike x range expansion, scaled by a refractory 'time since last sweep' term), Channels.sweep accessor, modules/sweep.py presses size on the bar after a sweep (bounded x1.3, never enters/vetoes on its own). Lever wired; grid rows sweep 0.5 and meta+sweep 0.5. 5 tests pass (incl. a discriminator proving a ONE-sided capitulation wick does NOT fire, verified by deliberately breaking min->max) ; full suite 355. Real-data smoke: fires on 0.97% of BTC bars (3063 in 9y) - the right rarity for genuine MM cleanups. ANTICIPATORY half (veto entries when a sweep looks due) deliberately deferred: it would gate on a prediction, not an observation.

### A39-live-edge-monitor — Live edge monitor: cut exposure when the realized edge decays or inverts
*risk/meta · risk · high · creada 2026-08-25*

**Por qué.** If an edge can invert without any observable regime signature, the remaining defence is to watch the realized performance of our own closed trades and stand down when it stops working - a causal, self-referential circuit breaker. That would have limited 2026 to a small loss instead of a year of break-even churn, and it also protects against the next unknown regime.

**Qué esperamos.** exposure scales down within weeks of an edge decaying; the worst year improves without clipping healthy years

**Cómo se prueba.** Track a causal rolling hit-rate / expectancy over the closed trades; scale deploy down as it falls below its historical band. Validate on research years only (fires in 2018/2022, quiet in 2020/2021).

**Qué la mataría.** the monitor fires too late (after the damage) or too often (clips good years) on research data

**Resultado.** Implemented as modules/edgemonitor.py: keeps a rolling record of the realized return of every position the book CLOSES and, once it has enough trades, scales the whole book's deployment down in proportion to how negative that expectancy is (bounded by a floor, released as soon as trades work again). Causal and self-referential - it reads only outcomes that already happened - and it never votes direction or vetoes a name. 7 tests (silent until enough evidence, quiet while winning, cuts and floors while losing, strength scales the cut, recovery releases the book, reset clears between years); full suite 368 pass. Live in the grid at edge_monitor 1.0, alone and with meta. | n=1 EARLY NEGATIVE: vs same-net baseline (score -0.0960, worst -10.5%, cagr +8.6%, 2022 +1%) the breaker scored -0.1079, worst -11.5%, cagr +7.0%, 2022 -7%. Likely mechanism: cutting size after a losing streak sells into the drawdown and stays small through the recovery (whipsaw). Accumulating more nets before a verdict.

### A55-drawdown-constrained-sizing — Size from the distance to the drawdown limit (Grossman-Zhou), instead of a fixed fraction
*mathematics/growth-optimal · module · high · creada 2026-08-28*

**Por qué.** Position size is currently a CONSTANT chosen by the risk grid - the same fraction whether the account is at a high-water mark or close to its limit. The growth-optimal literature under a maximum-drawdown constraint says the principled rule is to invest in proportion to the EXCESS above the moving stop level: large when far from the limit, shrinking to nothing as it is approached. That is strictly better suited to a hard 25% mandate than a constant, because it spends the risk budget where there is budget to spend. It also fits the measured situation exactly: drawdowns of 2.7-10% mean the account is almost always far from the limit and could safely carry far more than it does.

**Qué esperamos.** higher average exposure and therefore higher returns for the SAME worst-case drawdown, because size is withdrawn only when the mandate is actually threatened rather than permanently

**Cómo se prueba.** Depends on P06: if the deployment curve is favourable, this is the principled way to ride it instead of a constant fraction. Implement as a deploy_mult on the existing money-management slot - deploy scales with (equity - stop_level) / equity, where the stop level trails the high-water mark by the mandate. Off by default, paired test on the champion genome, judged on every year with the drawdown rejection fixed in advance.

**Qué la mataría.** the rule raises size precisely when the edge is weakest (after a good run) and the path-dependence makes the worst year worse, or the extra exposure simply cannot be filled because the meta filter refuses the candidates

**Resultado.** BUILT 2026-08-28 as the lever `dd_sizer`. Grossman-Zhou in this book's own terms: floor = peak * (1 - mandate), headroom = (equity - floor) / (peak - floor) = 1 - dd/mandate, and deploy_mult = headroom ** dd_sizer. So size is withdrawn SMOOTHLY as the limit nears and RESTORED as the account recovers, which an abort never does within the year. Off by default, 7 tests, suite 436, golden ensemble tests still pass so zero is byte-identical. TWO HONEST LIMITS traced from the arithmetic rather than assumed: the orchestrator computes deployed = min(1.0, max(0.05, base * deploy_mult)), so a 5% floor is applied AFTER this module - it can taper the book but cannot flatten it, and the abort remains the only full stop, making this a complement rather than a replacement; and the power above 1 cuts early while below 1 holds late, which is empirical rather than theoretical, so it is swept. Queued as P12 to test whether the taper lets a HIGH ceiling survive - P09 showed ceiling 0.90 loses only because the abort forfeits 2021.

**Experimentos.** `P12-taper-instead-of-cliff` (done)

### A01-breadth-gate-030 — Light breadth risk-off (~0.30) to lift the worst year
*risk-lever · creada 2026-08-21*

**Por qué.** The champion loses only 2022 (-5.3%); a light market-breadth risk-off flattens the book in a broad bear. 14-symbol A/B (2026-08-21): breadth_gate 0.30 improved the consistency score -0.0386 -> -0.0184, worst -7.9% -> -5.5%, 2021 bull intact (+289% -> +278%), CAGR barely moved (+40.7% -> +37.1%). Heavier gates (0.40/0.50) and persist HURT (clip the bull).

**Qué esperamos.** worst-year up, score up, allpos closer, 2021 preserved

**Qué la mataría.** score drops below champion or 2021 falls > 20%

### A03-variants-showcase — Four labelled backtests: model-only / +modules / +money / +martingale
*visibility · creada 2026-08-21*

**Por qué.** Operator asked to SEE the decision-stack range as distinct, clickable backtests, each with its capability chips, so the modular system's breadth is legible at a glance.

**Qué esperamos.** 4 variants.json records, each honest per-year + sealed 2026, rendered as a rail group

**Qué la mataría.** n/a (visibility)

### A04-martingale-module — Bounded occasional martingale module (press shallow dips, stand down on deep drawdown)
*module · creada 2026-08-21*

**Por qué.** Operator asked to test 'alguna especie de martingala, ocasional y opcional'. Implemented modules/martingale.py: presses deploy into a shallow dip, snaps to 1.0 past floor_dd, capped, off by default. 4 unit tests pass; golden fixture unchanged.

**Qué esperamos.** in V4 backtest, martingale improves recovery from shallow dips without deepening drawdowns

**Qué la mataría.** raises max drawdown or worsens worst-year

### A05-meta-money-sweep — Meta-label + Kelly + anti-martingale combined configs
*risk-lever · creada 2026-08-21*

**Por qué.** Meta is a drawdown-reducer (honest A/B), value is in combination with low-exposure + regime. The grid already explores meta/money twins of the survivors.

**Qué esperamos.** a meta/money config that reduces drawdown without killing CAGR

**Qué la mataría.** no meta/money config beats champion on validation

### A06-microstructure-ohlcv-proxy — OHLCV capitulation signal — narrow bear-bottom detector (step 1: feature built+tested)
*features · creada 2026-08-21*

**Por qué.** Only a NARROW signal (acting at bear bottoms, not a global cut) can raise rolling reliability given the 3 refutations. Built quantlab_system06/capitulation.py: causal, pure-numpy+pandas, score in [0,1) high ONLY when volume-spike z-score + recent drop + lower-wick rejection coincide. 4 unit tests pass (fires on a capitulation candle, ~0 on calm and on uptrend volume spikes, strictly causal). NOT wired live yet.

**Qué esperamos.** used as a small contrarian entry boost at capitulation bottoms, it helps bear-entry cohorts recover WITHOUT touching bull cohorts

**Qué la mataría.** offline test shows it doesn't lift bear-entry cohort returns, or it also clips/whipsaws the bull

**Resultado.** step 1 complete (feature + tests). Step 2: compute the channel + offline rolling test on bear-entry cohorts before any live wiring.

### A09-system07-mean-reversion — system 07 = capitulation dip-buyer — EDGE CONFIRMED (step 1 pass)
*new-system · creada 2026-08-21*

**Por qué.** Edge study (research 2018-2025, net 0.003, BTC+ETH+SOL): buying capitulation (score>0.4) and holding ~96-384 bars returns mean +3% to +5% at 63-66% win, vs the unconditional forward-return baseline of +0.16% (52% win). Consistent across all 3 majors and horizons >=96 bars; weak at H=48 (too short). Real positive-carry mean-reversion edge, strongest exactly in the drop/bear regimes where system 06's cohorts lose.

**Qué esperamos.** a standalone long-only system 07 (entry capit>0.4, exit ~horizon 96-192 or bounce target) is profitable and UNCORRELATED with system 06; a 06+07 combine raises the rolling 1-yr win rate above 82% without a median hit

**Qué la mataría.** the event-study edge does not survive as a real position-managed strategy (overlap, sizing, drawdown) or is correlated with system 06

**Resultado.** STEP 1 PASS (edge confirmed). Step 2: build system 07 as a separate long-only module (capitulation entry + horizon exit), unit-tested, never touching system 06 files; then a proper per-year + rolling backtest.

### A09-system07-mean-reversion — system 07 capitulation dip-buyer — step 2 built (strategy + backtester + tests)
*new-system · creada 2026-08-21*

**Por qué.** Wrote quantlab_system07/ (new package, system 06 untouched): CapitulationDip strategy — long-only portfolio backtester, entry when capitulation score>0.4, exit on target/stop/horizon, equal-fraction sizing capped at max_positions, 0.003 costs, 25% mandate. Reuses system 06's tested capitulation feature (import only). 4 unit tests pass (no trades on calm, enters+takes profit on a bounce, horizon exit when flat, long-only bounded); +4 capitulation tests. Additive files -> existing 326-suite unaffected.

**Qué esperamos.** the event-study edge (+3-5%/trade, 65% win) survives as a position-managed strategy on research years, uncorrelated with system 06

**Qué la mataría.** real backtest shows the edge evaporates under position management/costs, or it's correlated with system 06

**Resultado.** step 2 DONE (strategy+backtester+tests). Step 3: run it on research years (2018-2025) per-year + rolling; then a 06+07 combine rolling test vs the champion.

### A15-longer-trend-fewer-bear-entries — Longer slow-trend filter (90d/120d) to cut bear-entry cohort losses
*model-arch · creada 2026-08-21*

**Por qué.** Rolling diagnosis (arithmetic): ALL 17 of the champion's losing 1-yr cohorts are bear-entry cohorts (2018-01..04, 2021-11..2022-10, 2025-08), losses shallow (-2%..-8%). Adding breadth (var-2) makes it WORSE (23 losers, 2018 deepens to -25%/-19%) via whipsaws. The non-whippy lever is a SLOWER entry/trend filter. search.json had been narrowed to trend_span [2880,5760] (30/60d); restored [8640,11520] (90/120d) so the autoloop trains slower-trend models.

**Qué esperamos.** models with trend_span 8640/11520 enter fewer bear-top cohorts -> higher rolling 1-yr win rate than 82%

**Qué la mataría.** longer-trend models only clip the bull (lower CAGR) and score worse on validation without improving rolling

**Resultado.** seeded into search.json; judge over coming autoloop iterations

### A16-vol-target-bear-derisk — Volatility-targeted sizing to de-risk bear-entry cohorts WITHOUT whipsaw
*risk-lever · creada 2026-08-21*

**Por qué.** Bear-entry cohorts are the champion's only rolling losers; breadth risk-off (binary) whipsaws and makes 2018 worse. Vol-targeting sizes DOWN continuously as realized vol rises (bears are high-vol) with no binary in/out flip — a non-whippy way to cut bear exposure. Swapped the dominated regime_persist=1440 grid row for vol_scale=1.5/vol_floor=0.4 (no net grid growth).

**Qué esperamos.** vol-targeted configs cut bear-entry cohort losses / drawdown without the 2018 whipsaw breadth caused

**Qué la mataría.** vol-targeting only lowers CAGR (dulls the bull) without improving worst-year or rolling

**Resultado.** seeded; judge on the next few autoloop sweeps

### A19-cross-sectional-momentum — NEW: cross-sectional relative-strength (mom_gate) — SELECT strongest symbols, not cut exposure
*risk-lever · creada 2026-08-21*

**Por qué.** Genuinely different from the refuted exposure-cut levers: mom_gate holds only above-threshold cross-sectional momentum names (rotate into relative strength) rather than reducing total exposure. Could avoid the weakest names during drops (helping bear-entry cohorts) without clipping the bull. Seeded one mom_gate=0.5 grid row (swapped the proven-weak money_pyramid row) for the autoloop to score on consistency.

**Qué esperamos.** holding relative-strength leaders improves worst-year or rolling vs the champion without a CAGR hit

**Qué la mataría.** mom_gate just reduces positions like an exposure cut and clips returns / no improvement

**Resultado.** seeded; judge over next autoloop sweeps

### A20-hurst-fractal-regime — Fractal-regime exposure via the generalized Hurst exponent (H)
*physics/fractals · module · creada 2026-08-24*

**Por qué.** Markets alternate between persistent/trending (H>0.5) and anti-persistent/choppy (H<0.5) phases (Mandelbrot; Di Matteo generalized Hurst). Trend-following whipsaws exactly when H<0.5 - the bear-chop of 2018/2022 that breaks the consistency law. A causal rolling GHE channel + a Fractal module that scales deployment by H attacks the open problem WITHOUT a blanket exposure cut (A16/A15 proved a blanket cut hurts rolling reliability).

**Qué esperamos.** higher WORST year (bear survival) with bull participation intact; better rolling 1yr win-rate

**Qué la mataría.** no lever setting beats the iter-42 bar on the consistency score AND rolling reliability

**Resultado.** n=4: hurst 0.45 helps 3/4 nets, sometimes dramatically - on the first EVOLVED net it was SELECTED and cut the worst year -19.5%->-8.8% (score -0.1817->-0.0727). Reliably raises the worst year (the consistency lever). Not yet champion-beating because the fresh evolved nets aren't as strong as iter-42; expected to become a promotion candidate as evolutionary search climbs. Grid: hurst_gate 0.45.

### A26-evolutionary-search — Genetic-algorithm search over the config space (mutate+crossover champions)
*nature/evolution · search · creada 2026-08-24*

**Por qué.** The loop random-samples search.json. Natural selection is a better optimizer of a rugged fitness surface: seed a population from past champions, mutate/crossover the genome (window/threshold/trend_span/risk levers), select on the consistency score. Makes the WHOLE loop smarter, not one strategy.

**Qué esperamos.** faster discovery of higher-consistency champions than random search

**Qué la mataría.** GA finds nothing random search would not have found within the same budget

**Resultado.** implemented (_evolve/_top_configs in autoloop; 35% explore / 65% exploit-mutate-crossover from elite ledger genomes; cold-start falls back to random). 3 tests pass, full suite 344. Live: first bred config is an elite-region genome. Directly attacks the weak-fresh-net bottleneck.

## 💡 Propuestas — esperando su turno

### A73-response-curves — Per-indicator response curves: find each indicator's optimal value mathematically, then feed the tree a score or a binary barrier  ⭐
*operator/mathematics · diagnostic+module · critical · creada 2026-09-02*

**Por qué.** Operator, 2026-09-02, with a worked example: if longs above the 200-period mean win 85% and below it 60%, sweeping the period 1..300 might reveal the true optimum at 162 - the maximum of a smooth response curve, found by calculus rather than by trying three values. Generalised: for every indicator in the A32 set, estimate the smoothed curve hit_rate(x) over the indicator's value using the attribution ledger's decision rows, locate its extrema, and expose the result to the decision tree as either an additional score or a binary barrier. The ledger built today is exactly the dataset this needs: every row already carries the indicator snapshot at the decision bar and the outcome. The mathematical names: univariate partial-dependence / marginal response estimation, with the optimum at the zero of the smoothed curve's derivative.

**Qué esperamos.** Curves with a real interior optimum and enough support become levers; monotone curves justify simple thresholds; flat curves retire an indicator honestly.

**Cómo se prueba.** Stage 1 (CPU, cheap): extend attribution.py with response_curve(feature, rows) - kernel-smoothed hit rate over each A32 feature from the ledger's won/lost rows, bootstrap bands, report extrema with support. Stage 2: the surviving optima become a 'responsegate' module (score or veto) and one paired A/B decides adoption. Runs AFTER the width-192 champion attempt - one heavy job at a time.

**Qué la mataría.** The trap is named in advance: sweeping many indicators over many values is a MULTIPLE-COMPARISONS engine, and the optimum of a noisy curve is selection bias in a lab coat (the P35 lesson: even four seeds disagree). So (1) curves are fitted on research years only, (2) an optimum must hold on walk-forward held-out years before it becomes a lever, (3) support floors like explain()'s min_leaf apply per bucket, and (4) anything adopted goes through the ordinary paired A/B with reseeds. If no curve survives walk-forward, the idea is measured and closed, not stretched.

### A75-participation-is-the-gap — Attack PARTICIPATION, not the forecast: the ceiling says we take 0.03-5.9% of what our own constraints allow  ⭐
*measurement/participation · training+risk · critical · creada 2026-09-02*

**Por qué.** tools/ceiling.py, 2026-09-02: with perfect foresight and every one of our own constraints and costs, 2026 pays +5,271% and 2022 pays +25,423%. We take 0.49% and 0.03%. Every gate in front of the entry - enter 0.75, breadth_gate 0.3, regime_deploy 0.5, fng_min 25, meta_margin, min_hold 16 - was last measured on the 64-CHANNEL net, and P35 proved that net was underfitting. A gate calibrated to protect a weak forecaster is exactly what should be re-opened once the forecaster gets stronger.

**Qué esperamos.** If the 192-channel net is genuinely better, its convictions are better ordered, and the optimal entry bar moves DOWN. 2022 needs capture 0.03% -> 0.10% for a +30% year.

**Cómo se prueba.** P42, paired train_ab on the shipping genome: entry bar 0.75 vs 0.70 vs 0.65, then the gates one at a time. Judge on the walk-forward held-out column.

**Qué la mataría.** P13 measured that loosening the filters loses - on the old net. If it still loses at 192 channels, participation is closed as a direction and the gap is genuinely the forecast, which sends the work to A73/A74 instead.

**Experimentos.** `P42-entry-bar-at-full-capacity` (running)

### A33-multi-discipline-committee — Multi-discipline model committee: train several disciplines, then combine for decisions
*ensemble/meta · architecture · high · creada 2026-08-25*

**Por qué.** OPERATOR IDEA (2026-08-25). Instead of one oracle-NN, train SEVERAL models of DIFFERENT DISCIPLINES (trend-anticipation oracle, mean-reversion, cross-asset cascade/horse-race, microstructure/liquidation), each a directional voter, then COMBINE them (weighted vote / stacking / consensus). Diversity of METHOD (not just random seed) is the strongest robustness lever and covers regimes any single model misses - the direct route to profit in ALL years incl 2026. Humans cannot juggle this many models live; the loop can.

**Qué esperamos.** regime coverage + robustness that a single discipline cannot reach; steadier all-year profit incl 2026

**Cómo se prueba.** Formalise the module contract as directional VOTERS (oracle + tree + horse-race + microstructure), each exporting a prob channel; the orchestrator combines via weighted vote / consensus / stacking. Builds on the existing modular ensemble + A32 + A30 + A31.

**Qué la mataría.** the disciplines' errors correlate (no diversification) / combination adds no OOS value

### A51-cvar-native-objective — Optimise the tail natively (CVaR) instead of reaching it through a risk grid
*statistics/tail-risk · selection · high · creada 2026-08-27*

**Por qué.** The selection law is worst calendar year plus a tenth of CAGR - a tail measure. But we reach it indirectly: train on a regime-blind objective, then grid a risk layer and keep whichever row happens to have the best worst year. That is a search over configurations standing in for an objective, which is exactly the structure that produced eight hundredths of selection inflation per step. The literature optimises conditional value-at-risk directly.

**Qué esperamos.** a configuration whose worst year is good BY CONSTRUCTION rather than by having been selected for it, which should also reproduce better across seeds

**Cómo se prueba.** Start where it is cheap: replace the risk grid's argmax with a CVaR-aware choice over the same rows, then measure whether the reproducible level improves. Only build a differentiable objective if the cheap version shows promise. 2026 stays sealed.

**Qué la mataría.** CVaR-optimal allocations collapse to near-zero exposure - the same flat-book trap by another route - or the objective cannot be expressed without a differentiable portfolio simulator

### A52-three-state-regime — Three regimes (quiet, volatile, distressed) instead of a binary uptrend gate
*econophysics/regime · module · high · creada 2026-08-27*

**Por qué.** The gate is binary - in an uptrend or flat - and that binary IS the ceiling: the flat state earns nothing by construction. The regime-switching literature on crypto uses three states (low volatility, high volatility, distress) and sets a different invested share in each. A middle state would let the book stay small but active in quiet years rather than empty, which is the only way the worst year rises.

**Qué esperamos.** the quiet-but-not-falling periods of 2022 and 2025 become tradeable at reduced size, turning near-zero years into small positive ones

**Cómo se prueba.** Classify each bar from the causal vol and trend channels already exported. Wire as a deploy fraction per state rather than a veto. Queued as P03; note P01 (a simple exposure FLOOR) is the cheap first probe of the same hypothesis and runs first.

**Qué la mataría.** the third state is never occupied, or trading it loses money - in which case the binary gate was right and the flat years are genuinely untradeable long-only

**Experimentos.** `P03-three-state-regime` (blocked)

### A68-train-narrow-trade-wide — The untested mirror: keep the well-calibrated NARROW net, let it shop in a wider market
*generation/breadth · analysis · high · creada 2026-08-29*

**Por qué.** A66's first two cutoffs are brutal (2019 -42.5% vs -0.8% narrow; 2020 -25.2% vs -4.7%), and the mechanism is visible: a net TRAINED on 24 symbols produces conviction that is not comparable across them, so the top-2 pick is worse even though the pool is bigger. A40 already refuted train-wide/trade-narrow. The remaining cell is the operator's actual idea in its cleanest form: the net stays trained on the 14 it calibrates well, and only the SHOPPING LIST widens - inference is per-symbol, so a narrow-trained net can score names it never trained on. If its conviction transfers, breadth costs nothing and buys selectivity; if it does not, breadth is dead in all three directions and we stop paying for it.

**Qué esperamos.** held-out years improve or at least hold, with more trades in the starved years

**Cómo se prueba.** Reuse P19's seven walk-forward nets - NO training. Run infer.export over the 24 deep symbols per net, then evaluate each held-out year at enter 0.75/0.85. Cheap: inference only.

**Qué la mataría.** transferred conviction is miscalibrated too (wide trades lose like A66) - then the breadth thesis is closed for good

### A35-architecture-bakeoff — Architecture bake-off: causal TCN vs attention/PatchTST-style heads (extends A07)
*deep-learning/architecture · model · medium · creada 2026-08-25*

**Por qué.** OPERATOR QUESTION (2026-08-25): is our ML the most advanced we can use? Honest answer: no - the oracle-clone is a deliberately SMALL causal TCN (44 features, 3x64 channels, ~100k params) on 15m OHLCV of 14 coins. Modern time-series architectures (patch-based transformers / iTransformer-style attention) may capture longer swing structure. BUT in low-signal financial data, capacity is rarely the binding constraint - regularization, labels and data breadth are. So test as a controlled A/B inside the loop (same labels, same selection), not as a rewrite.

**Qué esperamos.** either a real val/worst-year gain from attention, or evidence our bottleneck is data/labels (equally valuable)

**Cómo se prueba.** Add a model_arch gene to search.json ('tcn'|'attn'); small causal attention head in train.py behind the flag; evolution then explores it natively.

**Qué la mataría.** attention head no better than TCN at equal parameter budget, or overfits (val<<train)

### A36-ts-foundation-model — Time-series foundation model channel (Chronos/TimesFM-style zero-shot forecasts)
*deep-learning/foundation-models · model · medium · creada 2026-08-25*

**Por qué.** Pretrained TS foundation models (Amazon Chronos, Google TimesFM, Moment) bring knowledge from billions of series - genuinely more advanced than anything trainable on a single 4060. Cheapest honest integration: run one LOCALLY as a frozen forecaster over our bars and export its forecast/uncertainty as ONE causal channel; a module (or the tree voter A32) then A/Bs whether pretrained knowledge adds edge over our from-scratch nets.

**Qué esperamos.** a pretrained-knowledge channel that helps flat/choppy regimes where our trend-oracle sits flat

**Cómo se prueba.** pip-install chronos (small variant, CPU/GPU), batch-forecast per symbol over research era into an .npz overlay channel (strictly causal windows), wire like meta/micro overlays. NO network calls at backtest time; download weights once.

**Qué la mataría.** forecast channel adds no edge on validation; or local inference too slow for 14 symbols x 15m

### A53-regime-conditional-labels — Regime-conditional labels: teach the net that a good trade in 2022 is not a good trade in 2021
*ML/objective · training · medium · creada 2026-08-27*

**Por qué.** The oracle labels are regime-blind - a swing is a swing whether the market is trending or ranging - so the net learns one notion of a good trade and applies it everywhere. Recent reinforcement-learning work rewards different behaviour per market condition rather than optimising one objective throughout. Our own evidence says the edge is regime-dependent: two independent disciplines both inverted in the sealed window.

**Qué esperamos.** a net that behaves differently in quiet markets rather than simply finding fewer of the same setups, which is what the trend filter currently forces

**Cómo se prueba.** Label swings separately by regime state and either train one net with the regime as an input feature or two nets combined by the orchestrator. Cheaper first step: add the regime state as an input FEATURE and see whether the net uses it at all.

**Qué la mataría.** conditioning splits the training data too thin and both regimes get worse - the usual price of specialisation

### A06-microstructure-ohlcv-proxy — Liquidation / market-maker-move proxy from OHLCV (no derivatives feed)
*features · creada 2026-08-21*

**Por qué.** The microstructure module is off because there is no funding/OI/liquidation feed locally. Build a PROXY from data we DO have: volume spikes + long-wick rejections mark liquidation cascades. Operator's 'detect market-maker moves / liquidations' idea, made feasible.

**Qué esperamos.** a causal contrarian channel that adds edge at capitulation lows

**Qué la mataría.** no measurable edge vs the bare model on validation

### A07-model-arch-attention — Attention/temporal-transformer head vs the causal TCN
*model-arch · creada 2026-08-21*

**Por qué.** The oracle-clone is a TCN. A small causal self-attention head may capture longer-range swing structure. Train as an autoloop arch variant, judge on validation, 2026 sealed.

**Qué esperamos.** higher validation worst-year or CAGR from better swing anticipation

**Qué la mataría.** no gain over TCN at equal params, or overfits (val<<train)

### A09-system07-mean-reversion — DISRUPTIVE: a second system for sideways regimes (range / mean-reversion)
*new-system · creada 2026-08-21*

**Por qué.** System 06 is trend-anticipation; it earns little in ranging years (2019/2025 modest). A complementary long-only mean-reversion system for sideways regimes could raise the worst year via diversification. Kept separate (system 07), never breaks system 06.

**Qué esperamos.** positive returns in the years system 06 is flat, raising the floor

**Qué la mataría.** no positive-carry range edge after costs on validation

### A11-consistency-vs-rolling-DECISION — OPERATOR DECISION now CONCRETE: consistency vs rolling reliability conflict
*research · creada 2026-08-21*

**Por qué.** The new champion makes the A11 trade-off real and measurable. NEW champion: consistency +0.034 (ALL positive years, sealed 2026 +3.3%) but rolling 65/92 (71%), median +8.1%. OLD champion: consistency -0.0127 (lost 2022, sealed 2026 -9.7%) but rolling 75/92 (82%), median +23.3%. The autoloop selects on CONSISTENCY, so it promoted the calendar-year-smooth config at the cost of rolling reliability AND median return. Neither is strictly better — it depends which the operator values: 'profitable every calendar year incl forward' (new) vs 'up a year later whenever you invest, higher median' (old).

**Qué esperamos.** operator picks the selection criterion (or a blend); the loop does NOT change methodology unilaterally

**Qué la mataría.** n/a

**Resultado.** AWAITING OPERATOR. Both champions' full profiles recorded. Do not revert the autoloop's honest consistency-based promotion; do not add rolling to selection without operator sign-off.

### A11-consistency-vs-rolling-DECISION — OPERATOR DECISION — INVERSE TREND now confirmed across 3 champions (consistency UP -> rolling DOWN)
*research · creada 2026-08-23*

**Por qué.** Three champions, measured both ways: retired (worst -5%, score -0.013) rolling 82%/median +23.3%; iter5 (worst +0.5%, +0.034) rolling 71%/+8.1%; iter42 (worst +5.2%, +0.086) rolling 66%/+10.5%. As the autoloop raises the calendar-year consistency floor, the ROLLING one-year win rate FALLS monotonically (82->71->66%). The selection criterion (consistency) and the operator's stability criterion (rolling) genuinely pull apart: calendar-year smoothness (short hold + breadth gate) reduces arbitrary-entry reliability.

**Qué esperamos.** operator picks the criterion (or a blend). If rolling reliability is the true goal, the RETIRED champion (82%) was better and selection should weight rolling; if 'positive every calendar year incl forward' is the goal, iter42 is best.

**Qué la mataría.** n/a

**Resultado.** AWAITING OPERATOR. Do NOT change the selection criterion unilaterally. The autoloop keeps optimizing consistency (its mandate); each new consistency champion tends to LOWER rolling. This is the key decision for rjj.

### A21-permutation-entropy-gate — Permutation-entropy predictability gate (Bandt-Pompe)
*information-theory/complexity · feature · creada 2026-08-24*

**Por qué.** Permutation entropy of recent returns measures how ORDERED vs random the local dynamics are. When PE is high the tape is noise and any signal is a coin-flip; when low it is legible. Gate/abstain entries in high-PE regimes; upsize in low-PE. Complements Hurst (temporal self-similarity) with an ordinal-complexity view.

**Qué esperamos.** fewer losing trades in noise regimes; steadier per-year returns

**Qué la mataría.** PE gate adds no edge over the bare model on validation

### A22-lppl-bubble-earlywarn — LPPL log-periodic bubble/crash early-warning (Sornette)
*econophysics · risk · creada 2026-08-24*

**Por qué.** Pre-crash markets show faster-than-exponential (super-exponential) growth decorated with accelerating log-periodic oscillations. A causal rolling LPPL-fit confidence de-risks BEFORE tops (e.g. 2021). Directly targets the rolling cohorts that buy near a top and are underwater a year later.

**Qué esperamos.** rescue near-top monthly cohorts; lift rolling 1yr win-rate

**Qué la mataría.** causal fit too unstable / false-positives cost more bull upside than they save

### A23-fractional-diff-features — Fractional differentiation of price as an NN feature (memory-preserving stationarity)
*mathematics/fractional-calculus · training · creada 2026-08-24*

**Por qué.** Returns are stationary but memory-less; raw price is non-stationary. Fractional differencing (Lopez de Prado ch.5) finds the minimum d that makes the series stationary while KEEPING long memory - feeding the net level-aware, still-stationary information it currently discards. Cited as frac-diff but never wired as a training feature.

**Qué esperamos.** higher signal quality / accuracy; better generalization to sealed 2026

**Qué la mataría.** no val accuracy or consistency gain vs return-only inputs

### A24-tda-persistence-earlywarn — Topological early-warning via persistence landscapes (Gidea-Katz 2018)
*mathematics/topology · risk · creada 2026-08-24*

**Por qué.** The Lp norm of the persistence landscape of a sliding return point-cloud spikes BEFORE the 2000/2008 crashes. A cheap 1-D sublevel-set persistence over a trailing window gives a causal topological-stress scalar to de-risk on - no heavy deps needed.

**Qué esperamos.** crash pre-warning that raises the worst year and near-top rolling cohorts

**Qué la mataría.** topological stress no better than the vol-ratio channel we already have

### A25-kalman-adaptive-trend — Kalman adaptive local-level+slope trend filter (replace the fixed SMA gate)
*mathematics/state-space · module · creada 2026-08-24*

**Por qué.** The trend gate is a fixed 30/60-day SMA - one timescale for all regimes. A local-level+slope Kalman filter estimates trend and its slope adaptively and causally, reacting fast in trends and staying calm in noise. Fewer whipsaws at the exact bear/bull transitions that decide the worst year.

**Qué esperamos.** cleaner trend gate; higher worst year without clipping bull entries

**Qué la mataría.** Kalman trend gate no better than the tuned SMA trend_span

### A27-immune-novelty-derisk — Artificial-immune novelty detector (negative selection) for regime shocks
*nature/immunology · risk · creada 2026-08-24*

**Por qué.** Learn the distribution of normal (self) market feature vectors on the training era; when the live bar is non-self (anomalous) beyond a margin, de-risk. A bio-inspired, model-agnostic regime-change alarm distinct from breadth/vol.

**Qué esperamos.** early de-risk on structural shocks (2018 unwind, 2020 COVID, 2022)

**Qué la mataría.** novelty flags fire too late/too often to beat vol-ratio

### A29-disposition-breakout — Disposition-effect / anchoring breakout overlay (prospect theory)
*psychology/prospect-theory · feature · creada 2026-08-24*

**Por qué.** Loss-averse holders sell winners early and hold losers (disposition effect), and anchor to prior highs - creating predictable under-reaction and clean momentum once price clears a long-standing high. A causal distance-to-trailing-max + fresh-breakout feature exploits the anchoring release.

**Qué esperamos.** cleaner momentum entries; complements xsec-momentum (A19)

**Qué la mataría.** no edge beyond the existing momentum channel

## ✅ Ganadoras — medidas y adoptadas

### A41-robust-selection — Robust selection: stop enshrining lucky draws, and reset the promotion bar to a reproducible estimate  ⭐
*statistics/selection · meta · critical · creada 2026-08-26*

**Por qué.** Across 136 iterations the score distribution has mean -0.069 and stdev 0.052, and the champion's +0.0864 is the maximum - about what the expected maximum of 136 draws would be by luck alone. The promotion margin (0.02) is well below that noise, so the loop cannot tell a better strategy from a luckier one, and it has not promoted in 94 iterations. This is the most likely explanation both for the sealed-window collapse and for the operator's complaint that nothing improves.

**Qué esperamos.** the champion genome re-run under different seeds scores far below +0.0864, near the population mean; the bar is then reset to a reproducible estimate and the loop can make real progress again

**Cómo se prueba.** Step 1 (running): retrain the champion genome under seeds 43 and 44, score each with the champion's own risk config, compare against +0.0864 and against the population mean. Step 2: if it was luck, make promotion seed-robust - verify a candidate by re-running its genome under 2 extra seeds and promote on the MEDIAN, and set PROMOTE_MARGIN from the measured selection noise. 2026 stays sealed throughout.

**Qué la mataría.** the reseeds cluster near +0.0864, which would mean the genome is genuinely superior and the bar is fair

**Resultado.** CONFIRMED and SHIPPED. Champion genome reseeds: seed 43 -0.1054, seed 44 -0.1171, versus the champion's +0.0864 - median -0.1054, both reseeds ~0.20 below and beneath the population mean. Shipped: _promotion_survives (median rule), _score_genome (seed replay), VERIFY_SEEDS=2 wired into the promotion gate with verify_scores stored in the ledger; PROMOTE_MARGIN 0.02 -> 0.05 (~1 sigma of measured noise); incumbent bar reset +0.0864 -> -0.1054 with the original archived at champion_iter42_lucky_draw.json. 10 promotion tests (one encoding the real champion case, verified to fail against the old best-draw rule); full suite 380 pass. Loop restarted (pid 10912) - the search is unblocked for the first time in 94 iterations.

### A45-learned-money-management — A learned money-management model: map every past trade opportunity and train a model to size, stop and take profit  ⭐
*ML/decision-theory · module · critical · creada 2026-08-26*

**Por qué.** Operator idea (2026-08-26). Today money management is rules: fixed position count, breadth gates, stops, size multipliers from modules. The operator proposes a MODEL trained on the mapped universe of past operations (training period only, up to 2026-01-01 - the seal holds) that decides position size, stop distance, take-profit levels and PARTIAL exits. The directional signal stays with OracleNN; this model manages the capital around it. This is also where the profit-maximisation mandate bites hardest: the champion's edge exists (85% of monthly cohorts profitable) but is thin (+4.2% sealed) - better capital allocation on the SAME signals is the cheapest multiplier.

**Qué esperamos.** same entry signals, materially higher profit per year at equal or lower drawdown, because size concentrates on the trades that historically resembled winners

**Cómo se prueba.** Stage 1: build the trade-opportunity map - for every bar the champion COULD have entered in research years, record features (prob, trend, vol, mom, hurst, sweep, breadth, time-in-trend) and the counterfactual outcome distribution (MFE/MAE curves, best TP, whether a stop at X would have hit). Stage 2: train a small model (gradient trees first, purged walk-forward, embargo) to predict expected R-multiple and its variance; map that to size_mult / stop / TP / partial-exit fractions. Stage 3: wire as a module in the orchestrator (money-mgmt slot already exists, off by default) and A/B on research years; sealed 2026 read once at the end. Kelly-fraction capping and the 25% DD mandate stay binding.

**Qué la mataría.** the sizing model just re-learns the direction model's confidence (redundant with prob channel) or overfits trade-level noise - shows up as sealed-window collapse of the sizing decisions

**Resultado.** Stage 1 (map) and stage 2 (OOS validation) DONE, both positive. Map: 22,439 champion-rule entries, mean +0.17%/trade, win 43%; expectancy strongly state-dependent (Q4-Q1: vol +0.83pp, mom +0.70pp, prob +0.58pp, trend_age +0.44pp; hurst flat), gradients positive in essentially every year - not 2021 in disguise. Stage 2 walk-forward (expanding, 1-month embargo, clipped target, train-quintile multipliers 0.5-2.0): sized beats flat in 5/7 OOS years, mean lift +0.08pp/trade (~+45% relative), worst year -0.0001, loss-REDUCING in the 2022 bear. Stage 3 next: per-bar sizing channel npz (tree.npz pattern - expanding annual retrain in research, research-only final model for sealed), SizingModel module (off-by-default), tests, money_model row in risk_grid.json so the loop judges it on the real engine. Trade-level lift does NOT yet imply portfolio lift - the loop's A/B decides. | STAGE 3 WIRED: moneymodel.py exports a per-bar size-multiplier overlay (walk-forward by year, December embargo, train-quintile mults 0.5-2.0, early years abstain, sealed window scored by a research-only model); Sizing module (modules/sizing.py, lever money_model, entries only, bounded 0.25-2.5, abstains without a verdict); channel size()/size_path wired through Channels/strategy/orchestrator; money_model added to MODULE_LEVERS; risk_grid.json got an 11th row = champion shipping config + money_model 1.0, so every iteration A/Bs the learned sizing against the incumbent per-year on the real engine. 8 new tests (incl. train_mask leak guard and train-bounds mapping); suite 398 green. Activates at the next loop restart. The loop's per-year sweep now delivers the portfolio-level verdict the trade-level +45% cannot give by itself. | FIRST PORTFOLIO A/Bs (same net, config 7 vs 11): iteration 1 a wash (score -0.0011, CAGR -0.0114); iteration 2 clearly positive (score +0.0206, worst year +0.0147, CAGR +0.0587, 2021 +61.6pp, 2022 bear +1.5pp) and the money_model row WON the eleven-row grid. The pre-registered prediction (score up, profit DOWN in flat years) is NOT supported: sizing raised profit in the positive sample. The reasoning behind the prediction was the error - a mean multiplier per year does not predict a portfolio outcome when only two positions are held and selection interacts with sizing. Two samples is encouraging, not conclusive; the row stays and evidence accumulates. Known understatement: the overlay is built from the CHAMPION's signals while these iterations score different nets. | THIRD A/B SAMPLE: iteration 3 dscore +0.0060, dcagr +0.0600, worst year unchanged. Running tally n=3: -0.0011, +0.0206, +0.0060 (mean +0.0085, positive in 2 of 3). Verified properly this time that iteration 2's money_model row DID win its grid (rank 1/11) - the earlier check compared an exact float against ROUNDED sweep values and reported a false negative. Per-iteration ranks: 4/11, 1/11, 7/11. Encouraging, still not conclusive; the row stays and samples accumulate. | STAGE 4 SHIPPED (pending restart): the sizing channel is rebuilt FROM EACH NET'S OWN SIGNALS every iteration, mirroring the meta channel's existing discipline, with exit rules read from the money_model row so the model learns the outcomes of the rules it will size. This removes the handicap under which the lever already went 3-for-4. Measured cost: 22.7s per iteration with the loop's precomputed bars (~0.4%). The verification path rebuilds it too and FAILS CLOSED - a config needing sizing that cannot build the channel returns None and blocks promotion rather than scoring a sizing-free strategy against a bar that includes sizing. 4 new tests; suite 407 green. | FIFTH A/B SAMPLE: dscore +0.0349, dworst +0.0255, dcagr +0.0943. Tally n=5: -0.0011, +0.0206, +0.0060, +0.0362, +0.0349 - mean +0.0193, positive in 4 of 5, and the last three all improved CAGR by 0.058-0.094. Per-net rebuild now ACTIVE (restarted seed 53629). Launched the decisive targeted test: the CHAMPION genome, band pinned, scored with money_model 1.0 under two fresh seeds by the loop's own verification method, so the median is directly comparable to the +0.0029 bar. | *** TARGETED TEST: the CHAMPION genome with money_model on reproduced at MEDIAN +0.1183 (seeds 77101/77102, band pinned, loop's own verification method) against the +0.0029 bar - delta +0.1154, far past promotion grade. NOT ACTED ON YET: those seeds differ from the bar's (91001/91002), the same confound that nearly sold the band result, so a PAIRED test is running - one net per seed, scored twice, with and without sizing, seed variance cancelling exactly, plus per-year detail. Leak audit already clean: zero test-year or December rows in any training fold, and the embargo's residual path is empirically empty since the longest trade is 648 bars (~6.7 days) against the month-plus needed to reach the next year. The remaining question the per-year deltas answer: whether the gain concentrates in the NET's training years (exploiting in-sample optimism) or persists into its validation window. | *** PAIRED VERDICT: NOT promotion-grade, and the +0.1183 headline was confounded. Same net scored twice: plain +0.0738/+0.0724, money +0.1296/+0.1070, PAIRED DELTA +0.0558/+0.0346 (median +0.0452) - just under the 0.05 margin. The apparent +0.1154 came from comparing against a bar measured on OTHER seeds. Both pre-registered checks PASSED: 2018 (no verdicts) is byte-identical between arms at +0.0%, proving no leak; and the gain persists into the net's validation window (2024 +7.6/+12.5pp, 2025 +3.3/+5.6pp), so it is not exploiting in-sample optimism. BUT seed 77102's money arm TRIPPED THE 25% MANDATE (all_positive False with every year positive). Verdict: a real, leak-free, consistent effect worth ~+0.045 that currently buys part of its return through the operator's hard limit. Testing intensities 0.5/0.75 next. | *** RESOLVED AND SHIPPED AT 0.5. Paired intensity sweep (same net per seed, status and drawdown recorded): paired deltas +0.0229 at 0.5, +0.0342 at 0.75, +0.0452 at 1.0; worst drawdown 22.2% / 24.9% / 25.7%, with 1.0 breaching the mandate in 2021. Perfectly monotone in both - a risk/return dial, not free money. Shipped 0.5 in risk_grid.json: about half the gain with a 2.8-point mandate buffer. 0.75 rejected DESPITE a higher score, on this codebase's own measured precedent that configs sailing to a 24-25% drawdown overfit and generalise worse (fast_portfolio's SELECTION_MANDATE comment). Honest framing: applying the paired delta to the bar puts champion+sizing-at-0.5 near +0.062 against a +0.0391 bar - real, safe, and NOT promotion-grade on its own against the 0.05 margin. The operator's flagship idea is therefore a genuine, verified, leak-free improvement of about two hundredths, now riding every iteration.

**Experimentos.** `P04-money-model-more-samples` (cancelled)

### A54-deploy-more-capital — THE BINDING CONSTRAINT: the book risks under 1% of capital; offer the search a bigger one  ⭐
*portfolio/exposure · selection · critical · creada 2026-08-28*

**Por qué.** Return on deployed capital runs 287% to 3900% a year, while average deployment runs 0.5% to 13.9% and has been under 3% since 2022. Drawdowns sit at 2.7-10%, far inside the 25% mandate. The strategy has an extraordinary edge on a vanishing position. Every row of the live risk grid fixes max_positions=2 and position_fraction=0.15, so the search has never been offered anything larger; the code's default grid uses five positions at 0.5-0.7. Compounding that, the selection law weights profit at only a tenth of the worst year, and the surest way to protect a worst year is not to trade - so the objective itself prefers cash.

**Qué esperamos.** returns scale roughly with deployment while drawdown scales more slowly, so a materially larger book stays inside the mandate and multiplies the yearly figures the operator objected to

**Cómo se prueba.** P06 sweeps deployment upward (2/0.15 -> 3/0.30 -> 4/0.50 -> 5/0.70) paired on the champion genome, judged on EVERY year, with the drawdown rejection fixed at 24% in advance. Report the return/drawdown trade-off as a curve rather than a verdict, because the choice of where to sit on it is the operator's risk appetite and not a technical fact. If the curve is favourable, the risk grid must be widened - and the CAGR weight in the selection law becomes a question for him.

**Qué la mataría.** drawdown scales at least as fast as return, so larger deployment breaches the 25% mandate or turns the worst year negative - in which case the tiny book is the price of the consistency law and the OPERATOR must decide whether he still wants that law

**Resultado.**  | P06 RESULT, and it tested the wrong knobs - usefully. Control exact at 0.0228. 2x0.30 delta -0.0020 with exposure up only 9% (5.49%->5.99%) and a 2018 MANDATE BREACH at 25.1% drawdown; 3x0.30 delta -0.0505 with exposure DOWN to 5.03%; 4x0.50 delta -0.0592 with exposure DOWN to 4.70%. Reading the source explains all three: deploy = position_fraction + (regime_deploy - position_fraction) * breadth_score, and per-position size = equity * deploy / max_positions. So position_fraction is the BEAR-MARKET FLOOR (raising it doubles the book exactly when breadth is worst - hence the 2018 breach), regime_deploy is the CEILING, and max_positions is a DIVISOR that shrinks each position when slots outnumber candidates. A pre-registered diagnostic did fire though: exposure FELL when slots were added, which is the signature of filters refusing to fill them - the strategy cannot find three concurrent names that pass meta, breadth and regime. NEXT: sweep regime_deploy (the ceiling) with max_positions=2 and position_fraction=0.15 held fixed - queued as P09. | CORRECTION on the CAUSE: I had blamed the selection law as well as the grid. Re-scoring 153 stored sweeps under CAGR weights 0.10 to 2.00 shows the law is largely innocent - a TWENTYFOLD weight increase moves median CAGR only +21.2% to +28.3%, worsens the median worst year -8.4% to -13.1%, and never selects anything other than two positions at fraction 0.15; only the deployment ceiling moves, 0.35 to 0.5, which is the grid's own maximum. At weight 0.25 the choice is identical in 97% of iterations. So the GRID caps the book, full stop: no weight can produce a large book from a menu whose every row is small. Changing the weight remains a genuine operator choice about profit versus a bad year, but it cannot answer his complaint on its own. | *** P09: BEST RESULT OF THE PROJECT. Raising the deployment CEILING for the first time ever above 0.5 - ceiling 0.50 gives paired delta +0.0308 with exposure 5.49%->7.67% and worst drawdown 25.0% (one stop, 2018), beating the learned money model's +0.0228 and doing it by deploying more rather than choosing differently. Above that it collapses: 0.70 gives -0.0887, 0.90 gives -0.0922, despite exposure reaching 11.3% and 13.6%. THE COLLAPSE IS THE ABORT, NOT THE MARKET: at ceiling 0.90 the year 2021 scores MINUS 2.2671 - 227 percentage points below baseline - because the 25% peak-to-trough abort halts the account early and forfeits the +281% run; 2018, 2019 and 2021 all stop out at both 0.70 and 0.90. So this curve's concavity is an artefact of the hard stop, which the operator removed on the same day. Ceiling 0.50 is therefore the best configuration UNDER A 25% ABORT; what is best under a looser one is unmeasured, and P10 now tests ceiling and abort TOGETHER because levers do not compose.

**Experimentos.** `P06-deploy-more` (done); `P09-raise-the-ceiling` (done)

### A57-drawdown-as-objective-not-constraint — OPERATOR: remove the hard 25% cap - minimise drawdown, do not bound it  ⭐
*mandate/risk · selection · critical · creada 2026-08-28*

**Por qué.** Operator instruction of 2026-08-28: seek the minimum drawdown but set no ceiling; a winning strategy that needed 30% once is acceptable. Maximise results first and reduce risk afterwards. This turns drawdown from a binding constraint into a reported criterion, and it unblocks configurations that were being refused outright - including P06's 2x0.30 arm, rejected at 25.1%.

**Qué esperamos.** configurations previously refused become comparable, and the return/drawdown curve can be shown over its whole range instead of being truncated at the old cap

**Cómo se prueba.** Runner: DD_REJECT becomes a FLAG, nothing is discarded. Project rule file updated so an autonomous loop cannot keep enforcing a revoked policy. The brain's own max_drawdown is NOT silently changed - it is part of the strategy, since it halts the account for the year - so P10 sweeps it (0.25 / 0.35 / 0.50 / effectively off) as a free parameter, judged on every year with drawdown reported alongside return.

**Qué la mataría.** the freed configurations turn out to be the edge-sailing kind this repository has already measured as generalising WORSE out of sample, in which case the cap was doing real work and the operator should be told so with the evidence

**Resultado.**  | *** P11 SETTLES IT: the abort was the WHOLE cap on the deployment curve. Loosened, the curve rises monotonically - +0.0308 (c0.50/cap0.50, dd 25.5%), +0.0730 (c0.70/cap0.50, dd 31.5%), +0.1166 (c0.90/cap0.60, dd 38.0%) - the largest paired delta ever measured, with EVERY year better at EVERY arm and no stops anywhere. Thin years roughly double (2022 +7.0pp, 2025 +4.3pp). The price is intra-year drawdown, reported per arm as the mandate requires. Curve still monotone at the edge -> P14 probes beyond. Grid widened 13->15 (needed max_drawdown added to KNOWN_LEVERS first - the silent-strip trap, caught proactively).

**Experimentos.** `P10-drawdown-cap-sweep` (done); `P11-ceiling-times-cap` (done); `P14-beyond-the-tested-edge` (done)

### A65-new-information-funding-feargreed — The new-information frontier opens: perp funding history + real Fear & Greed, feeding two modules built and waiting  ⭐
*generation/new-information · data+training · critical · creada 2026-08-29*

**Por qué.** Every price-derived generation lever is now a measured loss (P13 filters, P15 market features, P16/P17 labels, A61 committee) and the walk-forward mandate demands unseen-data performance. The two honest, free, point-in-time sources that feed ALREADY-BUILT modules: Binance USD-M funding settlements (crowd positioning; the microstructure module has waited for this feed since A06) and alternative.me Fear & Greed daily (real crowd emotion; the sentiment module currently uses a price proxy). Funding coverage starts ~2019-09 for BTC, later for alts - partial coverage is a fact to handle, not hide.

**Qué esperamos.** Stage 1 (CPU map): funding extremes / F&G extremes stratify our champion trade outcomes or mark the bear-rally windows the sleeve buys. Stage 2: causal channels (bar reads only strictly-past settlements/days) + micro_gate / real-feargreed paired tests. Success signature under the NEW instrument: held-out walk-forward years improve.

**Cómo se prueba.** external_data.py (fetch+store verbatim, gitignored data dir). Consumers enforce causality: funding read strictly before bar time, F&G day strictly past.

**Qué la mataría.** No stratification of realised outcomes at stage 1 (dies for the price of a download), or coverage too thin before 2020 to evaluate honestly.

**Resultado.** Stage 1 PASSED on Fear & Greed; funding PARKED. Trend book by prev-day real F&G, 3,158 trades: Q1 fear -0.099pct/trade at 34pct win vs Q4 greed +0.956 at 48pct - near-monotone, a real losing tail our book does not avoid. DESIGN FINDING: the built sentiment module is CONTRARIAN (press on fear) and the real data says the OPPOSITE for a trend book - trend entries during fear days are counter-regime and lose; measuring before wiring saved us again. Capitulation book: best bounces at MID sentiment (+1.9/+2.2pct, 69pct win); panic-day entries ~breakeven (+0.05). Funding: U-shaped on trend, flat on sleeve - no clean signal, parked. STAGE 2: fng_min veto lever (prev-day real F&G below the indexs OWN published extreme-fear boundary of 25 - an external threshold, not fit to our map), new channel + module, off-by-default, tests; evaluated under the walk-forward instrument. || STAGE 2 WIN, and judged on the column that counts. Research years (P20, paired): fng_min 25 best arm +0.0045, both seeds positive, exposure DOWN 8.09->7.88. HELD-OUT years (P19's seven walk-forward nets, paired on identical nets): median -0.8% -> +2.0%, mean +17.3% -> +21.8%, negative years 4/7 -> 3/7. HONEST READING: the effect is concentrated - 2019 +2.8pp and 2021 +28.4pp - and is EXACTLY ZERO in 2022/2023/2024/2025, because in those years the book barely trades (exposure 1-4%) and rarely has an entry to refuse on a panic day. So this fixes a real leak in ACTIVE years and does nothing for the thin ones; it is a genuine improvement and not the answer to the 30% mandate. First lever built on non-price information, and the first to improve the held-out median.

### A44-held-out-risk-selection — Both nested selections: hold out years for the risk grid, and stop the band optimiser inflating too
*statistics/validation · selection · high · creada 2026-08-26*

**Por qué.** Measured across 125 sweeps, choosing the best of ten risk configurations on the same eight years that score them inflates the reported result by 0.077 on average - about half of the entire gap between a champion's headline and what it reproduces. The grid search is a multiple-comparisons problem scored on its own selection set.

**Qué esperamos.** iteration scores drop by roughly the measured inflation but become honest, so the search stops chasing configurations that merely fit the scoring years best

**Cómo se prueba.** Choose the risk row on an early block of research years and score it on a later block, or keep the current selection but report and promote on the MEDIAN of the grid rather than its max. Compare against the measured 0.077 inflation to confirm the fix removes it. 2026 stays sealed.

**Qué la mataría.** splitting the years leaves too little data for either selection or scoring to be stable, making the cure worse than the disease

**Resultado.** Free half implemented: every ledger row now records grid_median (the median configuration on that net) and grid_inflation (reported max minus median), so each iteration carries an uninflated number at zero cost. Tested; awaiting the next restart. The remaining half - selecting the risk config on held-out years, or promoting on the median rather than the max - follows once the per-iteration data confirms the aggregate 0.077. | WIDENED after the ensemble refutation: the system performs TWO best-of selections per iteration - the band on validation and the risk config on the research years - so every reported score is a max of a max. The ensemble experiment showed the band step is not benign, since smoothed probabilities made its choice swing between min_hold 96 and 288 and the scores spread five times wider. Fixing only the risk grid would leave half the problem. | TRIGGER DEBIAS SHIPPED (pending restart): the verification trigger now compares score MINUS the measured grid inflation against the bar (_is_candidate), with the inflation read live from the ledger's per-iteration grid_inflation median once 8+ rows exist (_inflation_prior, fallback 0.0765). Margin is enforced ONLY at promotion on the reproduced median - demanding it at the trigger too would double-count. Measured justification: 26% of the 142 historical iterations would have triggered a ~2 GPU-hour verification under the old rule and essentially all get refused (reproducible medians near -0.10); under the debiased trigger ~1-2%. Each trigger decision is recorded in the ledger row (trigger.inflation_prior, trigger.debiased_score). 4 new tests; suite 390 pass. The BAND optimiser half and true held-out year-block selection remain open - note the year-block split has a structural problem to solve first: only two bear years exist (2018, 2022), so any contiguous split leaves one block bear-free and its worst-year criterion toothless. | BAND HALF, MECHANISM SHIPPED (opt-in, no behaviour change yet): the genome may now pin the band via band_enter/band_exit/band_hold (_pinned_band), converting train()'s hidden 72-way validation maximum into an explicit searched dimension that is recorded, reproducible and seed-verified like every other lever. Pinned in the VERIFICATION path too - re-sweeping there would hand each re-run its own 72-way maximum, reintroducing optimism into the one measurement built to be free of it (the same bug that once made verification re-search the risk grid). A partial pin never applies: all three keys or none. 2 tests (incl. a signature check so a renamed train kwarg cannot make the pin silently do nothing); suite 400 pass. search.json does NOT declare the band dims yet - the measurement decides, same discipline as the risk grid. | BAND INFLATION MEASURED: +0.0811 (max -0.0183 vs median -0.0994 over 72 bands), and the winning band wins ZERO of the eight years individually - an artefact, not a setting. Combined with the grid's +0.0765 that is ~0.158 of pure selection optimism per reported score, which matches the long-observed ~0.15 headline-to-reproduction gap almost exactly: the decomposition is complete. BUT declaring band dims immediately would have created a STALL - the bar on disk was itself measured with band-swept verification re-runs, so pinned candidates would score ~0.08 lower than the incumbent forever (the mirror of the original lucky-champion stall, and the third instance of the same bug class - now recorded as bar-must-measure-what-candidates-measure). Caught before shipping. The bar is being re-measured with the champion's band pinned; search.json flips only once that number exists. | *** WIN, AND THE BIGGEST RESULT SO FAR. Controlled A/B on identical seeds: swept -0.1666/-0.0329 (median -0.0997) vs pinned +0.0057/+0.0000 (median +0.0029). Sweeping the band COSTS ~0.10 of score. Mechanism: train() maximises per-symbol validation net-of-toll RETURN while the genome is judged on worst-year + 0.10*CAGR over a two-position portfolio - seed 91002's sweep chose a band with 4x the validation return that scored WORSE on the real law. Hard maximisation on a misaligned proxy is worse than no maximisation. It also resolves A43: pinned re-runs are ~20x more reproducible (spread 0.006 vs 0.134), so the band optimiser was the variance source, and bagging failed because it pushed MORE variance into it. SHIPPED: band_enter/band_exit/band_hold declared in search.json (spanning the grid, NOT cherry-picking the measured argmax), bar re-measured through the new path to +0.0029 with the old -0.0885 and the reason preserved in the note, loop restarted on seed 50227. Both nested maximisations are now addressed: the risk grid by the debiased trigger, the band by pinning. | PREDICTION CORRECTED (honestly): I predicted pinned scores would rise ~0.10 across the search; the first pinned iteration scored -0.0922, BELOW the swept mean of -0.0674. n=1 proves little, but the prediction was ill-formed. The +0.10 was measured for the CHAMPION's band; the search now draws arbitrary bands, and the declared sub-grid's median (-0.0934) sits essentially at the full-grid median (-0.0994) and the swept result (-0.0997). So sweeping buys about what a RANDOM band buys - the gain came from pinning a GOOD band. A44's core claim is unchanged; its interpretation is: pinning makes the band a searchable, verifiable gene, and the search must now actually find good bands.

### A56-shipped-trade-concentration — Measure how concentrated the SHIPPED champion's profit is, before scaling anything
*statistics/tail · measurement · high · creada 2026-08-28*

**Por qué.** The raw entry rule's profit is carried by roughly the top one percent of its trades and is outright negative in 2022, 2023 and 2025, yet the shipped champion is positive in every year - so the meta, breadth and regime filters are doing the real work. What is not known is whether the SURVIVING trades are themselves concentrated. It matters directly for the deployment decision: if the shipped profit also rides on a handful of trades, scaling the book multiplies variance faster than the mean, and calling it under-sized would be the wrong description of an unusually selective strategy.

**Qué esperamos.** filtering removes the losing mass and leaves a flatter distribution, in which case scaling is genuinely just scaling

**Cómo se prueba.** The real engine per-trade ledger is not exposed by launch.year_window's summary, so either surface it or reconstruct the filtered trade set by applying the meta, breadth and regime verdicts to the mapped trades. Then report, per year, the share of profit from the top 1% and 5% of SURVIVING trades, alongside the same numbers for the raw rule already measured.

**Qué la mataría.** the survivors are as concentrated as the raw set, which would mean the strategy is a tail harvester and any deployment increase must be judged on variance rather than on average return

**Resultado.** CAPABILITY BUILT 2026-08-28: launch.round_trips pairs the ledger's BUY/SELL orders into closed round trips with realised P&L, measured on invested capital including BOTH fees, excluding positions still open at the window's end because an unrealised mark is not a result. Exposed through run_window/year_window as with_trades, OFF BY DEFAULT - a year holds thousands of round trips and the autoloop writes every summary into the ledger, so it must never turn itself on. 6 tests including unmatched sells, zero-cost orders and the default-off guarantee; suite 429. The measurement itself is now a plain script: run the champion config per year with with_trades=True and report the share of profit from the top 1% and 5% of SURVIVING trades, against the raw rule's 111% and 321%. | ANSWERED. Profit measured in MONEY (a first pass using per-trade percentages produced negative sums in years returning +8.9% and +14.3% - the giveaway that the metric was not tracking what it named). Shipped champion: top 1% of trades = ~20% of gross profit, top 5% = ~45%, win rate 42%. Raw rule for comparison: 111% and 321%. So the filters strip the losing mass and leave a distribution that CAN be scaled - 'under-sized' is a fair description for normal years. EXCEPTION: the thin years. 2022 took 34 trades with its single best supplying 53% of gross profit, 2025 took 44. Concentration is a property of how many trades a year offers, not of the strategy - and in those years doubling size doubles one bet, not a portfolio.

**Experimentos.** `P08-shipped-concentration` (done)

### A13-modules-generalize-to-2026 — Decision modules (breadth 0.30 + meta) generalize far better to sealed 2026
*risk-lever · creada 2026-08-21*

**Por qué.** Corrected 4-variant run (same champion model, 14 symbols): V1 bare model -> 2026 SEALED -23.3%; V2 +breadth0.30+meta -> 2026 SEALED +15.8% AND worst-year -7.9%->-4.7% AND validation score -0.0386->-0.0189. V3/V4 (money/martingale) -> 2026 +19% but clip the 2021 bull so validation CAGR falls. So the modules add real OUT-OF-SAMPLE value; V2 loses on the CAGR-weighted score ONLY because it clips the bull. Strong evidence for A11 (the consistency criterion under-weights robustness).

**Qué esperamos.** a robustness-weighted criterion would prefer V2; 2026 stays SEALED (observation only, never selected on)

**Qué la mataría.** n/a (observed)

**Resultado.** V2 sealed 2026 +15.8% vs bare -23.3%; worst -4.7%; do NOT promote on 2026 — flag A11 for operator

### A17-new-champion-all-positive — BREAKTHROUGH: autoloop promoted the first ALL-POSITIVE champion (score +0.034)
*model-arch · creada 2026-08-21*

**Por qué.** iter 5 promoted (autoloop.log): score +0.034 (vs old -0.0127), worst year +0.5%, CAGR +29.2%, ALL YEARS POSITIVE 2018-2025 [2018:+1% 2019:+11% 2020:+65% 2021:+176% 2022:+4% 2023:+10% 2024:+19% 2025:+12%]. band enter0.85/exit0.15/min_hold384, risk 2/0.15/0.08/0.12. Even 2022 (the LUNA/FTX bear every prior champion lost) is now +4%. This is the operator's 'profitable every year' badge, found autonomously by the search.

**Qué esperamos.** much higher rolling 1-yr win rate than the old 82% (fewer losing calendar years)

**Qué la mataría.** n/a (promoted on honest 2018-2025 consistency; 2026 never used)

**Resultado.** NEW CHAMPION. Pending: sealed-2026 readout + rolling recompute once best.json/signals settle (promotion still writing curves).

## ✅ Ganadoras con condiciones

### A66-deep-wide-universe — Widen the universe to 24 DEEP-history symbols - A37's failure mechanism removed  ⭐
*generation/breadth · data+training · critical · creada 2026-08-29*

**Por qué.** Operator (2026-08-29): monitor more assets and only take the highest-certainty opportunities. A37 refuted a 35-symbol universe, but its mechanism was specific and is fixable: 'more coins means more chances for a spurious high-conviction signal on a noisy LATE-LISTED name to displace a good pick'. So the fix is not fewer symbols, it is deeper ones: this universe screens at 1,600 days of history (~4.4 years) and $5M turnover, giving 24 symbols that all actually EXIST across the held-out years. A37 also never tested the operator's real hypothesis - raising the certainty bar as the pool grows, so that a bigger pool buys selectivity rather than dilution.

**Qué esperamos.** held-out years improve, most where the book is starved (2022/2025 traded ~52 times on unseen data); the mechanism to watch is mean conviction of EXECUTED entries rising

**Cómo se prueba.** universe_deep.json (24 symbols) built; data downloading. Then a walk-forward campaign: train wide per cutoff, trade wide, sweeping enter in {0.75 (current), 0.80, 0.85} - judged ONLY on held-out years.

**Qué la mataría.** wide loses again on the walk-forward column even with the raised bar - then breadth is genuinely not the constraint and A37's verdict generalises

**Resultado.** MEASURED on 6 of 7 cutoffs; the 7th (2025) was deliberately TRUNCATED on 2026-08-30 to free memory for the champion attempt the operator had prioritised - one more observation was not worth blocking his stated goal for hours, and that truncation is recorded rather than hidden. Held-out returns, wide(24) vs narrow(14): 2019 -42.5/-0.8, 2020 -25.2/-4.7, 2021 +153.6/+113.4, 2022 +1.2/-10.2, 2023 +2.0/-13.2, 2024 +37.0/+29.2 (at the shipping bar 0.75). VERDICT: breadth is CONDITIONAL on universe maturity. Where the added symbols had years of history (2021+), wide wins EVERY held-out year and has no negative year at 0.75 or 0.80, against narrow's two - the operator's all-years-green criterion, on unseen data. Where the list was young (2019/2020: only 8 and 15 trainable symbols) wide lost catastrophically, which is A37's mechanism confirmed rather than contradicted. 2026 sits in the mature regime, so the champion attempt runs on the wide universe.

## ✅ Pasaron su fase

### A64-bear-rally-long-book — The measured path to the 30% floor: a LONG book for bear-market rallies (system 07 capitulation embryo, promoted to the program)  ⭐
*generation/counter-trend · training · critical · creada 2026-08-28*

**Por qué.** The same ceiling measurement that killed shorts revealed where the thin years' money actually is: 2022 holds ~95pp of 10%-leg LONG raw material across the universe - bear-market rallies - and our trend book is STRUCTURALLY blind to all of it (the slow-trend veto excludes down-trend names, correctly, for a trend system). P13 proved the thin years cannot be rescued from inside the trend stream; this is the stream that lives exactly there. The capitulation entry (A06->A09 repurpose, capitulation.py + tests, system 07 embryo) is the natural spotter: flush -> bounce, long, tight stop, short hold.

**Qué esperamos.** a counter-trend long book whose per-year profits concentrate in 2018/2022/2025 - anti-correlated with the trend book by construction; two-book capital split lifts the worst year toward the operator's 30% floor

**Cómo se prueba.** Own honest pipeline like the main book: capitulation labels, walk-forward meta, own money model, per-year measurement, 2026 stays sealed. Runs on CPU-light backtests first (rule-based entry, no net) to establish the edge exists at all; GPU only if a learned spotter beats the rule. After P15 in the queue.

**Qué la mataría.** walk-forward capitulation entries cannot clear costs in the bear years themselves (the bounce exists in hindsight but is not predictable), or the combined book's drawdown overlap erases the diversification (both books long, same crashes)

**Resultado.** Stage 1 PASSED with the predicted signature. Rule book (capitulation score entry, 6pct tp/sl, 1d max hold), continuous 2018-2025, 14 symbols: at enter=0.5, +160.4pct total, 537 trades, 63pct win. Earns exactly where the trend book cannot: 2022 +10.5 (dd 4.0), 2025 +15.5 (dd 3.8), 2023 +9.7, 2018 +7.4; small losses in the trend books big years (2020 -2.6, 2024 -1.5). Trades when the main book sits in cash, so it can ride the idle-cash sleeve without diluting 2021. CAUTION: enter 0.4->0.5 flips 2018 by 16pp - stage 2 (threshold plateau + cost x2) running before anything is believed. || Stage 2 PASSED: the complementarity signature is a PLATEAU, not a magic cell. 2025 positive at ALL thresholds 0.40-0.60 (+4.5 to +15.5); 2022/2023/2019 positive across nearly all; at enter 0.55 EVERY research year is positive (2018 +15.1, 2019 +2.2, 2020 +1.1, 2021 +20.3, 2022 +2.2, 2023 +3.9, 2024 +3.6, 2025 +10.1; 353 trades, 63pct win). Cost x2 at 0.50: thin years SURVIVE (2022 +3.9, 2023 +7.5, 2025 +11.1, 2018 +1.2); bull-year losses deepen (2020 -13.4, 2024 -8.0) - years the trend book carries anyway. The loose-threshold 2018/2024 losses are weak capitulations that die - strictness is the fix, mechanism understood. Operating region 0.50-0.55. NEXT: stage 3 - the cash-sleeve combine (capitulation book rides the trend books idle cash), shared-equity accounting, overlap drawdown measured; tests before it touches any live path. || Stage 3 PASSED (cash-sleeve combine, 30pct sleeve, capit enter 0.50, aligned equity curves): EVERY thin year lifts (2022 +3.1pp to 15.5, 2025 +2.6pp to 7.6, 2023 +2.9pp, 2019 +1.1pp; worst year 5.1 -> 7.6) AND combined drawdown FALLS in 6/8 years - 2021 dd nearly halves (17.4 -> 10.8): the bounce-buyer earns during the very crashes that draw the trend book down. Max combined dd 24.4 vs 26.1 trend-alone. CAVEAT: year-start sleeve overdraws cash up to 106.8pct in growth years (positions appreciate past the 0.50 entry ceiling); monthly rebalance fixes it and will shave those lifts slightly; thin years run 80-99pct use, feasible as-is. HONEST GAP: the combine is a stabilizer, not a rocket - 2019/2025 remain far below the 30pct floor; closing that gap still belongs to generation (P15/A60/A62) and to raising the capitulation books own expectancy (its sizing is naive equal-fraction). NEXT: engineer the combine properly (monthly rebalance, cash-capped sleeve, tests) and give the capit book the learned-sizing treatment. || Stage 3b (monthly rebalance + worst-bar cash cap, the FEASIBLE version) is BETTER than the naive sleeve: compounding the sleeve monthly turns 2021 into +113.8pp extra (dd 11.0 vs 17.4), thin years hold their lifts (2022 +3.3 to 15.6, 2025 +3.0 to 8.1, 2023 +3.2, 2019 +0.9), worst year 5.1 -> 8.1, max combined dd 24.3 vs 26.1, and the cash cap barely binds (avg r_m 88-100). Measurement phase COMPLETE. Remaining: live-path engineering (two-book orchestration + tests) and the capit books learned sizing - queued behind the P15 verdict and the operators adoption decision.

## 🔧 Construidas, pendientes de medición

### A69-seasoning-gate — A symbol is not tradable until IT has history - the causal version of the universe screen  ⭐
*universe/causality · code+training · critical · creada 2026-08-30*

**Por qué.** The wide candidate's only losing research year is 2018 (-6.8%), and the wide walk-forward's only disasters were 2019/2020 - precisely the years when most of the 24 screened symbols were freshly listed. The screen asks 'does this coin have 4.4 years of history?' ONCE, today; the book needs the answer AT EACH BAR. A coin with four years of history in 2026 had four months of it in 2018, and we were trading it as though the screen had vetted it. This is a real look-ahead of a subtle kind: not in the prices, but in the membership of the universe itself.

**Qué esperamos.** the young-universe years stop bleeding - 2018 for the full-history candidate, and the 2019/2020 walk-forward cutoffs - without touching the years that already work

**Qué la mataría.** the gate removes so many names that the book starves in the early years, trading the immature ones was not the cause, or the fix costs more in good years than it saves

**Resultado.** BUILT: modules/seasoning.py with lever min_age_days, vetoing any symbol whose own history at that bar is shorter than the threshold. Wired through orchestrator, strategy adapter and KNOWN_LEVERS; 6 tests including the exact 2018 failure shape. Off by default, so nothing changes until it is measured.

### A74-vector-memory — Vector memory of past decisions: 'what happened the last N times the market looked like this?'  ⭐
*operator/retrieval · module · critical · creada 2026-09-02*

**Por qué.** Operator, 2026-09-02: a vector database that helps the decision tree. The trade ledger already produces exactly its content - every decision bar with its 20-feature A32 snapshot AND its resolved outcome (won / lost / unforced / missed). Store those vectors and at each candidate entry retrieve the k nearest historical situations, then vote with their realised outcome. This is a genuinely different inductive bias from both the TCN (learned convolutions) and the tree (axis-aligned splits): non-parametric, local, and it can say 'no analogue found' - a form of honest abstention neither of the others has.

**Qué esperamos.** Lift concentrated where the TCN is weakest: rare configurations it has few examples of. Also a natural confidence signal - the distance to the k-th neighbour.

**Cómo se prueba.** Stage 1 (CPU): build the store from attribution rows, standardise features, cosine/L2 index (sklearn NearestNeighbors - no new dependency), purge by resolution time. Stage 2: a `vectormem` module voting size_mult/veto from neighbour outcomes, one paired A/B. Runs after the participation work.

**Qué la mataría.** Leakage is the risk that kills this silently: a neighbour must be strictly in the PAST of the query bar and its outcome must have RESOLVED before the query bar, or the module is reading the future through a lookup table. Built with the same expanding time-purged walk-forward meta.py uses. If the walk-forward held-out column does not improve, it joins the measured-and-closed list.

**Resultado.** Stage 1 BUILT (quantlab_system06/vectormem.py, 6 tests). Expanding block index: a query is only ever answered by neighbours whose outcome resolved strictly before its block began, and the leakage rule is pinned by a test that plants a perfectly predictive answer in FUTURE rows - a leaking implementation scores 100%, this one abstains. Reports hit_rate, support and DISTANCE, so 'I have never seen anything like this' is expressible; unanswered queries are NaN rather than the base rate, because a default that looks like an opinion is how a dead module reads as a working one. Waiting on the champion's rebuilt trade ledger for its real feature/outcome rows.

## 📏 Medidas

### A77-why-is-in-sample-not-near-perfect — The operator's question: why is a backtest on the TRAINING data not almost perfect?  ⭐
*operator/diagnosis · measurement · critical · creada 2026-09-03*

**Por qué.** Operator, 2026-09-03: it does not seem normal that a backtest over the data we trained on is not nearly perfect. He is right that it is diagnostic. A model with enough capacity and enough passes SHOULD be able to memorise its training labels; ours reaches 66% validation accuracy and the ceiling measurement says we capture 0.03-5.9% of what perfect foresight would earn IN THE RESEARCH YEARS THEMSELVES. Three candidate explanations, and they call for different work: (1) the net still underfits - P34/P35 measured gains monotone in width and P37 died on hardware before finding the ceiling; (2) the labels are not learnable from 96 bars of causal price - the oracle uses hindsight the features cannot contain; (3) the gates in front of the net discard most of what it does get right, which is what P42 is testing.

**Qué esperamos.** Measuring TRAIN accuracy against VAL accuracy separates (1) from (2) cleanly: a big gap means we memorise but do not generalise; a small gap at 66% means we cannot even fit the training labels, which is underfitting and points straight back at capacity and at A76's extra data.

**Cómo se prueba.** tools/fit_diagnosis.py: accuracy and oracle-capture on TRAIN windows vs VAL windows for the shipping net. GPU, minutes, runs when the queue frees.

**Qué la mataría.** n/a - this is a measurement, not a proposal. It cannot lose, only inform.

**Resultado.** MEASURED. TRAIN accuracy 70.8% against VAL 66.2% - a generalisation gap of only 4.6%. The net does NOT memorise: after fifty passes it reaches 70.8% on data it has already seen. So the operator's intuition was right that an in-sample backtest ought to be far better than this, and the reason is the opposite of overfitting.

The number that reframes everything, though, is the precision AT THE TRADING BAR: conviction >= 0.75 fires on 21.1% of validation bars and is RIGHT 77.1% of the time (84.0% in-sample). The forecaster is not the weak link it looked like. With 14 symbols and ~35,000 bars a year, 21% of bars is on the order of 100,000 high-conviction bar-signals per year - and the book takes 90 trades. Whatever is losing the ceiling, it is downstream of the model.

### A63-short-book-feasibility — Shorts as the rescue for the thin years: hindsight ceiling measured, and it says no
*direction/shorts · analysis · high · creada 2026-08-28*

**Por qué.** Operator (2026-08-28): 30%/year minimum, and if nothing else works, try shorts - with the theory that market makers play against short positions. Measured before believed: zigzag decomposition of all 14 research symbols, legs charged the engine's full round-trip cost, summed per year per SIDE, at 5/10/20% thresholds.

**Resultado.** At every tradeable scale the SHORT ceiling is SMALLER than the LONG ceiling in EVERY year - including 2022, the -64% BTC bear (short/long 0.74-0.94 by scale). At 20% legs shorts hold roughly HALF the raw material (0.44-0.74). Structural, not conspiratorial: crypto's drift is up, and downside arrives compressed - crashes are fast, so harvestable down-legs are fewer and shorter-lived, while bear-market RALLIES keep feeding the long side even in 2022 (95pp of 10%-leg long material there, comparable to good years). The operator's market-maker intuition has a real mechanical kernel - liquidation-cluster hunts make squeezes an asymmetric tail AGAINST shorts (explosive rallies gap through stops) - and that cost is NOT even charged in this table, nor is perp funding or borrow. VERDICT: shorts are the worse half of the same opportunity set, with extra costs and a fatter left tail. Not the next move. Kept as an option if a future stream shows genuine down-edge the long side cannot express.

## ❓ No concluyentes — el test no respondía a la pregunta

### A72-information-driven-bars — Sample the market on ACTIVITY, not on the clock - the one axis never touched  ⭐
*generation/sampling · data+training · critical · creada 2026-09-02*

**Por qué.** Everything this project has tested changes what the model SEES (features, labels, filters, sizing, universe, capacity). Nothing has changed WHEN it looks. Every bar is 15 minutes of wall clock, whether a million dollars traded or nothing did - so a dead night and a violent hour are the same observation, and the inputs are heteroscedastic by construction. Dollar/volume/CUSUM bars close a bar when a fixed amount of VALUE has changed hands, giving returns far closer to the i.i.d. assumption every estimator in this stack quietly makes. Two of our own measurements point here rather than away: A62 showed a coarser CLOCK holds strictly less material in every year (0.70-0.78x), which says the interval length is not the problem - the ruler is; and the thin years are thin at a FIXED cadence, while activity bars would spend fewer observations on the dead months.

**Qué esperamos.** the net trains on a series whose statistics it actually assumes; the signature would be improvement concentrated in the thin years, where clock sampling wastes most of its observations on nothing happening

**Cómo se prueba.** Stage 1 (CPU, cheap): build dollar bars from the 15m data (aggregate until cumulative quote volume crosses a threshold chosen so the average bar count matches today's), then run the hindsight raw-rule map per year - the same gate that killed A62 in one afternoon. Only if the material is richer in the thin years does this reach the GPU.

**Qué la mataría.** aggregated dollar bars leave too few observations to train on at our history length, or the walk-forward held-out column does not improve - then sampling joins the list of things measured and closed

**Resultado.** Stage 1 run, and the honest finding is about my own GATE rather than the idea. Dollar bars (threshold set so each symbol's bar count scales with its traded value) retain 93-95% of the harvestable long material in 2021-2025 while using only 41% of the observations - far better retention per observation than the 1h clock managed (70-78%). But NO year is proportionally richer: the thin years sit at 0.95, 0.93, 0.94, the same as the good ones. So the A62 half of the question is answered - activity sampling does not expose material the clock misses, because the material is a property of the price path and no ruler creates it.

What the gate CANNOT answer is what A72 actually claims. The proposal is not that dollar bars reveal more material; it is that they give the NET a series whose statistics match what every estimator in this stack assumes. A hindsight zigzag map measures price movement, not learnability, so passing or failing it says nothing about that claim. Recording this rather than dressing a mismatched test as a refutation - the P33 lesson, one level up: a gate that answers a different question than the one asked is not evidence.

Stage 2 is therefore a real GPU experiment (train on dollar-sampled bars, judge on the walk-forward held-out column), and it is worth the hours precisely because the retention number is encouraging: 94% of the material at 41% of the observations means a net trained on them sees nearly everything while spending far fewer parameters on dead time.

## ⏸ Aparcadas

### A34-objective-profitability — Rebalance the selection objective toward PROFIT (not only defensive consistency)
*meta/objective · objective · high · creada 2026-08-25*

**Por qué.** OPERATOR FEEDBACK (2026-08-25): the champion is all-positive 2018-2025 but makes ~0 in 2026 - too passive. The objective score = worst_year + 0.10*CAGR under-rewards growth, biasing selection to defensive flat-book algos. Operator wants algos that GENERATE PROFIT every year in any market, not just avoid losses. Raise the CAGR weight while KEEPING all-positive as the badge and 2026 SEALED. This connects to the long-open A11 (consistency vs growth) - operator has now given the direction: more profit.

**Qué esperamos.** the loop selects algos that are both all-positive AND high-growth; less passivity; more trades -> more chance of 2026 profit via generalization

**Cómo se prueba.** CAGR_WEIGHT 0.10 -> 0.20 in autoloop._consistency; re-baseline the champion's stored score under the new weight so the promotion bar stays fair.

**Qué la mataría.** raising CAGR weight causes overfitting to bull years / worse worst-year robustness

**Resultado.** DECLINED after analysis (2026-08-25): the champion is ALREADY all-positive 2018-2025 with 35% CAGR - it is not too passive IN-SAMPLE; its only gap is sealed 2026 (~+0.4%). Raising CAGR_WEIGHT would just entrench the (bull-heavy) champion and CANNOT touch 2026 (sealed). The real gap is REGIME COVERAGE (non-trend alpha for flat years), not the training objective. Kept documented; revisit only if in-sample selection ever looks too defensive on its own merits.

### A06-microstructure-ohlcv-proxy — OHLCV capitulation signal — REAL but poor as a standalone add; repurpose as system-07 entry
*features · creada 2026-08-21*

**Por qué.** Diagnostic (BTC): the feature fires at genuine capitulations (COVID 2020-03-13 score 0.86, 2018 top, 2019 flash-crash; rare, >0.2 on 0.25% of bars). BUT it fires at BOTH bear bottoms AND bull corrections (172 in the 2021 bull), and capitulation candles precede both recoveries (COVID V) and false bottoms that fall further (2022). So a naive contrarian-add into the champion is a coin-flip (catches falling knives in sustained bears); refining it recreates the refuted trend filters.

**Qué la mataría.** standalone contrarian-add is a coin-flip; not a clean win for system 06

**Resultado.** SHELVED as a system-06 add. The tested feature (capitulation.py, 4 tests) is REPURPOSED as the ENTRY signal for system 07 (A09) — a mean-reversion dip-buyer for flat/bear periods.

### A11-consistency-law-robustness — OPERATOR-DECISION: robustness of the selection criterion vs raising CAGR weight
*research · creada 2026-08-21*

**Por qué.** Open question: winsorize monster years / walk-forward selection / meta-labeling for robustness, vs raising CAGR weight. Recommendation: robustness BEFORE raising CAGR weight. Methodology changes are NOT made unilaterally — flag for rjj.

**Qué esperamos.** a more robust score less dominated by 2021

**Qué la mataría.** n/a

**Resultado.** awaiting operator decision (do not change the criterion unilaterally)

### A12-consensus-needs-multi-directional — consensus_k>1 is a no-op-that-kills with a single directional model
*module · creada 2026-08-21*

**Por qué.** First variants run: V2 with consensus_k=2 traded NOTHING (0% every year). Only OracleNN casts a directional vote (conviction>0); meta/regime/money only veto or size. So consensus_k>=2 can never be satisfied and blocks every entry. Consensus needs >=2 direction-voting modules to be meaningful — a prerequisite for a real multi-signal decision tree.

**Qué esperamos.** consensus becomes useful only after a 2nd directional module exists (e.g. a mean-reversion or momentum-direction voter)

**Qué la mataría.** n/a (recorded limitation)

**Resultado.** shelved until a second directional voter exists; links A09 (system-07) and a future momentum-direction module

## ❌ Refutadas — medidas y cerradas, con su resultado

### A38-adaptive-recency-training — Adaptive / recency-weighted training: track the CURRENT market instead of the 2018-2025 average  ⭐
*machine-learning/non-stationarity · training · critical · creada 2026-08-25*

**Por qué.** THE central finding (2026-08-25): two independent disciplines both hold a stable edge for six research years and then INVERT in 2026, in every fractal regime. That is alpha decay / structural change, not capacity and not a detectable regime. The direct answer to non-stationarity is to fit on RECENT data: rolling-window or recency-weighted training with frequent refits, so the model tracks what the market is doing now. Fully testable WITHOUT 2026 by comparing rolling-window against expanding-window models on later research years.

**Qué esperamos.** a rolling/recency-weighted model beats the expanding-window one on the most recent research years and degrades more gracefully out-of-sample

**Cómo se prueba.** Add a train_window gene (expanding | 2y | 1y) plus a recency half-life weight to train.py and tree.py; judge on the per-year sweep. 2026 stays sealed.

**Qué la mataría.** rolling windows do no better than expanding on later research years (then decay is too fast for any fit to track, and the answer is exposure control instead)

**Resultado.** REFUTED on research data alone. 3 arms x 16 quarterly purged folds, judged on 2022-2025: expanding +0.312pp vs rolling-2y +0.110pp vs rolling-1y +0.115pp - rolling worse in every single year, roughly a third of the edge. The faint edge needs a large sample; shrinking it adds more estimation variance than it removes staleness. (Observation only: no arm changed the sealed-window inversion either.) The train_window_days capability is KEPT in tree.py, tested and off by default, since it is the honest control arm for any future claim that 'fresher data would fix it'. Corollary: prefer MORE data (A37) over fresher data.

### A43-ensemble-reduces-seed-variance — Do bagged ensembles raise the REPRODUCIBLE level, not just the headline?  ⭐
*statistics/variance · training · critical · creada 2026-08-26*

**Por qué.** Five reseeds across two genomes all land near -0.10 regardless of headline, so the binding constraint is seed variance: the search keeps sampling lucky draws from a distribution whose reproducible centre is poor. Bagging averages several seed-varied nets and is the standard remedy for exactly this variance. If an ensemble-of-3 genome shows a materially smaller gap between its headline draw and its re-runs, then ensembles are the route to a champion that reproduces - which is what the operator's goal actually requires.

**Qué esperamos.** an ens=3 genome reseeds much closer to its headline than an ens=1 genome does, and its reproducible level is meaningfully above -0.10

**Cómo se prueba.** Take an ens=3 genome (search.json already samples ensemble 1 and 3), score it, then reseed it twice with the fixed-config method and compare the headline-to-reseed gap against the ens=1 measurements already recorded. If it wins, bias search.json toward larger ensembles and consider making ensemble size part of the promotion requirement.

**Qué la mataría.** ens=3 reseeds scatter as widely as ens=1, which would mean the variance is in the data or the labels rather than the initialisation, and the answer lies elsewhere

**Resultado.** REFUTED, and in the opposite direction to the hypothesis. Same genome, same risk config, fixed-config scoring: ensemble-of-three scored -0.1288, -0.1845 and -0.0718 (spread 0.1127, mean -0.1283) against single nets at -0.0776 and -0.0993 (spread 0.0217, mean -0.0885). Five times WIDER spread and a worse level at three times the cost. Mechanism visible in the data: averaging pulls probabilities toward the middle (bars above 0.5 fell from ~50.5% to 45.8-47.6%), the band optimiser compensates, and it chose min_hold 288, 96 and 288 across the three runs - so variance moved from the network into the band selection and amplified. Confound acknowledged: band choice is mixed in, but that is precisely the finding. search.json ensemble dropped back to [1], which also buys 3x training throughput. The third seed was recovered on CPU after a CUDA collision killed its export, so the verdict rests on all three runs.

### A47-alternative-data-news-social — Alternative data: historical news and social sentiment as training features, readable in real time at deployment  ⭐
*data/NLP · data · critical · creada 2026-08-26*

**Por qué.** Operator idea (2026-08-26). Every channel today is derived from price/volume. The operator asks to complement with news, Twitter/X and anything else obtainable both HISTORICALLY (for training, pre-2026 only) and IN REAL TIME (for forward testing / production). Independent information sources are the only escape from the ceiling that price-derived features share; the existing feargreed channel is a price-based PROXY for exactly this and was refuted as a sizing signal - real sentiment data is the honest version of that test.

**Qué esperamos.** modest but independent lift, most visible in regime-change months where price-derived features lag the narrative

**Cómo se prueba.** Stage 1: source audit - Fear & Greed index (alternative.me, daily, history to 2018, free), GDELT news tone (free, 15m cadence), Wikipedia pageviews for BTC/crypto articles (free, hourly). Reject anything without point-in-time timestamps. Stage 2: align to 15m bars STRICTLY causally (last known value), add as channels like hurst/feargreed. Stage 3: retrain A/B with identical genome, purged validation. The seal holds: nothing after 2026-01-01 enters training. Real-time readability is a hard requirement for any source admitted.

**Qué la mataría.** no free historical source with clean timestamps exists (look-ahead through revised/backfilled data is the classic trap), or the aligned feature adds nothing after purged validation

**Resultado.**  | PROMOTED TO CRITICAL 2026-08-27, on the pre-registered condition being met: every built lever has now been tested paired on the champion genome and NONE closes the gap to promotion. Only money_model is positive (+0.020, 1.8 SE); horserace, sweep and hurst_gate are null; the tree voter and consensus are harmful; edge_monitor trades score for drawdown and does NOT compose with sizing. Even full-intensity sizing reaches only +0.0843 against a +0.0891 requirement, and it breaches the mandate. The honest reading is that this TCN-on-price family is near its ceiling, so the next move is new INFORMATION rather than more search or more levers - which is exactly what this item is for. | STAGE 1+2 DONE, NOT BUILT - the kill criterion is effectively met. Sources: Wikipedia pageviews pass every requirement (free, daily, pre-2018 history, point-in-time by construction, live-readable); Fear & Greed is reachable but partly price-derived; GDELT unreachable from this machine. Signal: monotone expectancy AND win rate across attention quartiles (raw spread +0.0064) - but only 5/8 years positive, inverted in 2025, dominated by 2021. Independence: price features explain just 7.5% of attention, so it IS new information, yet its contribution halves when they are controlled (+0.0064 -> +0.0033, correlation +0.063 -> +0.038) and stays 5/8 with a large 2018 negative. Half the strength of features that are 8/8 stable and together yield only +0.020 at portfolio level. Not worth a channel, module, per-net rebuild and GPU sweep. REVISIT IF: a higher-frequency attention source appears (per-article hourly does not exist), or the money model becomes decisive enough to carry a weak extra feature cheaply.

### A48-ensembles-under-pinning — Re-test bagged ensembles now that the band optimiser can no longer absorb the variance  ⭐
*statistics/variance · training · critical · creada 2026-08-27*

**Por qué.** A43 refuted ensembles decisively - three bagged nets scored FIVE TIMES less reproducibly than single nets - but the mechanism was specific: averaging pulled probabilities toward the middle, and the ANTI-CHURN BAND OPTIMISER compensated, choosing min_hold 288, 96 and 288 across three runs. The variance did not vanish, it moved into that selector and amplified. The band is now PINNED per genome, so that pathway is closed, and this system's own standing rule says a measurement taken under one selection regime must be re-taken when another selector is constrained. Seed variance is now the dominant problem: four re-runs of the champion genome span 0.074 with a standard deviation of 0.041, its all-positive badge appears in only two of four, and the reproducible level (+0.0391) sits far below the good draws (+0.0724, +0.0738). Reducing that variance is worth more than any lever measured so far - money_model, the best of them, is worth +0.020.

**Qué esperamos.** with the band fixed, ensemble-of-three re-runs cluster far more tightly than the 0.041 standard deviation of single nets, lifting the reproducible level toward the good draws rather than the median of lucky and unlucky ones

**Cómo se prueba.** Train ensemble-of-three under three or four seeds with the CHAMPION genome and its band pinned, score each fixed-config on the research years, and compare the SPREAD and the MEDIAN against the four existing single-net measurements (+0.0000, +0.0057, +0.0724, +0.0738). Judge on spread first and level second - A43's lesson was that a variance intervention must be judged END TO END, never at the component it touches. Record per-year status and max drawdown. 2026 stays sealed.

**Qué la mataría.** ens=3 under pinning scatters as widely as ens=1, which would mean the variance lives in the data or the labels rather than in initialisation or in any selector, and the answer lies outside the training procedure entirely

**Resultado.** REFUTED on LEVEL, confirmed on SPREAD. Ensemble-of-three with the band pinned scored -0.0013, +0.0162, +0.0422: stdev 0.0219 against the single-net 0.0406, a spread RATIO of 0.54, where A43 under band SWEEPING measured five times worse. So the A43 post-mortem is settled - the band optimiser really was absorbing and amplifying the variance. But the level fell: median +0.0162 against +0.0391, mean +0.0190 against +0.0380, consistent with averaging thinning conviction. Neither effect is statistically established at n=3 vs n=4 (level 0.8 SE; the variance ratio would need about 9x on these degrees of freedom), and ensembles cost 3x training - so search.json stays at [1]. THE PREMISE WAS ALSO WRONG: I expected variance reduction to lift the level toward the good draws, but shrinking a distribution pulls toward its MEAN, not its good tail. Reliability and level are separate goals.

### A49-earn-in-the-flat-years — Earn money in bear and sideways years, where the book is currently empty by design  ⭐
*architecture/regime · system · critical · creada 2026-08-27*

**Por qué.** The champion's worst years are 2022 and 2025, and its sealed 2026 is +4.2%; strip out 2021 and 2022-2025 average +5.9% a year. The selection law rewards the worst year, but the system defends bad years by NOT TRADING - the sixty-day trend filter holds average exposure between one and nine percent there. A defence of 'stay flat' bounds the worst year near ZERO by construction. That is why every lever has failed: sizing, circuit breakers, fractal gates, lead-lag and second opinions all act on trades the system chooses to take, and none can create return in a year when the book is deliberately empty. The operator's request - profit in falling and sideways markets - is therefore a request to change the architecture, not to tune it.

**Qué esperamos.** a mechanism that earns a few percent in 2022 and 2025 without giving back the bull years lifts the worst year off zero, which is worth far more under the consistency law than anything measured so far

**Cómo se prueba.** Judge candidates on 2022 and 2025 SPECIFICALLY, not on a CAGR that 2021 dominates, and always paired against the champion on the same nets. Candidates, cheapest first: (1) hold a reduced position through downtrends instead of going flat, sweeping the trend-filter exposure floor rather than treating it as binary; (2) mean-reversion inside ranges, which is a different label and a different net, tested only if (1) shows the exposure floor matters; (3) cross-sectional rotation into whatever holds up in a falling market, using the existing momentum channel. Long-only throughout; the 25% mandate is untouchable; 2026 stays sealed.

**Qué la mataría.** every candidate mechanism either loses money in the flat years or gives back more in the bull years than it earns in the flat ones - which would mean the flat-book design is not a limitation but the correct answer for a long-only book in this universe

**Resultado.**  | LEVER BUILT 2026-08-28: `trend_soft`. Reading the code first corrected the mechanism - the flat book is caused by a hard VETO in OracleNN (`veto = not uptrend`), not by a deploy fraction, so an exposure floor could never have worked: there are no candidate entries for a fraction to scale. trend_soft turns that veto into a dimmer, admitting a down-trend name at a fraction of normal size. Off by default and bounded at 1.0 (this lever exists to trade the flat years SMALL, never larger than an uptrend); 5 tests; suite 419; golden ensemble tests still pass, so zero reproduces every result on record. Queued as P05 at priority 0, sweeping 0.15/0.30/0.50 with a money-model control arm, judged on 2022 and 2025. | FIRST trend_soft RUN VOID, not refuted: the runner held stale imports (process started 23:59:08, lever written 00:54:14), so **_ignored swallowed the keyword and all three arms measured the baseline. The inertness guard caught it; without that guard this would have been written up as a refutation of the operator's idea. Requeued as P07 after restarting with fresh code, and two structural guards added so it cannot recur: unknown_levers checks every arm against the LIVE brain signature before training, and recover_orphans returns interrupted rows to the queue at startup. | *** ANSWERED NEGATIVELY (P07, paired, control exact, no inert arms). trend_soft deltas -0.0596 / -0.0825 / -0.1295 at 0.15 / 0.30 / 0.50 - monotone in the dose AND in each judge year: 2022 loses 1.4, 2.9, 4.9 points; 2025 loses 6.9, 7.5, 8.3. Drawdown FELL slightly, so this is not a risk story, just worse trades. Notably 2025 - a year the market rose 18.7% - was hurt MORE than the 2022 bear, so the trend bit carries real information rather than merely marking bear markets. All three architectural candidates are now closed: exposure floor mechanically impossible (the gate is a VETO, not a deploy fraction), volatility harvesting measured negative in both flat years on our universe, trend gate refuted monotonically. THE HONEST CONCLUSION: within a long-only book in this universe the bear and sideways years are NOT tradeable by relaxing the trend gate, and the modest returns come from the book being tiny in EVERY year rather than from standing aside in bad ones. KEY DETAIL for what comes next: trend_soft 0.50 RAISED exposure (5.5% to 7.2%) and still lost - so HOW exposure is added matters more than how much.

**Experimentos.** `P01-exposure-floor` (done); `P05-trend-soft` (void); `P07-trend-soft-rerun` (done)

### A50-volatility-harvesting — DISRUPTIVE: harvest volatility by rebalancing - earn FROM chop in the years we currently sit out  ⭐
*information-theory/portfolio · system · critical · creada 2026-08-27*

**Por qué.** Shannon showed in 1961 that periodically rebalancing a volatile asset against cash converts variance into return even when the asset ends where it began. That is precisely the missing mechanism: our worst years are the sideways ones, and our entire defence there is to hold nothing, which bounds the worst year near zero. Rebalancing is long-only, needs no shorting and no new data, and it earns from the one thing those years reliably supply - volatility.

**Qué esperamos.** a small but positive return in 2022 and 2025 where the book is currently empty, lifting the worst year off zero without touching the bull years

**Cómo se prueba.** Add a rebalance_bars lever: every N bars, restore held names to equal target weight, trimming what rose and topping up what fell. Sweep N over daily (96), weekly (672) and monthly (2880) - NEVER per-bar, since fees are the known killer. Judge on 2022 and 2025 specifically, paired on the champion genome, and count the trades so the toll is visible. Queued as P02 in rnd/program.jsonl.

**Qué la mataría.** the 0.30% round trip eats the premium at every rebalancing frequency that is fast enough to capture it - which would be a real answer, not a failure, and would say the flat-book design is correct for a book paying these costs

**Resultado.** REFUTED BEFORE BUILDING, on our own data. Equal-weight basket simulated per year 2019-2025 with the real 0.30% round trip: positive in only 2 of 7 years; medians weekly -5.8%, monthly -4.5%, 5% band -2.2%; and NEGATIVE in both years that matter (2022 about -2%, 2025 -36% to -45%). Average pairwise correlation 0.47-0.69. The premium depends on DISPERSION - positions outgrowing one another and being trimmed - not on volatility alone; in a correlated basket with one persistent leader, rebalancing sells the leader to buy laggards, a drag rather than a harvest (worst case 2021, -175 points). The tolerance band was least-bad, matching the theory that move-based beats time-based under proportional costs, but least-bad is still negative. Cost: minutes of CPU instead of a lever, tests and GPU hours. P02 closed.

**Experimentos.** `P02-volatility-harvesting` (cancelled)

### A58-loosen-the-meta-filter — OPERATOR GOAL: more money EVERY year - so test loosening the filter that starves the thin ones  ⭐
*selection/opportunity · module · critical · creada 2026-08-28*

**Por qué.** The opportunity funnel shows the meta filter cutting 29,653 candidates to 155 in 2025 and 11,844 to 153 in 2022 - survival rates of 0.5% and 1.3%, against 60.6% in 2020. The thin years are thin because of OPPORTUNITY COUNT, not size: 34 and 44 round trips, where no amount of extra size creates a chance the filter refused. The champion runs the strictest margin the grid offers. And the selection law rewards the worst year, which a strict filter protects by trading less - so the law may be selecting a filter stricter than the operator's goal wants.

**Qué esperamos.** a looser margin admits far more trades, raising the thin years materially while costing something in the worst year and in drawdown - a trade-off curve for the operator rather than a single answer

**Cómo se prueba.** P13 sweeps meta_margin BELOW the values ever tried: 0.005 (baseline) against 0.0, -0.005 (accept a slightly negative expected net for many more trades) and off entirely. Judge on EVERY year but weight the thin ones - 2022, 2023, 2024, 2025 - and report trade count, drawdown and worst year alongside return, since drawdown is now an objective rather than a limit.

**Qué la mataría.** the extra trades are the ones the meta model correctly identified as losers, so returns fall as the filter loosens - which would confirm the filter is doing real work rather than merely hiding in cash, and would be a genuine answer

**Resultado.** REFUTED with a clean dose-response (control exact 0.0228, no inert arms). meta 0.0: -0.1369; meta -0.005: -0.2365 (stops 2023, 2024); meta off: -0.2481 (stops 2020, 2023, 2024, 2025). Every judged thin year worsens at every loosening except one noisy cell (2024 at margin 0.0). Exposure rises 5.49% -> 12.88% while returns collapse - the THIRD demonstration that more exposure via worse trades loses. The kill criterion fired exactly as written: the extra trades are the ones the meta model correctly identified as losers. The filter is not hiding in cash - it is the reason the thin years are positive at all. GENERATION is now the PROVEN constraint; the candidate stream itself must improve (P15 market features, then A53).

**Experimentos.** `P13-loosen-the-meta-filter` (done)

### A59-market-state-features — Let the net SEE the market: breadth, BTC state and cross-sectional rank as training features  ⭐
*generation/features · training · critical · creada 2026-08-28*

**Por qué.** All 44 features are per-symbol; the net cannot see the market it trades in, and every market-level judgment lives in filters applied AFTER it. Generation is the measured deep constraint - raw candidates lose money in 2022, 2023 and 2025 - and this is its cheapest credible upgrade. The meta filter's outsized value is itself evidence that market-conditional information matters; teaching it to the net directly attacks the cause instead of amputating the symptom.

**Qué esperamos.** the net differentiates its behaviour by market state, lifting candidate QUALITY in the thin years rather than candidate count alone - visible as raw-rule gross profit appearing in years where there is currently none

**Cómo se prueba.** A flag (market_features), never an edit to FEATURE_COLUMNS - the Standardizer pins the tuple so old models fail loudly, and a flag lets the test be PAIRED on one seed. Columns, all causal: breadth of the universe's trend bits, BTC return_20/trend, median cross-sectional natr, and the symbol's momentum rank in the universe. Build in features.py + pooled.py, test first, then a paired experiment. If it wins, A53 (regime-conditional labels) follows.

**Qué la mataría.** paired on the same seed, features-on does not beat features-off; or the market columns are so dominant the net collapses onto them and per-symbol discrimination degrades

**Resultado.** REFUTED at this dose by P15 (train_ab, 2 seeds). Mean delta -0.0106; seeds disagree (77101 -0.0267, 77102 +0.0056) - inside known seed variance, so read as NO EVIDENCE OF LIFT, clearly below the +0.0391 bar, not proof of harm. The decisive signature is absent: the thin years did not move (2022 -1.3pp, 2023 -0.7pp, 2025 +1.8pp). Reconciliation PASSED: baseline variant reproduced 0.0738/0.0724 vs the known 0.072/0.073 - the train_ab path measures what it claims. Market features stay in the codebase behind their off-by-default flag.

**Experimentos.** `P15-market-features` (done)

### A67-progressive-entries — Pyramiding: add to a position as it proves itself, never average down  ⭐
*money-management · code+training · critical · creada 2026-08-29*

**Por qué.** Operator (2026-08-29): do not commit everything at once; scale in as more positive signals arrive. Verified gap - orchestrator entries were gated on `s not in positions`, so a held name could never be topped up regardless of how strong its signal became. The existing `money_pyramid` lever is ACCOUNT-level deployment, not per-position scaling; the name collided with the concept but not with the behaviour (the fifth name-vs-behaviour instance in this project).

**Qué esperamos.** more capital deployed into the trends that are working, without raising the number of distinct bets - the opposite of the refuted 'more exposure via worse trades'

**Qué la mataría.** no lift on the held-out column, or drawdown rises faster than return

**Resultado.** BUILT: scale_in (tranches), scale_step (profit required since the last fill), scale_decay (geometric shrink). An add must clear the SAME bar as a fresh entry (conviction, veto, consensus) and the position must be IN PROFIT since its last fill - the single rule that separates pyramiding from averaging down. 7 tests including the explicit never-average-down case; suite 494. Off by default; measurement queued. || MEASURED AND REFUTED (P25, once the engine allowed the orders). Paired deltas: 1 tranche @0.55 -0.0157, 2 @0.55 -0.0243, 2 @0.45 -0.0230, drawdown 28.5% -> 34-36% in every arm. The per-year picture is the honest story: 2021 gains a spectacular +494pp, but 2019 loses 13.3pp (turning a POSITIVE year negative, -4.4%), 2020 loses 12.9pp, 2024 -5.5pp, 2025 -5.0pp, 2018 -4.5pp. It amplifies the moonshot and taxes everything else - the exact shape the judge was written to refuse. Mechanism: adding at +3% into a name whose conviction has already decayed buys the LATE part of a move, which is where the give-back lives; in a runaway year that is free money and in a normal year it is a worse average entry. The engine change stays (correct, opt-in, tested) and the lever stays off.

### A37-data-breadth — Widen the data: more symbols (~50) and richer features before bigger models
*data · data · high · creada 2026-08-25*

**Por qué.** The REAL frontier constraint is data, not model size: 14 symbols x 15m OHLCV is a small, homogeneous panel. The operator's horse-race idea explicitly assumes ~50 coins. More symbols = more cross-sectional signal (lead-lag, breadth, rotation), more training samples for the pooled oracle, and better generalization. Richer per-bar features (multi-timeframe aggregates, cross-asset relatives) feed every model incl. the tree voter.

**Qué esperamos.** stronger pooled nets + a much sharper horse-race/lead-lag signal; better sealed-2026 generalization

**Cómo se prueba.** Extend universe + backtester data download to top-N liquid USDT perps/spot with full 2017-2026 history; re-run prepare; keep the 14-coin universe as the control.

**Qué la mataría.** data quality/liquidity of added alts too poor (survivorship, gaps); training time explodes without gain

**Resultado.** REFUTED as a TRADING universe (the training question is still open). Same net, both arms, 2018-2025: narrow-14 score -0.0760 / worst -11.3% / CAGR +36.7% versus wide-35 score -0.1326 / worst -15.4% / CAGR +21.1%. Wide lost on every axis. Mechanism: a two-position book does not diversify across 35 candidates, it dilutes - more coins means more chances for a spurious high-conviction signal on a noisy late-listed name to displace a good pick. The 35-symbol dataset (research + forward, ~6GB) is built and cached, so the remaining question - TRAIN on 35, TRADE the 14 - can be answered cheaply whenever the GPU is free. universe.json keeps the 14.

### A40-train-wide-trade-narrow — Train on 35 symbols, TRADE the 14: more data for the net without diluting the book
*machine-learning/data · training · high · creada 2026-08-26*

**Por qué.** A37 refuted breadth as a TRADING universe (a two-position book dilutes across 35 candidates), but that experiment held the brain fixed, so it never tested whether more symbols make a BETTER net. A38 showed more data beats fresher data, which argues the pooled oracle should learn from as many swings as possible. Separating the two roles - learn from 35, trade the best-quality 14 - keeps the data benefit and drops the dilution.

**Qué esperamos.** a net trained on 2.5x the swings generalises better and lifts the per-year record on the SAME 14-symbol trading universe

**Cómo se prueba.** Train one net with the champion genome on universe_wide.json (data already cached), export signals for the 14 only, and run the per-year sweep with the TRUE champion config (meta_margin 0.0) against the narrow-trained champion. Needs the GPU, so run it in a training gap or accept contention. 2026 stays sealed.

**Qué la mataría.** the wide-trained net scores no better than the narrow-trained one on the 14-symbol per-year sweep

**Resultado.** REFUTED. The champion genome trained on 35 symbols (4.95M windows, val accuracy 72.5%) and trading only the 14 scored -0.1452 (worst -16.6%, CAGR +21.1%). Against the honest reference - recent fresh narrow-trained nets in the same config family, median -0.0815 - it is still about 0.06 worse, so more training symbols did not make a better net. Caveat: the wide net auto-tuned to min_hold 192 rather than 16. With A38 and A37 this exhausts the data thesis in all three directions: not fresher, not wider to trade, not wider to learn from.

### A46-progressive-entry-exit — Progressive entries and trailing exits: scale in while the signal strengthens, scale out like a trailing stop
*execution/market-microstructure · module · high · creada 2026-08-26*

**Por qué.** Operator idea (2026-08-26). Today entries and exits are all-or-nothing at band crossings. The operator proposes buying progressively on successive signals while a move develops, and selling in tranches - a trailing-stop-like partial liquidation. This decouples 'being right about direction' from 'being right about timing', and mechanically caps the damage of a full-size entry at a local top - one of the visible failure modes in bear-year cohorts.

**Qué esperamos.** lower MAE per position and a higher worst-year, at some cost to best-case years (late full size misses part of the move); net effect on the consistency score positive

**Cómo se prueba.** Add fractional position support to the backtest engine (currently 0/1 per slot). Entry: split target size into 2-3 tranches released by successive confirmations (prob still above band, trend intact, breadth improving). Exit: ratchet - after +X% move the exit band tightens, releasing tranches on the way down. Tests first (engine change touches the live path). A/B on research years against the champion. Note overlap with A45: A45 decides HOW MUCH in total, A46 decides the PATH in and out - build A46's engine support first since A45's partial exits need it.

**Qué la mataría.** 15m bars plus fees make tranching too expensive - more crossings of the fee threshold eat the benefit; or the band optimiser already captures the effect via min_hold

**Resultado.** REFUTED on all six variants in the fast-sim screen (champion signals + shipping config, research years, baseline pinned to the production sim at drift 0.00000). Baseline score -0.0839 (worst -10.3%, mean +19.3%, exposure 9.1%). T2 -0.1023 (mean +8.7%, trades +64%), T3 -0.0964 (mean +3.8%, trades +97%), trailing half-exit -0.1109 with a WORSE worst year (-12.6%), combos worse still. The kill criterion fired exactly as written: at 15m the 0.30% toll makes extra crossings ruinous, and tranching cuts exposure - the binding constraint - from 9.1% to 5.6-7.0%. The real-engine change (fractional positions in the shared backtester) is NOT justified and was not made. Partial exits may be revisited only through A45 if a learned model finds states where trimming has positive expectancy; as a mechanical rule this is dead.

### A60-label-with-the-real-exits — Triple-barrier labels using the book's OWN exits: a good entry = one that wins through OUR stops
*generation/labels · training · high · creada 2026-08-28*

**Por qué.** Generation is the proven constraint (P13), and labels are its other half beside features. Today's oracle labels mark perfect-hindsight swings with no reference to the path: an entry can be labelled good even if its route passes through an -8% dip that the SHIPPED book's stop-loss would have realised as a loss. So the net is trained to admire trades the strategy cannot actually hold. The triple-barrier literature says exactly this: label by which barrier the path hits FIRST - profit target, the real stop (8%), the real trail (12%), or time - so a positive label certifies survival of the risk machinery the book runs.

**Qué esperamos.** fewer but truer positive labels; the net's candidates stop dying on stops, raising per-trade expectancy - visible as raw-rule gross profit improving in the thin years, the one signature no filter or sizing change has produced

**Cómo se prueba.** New labeller beside oracle.holding_labels: walk each bar forward, first-touch of {+target, -stop 8%, trail 12% from running peak, vertical N bars} -> label. Wire as a train() flag like market_features (train_ab shape tests it paired). Build AFTER P15 reads out - if market features already lift generation, test the combination deliberately, never assume composition.

**Qué la mataría.** the stricter labels thin the positive class so much the net cannot learn (class imbalance), or the label change just reproduces what the meta filter already learns downstream - paired same-seed test decides

**Resultado.** REFUTED decisively by P16 (train_ab, 2 seeds, baseline reconciliation exact both seeds): mean -0.2318, seeds -0.0841/-0.2333, mandate stops 2018/2019, deep-dd flag. The labels were HONEST about tradability but WEAK about entry timing: path-survival approves any bar whose forward path banks 1pct before an 8pct dip - masses of mid-swing and sideways bars - diluting the start-of-swing signal the zigzag labels carry. Being right about WHAT survives is not the same as teaching WHERE to enter. Possible refinement (A60b, separate row if ever queued): raise min_gain to 5-10pct so only swing-sized survivals qualify, or intersect path-survival WITH swing-start. Not chased tonight - three generation hypotheses (filters P13, features P15, labels-v1 P16) are now measured losses; the discipline is to think before the next GPU bet. || A60b (P17, intersect labels) ALSO REFUTED: mean -0.1257, seeds -0.0812/-0.024, a 2018 mandate stop; baseline reconciliation exact for the fourth time. Even pruning ONLY the positives that die on our stops makes the net worse - the pruned dip-then-recover starts are apparently the very pattern the net needs to learn early-swing shapes, and the meta filter already handles their tradability downstream. THE LABEL WELL IS DRY: generous zigzag labels + downstream meta filter beat every label surgery tried.

### A61-seed-committee-confidence — Committee of same-architecture nets: agreement = confidence, sizing follows agreement
*decision-tree/sizing · training · high · creada 2026-08-28*

**Por qué.** The operator's decision-tree mandate (2026-08-28): very sure operations sized up, doubtful ones sized down or skipped, each entry questioned by an independent opinion. The tree already questions entries five ways (meta model, trend veto, breadth regime, momentum gate, stops), and A32 proved a DIFFERENT-discipline second voter inverts out of sample. The untried alternative is a committee of the SAME discipline: K nets trained from different seeds, whose DISAGREEMENT is a measured, honest uncertainty signal. Seed variance is currently pure noise we average over (4 seeds spread 0.074) - a committee turns that liability into a confidence channel: entries all K nets want, sized up; split votes, sized down via money-model composition; unanimous rejections never entered. Unlike A32 this adds no new inductive bias to invert - it reads the variance we already own.

**Qué esperamos.** committee-agreement sizing beats single-net sizing paired on the same seeds; visible as higher typical-year efficiency (gain per pp of drawdown), because doubtful trades shrink exactly where losses cluster

**Cómo se prueba.** Stage 1 (CPU, no training): take the per-seed signals.npz already produced by paired experiments, compute cross-net prob agreement per (symbol, bar), join against the champion trade map (p08_trades) - does agreement stratify realised per-trade PnL? Only if yes: stage 2 wires agreement as a size_mult channel (composes with money_model like every sizing module) and a train_ab-shaped paired test decides. After P15 - the GPU queue owns priority. REFINED (2026-08-29, deep-ensembles literature): the channel is cross-net VARIANCE of prob (epistemic uncertainty), continuous, not binary vote-counting; sizing downweights high-variance entries. Stage 1 stays: variance must stratify realised per-trade PnL on the champion trade map before any committee ships. Inference for K extra nets is minutes of GPU - slot between experiments; nets already exist in the _auto_ workdirs (P08/P14/P15 seeds).

**Qué la mataría.** agreement does not predict per-trade expectancy on the champion's own trade map (cheap CPU pre-test on existing per-seed signals BEFORE any committee training), or the K-net cost buys less than money_model 0.5 already delivers

**Resultado.** Stage-1 kill criterion FIRED, cheaply as designed (inference only, no training). 2-net committee (champion + P08-77101), all 3,329 champion trades matched to entry-bar prob variance: disagreement does NOT mark bad trades - it marks the BEST ones (Q4 disagreement +0.803pct/trade vs Q1 agreement +0.290; corr +0.061). Mechanism: cross-net variance is in practice a VOLATILITY proxy (A45 map: vol Q4-Q1 = +0.83pp, nearly identical), and the money model already monetises that axis. Downweighting high-variance entries would cut the best trades. Caveat recorded: 2 nets is the minimum committee; a wider one could read differently, but the axis it would trade on is already owned.

### A62-multi-timeframe-books — A second book on a different timeframe: a new candidate stream, not more trades from the old one
*generation/timeframes · training · high · creada 2026-08-28*

**Por qué.** Operator (2026-08-28): can we use other timeframes to operate more? The honest frame: 'operate more' from the SAME stream was refuted three times (P13, trend_soft, extra slots) - more exposure via worse trades loses. But a DIFFERENT timeframe is a different generation process: a 1h/4h trend book sees swings our 15m zigzag labels fragment, and a faster mean-reversion book (system 07's capitulation embryo) trades exactly the flat/bear tape where our trend stream produces nothing. The prize is not correlation-free volume but COMPLEMENTARY years: gross profit appearing in 2022/23/25, the signature no filter or sizing change has ever produced. Note 15m is only our DECISION cadence - features already span 1 day to 30 days and holds run days-weeks; the experiment is about a genuinely different label+cadence, not a knob.

**Qué esperamos.** a 1h-aggregated book (same architecture, same honest pipeline: own labels, own walk-forward meta, own money model) whose per-year profits are positive in at least one year where the 15m book's raw rule shows NO gross profit; capital split between books then lifts the consistency score above either alone

**Cómo se prueba.** Stage 1 (CPU): aggregate research 15m bars to 1h honestly (OHLCV resample, no peeking); rerun the RAW RULE per-year gross-profit map on 1h - if even the hindsight rule finds no gross profit in the thin years at 1h, the stream cannot help and we stop before GPU. Stage 2: train the standard pipeline on 1h (train_ab shape vs 15m baseline, ~4x fewer bars so cheaper than a 15m run). Stage 3 only on complementarity: two-book capital split measured per-year. After P15 in the GPU queue; stage 1 anytime on CPU.

**Qué la mataría.** the 1h book's profitable years merely duplicate the 15m book's (same regimes, correlated equity curves) - then it adds risk concentration, not coverage; or aggregated-bar training cannot reach positive expectancy at 1h costs at all

**Resultado.** KILLED AT STAGE 1, for the price of a resample - exactly as the gate was designed to do. Hindsight harvestable long material at the confirmed 3% leg size, engine costs charged: the 1h grid holds 70-78% of what the 15m grid holds, and the RATIO IS FLAT ACROSS EVERY YEAR (2018 0.72, 2019 0.76, 2020 0.73, 2021 0.70, 2022 0.77, 2023 0.78, 2024 0.75, 2025 0.76). The thin years are not thin because of the sampling grid - they are thin in the price itself, and a coarser grid inherits the same drought with strictly less material. There is no year where 1h is proportionally richer, which is the only thing that could have justified a second book on that timeframe. The kill criterion written when the idea was recorded fired precisely: 'if even the hindsight rule finds no gross profit in the thin years at 1h, the stream cannot help and we stop before GPU.'

### A70-onchain-activity — On-chain network activity as a second non-price input
*generation/new-information · data+code · high · creada 2026-08-31*

**Por qué.** The fear veto is the only lever that ever improved the held-out column, and it came from information that is not price. This mines the same seam: four free, long-history daily series from blockchain.info describing NETWORK USE rather than price - unique addresses, transactions, hash rate, miner revenue - each read as a deviation from its own trailing trend, because a level is not a signal.

**Qué esperamos.** an 'activity gate' - refuse new entries when on-chain activity is unusually weak for its own recent history - lifting the held-out median the way the fear veto did

**Qué la mataría.** the effect is a proxy for the fear index we already use (check the overlap before building), or it vanishes once the causal 4-day grid is respected in the channel

**Resultado.** Stage 1 PASSED on two of four, on the champion's 3,329 round trips with strictly-past values only. Unique addresses: Q1 +0.107%/trade at 39% win rising monotonically to Q4 +0.867% at 47% - a spread of +0.76pp, comparable to the Fear & Greed spread that produced the adopted veto. Miner revenue: +0.006% to +0.720%, spread +0.57pp, though not monotone (Q3 above Q4). Transactions (+0.05pp) and hash rate (+0.18pp) carry nothing. CAVEAT recorded: blockchain.info downsamples long histories to roughly one point every four days, so this is a slow signal measured on a coarse grid - fine for a regime-style gate, useless for timing. || STAGE 2 REFUTED (P27, control healthy at +0.0563). Every arm negative and dose-ordered by strictness: -1.0sd -0.1208, -0.5sd -0.1091, -1.5sd -0.0445, with exposure falling 7.88% -> 6.55-7.77%. The gate does exactly what it was built to do - it refuses entries on quiet-chain days - and those refusals cost far more than they save. So the trade map was right that quiet-chain days have worse AVERAGE outcomes, and wrong as a basis for a veto: the trades it removes include the ones the year depends on. This is the same lesson P13 taught from the opposite direction (loosening the filter also loses), and it sharpens the rule: a per-trade average is not a licence to remove trades, because the distribution's right tail is where the years live.

### A32-decision-tree-branches — Decision tree: probabilistic-stats + candlestick-shape branches (a 2nd directional voter)
*mathematics/statistics+pattern · model · medium · creada 2026-08-25*

**Por qué.** OPERATOR IDEA (revisit + extend). Grow the decision-tree idea with new branch types: (a) PROBABILISTIC statistics - conditional P(up | regime bucket, vol bucket, momentum bucket, day-of-cycle); (b) CANDLESTICK SHAPES of the prior N bars (engulfing, pin/hammer, inside bars, wick asymmetry). A gradient-boosted / shallow tree over these engineered features becomes a SECOND directional voter alongside the oracle-NN - which is exactly what A12 said consensus_k>1 needs to become useful.

**Qué esperamos.** a complementary directional signal + a real multi-voter consensus (unblocks consensus_k>=2)

**Cómo se prueba.** Engineer causal features (prob buckets + candlestick flags) -> train a small GBM/tree (CUDA optional) -> export a per-bar directional prob channel -> a Tree module that votes direction; combine with OracleNN via the existing consensus_k / weighted vote.

**Qué la mataría.** no out-of-sample edge / overfits the training era

**Resultado.** BUILT and MEASURED. Real independent edge in research: 2.22M purged walk-forward verdicts, P>0.55 -> +0.338% fwd-32-bar vs P<0.45 -> -0.028% (spread +0.365pp), monotonic deciles, positive in EVERY Hurst bucket and EVERY year 2020-2025. BUT it INVERTS in sealed 2026 (-0.174pp) in both Hurst buckets. NOT wired into the live grid: adding a known regime-fragile voter would manufacture a champion that looks excellent on 2018-2025 and inverts forward - precisely the failure the operator is reporting. Code, channel (tree.npz) and tests are kept and ready; wire it once the adaptivity work (A38) makes a voter track the current regime. TRANSPARENCY: this call was informed by the 2026 readout, used ONLY to be more conservative, never to optimize; 2026 is therefore no longer a pristine window for THIS voter. | REFUTED in a paired sweep on the champion genome: tree_weight 0.5 gives a paired delta of -0.0677 and turns the worst year negative (-1.3%/-1.0% against +4.5%/+3.8%), destroying the all-positive property; stacked with sizing it is still -0.0636. The channel truly engaged (100% bar overlap, inertness-checked). Mechanism: the orchestrator combines directional convictions as a WEIGHTED MEAN, so a voter whose probabilities sit near the middle drags the blend below the 0.75 entry band - arithmetic dilution, not a failure of the tree's skill. Revisit only as a gate/veto or with conviction on the oracle's scale, never as another term in the mean.

### A09-system07-mean-reversion — system 07 capitulation dip-buyer — REFUTED (aborts in bears)
*new-system · creada 2026-08-21*

**Por qué.** 14-symbol diversified test: all configs -11% to -20%, ALL hit the 25% mandate (stopped), win 43-54%, dying in the 2018 cascade. Diversification did not help: market-wide crashes (2018/2022/COVID) make all names capitulate together and keep falling, so the book buys the whole market down and aborts. The per-event edge (+3-5%/trade) does NOT survive sequential position management (falling knives). Dip-buying works in V-recoveries/bull-corrections, NOT sustained bears = system 06's weak spots -> not the complement hoped.

**Qué la mataría.** confirmed on BTC and 14-symbol; systemic falling-knife failure in sustained bears

**Resultado.** LOSS. system 07 SHELVED (code kept, tests pass; capitulation feature still valid). Diversification via a NEW STRATEGY TYPE that loses in bears cannot fill system 06's bear gaps.

### A15-longer-trend-fewer-bear-entries — Longer slow-trend filter (90d/120d) (REFUTED on BOTH criteria)
*model-arch · creada 2026-08-21*

**Por qué.** Tested the stashed 120d model. Rolling: 56/84 (67%) vs champion 70/84 (83%); worst cohort -23% vs -16%; median +14.5% vs +25.5%; best +101% vs +393%. Consistency (old ledger rows): 120d -0.14..-0.16, 90d -0.19 vs champion -0.0127. The longer trend MISSES the bull-recovery entries that create the winning cohorts, and still enters bears late enough to lose -> worse on everything.

**Qué la mataría.** confirmed on both consistency and rolling

**Resultado.** LOSS both criteria. Reverted search.json trend_span to [2880,5760] so the autoloop stops wasting iterations on 90d/120d. Third refutation: money/vol/longer-trend all hurt rolling because they reduce bull participation.

### A16-vol-target-bear-derisk — Volatility-targeted sizing to de-risk bear-entry cohorts (REFUTED)
*risk-lever · creada 2026-08-21*

**Por qué.** Tested: vol-targeting HURTS rolling reliability (champion 70/84 83% -> +vol 63/84 75%), deepens worst cohort (-16%->-19%), clips the bull (best +393%->+253%). Like breadth, a GLOBAL exposure cut sacrifices the recovery/bull that produces the winning cohorts.

**Qué la mataría.** confirmed: exposure-reduction levers lose more winners than they save losers

**Resultado.** LOSS. Removed the vol_scale grid row. Consolidated law: global exposure-reduction (breadth, vol-target) both LOWER rolling reliability. Fixes must change ENTRY SELECTION (A15 longer-trend) or act ONLY at bear entries, not cut exposure globally.

### A18-ensemble-of-champions — Ensemble-of-champions — WEAK (models' weak years overlap: crypto is one beta)
*model-arch · creada 2026-08-21*

**Por qué.** Cheap per-year blend of 45 distinct ledger configs: a 1/N blend of the top-2-by-worst-year keeps ~all-positive (worst +0.4% vs champion +0.5%) with slightly more CAGR (+30% vs +29%) — a wash on worst-year. Adding more configs raises CAGR (+33..37%) but reintroduces negative years (2022 -1% to -2%). Every config is weakest in 2022, so the weak years OVERLAP and calendar-year diversification barely smooths the floor (the A18 kill condition: single-beta crypto).

**Qué la mataría.** weak-years overlap -> marginal benefit only

**Resultado.** WEAK on the per-year proxy. A modest CAGR-only boost exists (top-2 blend +30% ~all-positive) but not a worst-year/rolling breakthrough; a heavy multi-signal rolling test isn't worth it after 5 refutations. Model-ensembling can't be promoted by the single-config autoloop anyway.

### A28-fear-greed-contrarian — Composite Fear&Greed emotional-state index, contrarian scaling at extremes
*psychology/behavioral-finance · module · creada 2026-08-24*

**Por qué.** Build a causal sentiment proxy from OHLCV alone (realized vol, momentum, breadth, distance-from-high, volume surge). At GREED extremes trim/hold entries (do not buy euphoria); at FEAR extremes upsize (buy capitulation). Behavioral-finance edge that directly protects the rolling cohorts that buy at greed peaks.

**Qué esperamos.** higher rolling 1yr win-rate by avoiding greed-peak entries and pressing fear lows

**Qué la mataría.** the composite adds no edge beyond capitulation + vol already tested

**Resultado.** REFUTED via champion rolling A/B: feargreed=0.5 rolling win-rate 68%->68% (no change), upside clipped (median +14.0%->+13.7%, best +524%->+455%), worst -17%->-16%. Contrarian trim costs upside without lifting the win-rate. Removed from the grid. Possible future refinement: press-fear-only (no greed trim) - but the win-rate was already unchanged, so low expected value.
