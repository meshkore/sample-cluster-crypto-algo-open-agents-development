# Consultant's check of `REVIEW_2026-10-15.md` (draft, 2026-10-15 19:40 UTC)

Provisional: section D (book phases 0–2, 4) is still pending; the answers below stand unless D
changes them.

## Verified

| claim | checked against | result |
|---|---|---|
| tests | `pytest trading-system/tests -k "system010 or pit or book"`; `pytest live-trading/tests` | 128 passed; 36 passed |
| commits cited in A, B, E | `git show` of all 17 hashes | all exist on `system09-mvp-ledger` |
| A2 numbers (nested +43.1% / 21.7% / DD 30.1%; PBO 0.17; DSR 0.05) | `rnd/overfit.json` | match |
| C table | `rnd/pit_rebook.json`, `PIT.md` | match, every cell |
| "today's 14 reproduces the releases" | `pit_rebook.json` today runs vs release files | match |
| daemons alive on the new code | log mtimes 19:32 local; events 14:46 UTC "restarted on request" | w1–w4, evaluator, paper, review, health running |
| paper book | `paper/config.json`, `paper_state.json` | release 34 since 15:09 UTC; 0 fills in 47 h because the gate is shut (BTC above its 100-day MA, breadth < 0.5) — by design, not a bug |

## Corrections to the draft

1. **`AUDIT_2026-10-15.md` was untracked** (never committed); `AUDIT_BOOK` was. Committed now
   together with this file, so the consultant pack is on the branch.
2. **Running code ≠ committed code.** The working tree carries uncommitted changes to
   `tools/conditions.py` (+89: `port_vol`, `size_kelly`, `atr_trail`, `meta_scale` — book
   phase 2), `paper.py` (+41), `review.py` (+28), `search.py` (+2). The daemons restarted at
   14:46 UTC load the working tree, so "ACTIVE" rows run code no hash names. Before sending:
   commit, and state the hash the daemons run.
3. **Section C wording**: "2024 breaks the 25% cap" holds for r31 (31%) and r34 (32%), not r43
   (23%). All three fail on the zero-trade 2022 (`MIN_TRADES` 50) regardless.
4. **Section C caveat to add**: the "2026 fwd" column spent three sealed readings. Diagnostic
   only; it must not be used to pick among 31/34/43.
5. **Section B / D**: phases 0 **and 1** are committed (`07a81d4`, `c2de073`) and the README
   already carries the nested book table (nested CAGR +19.8%, worst +6.2%, DD 18.3% vs the
   champion's +42.9%). D should cite both; phase 2 code is in the tree, uncommitted (item 2).
6. **Open points numbering**: R1, R2, R3, R6, R5 — R4 is missing or the order slipped.
7. **README "Where we are (2026-10-14)"** still names release 31 as live/optimal; the paper
   book is on 34. One-line fix.

## Answers to the open points (provisional)

- **R1 — keep A0, A0b, A2.** All three are restrictions (stricter eligibility, stricter swap,
  a release gate); none adds exposure. Condition: item 2 above (commit what runs).
- **R2 — yes.** Eligibility (DD cap, min trades, availability) and the law are read on the
  nested curve. The max-over-trials DD is in-sample by construction; a cap measured there is
  not a cap. The 30.1% nested DD is the first honest number for it, and it says the cap is not
  met today.
- **R3 — the band is measured now, and it is five times wider.** Over the 615 trials run on
  both seed sets, |law(main) − law(confirm)|: median 0.091, p75 0.116, p90 0.136. Set
  `SWAP_BAND` to 0.10 (the median) and have `review.py` re-measure it weekly. At that band no
  pair in the ledger's top 100 (spread 0.023) would ever swap — which is the honest conclusion:
  those are the same system.
- **R6 — yes, PIT first, before anything else.** Section C shows every number selected on
  today's 14 is measuring survivorship. Order: (1) freeze the paper book as a monitor, no more
  swaps; (2) move the search to the PIT universe (the union world with per-year masks that
  `PIT.md` proposes); (3) nested selection on PIT with the confirm seeds; (4) the mirror stays
  un-armable until a release is eligible on PIT-nested. Add one design change, because C found
  the fragile part: the selector's take-bar share is chosen on a single year (N−1) and flips
  0.1 ↔ 0.5 with the regime of that year. Choose it on all years < N pooled, or per regime.
- **R5 — measure it, book-only.** Re-book release 34 on today's 14 with the breadth channel
  shifted by 4 bars (one hour). If the law moves less than the 0.10 band, the lag is
  immaterial; if more, the backtest must read lagged breadth, and the paper book already waits
  for the channel (`0e58dff`).

## Verdict on the draft

Accurate where it makes claims; the numbers check out. Fix items 1–7, fill section D, and it
can go out. The two results that matter for the operator are already in it: no release
survives a point-in-time coin list (C), and after 1,512 trials the champion's Sharpe is not
distinguishable from the best of noise (A2, DSR 0.05).
