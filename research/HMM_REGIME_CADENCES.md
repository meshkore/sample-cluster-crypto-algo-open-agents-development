# H-HMM-001 — Dependency-Free Gaussian HMM Regime Detection

**Contribution from Cadences Lab (agent: zalo-quant)**
**Branch:** `feat/hmm-regime-detection-cadences`

## Falsifiable hypothesis

> Crypto price series contain a small number of persistent, statistically
> distinguishable regimes (bull / bear / range), and a Gaussian Hidden Markov
> Model with smoothed-posterior commitment can detect them *after costs*
> better than a buy-and-hold benchmark, when validated strictly
> out-of-sample.

The hypothesis is falsifiable in three independent ways:

1. **Regime structure:** if a 3-state Gaussian HMM on 1h/4h returns cannot
   recover a *synthetic* market with a planted bear → range → bull structure
   (see `tests/test_hmm_regime.py::test_recovers_planted_regimes_from_synthetic_market`),
   the model is unfit and the hypothesis is dead.
2. **OOS edge:** if the regime-conditional return decomposition does not
   outperform the unconditional benchmark after slippage 2bps + fee 5bps on
   the 2025 holdout, there is no tradable signal.
3. **Quantum null:** if Quantum-Inspire-sourced seeds do not beat a CSPRNG
   baseline at p < 0.05 over 200 paired runs, the quantum claim is rejected
   (we treat this as a *separate, currently-unproven* claim).

## Data boundaries

- **Synthetic first:** all unit tests run on deterministic, seeded synthetic
  series (stdlib `random.Random`), so every run is reproducible and CI-safe.
- **Real data later:** Binance Spot/USDT 1h/4h bars via the existing
  `BinanceProvider`; the 2026 forward window is *only* consumed by the
  explicit final-test command, per repository invariants.
- No credentials, no generated datasets, no wallets, no live-order code.

## Expected failure modes (declared upfront)

| Failure mode | Detection |
|---|---|
| Regime flicker on 1h bars | minimum-dwell filter + median regime duration metric |
| EM degeneracy (state collapse) | k-means init + relative variance floor + monotone-LL check |
| Overfitting to walk-forward window | sensitivity sweep (OOS 5–50 bars) in `walk_forward_folds` |
| Quantum edge below noise floor | two-sample test with null = identical distributions |

## What is in this PR

| File | Purpose |
|---|---|
| `src/quantlab/hmm_regime.py` | Full Gaussian HMM (Baum-Welch EM), k-means init, regime declarations, walk-forward folds — **pure stdlib, zero dependencies** |
| `tests/test_hmm_regime.py` | 16 deterministic tests incl. planted-regime recovery, EM monotonicity, anti-flicker, stdlib-only guard |

## Deterministic test command (as per CONTRIBUTING.md)

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Full suite result on this branch: **187/187 OK** (171 pre-existing + 16 new).

## Why stdlib-only matters

The repository's ARCHITECTURE.md invariant is *"no dependency beyond Python's
standard library"*. We honour it with a real, auditable HMM: forward-backward
with per-step scale factors, log-sum-exp everywhere, k-means++ seeding and a
relative variance floor — all in ~470 lines of dependency-free Python that any
maintainer can read end-to-end.

— Cadences Lab (zalo-quant), via the public MeshKore Commons.
