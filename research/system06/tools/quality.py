"""What this laboratory now calls a BETTER result: return weighted by its own efficiency.

Operator, 2026-09-17: "the best result under the best conditions is the one that offers
maximum profit with the minimum drawdown, in RELATIVE terms. +25% with a 22% drawdown is
worse than +20% with a 12% one. Monetary safety is a priority. But obviously if we only
make 5% with a 5% drawdown that is a bad result - I prefer the 20%. Find a formula for
what we call the best result. Even so, big results often need big drawdowns, so do not
erase, discard or hide the maximum-profit figure: give TWO numbers for the winning
system - the largest profit, and the optimal one."

The formula
-----------
    Q = sign(r) * r^2 / max(dd, DD_FLOOR)          (r and dd as fractions)

which is exactly `r * (r / dd)`: the return, weighted by the return it earned per unit
of drawdown. Two ways to read it, both true, and the pair is the point:

  * as MAR (r/dd) scaled by r, so efficiency only counts when there is something to be
    efficient about - it is the term that refuses the 5%/5% account;
  * as r scaled by MAR, so size only counts when it was not bought with pain - it is the
    term that refuses +40% at a 38% drawdown.

Why not the obvious alternatives, each of which this lab has been tempted by:

  * `r / dd` (MAR alone) ranks +2% at a 1% drawdown ABOVE +20% at a 12% one. The operator
    ruled that out in the same sentence he asked for the formula.
  * `r - k*dd` needs an exchange rate k between return and pain that nobody can defend,
    and it is not scale-free: it ranks differently if you express both in percent.
  * `r / sqrt(dd)` does rank the two candidates correctly, but it barely separates 5%/5%
    from 2%/1% (2.24 vs 2.00) - it is too soft on small accounts.
  * Sharpe/Sortino price VOLATILITY, and the operator has never once asked about
    volatility. He asks about the worst peak-to-trough hole, which is what dd is.

The floor exists because a candidate that barely traded can post a 0.4% drawdown and
divide by almost nothing. DD_FLOOR is 2%: below that the account was not really at risk,
and pretending otherwise manufactures infinite quality out of inactivity.

Q is NOT a replacement for the consistency law (`worst_year + 0.10*CAGR`), which governs
whether a system is allowed to exist: every calendar year positive comes first. Q ranks
what has already passed that gate. Read the two together - `python tools/quality.py`
prints both for every sealed 2026 reading on record.
"""

from __future__ import annotations

import json
import pathlib
import sys

DD_FLOOR = 0.02

S6 = pathlib.Path(__file__).resolve().parent.parent


def quality(return_pct: float, max_drawdown: float, dd_floor: float = DD_FLOOR) -> float:
    """Return weighted by return-per-drawdown. Negative returns stay negative."""
    r = float(return_pct)
    dd = max(float(max_drawdown or 0.0), dd_floor)
    return (1.0 if r >= 0 else -1.0) * (r * r) / dd


def efficiency(return_pct: float, max_drawdown: float, dd_floor: float = DD_FLOOR) -> float:
    """The MAR-style ratio, reported BESIDE Q because it is the number a reader feels."""
    return float(return_pct) / max(float(max_drawdown or 0.0), dd_floor)


def _readings() -> list[dict]:
    """Every sealed-2026 reading this laboratory has actually spent, plus the champion."""
    out: list[dict] = []
    best = json.loads((S6 / "best.json").read_text(encoding="utf-8"))
    fw = best["forward_2026"]
    out.append({"id": "champion (shipped)", "at": best["at"][:10],
                "return_pct": fw["return_pct"], "max_drawdown": fw["max_drawdown"],
                "trades": fw.get("trades")})
    path = S6 / "rnd" / "sealed_readouts.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sealed = row.get("sealed_2026") or {}
        # Five shapes across eight readings, because the file grew with the method. Take
        # whichever pair of keys a row happens to carry rather than rewriting history.
        ret = next((sealed[k] for k in ("return_pct", "return", "combined_return")
                    if k in sealed), row.get("return_pct"))
        dd = next((sealed[k] for k in ("max_drawdown", "dd", "combined_dd")
                   if k in sealed), row.get("max_drawdown"))
        if ret is None or dd is None:
            continue
        out.append({"id": str(row.get("id") or row.get("what") or row.get("date"))[:30],
                    "at": str(row.get("at") or row.get("date"))[:10],
                    "return_pct": ret, "max_drawdown": dd,
                    "trades": sealed.get("trades") or row.get("trades")})
    return out


def main() -> int:
    rows = _readings()
    for r in rows:
        r["Q"] = quality(r["return_pct"], r["max_drawdown"])
        r["eff"] = efficiency(r["return_pct"], r["max_drawdown"])
    rows.sort(key=lambda r: r["Q"], reverse=True)

    print(f"{'sealed 2026 reading':<32}{'return':>9}{'maxDD':>8}{'ret/DD':>8}{'Q':>9}{'trades':>8}")
    for r in rows:
        print(f"{r['id']:<32}{r['return_pct']:>8.2%}{r['max_drawdown']:>8.1%}"
              f"{r['eff']:>8.2f}{r['Q']:>9.4f}{(r['trades'] or '-'):>8}")

    top_profit = max(rows, key=lambda r: r["return_pct"])
    top_quality = rows[0]
    print()
    print(f"  MAXIMUM PROFIT   {top_profit['id']}: {top_profit['return_pct']:+.2%} "
          f"at {top_profit['max_drawdown']:.1%} drawdown  (Q {top_profit['Q']:.4f})")
    print(f"  OPTIMAL          {top_quality['id']}: {top_quality['return_pct']:+.2%} "
          f"at {top_quality['max_drawdown']:.1%} drawdown  (Q {top_quality['Q']:.4f}, "
          f"{top_quality['eff']:.2f} of return per unit of drawdown)")
    if top_profit["id"] != top_quality["id"]:
        keep = top_quality["return_pct"] / top_profit["return_pct"]
        print(f"  the optimal one keeps {keep:.0%} of the maximum profit for "
              f"{top_quality['max_drawdown'] / top_profit['max_drawdown']:.0%} of the drawdown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
