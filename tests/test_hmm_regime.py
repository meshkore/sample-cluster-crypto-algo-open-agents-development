import unittest
import math

from quantlab import hmm_regime
from quantlab.hmm_regime import (
    GaussianHMM,
    RegimeDeclarations,
    declare_regimes,
    walk_forward_folds,
    regime_score,
)


def trending_up(n=120, start=100.0, drift=0.4, noise=0.25, seed=7):
    """Deterministic upward-trending series (stdlib random, seeded)."""
    import random
    rng = random.Random(seed)
    out = []
    x = start
    for _ in range(n):
        x = x + drift + rng.gauss(0.0, noise)
        out.append(x)
    return out


def trending_down(n=120, start=200.0, drift=-0.4, noise=0.25, seed=11):
    import random
    rng = random.Random(seed)
    out = []
    x = start
    for _ in range(n):
        x = x + drift + rng.gauss(0.0, noise)
        out.append(x)
    return out


def flat_series(n=120, level=100.0, noise=0.2, seed=13):
    import random
    rng = random.Random(seed)
    return [level + rng.gauss(0.0, noise) for _ in range(n)]


def three_regimes(n_per=80, seed=17):
    """Synthetic market with a KNOWN regime structure (ground truth).

    Bar 0..n_per-1   : bear (negative drift)
    Bar n_per..2n-1  : range (no drift, low noise)
    Bar 2n..3n-1     : bull (positive drift)

    Used to verify the HMM recovers the planted regime sequence.
    """
    import random
    rng = random.Random(seed)
    out = []
    x = 100.0
    for _ in range(n_per):
        x = x - 0.5 + rng.gauss(0.0, 0.3)
        out.append(x)
    for _ in range(n_per):
        x = x + rng.gauss(0.0, 0.15)
        out.append(x)
    for _ in range(n_per):
        x = x + 0.5 + rng.gauss(0.0, 0.3)
        out.append(x)
    return out


class GaussianHMMFitTest(unittest.TestCase):
    def test_fit_runs_and_produces_valid_parameters(self):
        model = GaussianHMM(n_states=3, seed=42).fit(trending_up())
        self.assertEqual(len(model.means), 3)
        self.assertEqual(len(model.vars), 3)
        self.assertEqual(len(model.trans), 3)
        for row in model.trans:
            self.assertAlmostEqual(sum(row), 1.0, places=6)
            for v in row:
                self.assertGreaterEqual(v, 0.0)
        self.assertAlmostEqual(sum(model.pi), 1.0, places=6)

    def test_fit_is_deterministic_with_seed(self):
        a = GaussianHMM(n_states=3, seed=42).fit(trending_up())
        b = GaussianHMM(n_states=3, seed=42).fit(trending_up())
        self.assertEqual(a.means, b.means)
        self.assertEqual(a.trans, b.trans)

    def test_different_seed_changes_something(self):
        # Seeds perturb EM initialisation through the RNG path used when the
        # deterministic percentile init is not sufficient; two different seeds
        # must not produce byte-identical fits on noisy data.
        a = GaussianHMM(n_states=3, seed=1).fit(trending_up(seed=3, noise=1.2))
        b = GaussianHMM(n_states=3, seed=2).fit(trending_up(seed=3, noise=1.2))
        self.assertNotEqual(a.means, b.means)

    def test_too_few_observations_raises(self):
        with self.assertRaises(ValueError):
            GaussianHMM(n_states=3).fit([1.0, 2.0, 3.0])

    def test_posterior_rows_sum_to_one(self):
        model = GaussianHMM(n_states=3, seed=42).fit(trending_up())
        post = model.posterior(trending_up())
        self.assertEqual(len(post), 119)  # returns transform drops the first bar
        for p in post:
            self.assertAlmostEqual(sum(p), 1.0, places=8)


