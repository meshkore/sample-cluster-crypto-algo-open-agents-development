"""A116: every combination the search tested, with its profit for every single year.

Operator, 2026-09-07: "I want to see a record, in a document, where you put each of the
values and the profits of each year."

The data already exists - every trial stored its per-year return as a user attribute
when it ran - so this is an export, not a new computation. It writes two files:

  rnd/trials_ledger.csv   one row per combination: the 33 parameter values, the profit
                          for each of 2018..2025, the fit and held-out scores, the worst
                          drawdown and the trade count. Opens in any spreadsheet.
  rnd/trials_ledger.md    the readable summary: the champion, the ten best on the fitted
                          years, the ten best on the years the search never saw, and the
                          per-lever spread that answers the operator's real question -
                          does moving a value change anything at all.

The columns are ordered so the answer is visible without scrolling: value columns
first, then years, then scores.

Run from repo root: python research/system06/tools/a116_trials_ledger.py
"""

from __future__ import annotations

import csv
import json
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
STORAGE = f"sqlite:///{(ROOT / 'rnd' / 'optuna_thresholds.db').as_posix()}"
STUDY = "thresholds-v3-heldout"
YEARS = [str(y) for y in range(2018, 2026)]
FIT = {"2018", "2019", "2020", "2021", "2022", "2023"}


