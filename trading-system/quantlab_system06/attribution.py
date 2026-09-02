"""Every trade that was POSSIBLE, every trade the book took, and the difference.

Operator, 2026-09-02: *"deberíamos tener una tabla de todos los trades posibles que
hay durante un año... ver qué trade hemos tomado mal y bajo qué indicadores podríamos
haber previsto que iba a salir mal, y al revés, qué trade estamos dejando de hacer"*.

Everything this project has measured so far is an AGGREGATE: a year returns +8% or it
does not, a variant's median score beats the bar or it does not. An aggregate can only
be improved by search - try a change, look at the number, keep or discard - and search
over a noisy number is indistinguishable from randomness, which is exactly what the
iteration cards look like from outside. This file replaces the aggregate with a
LEDGER, so a change can be aimed instead of guessed.

The ledger has four kinds of row, and every trading year is fully partitioned by them:

  won       a trade taken inside a real up-leg that finished positive
  lost      a trade taken that finished negative - the ones to learn to decline
  unforced  a trade taken where the hindsight map says there was no harvestable
            up-move at all: not bad luck, a decision with no material behind it
  missed    an up-leg that cleared costs and the book never entered - the money
            left on the table, which no aggregate has ever made visible

The opportunity set is the same zigzag decomposition the labeller trains on, charged
the engine's real round trip, so "possible" here means possible AFTER costs - never a
hindsight fantasy of buying every tick.

**What this file is and is not.** It is a DIAGNOSTIC. The rules it extracts are fitted
with hindsight on the rows of a finished backtest, so they describe what separated the
good decisions from the bad ones IN THAT SAMPLE. They are candidate levers, not
adopted ones: a rule earns its place only by going through the ordinary paired A/B
with reseeds like any other idea. Fitting is restricted to the research years for that
reason - 2026 rows are carried in the table as a READOUT and never reach `explain()`,
because a rule fitted on 2026 would quietly convert the one honest year into training
data.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import numpy as np

from . import oracle, tree

ROUND_TRIP = 0.003          # 10 bps commission + 5 bps slippage a side - the invariant
THRESHOLD = 0.03            # the champion's zigzag leg size


def _ns(value) -> int:
    """Epoch nanoseconds from a datetime or an ISO string, tz-naive in UTC."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return int(np.datetime64(value, "ns").astype("int64"))


def _year(ns: int) -> int:
    return int(np.datetime64(ns, "ns").astype("datetime64[Y]").astype(int)) + 1970


@dataclass
class Opportunity:
    """One harvestable long leg: the market did offer this, after costs."""

    symbol: str
    year: int
    start_ns: int
    end_ns: int
    gross: float            # peak-to-trough move of the leg
    net: float              # the same move minus one round trip


@dataclass
class Row:
    """One ledger row. `kind` is one of won / lost / unforced / missed."""

    symbol: str
    year: int
    kind: str
    at_ns: int              # the decision bar: trade entry, or the leg's start if missed
    net_pct: float          # realised for a trade, forgone for a missed leg
    opportunity_net: float  # the leg's net move (0.0 for an unforced trade)


def opportunities(bars, *, threshold: float = THRESHOLD,
                  cost: float = ROUND_TRIP, symbol: str = "") -> list[Opportunity]:
    """Every up-leg of the zigzag whose move survives a round trip.

    This is deliberately the SAME decomposition the oracle labeller uses, so the
    opportunity set is the one the model was trained to catch - the table then measures
    the model against its own definition of the job rather than against a new one.
    """
    close = np.array([b.close for b in bars], dtype=float)
    stamps = np.array([_ns(b.timestamp) for b in bars], dtype=np.int64)
    out: list[Opportunity] = []
    pivots = oracle.zigzag_pivots(close, threshold)
    for a, b in zip(pivots, pivots[1:]):
        move = close[b.index] / max(close[a.index], 1e-12) - 1.0
        if move <= 0 or move - cost <= 0:
            continue
        out.append(Opportunity(symbol=symbol, year=_year(int(stamps[a.index])),
                               start_ns=int(stamps[a.index]), end_ns=int(stamps[b.index]),
                               gross=float(move), net=float(move - cost)))
    return out


def reconcile(opps: list[Opportunity], trips: list[dict]) -> list[Row]:
    """Match what the book DID against what was there to be done.

    A trade captures a leg when its ENTRY falls inside the leg's window. Entry rather
    than overlap on purpose: a position still open when a leg begins was not a decision
    to take that leg, and counting it as one would flatter the capture rate with
    coincidence.
    """
    by_symbol: dict[str, list[Opportunity]] = {}
    for o in opps:
        by_symbol.setdefault(o.symbol, []).append(o)
    for legs in by_symbol.values():
        legs.sort(key=lambda o: o.start_ns)

    captured: set[int] = set()
    rows: list[Row] = []
    for t in trips:
        entry = _ns(t["opened"])
        symbol = t.get("symbol", "")
        net = float(t.get("net_pct") or 0.0)
        leg = None
        for i, o in enumerate(by_symbol.get(symbol, [])):
            if o.start_ns <= entry <= o.end_ns:
                leg = o
                captured.add(id(o))
                break
        rows.append(Row(symbol=symbol, year=_year(entry),
                        kind=("won" if net > 0 else "lost") if leg is not None else "unforced",
                        at_ns=entry, net_pct=net,
                        opportunity_net=float(leg.net) if leg is not None else 0.0))
    for o in opps:
        if id(o) not in captured:
            rows.append(Row(symbol=o.symbol, year=o.year, kind="missed", at_ns=o.start_ns,
                            net_pct=float(o.net), opportunity_net=float(o.net)))
    rows.sort(key=lambda r: (r.at_ns, r.symbol))
    return rows


