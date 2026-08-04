"""hmm_regime.py — Dependency-free Gaussian Hidden Markov Model for market regimes.

Contribution from Cadences Lab (zalo-quant). Pure Python standard library:
no numpy, no hmmlearn, no external dependencies — the whole repository is
stdlib-only by design (see ARCHITECTURE.md invariants), so this module keeps
that contract while providing a real, tested Gaussian-HMM regime detector.

Implements:
  * Categorical-state Gaussian HMM via Expectation-Maximisation
    (forward-backward / Baum-Welch with diagonal covariance).
  * Smoothed posterior commitment: a regime is *declared* only when the
    filtered probability exceeds a threshold (default 0.65) instead of
    argmax flicker.
  * Minimum-dwell filter: no regime change is allowed within `min_dwell`
    bars of the previous change (anti-flicker; Zaelar's persistence point).
  * Walk-forward splitter with train/OOS windows and refit cadence.
  * Deterministic seeding so every run is reproducible.

The module deliberately exposes the math in small, auditable functions.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence


# ─────────────────────────────────────────────────────────────────────────────
# Gaussian utilities (stdlib only)
# ─────────────────────────────────────────────────────────────────────────────

def _log_gaussian_pdf(x: float, mean: float, var: float) -> float:
    """Log-pdf of a univariate Gaussian with floor on variance."""
    var = max(var, 1e-12)
    return max(-0.5 * (math.log(2.0 * math.pi * var) + (x - mean) ** 2 / var), -1e6)


def _mean_var(values: Sequence[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 1.0
    m = sum(values) / n
    v = sum((x - m) ** 2 for x in values) / n
    return m, v


# ─────────────────────────────────────────────────────────────────────────────
# Regime model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GaussianHMM:
    """Discrete-state Gaussian HMM with diagonal covariance (stdlib only).

    Parameters
    ----------
    n_states : int
        Number of hidden states (default 3: bull / bear / range).
    seed : int | None
        Deterministic RNG seed for initialisation reproducibility.
    max_iter : int
        EM iterations cap.
    tol : float
        Convergence tolerance on total log-likelihood improvement.
    """

    n_states: int = 3
    seed: int | None = 42
    max_iter: int = 100
    tol: float = 1e-6

    # Fitted parameters (1-D emissions per state for a single feature stream)
    means: list[float] = field(default_factory=list)
    vars: list[float] = field(default_factory=list)
    trans: list[list[float]] = field(default_factory=list)
    pi: list[float] = field(default_factory=list)

    _rng: random.Random = field(default_factory=random.Random, init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    # -- initialisation -----------------------------------------------------
    def _init_params(self, obs: Sequence[float]) -> None:
        """k-means initialisation (Lloyd, stdlib) so EM starts well-separated.

        Degenerate EM (one state absorbing everything) is largely caused by
        poor starting points. k-means with the seeded RNG gives stable,
        meaningful clusters — the same trick hmmlearn uses internally.
        """
        n = self.n_states
        lo, hi = min(obs), max(obs)
        span = (hi - lo) or 1.0
        # k-means++ style seeding: first centroid random, rest far apart
        centroids = [self._rng.uniform(lo, hi)]
        while len(centroids) < n:
            dists = [min((x - c) ** 2 for c in centroids) for x in obs]
            total = sum(dists)
            if total <= 0:
                centroids.append(self._rng.uniform(lo, hi))
                continue
            # pick with probability proportional to squared distance
            r = self._rng.random() * total
            acc = 0.0
            picked = obs[-1]
            for x, d in zip(obs, dists):
                acc += d
                if acc >= r:
                    picked = x
                    break
            centroids.append(picked)
        # Lloyd iterations (bounded)
        clusters: list[list[float]] = [[] for _ in range(n)]
        for _ in range(20):
            clusters = [[] for _ in range(n)]
            for x in obs:
                k = min(range(n), key=lambda i: (x - centroids[i]) ** 2)
                clusters[k].append(x)
            new_cent = []
            for c in clusters:
                new_cent.append(sum(c) / len(c) if c else self._rng.uniform(lo, hi))
            if all(abs(a - b) < 1e-9 * span for a, b in zip(new_cent, centroids)):
                centroids = new_cent
                break
            centroids = new_cent
        self.means = centroids
        # Per-cluster variances (not a global floor) — this is what keeps EM
        # from collapsing all states into one blob.
        self.vars = []
        for c in clusters:
            if len(c) >= 2:
                mc = sum(c) / len(c)
                self.vars.append(sum((x - mc) ** 2 for x in c) / len(c) + 1e-6)
            else:
                self.vars.append(max(span * span / (n * n), 1e-6))
        self.trans = [[1.0 / n] * n for _ in range(n)]
        self.pi = [1.0 / n] * n

    # -- forward-backward ----------------------------------------------------
    def _forward(self, log_b: list[list[float]]) -> tuple[list[list[float]], list[float], float]:
        """Forward pass with per-step scale factors.

        Returns (alpha, log_c, log_likelihood). ``log_c[t]`` is the log-sum-exp
        normaliser of step t; the backward pass MUST reuse the same factors so
        that alpha*beta is a correct joint probability.
        """
        n = self.n_states
        T = len(log_b)
        alpha: list[list[float]] = []
        log_c: list[float] = []
        a0 = [math.log(self.pi[i]) + log_b[0][i] for i in range(n)]
        m0 = max(a0)
        c0 = m0 + math.log(sum(math.exp(x - m0) for x in a0))
        log_c.append(c0)
        # Normalise by the SAME scale factor log_c (logsumexp), not by max —
        # otherwise forward and backward live on inconsistent scales and the
        # E-step posterior is distorted.
        alpha.append([x - c0 for x in a0])
        for t in range(1, T):
            prev = alpha[t - 1]
            at: list[float] = []
            for j in range(n):
                terms = [prev[i] + math.log(max(self.trans[i][j], 1e-300))
                         for i in range(n)]
                m = max(terms)
                at.append(log_b[t][j] + m + math.log(sum(math.exp(v - m) for v in terms)))
            c = max(at)
            at_raw = [x - c for x in at]
            c_t = c + math.log(sum(math.exp(x) for x in at_raw))
            log_c.append(c_t)
            alpha.append([x - c_t for x in at_raw])
        ll = sum(log_c)
        return alpha, log_c, ll

    def _backward(self, log_b: list[list[float]], log_c: list[float]) -> list[list[float]]:
        """Backward pass reusing the forward scale factors (log_c)."""
        n = self.n_states
        T = len(log_b)
        beta: list[list[float]] = [[0.0] * n for _ in range(T)]
        for t in range(T - 2, -1, -1):
            bt1 = beta[t + 1]
            bt: list[float] = []
            for i in range(n):
                terms = [math.log(max(self.trans[i][j], 1e-300)) + log_b[t + 1][j] + bt1[j]
                         for j in range(n)]
                m = max(terms)
                bt.append(m + math.log(sum(math.exp(v - m) for v in terms)) - log_c[t + 1])
            beta[t] = bt
        return beta

    # -- EM ------------------------------------------------------------------
    def fit(self, obs: Sequence[float], returns: bool = True) -> "GaussianHMM":
        """Fit the model with Baum-Welch EM on a feature series.

        Parameters
        ----------
        obs : sequence of float
            Feature series. For price series pass ``returns=True`` (default):
            the model fits the first differences, which are the stationary,
            regime-bearing quantity for trading signals.
        """
        series = list(obs)
        if returns and len(series) > 1:
            series = [series[i + 1] - series[i] for i in range(len(series) - 1)]
        T = len(series)
        if T < self.n_states * 5:
            raise ValueError("not enough observations to fit HMM")
        self._init_params(series)
        log_b = [[_log_gaussian_pdf(series[t], self.means[j], self.vars[j])
                  for j in range(self.n_states)] for t in range(T)]
        prev_ll = -math.inf
        for _ in range(self.max_iter):
            alpha, log_c, ll = self._forward(log_b)
            beta = self._backward(log_b, log_c)
            n = self.n_states
            # gamma[t][i] = P(state=i | all obs) in log space, normalised per t
            gamma: list[list[float]] = []
            for t in range(T):
                g = [alpha[t][i] + beta[t][i] for i in range(n)]
                m = max(g)
                denom = m + math.log(sum(math.exp(x - m) for x in g))
                gamma.append([math.exp(x - denom) for x in g])
            # xi[t][i][j] = P(state=i, next=j) in log space, normalised
            xi: list[list[list[float]]] = []
            for t in range(T - 1):
                row: list[list[float]] = []
                for i in range(n):
                    rj: list[float] = []
                    for j in range(n):
                        v = (alpha[t][i] + math.log(self.trans[i][j]) +
                             log_b[t + 1][j] + beta[t + 1][j])
                        rj.append(v)
                    row.append(rj)
                # normalise over all i,j for this t
                flat = [row[i][j] for i in range(n) for j in range(n)]
                m = max(flat)
                denom = m + math.log(sum(math.exp(x - m) for x in flat))
                for i in range(n):
                    for j in range(n):
                        row[i][j] = math.exp(row[i][j] - denom)
                xi.append(row)
            # M-step
            global_var = (sum((x - sum(series) / len(series)) ** 2 for x in series)
                          / len(series)) or 1.0
            # Relative floor: prevents the EM "spike" pathology where one state
            # grabs a tiny subset of extreme points with near-zero variance,
            # stealing mass from the true clusters.
            min_var = max(1e-6, 0.02 * global_var)
            for i in range(n):
                self.pi[i] = sum(gamma[t][i] for t in range(T)) / T
                for j in range(n):
                    num = sum(xi[t][i][j] for t in range(T - 1))
                    den = sum(gamma[t][i] for t in range(T - 1))
                    self.trans[i][j] = num / den if den > 0 else 1.0 / n
                # Renormalise row to a proper transition distribution with floor
                row_sum = sum(self.trans[i])
                if row_sum > 0:
                    self.trans[i] = [v / row_sum for v in self.trans[i]]
                else:
                    self.trans[i] = [1.0 / n] * n
                # Floor: avoid exact zeros that break log() in the next E-step
                self.trans[i] = [max(v, 1e-9) for v in self.trans[i]]
                ts = sum(self.trans[i])
                self.trans[i] = [v / ts for v in self.trans[i]]
                w = sum(gamma[t][i] for t in range(T))
                self.means[i] = sum(gamma[t][i] * series[t] for t in range(T)) / w if w > 0 else 0.0
                self.vars[i] = sum(gamma[t][i] * (series[t] - self.means[i]) ** 2
                                   for t in range(T)) / w if w > 0 else global_var
                self.vars[i] = max(self.vars[i], min_var)
            # Renormalise pi explicitly (numerical safety)
            pi_sum = sum(self.pi)
            if pi_sum > 0:
                self.pi = [v / pi_sum for v in self.pi]
            log_b = [[_log_gaussian_pdf(series[t], self.means[j], self.vars[j])
                      for j in range(self.n_states)] for t in range(T)]
            if ll - prev_ll < self.tol:
                break
            prev_ll = ll
        return self

    def posterior(self, obs: Sequence[float], returns: bool = True) -> list[list[float]]:
        """Smoothed state posteriors P(state_i | all obs) per timestep.

        Must be called with the same ``returns`` convention used in ``fit`` so
        the emission means align with the transformed series.
        """
        series = list(obs)
        if returns and len(series) > 1:
            series = [series[i + 1] - series[i] for i in range(len(series) - 1)]
        T = len(series)
        log_b = [[_log_gaussian_pdf(series[t], self.means[j], self.vars[j])
                  for j in range(self.n_states)] for t in range(T)]
        alpha, log_c, _ = self._forward(log_b)
        beta = self._backward(log_b, log_c)
        n = self.n_states
        out: list[list[float]] = []
        for t in range(T):
            g = [alpha[t][i] + beta[t][i] for i in range(n)]
            m = max(g)
            denom = m + math.log(sum(math.exp(x - m) for x in g))
            out.append([math.exp(x - denom) for x in g])
        return out

    def sorted_by_mean(self) -> "GaussianHMM":
        """Return a copy with states reordered by ascending emission mean.

        After reordering, state 0 always has the lowest mean (bear-like) and
        state n-1 the highest (bull-like). This makes regime labels stable and
        interpretable regardless of the EM initialisation order.
        """
        order = sorted(range(self.n_states), key=lambda i: self.means[i])
        clone = GaussianHMM(n_states=self.n_states, seed=self.seed,
                            max_iter=self.max_iter, tol=self.tol)
        clone.means = [self.means[i] for i in order]
        clone.vars = [self.vars[i] for i in order]
        clone.trans = [[self.trans[i][j] for j in order] for i in order]
        clone.pi = [self.pi[i] for i in order]
        return clone


# ─────────────────────────────────────────────────────────────────────────────
# Regime declarations (anti-flicker)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RegimeDeclarations:
    """Regime sequence after smoothed-posterior commitment + min-dwell filter.

    Attributes
    ----------
    states : list[int]
        Declared state per bar (0..n_states-1), -1 while undecided.
    confidence : list[float]
        Posterior probability of the declared state at declaration time.
    labels : list[str]
        Human labels: 'bull' | 'bear' | 'range' | 'undecided'.
    """

    states: list[int]
    confidence: list[float]
    labels: list[str]

    @property
    def n_declared(self) -> int:
        return sum(1 for s in self.states if s >= 0)

    @property
    def median_regime_duration(self) -> float:
        """Median number of bars a declared regime persists (0 if none)."""
        runs: list[int] = []
        cur, cnt = None, 0
        for s in self.states:
            if s >= 0 and s == cur:
                cnt += 1
            elif s >= 0:
                if cur is not None:
                    runs.append(cnt)
                cur, cnt = s, 1
            else:
                if cur is not None:
                    runs.append(cnt)
                cur, cnt = None, 0
        if cur is not None:
            runs.append(cnt)
        if not runs:
            return 0.0
        runs.sort()
        n = len(runs)
        return float(runs[n // 2])


def declare_regimes(posterior: list[list[float]],
                    threshold: float = 0.65,
                    min_dwell: int = 3,
                    labels: Sequence[str] = ("bear", "range", "bull")) -> RegimeDeclarations:
    """Turn smoothed posteriors into stable regime declarations.

    A state is declared only when its posterior exceeds `threshold`.
    After a change, the next change is forbidden for `min_dwell` bars
    (minimum-dwell anti-flicker filter — addresses regime persistence).
    """
    n = len(posterior[0]) if posterior else 0
    states: list[int] = []
    confidence: list[float] = []
    labels_out: list[str] = []
    last_change = -10**9
    for t, p in enumerate(posterior):
        best = max(range(n), key=lambda i: p[i])
        if p[best] >= threshold and t - last_change >= min_dwell:
            if states and states[-1] != best:
                last_change = t
            states.append(best)
            confidence.append(p[best])
        elif states:
            # hold previous declaration (persistence) but record lower confidence
            states.append(states[-1])
            confidence.append(p[best])
        else:
            states.append(-1)
            confidence.append(0.0)
        labels_out.append(labels[states[-1]] if states[-1] >= 0 else "undecided")
    return RegimeDeclarations(states=states, confidence=confidence, labels=labels_out)


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WFSplit:
    """One walk-forward fold (train / out-of-sample)."""

    train: list[float]
    oos: list[float]
    train_idx: tuple[int, int]
    oos_idx: tuple[int, int]


def walk_forward_folds(obs: Sequence[float],
                       train_size: int = 100,
                       oos_size: int = 20,
                       refit_every: int = 25) -> list[WFSplit]:
    """Rolling train/OOS folds.

    * train window: `train_size` bars
    * OOS window: `oos_size` bars (out-of-sample)
    * refit every `refit_every` OOS steps (the training window advances)
    """
    folds: list[WFSplit] = []
    start = 0
    total = len(obs)
    while start + train_size + oos_size <= total:
        tr = (start, start + train_size)
        oo = (start + train_size, start + train_size + oos_size)
        folds.append(WFSplit(
            train=list(obs[tr[0]:tr[1]]),
            oos=list(obs[oo[0]:oo[1]]),
            train_idx=tr,
            oos_idx=oo,
        ))
        start += refit_every
    return folds


def regime_score(declarations: RegimeDeclarations,
                 forward_returns: Sequence[float],
                 bullish_states: set[int] = frozenset({2})) -> dict:
    """Simple regime-conditional return decomposition (diagnostic, not a PnL).

    Returns the mean forward return conditioned on the declared regime and the
    fraction of bars declared — the falsifiable quantity a critic can attack.
    """
    by_state: dict[int, list[float]] = {}
    for state, ret in zip(declarations.states, forward_returns):
        if state >= 0:
            by_state.setdefault(state, []).append(ret)
    means = {s: sum(rs) / len(rs) for s, rs in by_state.items() if rs}
    declared = declarations.n_declared
    total = len(declarations.states)
    return {
        "regime_means": means,
        "bull_mean": means.get(next(iter(bullish_states)), None),
        "fraction_declared": declared / total if total else 0.0,
        "n_declared": declared,
        "n_total": total,
        "median_duration": declarations.median_regime_duration,
    }