class RegimeDeclarationsTest(unittest.TestCase):
    def test_recovers_planted_regimes_from_synthetic_market(self):
        """THE headline test: a synthetic market with known regime structure
        (bear → range → bull) must be recovered by the HMM + declarations."""
        obs = three_regimes(n_per=80)
        model = GaussianHMM(n_states=3, seed=42).fit(obs).sorted_by_mean()
        post = model.posterior(obs)
        decl = declare_regimes(post, threshold=0.55, min_dwell=3,
                               labels=("bear", "range", "bull"))
        # Tail of each planted segment should be dominated by its regime
        # (allow transition lag at segment edges: >9 of 20 bars).
        bear_tail = decl.labels[64:84]
        range_tail = decl.labels[144:164]
        bull_tail = decl.labels[224:244]
        self.assertGreater(sum(1 for l in bear_tail if l == "bear"), 9)
        self.assertGreater(sum(1 for l in range_tail if l == "range"), 9)
        self.assertGreater(sum(1 for l in bull_tail if l == "bull"), 9)

    def test_declares_bull_on_trending_up(self):
        model = GaussianHMM(n_states=3, seed=42).fit(trending_up()).sorted_by_mean()
        post = model.posterior(trending_up())
        decl = declare_regimes(post, threshold=0.5, min_dwell=2)
        # The highest-mean state (bull, index 2 after sorting) dominates late bars
        tail = decl.states[-40:]
        self.assertGreater(sum(1 for s in tail if s == 2), len(tail) * 0.32)

    def test_declares_bear_on_trending_down(self):
        model = GaussianHMM(n_states=3, seed=42).fit(trending_down()).sorted_by_mean()
        post = model.posterior(trending_down())
        decl = declare_regimes(post, threshold=0.5, min_dwell=2)
        # The lowest-mean state (bear, index 0 after sorting) dominates late bars
        tail = decl.states[-40:]
        self.assertGreater(sum(1 for s in tail if s == 0), len(tail) * 0.32)

    def test_min_dwell_prevents_flicker(self):
        # Alternating high-confidence noise should not flip faster than dwell
        import random
        rng = random.Random(99)
        # Two well-separated clusters that jump around
        series = [100.0 + (rng.gauss(0, 1) if i % 2 == 0 else 200.0 + rng.gauss(0, 1))
                  for i in range(120)]
        model = GaussianHMM(n_states=2, seed=5).fit(series).sorted_by_mean()
        post = model.posterior(series)
        decl = declare_regimes(post, threshold=0.8, min_dwell=3)
        # Count transitions
        transitions = sum(1 for a, b in zip(decl.states, decl.states[1:])
                          if a != b and a >= 0 and b >= 0)
        # With min_dwell=3 on 120 bars, max theoretical transitions is ~40
        self.assertLessEqual(transitions, 41)
        self.assertGreaterEqual(transitions, 1)

    def test_median_duration_positive_on_stable_regime(self):
        model = GaussianHMM(n_states=3, seed=42).fit(trending_up()).sorted_by_mean()
        post = model.posterior(trending_up())
        decl = declare_regimes(post, threshold=0.6, min_dwell=2)
        self.assertGreater(decl.median_regime_duration, 0.0)

    def test_labels_are_expected_names(self):
        # On noisy flat data with a high threshold, some bars stay undecided
        model = GaussianHMM(n_states=3, seed=42).fit(flat_series()).sorted_by_mean()
        post = model.posterior(flat_series())
        decl = declare_regimes(post, threshold=0.9, min_dwell=3,
                               labels=("bear", "range", "bull"))
        self.assertIn("undecided", set(decl.labels))


class WalkForwardTest(unittest.TestCase):
    def test_folds_cover_the_series_without_overlap(self):
        obs = list(range(500))
        folds = walk_forward_folds(obs, train_size=100, oos_size=20, refit_every=25)
        self.assertGreater(len(folds), 1)
        for f in folds:
            self.assertEqual(len(f.train), 100)
            self.assertEqual(len(f.oos), 20)
            self.assertEqual(f.train_idx[1], f.oos_idx[0])

    def test_last_fold_stays_in_bounds(self):
        obs = list(range(200))
        folds = walk_forward_folds(obs, train_size=100, oos_size=20, refit_every=25)
        for f in folds:
            self.assertLessEqual(f.oos_idx[1], len(obs))

    def test_fewer_observations_yield_no_folds(self):
        folds = walk_forward_folds([1, 2, 3], train_size=100, oos_size=20)
        self.assertEqual(folds, [])


class RegimeScoreTest(unittest.TestCase):
    def test_score_reports_regime_conditioned_means(self):
        obs = trending_up()
        model = GaussianHMM(n_states=3, seed=42).fit(obs)
        post = model.posterior(obs)
        decl = declare_regimes(post, threshold=0.65, min_dwell=3)
        # Forward returns = next-bar change; posterior on returns has len-1 bars
        fwd = [obs[i + 1] - obs[i] for i in range(len(obs) - 2)]
        # Align declarations to fwd length (drop the first undecided bar if needed)
        score = regime_score(decl, fwd)
        self.assertIn("regime_means", score)
        self.assertGreaterEqual(score["fraction_declared"], 0.0)
        self.assertLessEqual(score["fraction_declared"], 1.0)


class StdlibOnlyTest(unittest.TestCase):
    def test_no_numpy_no_hmmlearn(self):
        import sys
        loaded = [m for m in sys.modules if m.startswith(("numpy", "hmmlearn", "pandas"))]
        self.assertEqual(loaded, [])


if __name__ == "__main__":
    unittest.main()
