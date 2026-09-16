# System 08 — The Residual Book

*Opened 2026-09-08 · designed from the published record 2026-09-10/11 · first
implementation 2026-09-11 · **CLOSED by the operator 2026-09-14**.*

> **This system is finished and will not be restarted.** It made money in eight of eight
> research years and lost 26.1% in the sealed 2026 because the ranking inverted, and a
> bootstrap of its own annual distribution then showed the +30%-every-year mandate was
> never reachable — `P(year >= +30%) = 43.9%` even in the regime where it works.
>
> **Read `research/system08/POSTMORTEM.md` before designing any new strategy.** It carries
> the fifteen refuted ideas so none of them is proposed again, and six lessons that are not
> about this system. The most important: bootstrap the annual-return distribution and read
> `P(year >= target)` BEFORE building, not after. Ninety seconds of computation would have
> closed this project in week one.
>
> What survives and belongs to the laboratory rather than to System 08: the realistic
> execution model (`execution.py`), the deflated Sharpe (`stats.py`), and the walk-forward,
> placebo, capacity, signal-comparison and feasibility harnesses in
> `research/system08/experiments/`. Reuse them. The refusals recorded against the champion
> in `system006_oracle_net_15m/docs/SUMMARY.md` still stand alongside these.*

## 1. Hypothesis

**A crypto book that hedges out the common factor and holds only the residual, sized by
cross-sectional momentum of that residual, earns where an unhedged book does not — because
the factor is most of what an unhedged crypto book owns, and the residual is where the
idiosyncratic information lives.**

The hypothesis was not invented here. It was assembled from published work, deliberately,
because six systems from this laboratory were each argued from numbers computed on this
hardware and all six died in the same forward year.

- Crypto is one asset wearing many tickers: the common component explains about 80% of
  bitcoin returns (Makarov & Schoar, *JFE* 2020).
- In equities, running momentum on the residual after removing factor exposure nearly
  doubles the Sharpe, cuts crash risk, gives the largest drawdown reduction of the
  variants compared, and **held up out of sample after publication** (Blitz, Huij &
  Martens).
- It survives on crypto too: residual momentum is one of three factors in Li & Zhu's DS3,
  selected by double-selection LASSO — **in the same study that finds only 13 of 49 crypto
  anomalies still significant**.
- The loser is named and crypto-specific: retail traders are contrarian in stocks and gold
  but **momentum-chasing in crypto** (Kogan, Makarov, Niessner & Schoar, *JFE* 2024),
  leveraged and amplified by copy-trading platforms.
- The edge is allowed to persist because arbitrage capital is segmented by capital
  controls and regulation (Makarov & Schoar).

Full argument, with every citation: `research/system08/THEORY.md`.

## 2. What it is

Daily bars derived from the shared 15m catalogue, on the frozen universe — 14 symbols,
already screened at a USD 10M daily turnover floor.

    β_i,t  =  Cov_W(r_i, r_B) / Var_W(r_B)      window ends STRICTLY before t
    ε_i,t  =  r_i,t − β_i,t · r_B,t             the residual, the only thing owned
    s_i,t  =  compounded ε over 28 days, skipping the most recent day
    w_i,t  =  ±(gross/2) · (1/σ_ε) normalised within each leg
    h_t    =  −Σ w_i,t · β_i,t                  the factor leg that cancels the rest

Rank the cross-section every 14 days; long the top third, short the bottom third; size by
inverse residual volatility; equal gross per leg; gross capped at 1.0 **every day**.

Four constraints are forced by citations rather than chosen, and each is enforced in code:
large caps only (`require_screened_universe` raises if the floor is widened); the short
side is mandatory (the published alpha is largely on it); turnover is the enemy (two-week
horizon, from the only crypto momentum factor that survived selection); and decay is
expected (later-period alphas run 9–76% lower).

## 3. What helped

- **Enforcing the gross cap every day rather than only at rebalances.** The first run
  applied it at rebalances only; drift carried gross exposure to **2.67x on a 1.0 cap**
  and the book spent its worst nine days there. Fixing it — which is implementing the
  design as written, not tuning — moved total return 400% → 512%, max drawdown 64.5% →
  48.8%, Sharpe 0.66 → 0.78, and positive years 5 → 6 of 9.
- **The funding leg paid, as the design predicted.** The book RECEIVED +26,042 over the
  research period. O2's claim — that a sustained short leg in crypto is paid rather than
  charged — is confirmed on our own tape. **Kill criterion K3 did not fire.**
- **The hedge held.** Net exposure averaged +0.036 with a standard deviation of 0.141
  against a gross of ~0.90. The book is close to factor-neutral, which is what K1 asked.
- **Refusing to trade a residual that is not there.** A minimum residual-share floor was
  added after a test built a world with no residual and the book took a position in
  rounding error — inverse-volatility sizing hands a near-zero residual a near-infinite
  weight.

## 4. What hurt

- **It does not clear its own statistical bar, and that is the headline.** t = 2.24
  against the Harvey–Liu–Zhu hurdle of **t > 3**. The design registered that hurdle before
  any code existed precisely so this result could not be talked past.
- **Six of nine calendar years positive, not nine.** The mandate is a minimum +30% every
  year. 2018 (−7.4%) and 2022 (−3.7%) are losses, and 2024 (+7.6%) is far below the bar.
- **Max drawdown 48.8%.** Drawdown is an objective to minimise. This is not close.
- **Costs are material:** 122,578 on a 100,000 starting book across 196 rebalances. The
  two-week horizon was chosen to keep turnover down and it is still the second-largest
  line in the account.

## 5. What is still open

- **Which factor set the residual is taken against.** BTC alone today. The published
  three-factor models (CPT3, DS3) are the alternative, and Li & Zhu warn that the residual
  is defined by its factor set. Registered as the first decision of implementation rather
  than smuggled in as a default — and it is the first thing to try, since it changes what
  "idiosyncratic" means rather than tuning a number.
- **Whether anyone has TRADED residual momentum on crypto after costs.** DS3 shows it
  prices the cross-section; that is not the same claim. Still unanswered in the
  literature.
- **O5 — non-price inputs.** Crowd positioning, copy-trading flow, on-chain, attention.
  Deliberately deferred so that a second hypothesis is held in reserve rather than every
  idea being spent on the first system.
- **The 2018 and 2022 losses.** Both are crypto winters. Whether a state variable can
  stand the book aside in them without becoming another fitted parameter is open.

## 6. Rules learned

- **A constraint stated in a formula must be enforced on every bar, not at every
  decision.** "Subject to Σ|w| ≤ L" applied only at rebalances let the book lever itself
  to 2.67x simply by holding winners. The gap between a design's words and its
  implementation is where the drawdown lived.
- **Inverse-volatility sizing needs a floor on the denominator.** A name that tracks the
  factor almost exactly has no residual to own, and its measured residual is estimation
  noise — which attracts the largest position in the book. Caught by a test that built a
  world with no residual and expected the system to stand aside. It did not.
- **Declare the number of trials before reporting a Sharpe.** `deflated_sharpe` refuses to
  default `trials`. Every configuration tried from here on must be counted, because the
  count is what the result is deflated against, and understating it is the specific lie
  the six dead systems were built on.
- **A first run that fails its registered bar is information, not a setback.** The
  temptation is to sweep until it passes. That sweep is precisely what the deflated Sharpe
  exists to punish, and it is how this laboratory produced six systems that were positive
  in research and negative in the same forward year.
- **2026 was not read.** The catalogue's lock is structural: `research()` cannot return a
  sealed bar. No part of this result touches the forward year.
