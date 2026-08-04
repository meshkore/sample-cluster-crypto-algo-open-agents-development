#!/usr/bin/env python3
"""Falsification test: is the HMM regime or just volatility?

Compares HMM state labels against a dumb `realized_vol > median` binary
split on a synthetic series where bull and bear have IDENTICAL volatility
but opposite means — the case that separates a regime model from a vol
detector.
"""
import math
import random
import sys

sys.path.insert(0, "src")
from quantlab.hmm_regime import GaussianHMM, declare_regimes


def three_regimes(n_per=80, seed=17, bull_vol=0.30, bear_vol=0.30):
    """bear (-0.5, vol=bear_vol) -> range (0, 0.15) -> bull (+0.5, vol=bull_vol)."""
    rng = random.Random(seed)
    out = []
    x = 100.0
    for _ in range(n_per):
        x = x - 0.5 + rng.gauss(0.0, bear_vol)
        out.append(x)
    for _ in range(n_per):
        x = x + rng.gauss(0.0, 0.15)
        out.append(x)
    for _ in range(n_per):
        x = x + 0.5 + rng.gauss(0.0, bull_vol)
        out.append(x)
    return out


def realized_vol(returns, window=20):
    vols = []
    for i in range(len(returns)):
        lo = max(0, i - window + 1)
        chunk = returns[lo : i + 1]
        if len(chunk) < 5:
            vols.append(0.0)
            continue
        m = sum(chunk) / len(chunk)
        v = math.sqrt(sum((x - m) ** 2 for x in chunk) / (len(chunk) - 1))
        vols.append(v)
    return vols


def main():
    obs = three_regimes()
    n_per = 80
    returns = [obs[i + 1] - obs[i] for i in range(len(obs) - 1)]
    # Ground truth per RETURN index: 0=bear, 1=range, 2=bull
    truth = [0] * (n_per - 1) + [1] * n_per + [2] * n_per

    # --- HMM ---
    model = GaussianHMM(n_states=3, seed=42).fit(obs).sorted_by_mean()
    post = model.posterior(obs)
    decl = declare_regimes(post, threshold=0.55, min_dwell=3)
    hmm_labels = decl.states  # aligned to returns (len == len(returns))

    # --- Dumb vol split ---
    vols = realized_vol(returns)
    median_vol = sorted(vols)[len(vols) // 2]
    # 'high vol' = 1: predicts 'non-range' (bear or bull)
    vol_split = [1 if v > median_vol else 0 for v in vols]

    # --- Accuracy on the discriminative question ---
    # The question: can each method tell bull vs bear apart (both high-vol)?
    bull_bear_idx = [i for i in range(len(truth)) if truth[i] in (0, 2)]
    hmm_correct_bb = sum(
        1 for i in bull_bear_idx
        if (hmm_labels[i] == 2 and truth[i] == 2)
        or (hmm_labels[i] == 0 and truth[i] == 0)
    )
    # vol split can only say 'high vol' for both -> it cannot separate them
    vol_correct_bb = sum(
        1 for i in bull_bear_idx
        if (vol_split[i] == 1 and truth[i] in (0, 2))  # guesses 'non-range'
    )
    # but that's not discrimination: bull vs bear both get the SAME label
    vol_separates = sum(
        1 for i in bull_bear_idx
        if (vol_split[i] == 1 and truth[i] == 2)  # bull = high vol
        or (vol_split[i] == 0 and truth[i] == 0)  # bear = low vol (wrong direction)
    )

    print("=== FALSIFICATION TEST: HMM vs realized_vol split ===")
    print(f"Series: bear(-0.5, vol=0.30) -> range(0, vol=0.15) -> bull(+0.5, vol=0.30)")
    print(f"Bull and bear have IDENTICAL volatility; only the mean differs.\n")
    print(f"HMM means: {[round(m, 3) for m in model.means]}")
    print(f"HMM vars : {[round(v, 3) for v in model.vars]}")
    print(f"Median realized vol: {round(median_vol, 4)}\n")

    bb = len(bull_bear_idx)
    print(f"Bull+bear bars: {bb}")
    print(f"  HMM  bull/bear discrimination: {hmm_correct_bb}/{bb} = "
          f"{100 * hmm_correct_bb / bb:.1f}%")
    print(f"  VOL  'high vol' guess (both same label): {vol_correct_bb}/{bb} = "
          f"{100 * vol_correct_bb / bb:.1f}%  <- cannot separate")
    print(f"  VOL  actual separation (bull=1, bear=0): {vol_separates}/{bb} = "
          f"{100 * vol_separates / bb:.1f}%  <- pure chance on same-vol pair")

    # Full-series accuracy vs planted truth
    hmm_all = sum(1 for i in range(len(truth)) if hmm_labels[i] == truth[i])
    print(f"\nFull 3-regime accuracy: HMM {hmm_all}/{len(truth)} = "
          f"{100 * hmm_all / len(truth):.1f}%")
    # distribution of vol per true regime (proves same vol in bull/bear)
    import collections
    vol_by_regime = collections.defaultdict(list)
    for i, t in enumerate(truth):
        if i < len(vols):
            vol_by_regime[t].append(vols[i])
    for t, name in [(0, "bear"), (1, "range"), (2, "bull")]:
        vv = vol_by_regime[t]
        if vv:
            print(f"  mean realized vol in {name}: {sum(vv)/len(vv):.4f} (n={len(vv)})")


if __name__ == "__main__":
    main()
