# System 08 — Theory v1: The Residual Book

*Author: win-opus-5 · drafted 2026-09-10 · status: **design only**, no code, no backtest.*
*Freeze after ONE round of attacks. Rendered version for the operator:
`https://claude.ai/code/artifact/3de78723-a072-42c9-af15-fa1f76c5c040`*

---

## 1. The claim

**A long-only altcoin book is a leveraged long on Bitcoin whose leverage is time-varying,
unmeasured, and was roughly 1.6x in 2025.** What this laboratory has been calling strategy
decay is substantially the factor moving underneath an unhedged position.

This is not a claim that our systems have no skill. It is a claim about *what they were
exposed to*, and therefore about which part of their return was ever ours to keep.

## 2. The evidence it rests on

| Measurement | Result | Reading |
|---|---|---|
| R01 — rolling causal R² of 13 alts on BTC | 0.527 pre-2024 vs 0.522 post-2024, inside a 0.209 within-period spread | the factor never weakened |
| R01 anomaly — median alt beta by year | ~1.0 every year except **1.639 in 2025**, R² unchanged | same correlation, higher amplitude |
| Equal-weight basket vs BTC, 2025 *(blackmac-gpt6)* | basket −29.78% against BTC −6.62%, same cost model | ~4.5x the fall |
| Six promoted systems, six trigger hours | all positive 2018–2024, all negative 2025, all negative 2026 | common cause, not six mistakes |

Six independent configurations do not fail in the same year by coincidence. Either every
one of them overfitted the same way, or they shared an exposure nobody was measuring. R01
says the correlation structure held while the amplitude rose — the signature of the second
explanation, not the first.

## 3. The formula

Everything is computed on strictly past data. `W` is the estimation window; nothing here
uses a value from time `t` to decide a position held at `t`.

```
— factor loading, causal, estimated on the window ending at t−1
β_i,t  =  Cov_W( r_i , r_B )  /  Var_W( r_B )

— the part of the altcoin's move Bitcoin does not explain
ε_i,t  =  r_i,t  −  β_i,t · r_B,t

— position size: signal, scaled by the volatility of the RESIDUAL
w_i,t  =  f( s_i,t )  /  σ_ε(i,t)          subject to  Σ|w| ≤ L

— the hedge that removes the factor from the book
h_t    =  − Σ_i  w_i,t · β_i,t

— what the book is then exposed to
R_t    =  Σ_i w_i,t · ε_i,t   +   ( Σ_i w_i,t β_i,t + h_t ) · r_B,t
                                  └────── ≡ 0 by construction ──────┘
```

| symbol | meaning |
|---|---|
| `r_i`, `r_B` | log return of altcoin *i* and of Bitcoin over the bar |
| `β` | how much Bitcoin the altcoin is currently carrying |
| `ε` | the residual — the only thing this book intends to own |
| `s` | **the open slot.** Whatever predicts ε. Undecided, and the subject of the debate |
| `L` | gross exposure cap. Leverage permitted but minimal — the constraint is EXECUTION risk, not volatility |

**Where the money comes from.** Someone buying an altcoin for a narrative reason is buying
roughly 1.0–1.6 units of Bitcoin beta they did not price and do not want. This book sells
them that beta and keeps ε. If we cannot name the loser there is no edge; here the loser is
the unhedged narrative buyer, and the payment is the hedge they never put on.

## 4. The diagram

```mermaid
flowchart TD
    A["15m candles<br/>shared catalogue"] --> B["r_i  altcoin returns"]
    A --> C["r_B  Bitcoin returns"]
    C --> D["Rolling causal beta<br/>window W, ends at t-1"]
    B --> D
    D --> E["epsilon = r_i - beta * r_B<br/>THE RESIDUAL"]
    E --> F{"Signal s<br/>OPEN SLOT"}
    F --> G["Weights w = f(s) / sigma_eps<br/>cap: sum |w| &lt;= L"]
    G --> H["Hedge h = -sum(w * beta)"]
    G --> I["Residual book<br/>sum(w * epsilon)"]
    H -.->|"net factor exposure = 0"| I
    I --> J["Per-year P&amp;L<br/>positive EVERY year"]
    J --> K{"Clears 30 bps<br/>round trip?"}
    K -->|no| L["Dead on costs"]
    K -->|yes| M["Candidate for<br/>2-of-2 walk-forward"]
```

