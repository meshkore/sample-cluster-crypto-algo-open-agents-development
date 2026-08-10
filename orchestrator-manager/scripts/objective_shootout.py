"""Which scoring function actually predicts the window it has not seen?

The loop optimises whatever `objective()` says is good, so if that function
ranks configurations in an order that does not survive contact with the next
window, sixty-seven iterations of genetic search are sixty-seven iterations of
climbing the wrong hill. This measures that directly, on runs already recorded.

TWO TESTS, and the first is the one that counts.

  A · HELD-OUT FOLD. Score each recorded fit on folds 1-3 only, then ask how
      well that score ranks the SAME configurations by their fold-4 return.
      Every record has all four folds, so nothing is selected for and no 2026
      bar is touched. This is a walk-forward test of the scoring function
      itself rather than of any strategy.

  B · 2026. Score on all four folds, correlate with what the configuration
      actually did in the sealed window. Reported second and with a warning
      attached: the forward window only ever opened for configurations the
      CURRENT objective liked, so this sample is selected by the very thing
      under test. It can convict a variant, it cannot acquit one.

The 30% drawdown rejection is the operator's standing rule and is applied
identically in every variant. What varies is only how the surviving candidates
are ORDERED.

    python3 orchestrator-manager/scripts/objective_shootout.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from statistics import mean, median

LEDGER = Path("orchestrator-manager/loop/ledger/hypotheses.jsonl")
MANDATE = 0.30
FLOOR = 0.02  # a drawdown denominator cannot be zero, and 2% is a quiet window


# --------------------------------------------------------------------------- #
# The variants


def current(returns, drawdowns):
    """median x consistency - 1.0 x worst. What the loop uses today."""
    worst = max(drawdowns)
    middle = median(returns)
    consistency = sum(1 for r in returns if r > 0) / len(returns)
    return (middle * consistency if middle > 0 else middle) - 1.0 * worst


def lighter(returns, drawdowns):
    """The same shape, with drawdown priced at 0.3 instead of 1.0."""
    worst = max(drawdowns)
    middle = median(returns)
    consistency = sum(1 for r in returns if r > 0) / len(returns)
    return (middle * consistency if middle > 0 else middle) - 0.3 * worst


def risk_adjusted(returns, drawdowns):
    """Return PER UNIT of drawdown, rather than return minus drawdown.

    Subtracting makes a point of drawdown cost the same whether the strategy
    made 2% or 200%. Dividing asks the question a person actually asks: what
    did I get for the risk I took.
    """
    return median(returns) / max(max(drawdowns), FLOOR)


def mean_not_median(returns, drawdowns):
    """The median throws away both good folds. This keeps them."""
    return mean(returns) - 1.0 * max(drawdowns)


def returns_only(returns, drawdowns):
    """Control: no drawdown term at all, the mandate still rejecting."""
    middle = median(returns)
    consistency = sum(1 for r in returns if r > 0) / len(returns)
    return middle * consistency if middle > 0 else middle


VARIANTS = {
    "current  (med x cons - 1.0dd)": current,
    "lighter  (med x cons - 0.3dd)": lighter,
    "risk-adj (med / worst dd)": risk_adjusted,
    "mean     (mean - 1.0dd)": mean_not_median,
    "control  (no dd term)": returns_only,
}


# --------------------------------------------------------------------------- #
# Statistics, kept to the standard library on purpose


def spearman(xs, ys):
    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    return pearson(rank(xs), rank(ys))


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def permutation_p(xs, ys, observed, trials=20_000):
    """How often does shuffling produce a correlation at least this strong?

    A permutation test rather than a table lookup: n is small, the values are
    not normal, and a p-value nobody can re-derive is worth nothing here.
    """
    rng = random.Random(20260810)
    shuffled = list(ys)
    hits = 0
    for _ in range(trials):
        rng.shuffle(shuffled)
        if abs(spearman(xs, shuffled)) >= abs(observed):
            hits += 1
    return (hits + 1) / (trials + 1)


# --------------------------------------------------------------------------- #


def load():
    records = []
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        fit = (r.get("metrics") or {}).get("fit") or {}
        rets, dds = fit.get("returns"), fit.get("drawdowns")
        if not rets or not dds or len(rets) != 4 or len(dds) != 4:
            continue
        records.append(
            {
                "id": r.get("id"),
                "iteration": r.get("iteration") or 0,
                "returns": [float(x) for x in rets],
                "drawdowns": [float(x) for x in dds],
                "forward": ((r.get("metrics") or {}).get("forward") or {}).get(
                    "return_pct"
                ),
            }
        )
    return records


def legal(drawdowns):
    """The operator's rule, applied identically in every variant."""
    return max(drawdowns) < MANDATE


