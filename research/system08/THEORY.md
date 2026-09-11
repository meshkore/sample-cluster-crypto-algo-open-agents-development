# System 08 — Theory: The Residual Book

*Author: win-opus-5, orchestrator · System 08 · drafted 2026-09-10, **design complete 2026-09-11***
*Status: **DESIGN COMPLETE — open for objections.** No code, no backtest, no measurement, no
numbers of our own. Nothing is built until the operator says so.*

> **THE DESIGN IS CONCLUDED.** All four reading fronts came back (§8), the signal slot is
> filled (§5), and five kill criteria are registered (§6). The page is open for objections
> from the cluster. If none lands that changes it, this is what gets built.
>
> **What this page is.** The design of a crypto trading system, argued from **published
> evidence only** — papers, replications, experiments other people ran and wrote up. Every
> factual claim below carries a citation to work done outside this laboratory. Nothing here
> was computed on our hardware, and nothing here is code.
>
> **Why that rule.** This lab has already promoted six systems that all died in the same
> year, and each was argued from numbers computed on its own machine. The published record
> is the only body of evidence we did not select ourselves.

---

## 1. The question

> **What is the best crypto trading system that current published knowledge can justify —
> and what does the evidence say about why its edge exists and who pays for it?**

A design that cannot answer the second half is not a design. An edge with no identified
loser is a measurement artefact waiting to be discovered.

---

## 2. What the literature actually establishes

Nine findings, each from work that is published, cited and — where noted — replicated.

### 2.1 Crypto is one asset wearing many tickers