def yearly(rows: list[Row]) -> dict[int, dict]:
    """The table the operator asked for: one line per year, fully partitioned.

    `capture_rate` is the share of harvestable legs the book entered, and
    `left_on_table_pp` the percentage points of net move it declined - the number that
    says whether a thin year was thin in the MARKET or thin in the MODEL.
    """
    out: dict[int, dict] = {}
    for r in rows:
        y = out.setdefault(r.year, {"won": 0, "lost": 0, "unforced": 0, "missed": 0,
                                    "taken_pp": 0.0, "left_on_table_pp": 0.0,
                                    "captured_pp": 0.0})
        y[r.kind] += 1
        if r.kind == "missed":
            y["left_on_table_pp"] += r.net_pct * 100.0
        else:
            y["taken_pp"] += r.net_pct * 100.0
            y["captured_pp"] += r.opportunity_net * 100.0
    for y in out.values():
        taken = y["won"] + y["lost"] + y["unforced"]
        legs = y["won"] + y["lost"] + y["missed"]
        y["trades"] = taken
        y["opportunities"] = legs
        y["hit_rate"] = round(y["won"] / taken, 4) if taken else 0.0
        y["capture_rate"] = round((y["won"] + y["lost"]) / legs, 4) if legs else 0.0
        y["unforced_rate"] = round(y["unforced"] / taken, 4) if taken else 0.0
        for k in ("taken_pp", "left_on_table_pp", "captured_pp"):
            y[k] = round(y[k], 2)
    return dict(sorted(out.items()))


def features_at(bars, at_ns: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """The indicator snapshot at each decision bar, and a mask of which ones resolved.

    Reuses `tree.build_features` rather than growing a second feature set: those twenty
    indicators are the operator's own A32 list (candlestick shape plus probabilistic
    statistics), they are already pinned as causal by their own tests, and a diagnostic
    that invented its own features would explain a book nobody trades.
    """
    X, _y, ns, _fwd = tree.build_features(bars)
    if len(ns) == 0:
        return np.zeros((len(at_ns), len(tree.FEATURES)), dtype=np.float32), \
            np.zeros(len(at_ns), dtype=bool)
    idx = np.searchsorted(ns, np.asarray(at_ns, dtype=np.int64))
    ok = (idx < len(ns))
    idx = np.clip(idx, 0, len(ns) - 1)
    # Only an EXACT bar match is honest here: a near miss would read the indicators of
    # a different bar, and the whole point is what was on screen at the decision.
    ok &= (ns[idx] == np.asarray(at_ns, dtype=np.int64))
    return X[idx], ok


def explain(X: np.ndarray, y: np.ndarray, *, max_depth: int = 3, min_leaf: int = 25,
            seed: int = 42) -> list[dict]:
    """Fit a shallow, readable tree and return its leaves as rules.

    Shallow on purpose. The output has to be a sentence an operator can argue with -
    "when the 96-bar range position was above 0.83, three quarters of the entries lost"
    - not a model. Depth 3 with a floor under the leaf size keeps every rule backed by
    real support; anything deeper describes the sample rather than the market.
    """
    from sklearn.tree import DecisionTreeClassifier

    if len(y) < 4 * min_leaf or len(set(y.tolist())) < 2:
        return []
    clf = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=min_leaf,
                                 random_state=seed)
    clf.fit(X, y)
    t = clf.tree_
    base = float(np.mean(y))
    rules: list[dict] = []

    def walk(node: int, path: list[str]) -> None:
        if t.children_left[node] == -1:
            # sklearn >= 1.3 stores CLASS PROPORTIONS in `value`, not counts, so the
            # support has to come from `n_node_samples`. Reading value.sum() as a count
            # silently reports every leaf as holding one row - a rule with no support
            # dressed as a rule, which is the exact failure this function exists to
            # avoid. Normalised anyway, so an older sklearn behaves identically.
            share = np.asarray(t.value[node][0], dtype=float)
            support = int(t.n_node_samples[node])
            rate = float(share[1] / max(share.sum(), 1e-12)) if share.size > 1 else 0.0
            rules.append({"rule": " AND ".join(path) if path else "(all rows)",
                          "support": support, "rate": round(rate, 4),
                          "lift": round(rate - base, 4)})
            return
        name = tree.FEATURES[t.feature[node]]
        thr = float(t.threshold[node])
        walk(t.children_left[node], [*path, f"{name} <= {thr:.4f}"])
        walk(t.children_right[node], [*path, f"{name} > {thr:.4f}"])

    walk(0, [])
    rules.sort(key=lambda r: r["lift"])
    return rules


def report(rows: list[Row], sealed_year: int = 2026) -> dict:
    """Assemble the ledger into the shape the dashboard and the diary both read."""
    table = yearly(rows)
    research = {y: v for y, v in table.items() if y != sealed_year}
    return {
        "sealed_year": sealed_year,
        "sealed": table.get(sealed_year),
        "research": research,
        "totals": {
            "trades": sum(v["trades"] for v in table.values()),
            "opportunities": sum(v["opportunities"] for v in table.values()),
            "left_on_table_pp": round(sum(v["left_on_table_pp"] for v in table.values()), 2),
        },
        "note": ("Rules are fitted on research years only; the sealed year is carried as a "
                 "readout so it heads the table without ever entering the fit."),
    }


def dump(rows: list[Row], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([asdict(r) for r in rows], fh)