def report(title, note, xs_by_variant, ys, label):
    print(f"\n{title}")
    print(f"  {note}")
    print(f"  n = {len(ys)}\n")
    print(f"  {'variant':<32}{'rho':>8}{'p':>9}{'top-5 ' + label:>18}")
    for name, xs in xs_by_variant.items():
        rho = spearman(xs, ys)
        p = permutation_p(xs, ys, rho)
        best = [ys[i] for i in sorted(range(len(xs)), key=lambda i: -xs[i])[:5]]
        print(f"  {name:<32}{rho:>8.3f}{p:>9.3f}{100 * mean(best):>17.2f}%")


def main() -> int:
    records = load()
    print(f"{len(records)} recorded fits carry four folds of returns and drawdowns.")
    print(
        "Iterations 1-67 were measured on the alphabetical universe and 70+ on "
        "the corrected one.\nThat is fine here: the question is whether a "
        "SHAPE of scoring function ranks\nconfigurations in an order the next "
        "window agrees with, and each record is\nscored against its own folds."
    )

    # -- A: the held-out fold ------------------------------------------------ #
    a = [r for r in records if legal(r["drawdowns"][:3])]
    xs = {
        name: [fn(r["returns"][:3], r["drawdowns"][:3]) for r in a]
        for name, fn in VARIANTS.items()
    }
    report(
        "A · HELD-OUT FOLD  (score on folds 1-3, rank by the fold-4 return)",
        "No 2026 bar involved, nothing selected for. This is the test that counts.",
        xs,
        [r["returns"][3] for r in a],
        "fold-4 return",
    )

    # -- A2: is it overfitting, or is fold 4 simply a different market? ------ #
    #
    # A negative correlation into fold 4 alone has an innocent explanation: the
    # folds are consecutive eras, and 2024-2026 is not 2020-2022. "What worked
    # in the bull does worse in the bear" is regime dependence, not overfitting,
    # and it would be a fact about crypto rather than a defect in the search.
    # The two are separable -- if every fold boundary inverts, the search is
    # fitting noise; if only the last one does, it is the regime.
    print("\nA2 · IS IT THE SEARCH, OR IS IT FOLD 4?")
    print("  Same test at every boundary. If only the last inverts, blame the")
    print("  regime; if all of them do, the search is fitting noise.\n")
    print(f"  {'train -> test':<18}{'n':>5}{'rho':>8}{'p':>9}{'mean test return':>19}")
    for cut in (1, 2, 3):
        rows = [r for r in records if legal(r["drawdowns"][:cut])]
        if len(rows) < 8:
            continue
        xs = [current(r["returns"][:cut], r["drawdowns"][:cut]) for r in rows]
        ys = [r["returns"][cut] for r in rows]
        rho = spearman(xs, ys)
        print(
            f"  {'1-' + str(cut) + ' -> ' + str(cut + 1):<18}{len(rows):>5}{rho:>8.3f}"
            f"{permutation_p(xs, ys, rho):>9.3f}{100 * mean(ys):>18.2f}%"
        )
    print("\n  each fold's mean return across all recorded fits:")
    for i, name in enumerate(("2018-2020", "2020-2022", "2022-2024", "2024-2026")):
        print(f"    {name}  {100 * mean(r['returns'][i] for r in records):+7.2f}%")

    # -- B: the sealed window ------------------------------------------------ #
    b = [r for r in records if r["forward"] is not None and legal(r["drawdowns"])]
    if len(b) >= 5:
        xs = {
            name: [fn(r["returns"], r["drawdowns"]) for r in b]
            for name, fn in VARIANTS.items()
        }
        report(
            "B · THE SEALED WINDOW  (score on all four folds, rank by 2026)",
            "SELECTED SAMPLE: 2026 only ever opened for fits the CURRENT objective "
            "liked.\n  It can convict a variant, it cannot acquit one.",
            xs,
            [r["forward"] for r in b],
            "2026 return",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
