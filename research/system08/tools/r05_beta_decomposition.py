"""R05: is the 2025 "beta blowout" structural, or just arithmetic?

THEORY v1 rests on one number: the median altcoin beta to Bitcoin sat near 1.0 in every
year except 2025, where R01 measured 1.639 — with R² unchanged. I read that as "same
correlation, higher amplitude" and built a design on it.

Giller (arXiv 2412.04263, Dec 2024) is a direct threat to that reading. Using a
model-free N*(N) statistic on a retail crypto universe he finds average pairwise
correlation of order 60% and concludes the cross-section is better described by an
ISOTROPIC correlation model than by a linear factor model with additive noise — that is,
the loadings are not meaningfully dispersed.

That matters here because beta is not a primitive. It is

    beta_i  =  rho_i * sigma_i / sigma_B

so a beta can rise for two completely different reasons:

    STRUCTURAL   rho rises — altcoins became more tightly coupled to Bitcoin
    ARITHMETIC   sigma_i / sigma_B rises — altcoins simply got more volatile relative
                 to Bitcoin, with the coupling unchanged

R01 already reported R² (hence rho²) as UNCHANGED while beta rose 64%. That is the
signature of the second explanation, and I did not notice because I never decomposed the
number I was building on. If it is arithmetic, "the leverage went to 1.6x in 2025" is
true but it is not a discovery about a regime — it is a volatility ratio, and it was
always there.

WHY THIS IS NOT FATAL, AND WHY IT STILL CHANGES THE DESIGN

Either way the exposure is real and hedging is the right response — an unhedged alt book
carries beta units of Bitcoin whether that beta came from rho or from a vol ratio. What
changes is the CLAIM. "Something broke in 2025" would be wrong; "the exposure tracks a
ratio we can measure and mostly did not" would be right, and it is a weaker, more honest
and more useful statement. It also makes beta partly PREDICTABLE, since vol ratios are
persistent where regime breaks are not.

WHAT IS REGISTERED, BEFORE THE NUMBERS EXIST

  Decompose median beta per year into rho and the vol ratio, on a FIXED universe — only
  names listed before the earliest compared year, so composition cannot manufacture the
  result the way it did in R04.

  A: if the 2025 rise is carried by SIGMA RATIO with rho flat, the blowout is arithmetic.
     THEORY v1's claim is rewritten, not withdrawn: the exposure is real, the regime story
     is dropped, and beta becomes a quantity to forecast rather than a break to react to.

  B: if rho itself rises materially in 2025, the coupling did change, and the original
     claim stands as written.

  C: if neither — median beta on a fixed universe is NOT elevated in 2025 — then kill K1
     fires, the premise was a composition artefact, and THEORY v1 is withdrawn entirely.

  Registered threshold for "material": the 2025 value must sit outside the full range of
  the other measured years. Same rule for rho and for the ratio, so neither gets a softer
  test than the other.

This is a MARKET measurement, not a strategy. It builds no book, takes no position and
has no parameters to tune. Under the operator's code gate (2026-09-10) that makes it
design work, which is exactly the activity that is uncapped.

Run from the repo root:
    PYTHONPATH=trading-system python research/system08/tools/r05_beta_decomposition.py
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OUT = Path("research/system08/rnd")
FACTOR = "BTCUSDT"
WINDOW = 60          # trading days — a quarter, same as R01 so the two are comparable
MIN_DAYS = 200


def daily_closes(bars) -> dict[str, float]:
    out: dict[str, float] = {}
    for b in bars:
        out[b.timestamp.strftime("%Y-%m-%d")] = float(b.close)
    return out


def main() -> int:
    import quantlab_catalog as cat

    symbols = cat.load_universe()
    if FACTOR not in symbols:
        symbols = [FACTOR] + list(symbols)
    print(f"loading {len(symbols)} symbols ...", flush=True)
    research = cat.research(symbols)

    closes: dict[str, dict[str, float]] = {}
    for sym in symbols:
        merged = daily_closes(research.get(sym) or [])
        if len(merged) > MIN_DAYS:
            closes[sym] = merged
    btc = closes.get(FACTOR)
    if not btc:
        sys.exit("no BTCUSDT — the factor is the measurement")

    # ---- FIXED UNIVERSE. R04 was confounded by composition and fable5 caught it; the
    # fix is not to apologise for it but to make it impossible here. Keep only names whose
    # history starts before the earliest year we intend to compare.
    firsts = {s: min(v) for s, v in closes.items()}
    cutoff = "2019-01-01"
    fixed = sorted(s for s, f in firsts.items() if f < cutoff and s != FACTOR)
    print(f"  fixed universe (listed before {cutoff}): {len(fixed)} names")
    print(f"    {', '.join(fixed)}")
    dropped = sorted(s for s in closes if s != FACTOR and s not in fixed)
    print(f"  dropped as later listings: {', '.join(dropped) or 'none'}")

    rets: dict[str, dict[str, float]] = {}
    for sym in [FACTOR] + fixed:
        series = closes[sym]
        days = sorted(series)
        r = {}
        for prev, day in zip(days, days[1:]):
            p0, p1 = series[prev], series[day]
            if p0 > 0 and p1 > 0:
                r[day] = float(np.log(p1 / p0))
        rets[sym] = r

    all_days = sorted({d for s in rets.values() for d in s})
    per_year: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: {"beta": [], "rho": [], "ratio": [], "sig_i": [], "sig_b": []})

    for sym in fixed:
        r = rets[sym]
        days = [d for d in all_days if d in r and d in rets[FACTOR]]
        if len(days) < WINDOW + 100:
            continue
        a = np.array([r[d] for d in days])
        f = np.array([rets[FACTOR][d] for d in days])
        for i in range(WINDOW, len(days)):
            wa, wf = a[i - WINDOW:i], f[i - WINDOW:i]      # strictly past
            sa, sb = float(np.std(wa)), float(np.std(wf))
            if sa <= 0 or sb <= 0:
                continue
            cov = float(np.cov(wa, wf, bias=True)[0, 1])
            rho = cov / (sa * sb)
            year = int(days[i][:4])
            per_year[year]["beta"].append(cov / (sb * sb))
            per_year[year]["rho"].append(rho)
            per_year[year]["ratio"].append(sa / sb)
            per_year[year]["sig_i"].append(sa)
            per_year[year]["sig_b"].append(sb)

    print("\n" + "=" * 88)
    print("BETA DECOMPOSED.   beta = rho * (sigma_alt / sigma_BTC)")
    print(f"fixed universe of {len(fixed)} names, rolling {WINDOW}-day causal window")
    print("=" * 88)
    print(f"{'year':>6} {'median beta':>12} {'rho':>8} {'sig_alt/sig_B':>15} "
          f"{'sig_alt':>9} {'sig_BTC':>9} {'obs':>8}")

    rows = {}
    for year in sorted(per_year):
        v = per_year[year]
        if len(v["beta"]) < 200:
            continue
        rows[year] = {
            "beta": statistics.median(v["beta"]),
            "rho": statistics.median(v["rho"]),
            "ratio": statistics.median(v["ratio"]),
            "sig_i": statistics.median(v["sig_i"]),
            "sig_b": statistics.median(v["sig_b"]),
            "obs": len(v["beta"]),
        }
        d = rows[year]
        print(f"{year:>6} {d['beta']:>12.3f} {d['rho']:>8.3f} {d['ratio']:>15.3f} "
              f"{d['sig_i']:>9.4f} {d['sig_b']:>9.4f} {d['obs']:>8,}")

    if 2025 not in rows or len(rows) < 4:
        sys.exit("not enough years on a fixed universe to adjudicate")

    others = {y: d for y, d in rows.items() if y != 2025}
    b25, r25, q25 = rows[2025]["beta"], rows[2025]["rho"], rows[2025]["ratio"]
    b_rng = (min(d["beta"] for d in others.values()),
             max(d["beta"] for d in others.values()))
    r_rng = (min(d["rho"] for d in others.values()),
             max(d["rho"] for d in others.values()))
    q_rng = (min(d["ratio"] for d in others.values()),
             max(d["ratio"] for d in others.values()))

    print("\n" + "=" * 88)
    print("2025 AGAINST THE RANGE OF EVERY OTHER MEASURED YEAR")
    print("=" * 88)
    print(f"  beta          2025 {b25:>7.3f}   others {b_rng[0]:.3f} .. {b_rng[1]:.3f}"
          f"   {'OUTSIDE' if (b25 > b_rng[1] or b25 < b_rng[0]) else 'inside'}")
    print(f"  rho           2025 {r25:>7.3f}   others {r_rng[0]:.3f} .. {r_rng[1]:.3f}"
          f"   {'OUTSIDE' if (r25 > r_rng[1] or r25 < r_rng[0]) else 'inside'}")
    print(f"  sigma ratio   2025 {q25:>7.3f}   others {q_rng[0]:.3f} .. {q_rng[1]:.3f}"
          f"   {'OUTSIDE' if (q25 > q_rng[1] or q25 < q_rng[0]) else 'inside'}")

    beta_high = b25 > b_rng[1]
    rho_high = r25 > r_rng[1]
    ratio_high = q25 > q_rng[1]

    if not beta_high:
        verdict = ("C — KILL K1 FIRES. On a fixed universe the 2025 median beta is NOT "
                   f"outside the range of the other years ({b25:.3f} against "
                   f"{b_rng[0]:.3f}..{b_rng[1]:.3f}). The blowout was composition, exactly "
                   "as it was in R04. THEORY v1's premise is withdrawn.")
    elif ratio_high and not rho_high:
        verdict = ("A — ARITHMETIC, NOT STRUCTURAL. Beta is elevated and so is the "
                   f"volatility ratio ({q25:.3f} vs {q_rng[0]:.3f}..{q_rng[1]:.3f}), while "
                   f"rho stays inside its usual range ({r25:.3f}). Altcoins did not couple "
                   "more tightly to Bitcoin; they simply got more volatile relative to it. "
                   "Consistent with Giller's isotropic reading. The exposure is real and "
                   "hedging remains the right response, but the REGIME story is dropped: "
                   "beta becomes a quantity to forecast from a persistent vol ratio, not a "
                   "break to react to. THEORY v1 is REWRITTEN, not withdrawn.")
    elif rho_high:
        verdict = ("B — STRUCTURAL. Rho itself is outside its historical range in 2025, so "
                   "the coupling really did change and the original claim stands as "
                   "written. Note this cuts AGAINST Giller's isotropic-and-stable finding "
                   "and the disagreement should be stated, not smoothed over.")
    else:
        verdict = ("AMBIGUOUS — beta is elevated but neither rho nor the vol ratio is "
                   "individually outside its range. The rise is a joint effect too small "
                   "to attribute, which is itself a reason not to build a claim on it.")

    print("\nVERDICT:", verdict)
    print("\nThis measurement has no parameters and builds no book. It cannot be passed by "
          "a strategy\nand cannot be flattered by one.")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"r05_beta_decomposition_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps({
        "id": "R05", "at": datetime.now(timezone.utc).isoformat(),
        "window_days": WINDOW, "fixed_universe": fixed, "dropped": dropped,
        "listed_before": cutoff, "by_year": rows,
        "range_others": {"beta": b_rng, "rho": r_rng, "ratio": q_rng},
        "verdict": verdict,
        "challenges": "Giller, arXiv 2412.04263 — isotropic correlation rejects a linear "
                      "factor decomposition on a retail crypto universe",
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwritten -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