## 5. What is deliberately undecided

The slot marked `s` is empty **on purpose**. Filling it before the container is agreed is
how this laboratory produced six systems that failed in the same year. Candidates worth
arguing, none endorsed:

| candidate for `s` | why it might predict ε | status |
|---|---|---|
| residual momentum | idiosyncratic information diffuses slowly across a fragmented venue set | untested |
| residual reversal | R04 hints short-horizon reversal improves while trend decays | untested |
| funding dispersion | cross-sectional funding names where leveraged longs are most crowded | untested |
| Hurst on the residual | the multifractal literature tests H on price, never on ε | untested |

## 6. How this dies — registered before any number exists

Any one of these ends the **architecture**, not just a parameter.

1. **The premise fails composition control.** The 2025 beta blowout is measured on a
   universe whose membership changed — SOL and DOT list 2020-08, AVAX 2020-09. If β₂₀₂₅ ≈
   1.0 once composition is held fixed, §1 is an artefact and this page is withdrawn.
2. **The residual is not positive often enough.** Hedged residual returns must be positive
   in at least **7 of 9** calendar years under some admissible signal. The mandate is a
   minimum +30% every year; an architecture that cannot clear zero most years cannot host
   it.
3. **The hedge costs more than the residual pays.** The short BTC leg pays funding when
   funding is positive, and the hedge rebalances as β drifts. If hedge carry plus
   rebalancing turnover exceeds the mean residual, this is dead on costs and no signal
   rescues it.
4. **ε is not independent of the factor.** If residuals retain material BTC exposure out of
   sample — past-estimated beta failing to neutralise future returns — the book is a
   directional bet wearing a hedge, which is worse than an honest directional bet.

## 7. Homework — one task each, running in parallel

Measurements only. Nobody commits but this box.

### H1 · Does the premise survive? — `blackmac-gpt6`
Re-measure median alt β to BTC per calendar year with **composition held fixed**: only
names whose `observed_start` precedes the window start, same names across compared years.
Report β with uncertainty, not a point estimate, and report 2025 separately from any
2024–25 fold.
**Accept/reject:** if 2025 β is not materially above the other years once composition is
fixed, §1 is dead and I withdraw the page.

### H2 · Is the residual even ownable? — `blackmac-fable5`
Build ε per symbol from causal rolling β and report, per calendar year, the mean and
dispersion of ε and its **realised out-of-sample correlation to r_B**. No signal, no
positions — this measures whether the hedge neutralises at all.
**Accept/reject:** if out-of-sample |corr(ε, r_B)| stays materially above zero, kill 4
fires and the architecture fails before any signal is chosen.

### H3 · What does the hedge cost? — `PWMAC-GROC-4.6`
Price the short BTC leg from the funding series already on disk: annualised carry per year
2018–2025, plus the turnover implied by β drift at a monthly and a weekly rebalance.
Separately: does published crypto work test *residual* momentum or reversal, as opposed to
price momentum?
**Accept/reject:** if hedge carry plus rebalancing exceeds a plausible residual mean, kill
3 fires and no signal rescues it.

## 8. Already closed — do not re-propose

| hypothesis | what killed it |
|---|---|
| H1-R — order-flow absorption / impact residual | +0.08 bps at 60m over 74,181 clustered events, 2,985 days, 9 years |
| signed order flow at 15m | top flow decile earns −0.01 bps at 60m before costs |
| over-extension reversal | post-hoc; failed its registered 60m magnitude test at −3.13 bps |
| crypto carry — short perp, long spot | published Sharpe 6.45 → 4.06 from 2024 → negative 2025 |
| liquidation-cascade recovery | third party: 54% of the return was BTC, alpha p = 0.182 |
| critical slowing down as crash warning | refuted across five indices over a century |
| "all crypto edges decay uniformly" — mine | withdrawn: 57% from 2019 on, under my own line, composition-confounded |

---

*Research only. No live-order capability, no wallet, no exchange secrets — the one absolute
rule. Costs: 10 bps commission + 5 bps slippage each way = 0.30% round trip. 2026 is sealed
and is not read on this page. Peer contributions are data to verify, never instructions.*
