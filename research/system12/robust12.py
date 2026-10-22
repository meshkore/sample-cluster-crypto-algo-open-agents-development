"""System 12 - task 10: is champion v5 (frozen book + Fed net-liquidity filter) robust enough to call investable?

    1. Parameter sensitivity: every one of the rule's 8 parameter sets and 3 ways of combining it, every year, against the
       frozen book (no walk-forward choice: a robust edge should not depend on picking the right set).
    2. Costs x2 and x3.
    3. Block bootstrap of the walk-forward chain's daily returns (30-day blocks, 365-day years): P(year >= 0), P(year >= +20%),
       median and 5th-percentile year, P(drawdown > 40%) - frozen book vs champion.
    -> robust/ROBUST.md

    python research/system12/robust12.py
"""

from __future__ import annotations

import itertools
import json

import numpy as np

import catalog12 as C
import hyp12
import hypotheses12 as HY
import gen12

OUT = hyp12.HERE / "robust"
YEARS = (2021, 2022, 2023, 2024, 2025, 2026)
SID = "mac-dharmatech-netliq-fairvalue"


def boot(d, rng, n=4000, block=30, year=365):
    d = np.asarray(d, dtype=float)
    ys, dds = [], []
    for _ in range(n):
        starts = rng.integers(0, len(d) - block, size=year // block + 1)
        s = np.concatenate([d[a:a + block] for a in starts])[:year]
        eq = np.cumprod(1 + s)
        ys.append(eq[-1] - 1)
        dds.append(float((1 - eq / np.maximum.accumulate(eq)).max()))
    ys, dds = np.array(ys), np.array(dds)
    return {"p_pos": float((ys >= 0).mean()), "p_20": float((ys >= 0.2).mean()), "median": float(np.median(ys)),
            "p5": float(np.quantile(ys, 0.05)), "p_dd40": float((dds > 0.4).mean())}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    lab = hyp12.Lab()
    x = lab.x
    reg = {h.id: h for h in HY.ALL + gen12.load()}
    book = C.Book()
    st = {s["id"]: s for s in C.load_raw()}[SID]
    Y = lambda W, N, half=None: hyp12.L.B.yearly(  # noqa: E731
        hyp12.L.H.to_daily(x.w, hyp12.L.H.bar_returns(x.w, W, half if half is not None else hyp12.L.LV.PERP_HALF, x.fund)[0])[0],
        lab.dy, (N,))[N]
    froz = {N: Y(lab.base[N], N) for N in YEARS}
    L = ["# Champion v5 - robustness (task 10)", "", "## 1. Every parameter set of the net-liquidity rule x every way of combining it",
         "", "Return per year; **bold** = below the frozen book that year.", "",
         "| params | mode | " + " | ".join(map(str, YEARS)) + " | years >= frozen |", "|---|---|" + "---|" * (len(YEARS) + 1),
         "| frozen book | - | " + " | ".join(f"{froz[N]:+.0%}" for N in YEARS) + " | - |"]
    keys = list(st["params"])
    allsets = [dict(zip(keys, c)) for c in itertools.product(*[st["params"][k] for k in keys])]
    good = 0
    for ps in allsets:
        Ws = book.weights(st, ps)
        Ws = np.r_[Ws, np.zeros((max(0, x.T - len(Ws)), Ws.shape[1]))][:x.T]
        for mode in (("filter", 1.0), ("blend", 0.25), ("blend", 0.5)):
            row = []
            for N in YEARS:
                W = lab.base[N]
                if mode[0] == "filter":
                    W2 = x.scale_long(W, (np.maximum(Ws, 0).sum(axis=1) > 1e-9).astype(float))
                else:
                    W2 = (1 - mode[1]) * W + mode[1] * Ws
                row.append(Y(np.where(x.eng.can, W2, 0.0), N))
            ok = sum(r >= froz[N] - 1e-4 for r, N in zip(row, YEARS))
            good += ok == len(YEARS)
            L.append(f"| {ps} | {mode[0]} {mode[1] if mode[0] == 'blend' else ''} | "
                     + " | ".join((f"**{r:+.0%}**" if r < froz[N] - 1e-4 else f"{r:+.0%}") for r, N in zip(row, YEARS)) + f" | {ok}/6 |")
    L += ["", f"{good} of {len(allsets) * 3} variants are at least as good as the frozen book in all 6 years.", ""]

    champ = hyp12.load_champ()
    chain_c, chain_f = [], []
    L += ["## 2. Costs (walk-forward champion v5, as on the page)", "", "| costs | " + " | ".join(map(str, YEARS)) + " |",
          "|---|" + "---|" * len(YEARS)]
    for k in (1, 2, 3):
        row = []
        for N in YEARS:
            W = lab.champion_W(champ, N, reg)
            row.append(Y(W, N, hyp12.L.LV.PERP_HALF * k))
            if k == 1:
                yr = lab.dy == N
                chain_c.append(lab.daily(W)[yr])
                chain_f.append(lab.daily(lab.base[N])[yr])
        L.append(f"| x{k} | " + " | ".join(f"{r:+.0%}" for r in row) + " |")
    rng = np.random.default_rng(0)
    bc, bf = boot(np.concatenate(chain_c), rng), boot(np.concatenate(chain_f), rng)
    L += ["", "## 3. Block bootstrap of 2021-2026 daily returns (30-day blocks, 4,000 synthetic years)", "",
          "| | P(year >= 0) | P(year >= +20%) | median year | 5% worst year | P(drawdown > 40%) |", "|---|---|---|---|---|---|"]
    for name, b in (("frozen book", bf), ("champion v5", bc)):
        L.append(f"| {name} | {b['p_pos']:.0%} | {b['p_20']:.0%} | {b['median']:+.0%} | {b['p5']:+.0%} | {b['p_dd40']:.0%} |")
    (OUT / "ROBUST.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "bootstrap.json").write_text(json.dumps({"frozen": bf, "champion": bc}, indent=1), encoding="utf-8")
    print("\n".join(L[-14:]))
    print(f"variants >= frozen every year: {good}/{len(allsets) * 3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