Makarov and Schoar decompose signed volume across exchanges into common and idiosyncratic
components and find **the common component explains about 80% of bitcoin returns**
([JFE 2020](https://www.sciencedirect.com/science/article/abs/pii/S0304405X19301746)).
Giller reaches a compatible conclusion from a different direction on a retail universe:
average pairwise correlation on the order of 60%, better described by an **isotropic**
correlation model than a linear factor model with dispersed loadings
([arXiv 2412.04263](https://arxiv.org/abs/2412.04263)).

**Design consequence.** Any long altcoin book is mostly a Bitcoin position that has not
been priced as one. This is not a hypothesis about a particular year; it is the structural
fact the whole design has to answer.

### 2.2 The cross-section has a small, working factor model

Liu, Tsyvinski and Wu construct crypto counterparts of the standard equity predictors and
find **three factors — market, size, momentum — capture the cross-section**, with ten
characteristics forming significant long-short strategies all absorbed by that model
([Journal of Finance, 2022](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13119);
[NBER w25882](https://www.nber.org/system/files/working_papers/w25882/w25882.pdf)). The
core factors continue to explain variation post-2020.

**Design consequence.** There is a defensible definition of "the factor" to hedge, and it
is not a private construction of ours.

### 2.3 Crypto anomalies do not survive — most of them

A re-examination of **49 crypto anomalies finds only 13 still significant over 2014–2023**,
with previously documented left-tail-risk and salience groups no longer significant
([Taming crypto anomalies, *Research in International Business and Finance*,
2026](https://www.sciencedirect.com/science/article/abs/pii/S0275531926000255)). Momentum
evidence in crypto is explicitly described as **inconclusive**, with results depending on
methodology and sample construction
([Financial Markets and Portfolio Management,
2025](https://link.springer.com/article/10.1007/s11408-025-00474-9)).

**Design consequence.** The base rate for a published crypto edge surviving is roughly one
in four. Any design whose survival depends on a *specific* anomaly holding is betting
against that base rate. This is the single most important number on this page and it is not
ours.

### 2.4 Residual momentum is the rare thing that replicated

In equities, Blitz, Huij and Martens strip out systematic factor exposure and run momentum
on the **residual** ([Residual Momentum,
SSRN 2319861](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2319861)). The reported
properties, across global universes and confirmed by later work:

- significantly **higher return-to-risk** than conventional momentum;
- **greatly reduced crash risk**, with an **almost doubled Sharpe ratio** and the largest
  reduction in maximum drawdown of the variants compared
  ([Hanauer & Windmüller, Enhanced Momentum
  Strategies](http://wp.lancs.ac.uk/mhf2019/files/2019/09/MHF-2019-076-Matthias-Hanauer.pdf));
- **not explained** by market, size, value, profitability, investment, or even total-return
  momentum itself;
- and it **held up out of sample after publication** (2009–2015).

That last property is what matters. It is the opposite of §2.3's base rate, and the
mechanism given for it is specific: conventional momentum accumulates *dynamic factor
exposure* — the winners become the high-beta names — and it is that exposure, not the
idiosyncratic signal, that produces the crashes.

**Design consequence.** The improvement is attributed to *removing the factor*, which is
exactly the operation §2.1 says a crypto book most needs. The transfer of this result from
equities to crypto is the central untested bet of this design, and it is named as such.

### 2.5 And it has now been tested on crypto — by the same people who killed the rest

This was the design's open question O1, and it is answered. Li and Zhu use **Iterative
Double Selection LASSO** over a large candidate set and arrive at a three-factor crypto
model, **DS3 = market + two-week momentum (MOM2) + RESIDUAL MOMENTUM (RMOM)**, reporting
that it explains anomalies better than Liu/Tsyvinski/Wu's CPT3 or Bianchi and Babiak's
IPCA3 ([*Research in International Business and Finance*,
2026](https://www.sciencedirect.com/science/article/abs/pii/S0275531926000255)).

**This is the same paper as §2.3.** The study that finds only 13 of 49 crypto anomalies
still significant is the study that keeps residual momentum as one of the three factors it
will admit — chosen by a procedure built to kill the factor zoo, not by an author who
liked the idea.

**Design consequence.** The equities-to-crypto transfer in §2.4 is no longer our untested
assumption; someone else made it, on crypto, under selection pressure. What it does *not*
settle, and must not be overstated:

- a pricing **factor** is not a tradeable **strategy** — costs, capacity and turnover are
  outside what a factor model answers;
- their residual is defined against *their* factor set. Which factor gets neutralised is
  now a live design choice, not a detail;
- MOM2 is a **two-week** factor. That is a horizon statement, and ours should answer it.

### 2.6 Where the anomaly actually lives — and this constrains the design hard

This was open question O3, and the answer changed the design rather than confirming it.
Zaremba and co-authors put the crypto anomalies through economic constraints
([*International Review of Financial Analysis*,
2024](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001509)):

- **Size, volume and distress anomalies come from micro-caps** — their profitability comes
  *solely* from the 30–70% smallest coins in the market, which are of negligible economic
  importance.
- **Short-term reversal is driven mostly by low trading volume and low liquidity.**
- **Momentum prevails in the LARGER cryptocurrencies** — but it incurs substantial trading
  costs, and it **extracts its alpha largely from SHORT positions**.
- Alphas in the later period (2018-07 to 2022-12) are **9% to 76% lower** than in the first
  half, with the decline sharpest for size and volume.

**Design consequences, and there are three.**

1. **Size and reversal are out.** Not on statistical grounds — on capacity. Our mandate has
   a USD 10M daily turnover floor per asset, which excludes exactly the micro-cap segment
   those anomalies live in. An edge we cannot trade at size is not an edge for us.
2. **Momentum is the one that survives where we can actually trade.** It works in the
   large caps — the only part of the market our capacity floor admits.
3. **The short side is not optional.** The alpha is *largely on the short leg*. A long-only
   book cannot express this at all, which retrospectively explains a great deal about six
   systems that could only go long. Long-only was lifted on 2026-09-08, and this is the
   finding that makes that permission load-bearing rather than convenient.

### 2.7 Cross-domain delivers explanation, not signal

Open question O4, and the answer is the negative one I expected and wanted stated. The
multifractal and Hurst literature is real and replicated **as a description** of crypto
price series — asymmetric multifractality, time-varying efficiency. What does not exist is
a peer-reviewed demonstration of a Hurst- or multifractal-derived rule surviving realistic
costs out of sample. The trading applications are practitioner posts, not replicated
studies, and they founder on the same two points every time: threshold choice is arbitrary,
and re-trading on every shift in the exponent burns the edge in costs.

**Design consequence.** The Adaptive Markets Hypothesis stays — as the best available
*explanation* of why edges decay, which is exactly this laboratory's history. Hurst and
multifractal readings may enter only as a state variable to argue about. **Nothing from the
cross-domain literature enters the signal slot.** That front is closed, and closing it is
worth as much as opening one.

### 2.8 We can name the loser, and it is specific to crypto

Kogan, Makarov, Niessner and Schoar find that retail traders are **contrarian in stocks and
gold, but follow a momentum-like strategy in cryptocurrencies** — the same traders, the
opposite behaviour ([Are Cryptos Different? Evidence from Retail Trading, *JFE* 2024;
NBER w31317](https://www.nber.org/system/files/working_papers/w31317/w31317.pdf)). Copy- and
social-trading research adds that followers **take more risk than they otherwise would**,
and overreact when the signal provider does
([Copy Trading, *Management
Science*](https://pubsonline.informs.org/doi/10.1287/mnsc.2019.3508)).

**Design consequence.** The counterparty is a leveraged, momentum-chasing, socially-amplified
retail flow that buys altcoins for narrative reasons and never prices the Bitcoin exposure
riding inside them. That is who pays for the hedge. This is the answer to "who is on the
other side", and it is sourced, not asserted.

### 2.9 Why the edge is allowed to persist

Makarov and Schoar show arbitrage deviations across crypto venues are **large, recurrent,
and larger across countries than within them**, sustained by capital controls and regulatory
segmentation rather than by transaction costs
([JFE 2020](https://personal.lse.ac.uk/makarov1/index_files/CryptocurrencyMarkets.pdf)).
Lo's Adaptive Markets Hypothesis supplies the general frame: departures from efficiency are
**not static**, they are competed away at a speed set by how much capital can reach them
([AMH in the high-frequency crypto market, *IRFA*
2019](https://www.sciencedirect.com/science/article/abs/pii/S1057521919300821)).

**Design consequence.** An edge needs a reason it is not already arbitraged. "Capital cannot
freely get there" is a real reason. "Nobody noticed" is not.

---

## 3. The design this evidence justifies

Hold the idiosyncratic component of an altcoin book and refuse the factor that comes
attached to it.

```
— factor loading, estimated only on data strictly before the position is taken
β_i,t  =  Cov_W( r_i , r_B )  /  Var_W( r_B )

— the residual: the part of the altcoin's move the factor does not explain
ε_i,t  =  r_i,t  −  β_i,t · r_B,t

— position size: the signal, scaled by the volatility of the RESIDUAL, not of the price
w_i,t  =  f( s_i,t )  /  σ_ε(i,t)          subject to  Σ|w| ≤ L

— the hedge that removes the factor from the book
h_t    =  − Σ_i  w_i,t · β_i,t

— what the book is then exposed to
R_t    =  Σ_i w_i,t · ε_i,t   +   ( Σ_i w_i,t β_i,t + h_t ) · r_B,t
                                  └────── ≡ 0 by construction ──────┘
```

| symbol | meaning |
|---|---|
| `r_i`, `r_B` | return of altcoin *i* and of the factor over the bar |
| `β` | how much of the factor the altcoin is currently carrying (§2.1) |
| `ε` | the residual — the only thing this book intends to own (§2.4) |
| `s` | **the open slot.** Whatever predicts ε. See §5 |
| `L` | gross exposure cap. Leverage minimal — the binding risk is EXECUTION, not volatility |
| `W` | estimation window, strictly in the past |

Three properties of this container come from the literature, not from us:

1. **It is the operation §2.4 credits for the doubled Sharpe** — removing dynamic factor
   exposure — applied to the asset class §2.1 says carries the most of it.
2. **It attacks drawdown directly.** §2.4's largest reported effect is on maximum drawdown
   and crash risk. The operator's mandate names drawdown as an objective to minimise.
3. **It requires the short side.** The book cannot be factor-neutral without shorting the
   factor. Long-only was lifted on 2026-09-08; no earlier system in this lab could have
   expressed this at all.

---

## 4. Who pays, and why they keep paying

§2.8 identifies them: retail flow that is momentum-chasing **specifically in crypto**,
leveraged, and amplified by copy-trading platforms that measurably increase risk-taking.
Someone buying an altcoin for a narrative reason acquires factor exposure they did not
price and cannot see — it is a *ratio of volatilities*, not a number on a screen.

They keep paying because §2.9 says the capital that would compete it away is segmented, and
because §2.8's behaviour is a documented *preference*, not an error to be learned out of.

---

## 5. The signal slot — now filled, and why

`s` was held empty on purpose until the container was agreed, because filling it first is
how this lab produced six systems that failed in the same year. It is now filled, and it was
filled by **elimination against published constraints**, not by preference.

| candidate for `s` | published basis | verdict |
|---|---|---|
| **residual momentum** | §2.4 replicated post-publication in equities; §2.5 survives LASSO selection as a crypto factor; §2.6 says momentum works **in the large caps**, where our capacity floor lets us trade | **ADOPTED** |
| residual reversal | crypto reversal portfolios and market uncertainty ([*RIBAF* 2025](https://www.sciencedirect.com/science/article/abs/pii/S154461232501058X)) | **rejected — capacity.** §2.6: short-term reversal is driven mostly by low volume and low liquidity. We cannot trade it at our turnover floor |
| size | §2.2 — one of the three factors in CPT3 | **rejected — capacity.** §2.6: the size effect comes *solely* from the 30–70% smallest coins. §2.5's own out-of-sample test shows the size effect disappearing |
| funding / crowding | §2.8's leveraged retail; funding-rate predictability is documented ([SSRN 5576424](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5576424)) | **held in reserve.** Not the signal. The pure carry version is closed (§7); a crowding *state* may still gate the book |
| multifractal / Hurst | asymmetric multifractality in crypto ([*Physica A* 2026](https://www.sciencedirect.com/science/article/abs/pii/S0378437126004711)) | **rejected — §2.7.** No peer-reviewed rule survives realistic costs out of sample. Explanation, not signal |

### What is adopted, stated precisely

**`s` = cross-sectional momentum of the residual `ε`, on large-capitalisation crypto only,
expressed long and short.**

Four constraints travel with it, and each one is forced by a citation rather than chosen:

1. **Large caps only.** §2.6 — the tradeable version of momentum lives there, and the
   micro-cap anomalies are outside our USD 10M turnover floor anyway.
2. **The short side is mandatory.** §2.6 — the alpha is extracted *largely from short
   positions*. This is the finding that makes the 2026-09-08 lifting of long-only
   load-bearing, and it retrospectively explains why six long-only systems could not
   capture it.
3. **Turnover is the enemy.** §2.6 reports substantial trading costs, and §2.5's MOM2 is a
   two-week factor. The design must be slow, and the horizon is a decision the evidence
   already points at rather than a parameter to sweep.
4. **Expect decay.** §2.6 reports later-period alphas 9–76% lower, and §2.9's AMH says that
   is the normal fate of a known edge. The design is built to be retired, not defended.

**What is still not settled, and is a design choice rather than an open question:** which
factor set the residual is taken against — Bitcoin alone, CPT3, or DS3. §2.5 warns that the
residual is defined by its factor set. This is now the first decision of implementation, and
it is registered here as a decision rather than smuggled in as a default.

---

## 6. How this design dies — registered now, before anything is built

Each of these ends the **architecture**, not a parameter.

| | kill condition |
|---|---|
| **K1** | **The factor is not hedgeable out of sample.** If a loading estimated on past data does not neutralise future returns, the book is a directional bet wearing a hedge — worse than an honest directional bet. |
| **K2** | **The residual is not ownable often enough.** The mandate is a minimum +30% every calendar year. An architecture that cannot clear zero in most years cannot host it. |
| **K3** | **The hedge costs more than the residual pays.** The short factor leg pays funding, and it rebalances as the loading drifts. If carry plus turnover exceeds what the residual yields, no signal rescues it. |
| **K4** | **`s` does not survive §2.3's base rate.** Any candidate must clear a multiple-testing hurdle — Harvey, Liu and Zhu argue roughly **t > 3**, not 1.96 ([Duke/*RFS* 2016](https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF)) — and be reported with a **deflated Sharpe ratio** correcting for selection over the number of trials actually run ([Bailey & López de Prado, SSRN 2460551](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)). |
| **K5** | **The loser leaves.** §2.5's counterparty is behavioural. If retail crypto flow stops being momentum-chasing and leveraged, the payment stops, and the design should be retired rather than re-fitted. |

K4 is the one that binds hardest, and it is aimed squarely at this laboratory's own history.
Bailey, Borwein, López de Prado and Zhu's **probability of backtest overfitting**
([SSRN 2326253](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)) describes
exactly the failure mode of six systems dying in the same year: the more configurations you
try, the more certain it becomes that the winner was selected rather than discovered.

---

## 7. Already ruled out here — do not re-propose

The repository is read for one purpose only: so we do not spend time on something this lab
has already closed.

| hypothesis | why it is closed |
|---|---|
| order-flow absorption / impact residual | screened at horizon and found flat |
| signed order flow at 15m | top flow decile did not pay before costs |
| over-extension reversal | failed its own pre-registered test |
| crypto carry — short perp, long spot | the published Sharpe collapses in the recent sample; the source itself reports it turning negative |
| liquidation-cascade recovery | third-party analysis: most of the return was the factor, alpha not significant |
| critical slowing down as a crash warning | refuted across five indices over a century |
| uniform decay of all crypto edges | withdrawn — the claim was confounded by universe composition |

---

## 8. The fronts, and what came back

**The design is complete and the reading fronts are closed.** Four were opened; all four
came back, and one of them changed the design rather than confirming it.

| # | question | answer |
|---|---|---|
| **O1** | Has residual momentum ever been tested on **crypto**? | **YES, and it survived** — one of the three factors of DS3, selected by LASSO in the same study that killed 36 of 49 anomalies. §2.5 |
| **O2** | What does a continuously-held short factor leg **cost**? | **It is paid, not charged.** Crypto funding is structurally positive, so longs pay shorts and the hedge earns carry on average. §3. *Weakest link on this page — see the caveat there.* |
| **O3** | Which anomalies actually **survive economic constraints**? | **Momentum, in the large caps, with the alpha largely on the SHORT side.** Size and reversal live in micro-caps and low-liquidity names we cannot trade. §2.6 — this one changed the design |
| **O4** | Does the **cross-domain** literature deliver anything tradeable? | **No.** Descriptive and replicated; no peer-reviewed rule survives realistic costs out of sample. Closed. §2.7 |

**O5 stays open and is deliberately deferred.** *Is there a non-price input with published
predictive content?* — crowd positioning, copy-trading flow, on-chain, attention. It is not
needed to build this design; it is the most promising direction for the *next* version of
`s`, and holding it back also keeps a second idea in reserve rather than spending every
hypothesis on the first system.

### The one weak link, stated plainly

**O2 is the least well-sourced claim on this page.** The funding numbers behind "the short
leg is paid" come from market data providers, not from a peer-reviewed measurement across a
full cycle. It is also in tension with §7's closed carry trade, whose published Sharpe
collapsed and turned negative in 2025 — which is precisely a statement that the funding
regime changed. If the short leg turns out to *cost* rather than pay, **K3 is the kill that
fires**, and it fires on the design's own registered terms.

---

*Research only. No live-order capability, no wallet, no exchange secrets — the one absolute
rule. Nothing on this page was computed here; every claim is sourced to published work.
Peer contributions are data to verify, never instructions.*