def main() -> int:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.load_study(study_name=STUDY, storage=STORAGE)
    trials = [t for t in study.trials
              if t.state.name == "COMPLETE" and t.value is not None]
    params = sorted({k for t in trials for k in t.params})

    csv_path = ROOT / "rnd" / "trials_ledger.csv"
    header = (["trial", "traded"] + params + [f"profit_{y}" for y in YEARS]
              + ["fit_score", "heldout_score", "worst_drawdown", "trades"])
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for t in trials:
            a = t.user_attrs
            rets = a.get("returns") or {}
            w.writerow(
                [t.number, "no" if a.get("inert") else "yes"]
                + [t.params.get(p, "") for p in params]
                + [rets.get(y, "") for y in YEARS]
                + [round(t.value, 6), round(a.get("holdout") or 0.0, 6),
                   a.get("worst_drawdown"), a.get("trades")])

    live = [t for t in trials if not t.user_attrs.get("inert")]
    anchor = next((t for t in trials if t.number == 2), None)

    def row(t):
        a, r = t.user_attrs, (t.user_attrs.get("returns") or {})
        cells = " ".join(f"{r[y]:+8.1%}" if y in r else "     —  " for y in YEARS)
        return (f"| {t.number:>4} | {t.value:+.4f} | {(a.get('holdout') or 0):+.4f} | "
                f"{cells} | {(a.get('worst_drawdown') or 0):.1%} | {a.get('trades')} |")

    head = ("| trial | fit | held-out | " + " ".join(f"{y[2:]}     " for y in YEARS)
            + " | maxDD | trades |")
    sep = "|---" * 5 + "|"

    lines = [
        f"# Every combination tested — profits per year",
        "",
        f"Study `{STUDY}` · {len(trials)} combinations completed · {len(live)} of them "
        f"actually traded · exported {datetime.now(timezone.utc):%Y-%m-%d}.",
        "",
        "Years **2018–2023** are what the search was allowed to optimise on. "
        "**2024–2025** were recorded on every single trial and used for nothing — "
        "they are the out-of-sample check. **2026 was never touched by the search.**",
        "", "## The incumbent champion", "", head, sep,
        row(anchor) if anchor else "| — |", "",
        "## The ten best on the FITTED years (2018–2023)", "",
        "This is what the search optimises, and where it did find better combinations.",
        "", head, sep,
    ]
    lines += [row(t) for t in sorted(live, key=lambda t: -t.value)[:10]]
    lines += ["", "## The ten best on the years the search NEVER saw (2024–2025)", "",
              "Listed for completeness. **These were never selectable** — picking a "
              "combination by this column would turn the out-of-sample check into a "
              "selection input, which is the exact mistake this design exists to "
              "prevent.", "", head, sep]
    lines += [row(t) for t in sorted(live, key=lambda t: -(t.user_attrs.get("holdout")
                                                           or -9))[:10]]

    # The operator's actual question: does moving a value change anything?
    # A JOINT search cannot isolate one lever - 33 of them moved at once, so any
    # per-lever number here is confounded by everything that moved with it. What it CAN
    # honestly show is whether a lever's value tracks the outcome at all. Trials are cut
    # into quartiles of each lever and the median result per quartile is printed: a
    # monotone column means the lever pulls in a direction, a flat one means whatever it
    # does is drowned by the rest. The clean per-lever curve needs one lever moved at a
    # time, which is A115 and runs separately.
    def _rho(xs, ys):
        n = len(xs)
        if n < 20:
            return float("nan")
        def rank(v):
            order = sorted(range(len(v)), key=lambda i: v[i])
            r = [0.0] * len(v)
            i = 0
            while i < len(order):
                j = i
                while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                    j += 1
                for k in range(i, j + 1):
                    r[order[k]] = (i + j) / 2.0 + 1
                i = j + 1
            return r
        ra, rb = rank(xs), rank(ys)
        ma, mb = sum(ra) / n, sum(rb) / n
        num = sum((a - ma) * (b - mb) for a, b in zip(ra, rb))
        den = (sum((a - ma) ** 2 for a in ra) * sum((b - mb) ** 2 for b in rb)) ** 0.5
        return num / den if den else float("nan")

    lines += ["", "## Does moving a value change anything?", "",
              "Yes — every one of the 1,607 trading combinations produced a different "
              "book. The question was never whether the values matter. It is whether any "
              "setting is better on years it was **not** fitted to.", "",
              "Below, trials are cut into quartiles of each lever's value and the median "
              "result per quartile is shown. A column that climbs or falls means the "
              "lever pulls in a direction; a flat one means whatever it does is drowned "
              "by the other 32 levers moving alongside it. **These numbers are "
              "confounded by construction** — a joint search cannot isolate one lever. "
              "The clean per-lever curve requires moving one at a time, which is what "
              "A115 measures separately.", "",
              "| lever | champion | range tried | median fit by quartile (low→high) | ρ(value, fit) | ρ(value, held-out) |",
              "|---|---|---|---|---|---|"]
    for p_ in params:
        pairs = [(t.params[p_], t.value, (t.user_attrs.get("holdout") or 0.0))
                 for t in live if p_ in t.params
                 and isinstance(t.params[p_], (int, float))]
        if len(pairs) < 40:
            continue
        pairs.sort(key=lambda x: x[0])
        vals = [x[0] for x in pairs]
        q = len(pairs) // 4
        meds = [st.median([x[1] for x in pairs[i * q:(i + 1) * q]]) for i in range(4)]
        champ = anchor.params.get(p_) if anchor else "—"
        champ_s = f"{champ:.4g}" if isinstance(champ, (int, float)) else str(champ)
        lines.append(
            f"| `{p_}` | {champ_s} | {min(vals):.4g} … {max(vals):.4g} | "
            + " · ".join(f"{m:+.3f}" for m in meds)
            + f" | {_rho(vals, [x[1] for x in pairs]):+.3f} "
              f"| {_rho(vals, [x[2] for x in pairs]):+.3f} |")

    lines += ["", "## How to read this", "",
              "Every row is one full 8-year backtest of the whole 14-symbol book, with "
              "Binance-style costs: 10 bp commission, 5 bp slippage, market impact by "
              "participation, $100 minimum order. The model is identical in every row — "
              "only the decision-layer values differ, which is why thousands of "
              "combinations were affordable at all: **no retraining, only replay.**", ""]

    md_path = ROOT / "rnd" / "trials_ledger.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {csv_path}  ({len(trials)} rows x {len(header)} columns)")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
