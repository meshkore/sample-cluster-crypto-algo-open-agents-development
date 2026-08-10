"""A grammar of rules, so the laboratory can invent mechanisms instead of numbers.

A parameter search moves the knobs on rules a person already wrote. It can find
that a 55-day breakout beats a 20-day one; it can never find that the breakout
should also require rising volume, because nobody expressed that. Everything the
search could discover was already decided when the branch classes were written.

So a rule here is **data**: a small expression tree over the seventy-nine
columns the backtester already serves. The loop composes trees, mutates them,
crosses them and scores them, which means it can arrive at

    close > sma_50  AND  adx > 25  AND  supertrend_direction > 0

without anyone having written that class -- and equally at combinations no one
here would have thought to try. That is the difference between tuning a
hypothesis and generating one.

**Why a grammar rather than generated Python.** A tree is checked by
construction: every node is one of a dozen known shapes, every leaf is a column
name that either exists or is rejected, and evaluation touches nothing but the
tick it was handed. There is no arbitrary execution, no import, no filesystem,
and a malformed tree is a rejected genome rather than an incident. It also
serialises to JSON, so an invented rule is a ledger record a stranger can read
and re-run, which generated source in a scratch directory would not be.

**Three-valued on purpose.** A predicate returns True, False, or `None` when a
column it needs has not filled yet. `None` is not False: reading an unfilled
200-day average as zero is how a warm-up bar becomes a trade signal, and this
laboratory has made that mistake in two separate places.
"""

from __future__ import annotations

from typing import Any, Sequence
import random

# Which served columns a generated rule may reference, grouped so a generator
# can build something coherent rather than comparing an RSI to a dollar volume.
# Anything absent here is not reachable by evolution -- adding a family is how
# a contributor widens what the loop can invent.
# The four components of a single bar. Their ordering is fixed by definition --
# low <= open <= high and low <= close <= high -- so comparing any two of them
# is arithmetic about what a candle IS, never a signal about the market.
OHLC: frozenset[str] = frozenset({"open", "high", "low", "close"})

PRICE_LIKE: tuple[str, ...] = (
    "sma_5",
    "sma_10",
    "sma_20",
    "sma_50",
    "sma_100",
    "sma_200",
    "ema_9",
    "ema_12",
    "ema_21",
    "ema_26",
    "ema_50",
    "ema_200",
    "wma_20",
    "bb_mid",
    "bb_upper",
    "bb_lower",
    "keltner_mid",
    "keltner_upper",
    "keltner_lower",
    "high_20",
    "high_55",
    "high_200",
    "low_20",
    "low_55",
    "low_200",
    "mid_20",
    "mid_55",
    "mid_200",
    "supertrend",
    "vwap_rolling",
    "ichimoku_tenkan",
    "ichimoku_kijun",
    "running_high",
)
OSCILLATORS: dict[str, tuple[float, float]] = {
    "rsi_7": (0.0, 100.0),
    "rsi_14": (0.0, 100.0),
    "rsi_21": (0.0, 100.0),
    "stoch_k": (0.0, 100.0),
    "stoch_d": (0.0, 100.0),
    "williams_r": (-100.0, 0.0),
    "adx": (0.0, 60.0),
    "di_plus": (0.0, 60.0),
    "di_minus": (0.0, 60.0),
    "aroon_up": (0.0, 100.0),
    "aroon_down": (0.0, 100.0),
    "aroon_osc": (-100.0, 100.0),
    "money_flow_index": (0.0, 100.0),
    "cci": (-250.0, 250.0),
    "bb_percent_b": (-0.5, 1.5),
    "vortex_plus": (0.5, 1.5),
    "vortex_minus": (0.5, 1.5),
    "natr_14": (0.0, 0.20),
    "natr_20": (0.0, 0.20),
    "chaikin_money_flow": (-0.6, 0.6),
}
RATIOS: dict[str, tuple[float, float]] = {
    "return_1": (-0.20, 0.20),
    "return_5": (-0.40, 0.40),
    "return_20": (-0.60, 0.80),
    "return_60": (-0.80, 1.50),
    "return_252": (-0.90, 3.00),
    "distance_to_sma_50": (-0.50, 0.50),
    "distance_to_sma_200": (-0.70, 1.00),
    "drawdown_from_high": (0.0, 0.95),
    "pct_below_high_20": (0.0, 0.60),
    "pct_below_high_55": (0.0, 0.80),
    "pct_below_high_200": (0.0, 0.95),
    "bb_width": (0.0, 0.60),
    "macd_hist": (-0.05, 0.05),
    "supertrend_direction": (-1.0, 1.0),
}
VOLUME_LIKE: tuple[str, ...] = ("volume_sma_20", "volume_sma_50")
CANDLE_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume")

KNOWN_COLUMNS: frozenset[str] = frozenset(
    (*PRICE_LIKE, *OSCILLATORS, *RATIOS, *VOLUME_LIKE)
)

PREDICATES = ("gt", "lt", "cross_up", "cross_down", "and", "or", "not")

# How large an invented rule may get. Not a performance limit: a
# forty-node rule that fits four folds is an overfit wearing a
# mechanism's clothes, and nobody can argue with it afterwards.
MAXIMUM_SIZE = 24


class GrammarError(ValueError):
    """A tree that cannot be evaluated. A dead genome, never a dead search."""


# --------------------------------------------------------------------------- #
# Evaluation


def _value(
    node: Any,
    candle: dict,
    row: dict,
    previous_row: dict,
    previous_candle: dict,
    back: bool,
) -> float | None:
    """Resolve a value node. `back` asks for the PREVIOUS bar's reading.

    One function for both bars rather than two: a crossing is the same
    comparison evaluated twice, and writing it twice is how the two copies
    drift.
    """
    if not isinstance(node, dict):
        raise GrammarError(f"value node must be an object, got {type(node).__name__}")
    kind = node.get("t")
    if kind == "num":
        return float(node["v"])
    if kind == "col":
        name = node.get("name")
        if name not in KNOWN_COLUMNS:
            raise GrammarError(f"unknown column {name!r}")
        source = previous_row if back else row
        value = source.get(name)
        return None if value is None else float(value)
    if kind == "px":
        name = node.get("name")
        if name not in CANDLE_FIELDS:
            raise GrammarError(f"unknown candle field {name!r}")
        source = previous_candle if back else candle
        value = source.get(name)
        return None if value is None else float(value)
    if kind == "mul":
        # `close > sma_50 * 1.02` -- a band around a level, which the column
        # set cannot express on its own.
        left = _value(node["a"], candle, row, previous_row, previous_candle, back)
        right = _value(node["b"], candle, row, previous_row, previous_candle, back)
        return None if left is None or right is None else left * right
    raise GrammarError(f"unknown value node {kind!r}")


def evaluate(
    node: Any, candle: dict, row: dict, previous_row: dict, previous_candle: dict
) -> bool | None:
    """True, False, or None when the rule needs a column that has not filled.

    `None` propagates: an AND with one unknown term is unknown, not False. A
    branch that treated it as False would silently stop trading whenever any
    referenced window was still warming, and would look like a conservative
    rule rather than a broken one.
    """
    if not isinstance(node, dict):
        raise GrammarError(f"predicate must be an object, got {type(node).__name__}")
    kind = node.get("t")

    if kind == "always":
        return True
    if kind == "never":
        return False

    if kind in ("gt", "lt"):
        left = _value(node["a"], candle, row, previous_row, previous_candle, False)
        right = _value(node["b"], candle, row, previous_row, previous_candle, False)
        if left is None or right is None:
            return None
        return left > right if kind == "gt" else left < right

    if kind in ("cross_up", "cross_down"):
        now_left = _value(node["a"], candle, row, previous_row, previous_candle, False)
        now_right = _value(node["b"], candle, row, previous_row, previous_candle, False)
        was_left = _value(node["a"], candle, row, previous_row, previous_candle, True)
        was_right = _value(node["b"], candle, row, previous_row, previous_candle, True)
        if None in (now_left, now_right, was_left, was_right):
            return None
        if kind == "cross_up":
            return was_left <= was_right and now_left > now_right
        return was_left >= was_right and now_left < now_right

    if kind in ("and", "or"):
        terms = node.get("xs") or []
        if not terms:
            raise GrammarError(f"{kind} needs at least one term")
        seen = [
            evaluate(term, candle, row, previous_row, previous_candle) for term in terms
        ]
        if kind == "and":
            if any(v is False for v in seen):
                return False
            return None if any(v is None for v in seen) else True
        if any(v is True for v in seen):
            return True
        return None if any(v is None for v in seen) else False

    if kind == "not":
        inner = evaluate(node["x"], candle, row, previous_row, previous_candle)
        return None if inner is None else not inner

    raise GrammarError(f"unknown predicate {kind!r}")


def columns_used(node: Any) -> set[str]:
    """Every column a tree reads. Used to reject a rule nothing can feed."""
    found: set[str] = set()
    if not isinstance(node, dict):
        return found
    if node.get("t") == "col" and node.get("name"):
        found.add(node["name"])
    for key in ("a", "b", "x"):
        if key in node:
            found |= columns_used(node[key])
    for term in node.get("xs") or []:
        found |= columns_used(term)
    return found


def size(node: Any) -> int:
    """Node count. The generator penalises bulk: a forty-node rule that fits a
    fold is an overfit wearing a mechanism's clothes."""
    if not isinstance(node, dict):
        return 0
    total = 1
    for key in ("a", "b", "x"):
        if key in node:
            total += size(node[key])
    for term in node.get("xs") or []:
        total += size(term)
    return total


def describe(node: Any) -> str:
    """The tree as something a person can argue with.

    An invented rule that cannot be read is not a contribution to a laboratory,
    it is a black box with a good backtest.
    """
    if not isinstance(node, dict):
        return "?"
    kind = node.get("t")
    if kind == "num":
        return f"{float(node['v']):g}"
    if kind in ("col", "px"):
        return str(node.get("name"))
    if kind == "mul":
        return f"{describe(node['a'])}*{describe(node['b'])}"
    if kind == "always":
        return "always"
    if kind == "never":
        return "never"
    if kind == "gt":
        return f"{describe(node['a'])} > {describe(node['b'])}"
    if kind == "lt":
        return f"{describe(node['a'])} < {describe(node['b'])}"
    if kind == "cross_up":
        return f"{describe(node['a'])} crosses above {describe(node['b'])}"
    if kind == "cross_down":
        return f"{describe(node['a'])} crosses below {describe(node['b'])}"
    if kind == "not":
        return f"NOT ({describe(node['x'])})"
    if kind in ("and", "or"):
        joiner = " AND " if kind == "and" else " OR "
        return "(" + joiner.join(describe(t) for t in node.get("xs") or []) + ")"
    return "?"


# --------------------------------------------------------------------------- #
# Generation


def _price_value(rng: random.Random) -> dict:
    if rng.random() < 0.35:
        return {"t": "px", "name": rng.choice(("close", "high", "low"))}
    return {"t": "col", "name": rng.choice(PRICE_LIKE)}


def _comparison(rng: random.Random) -> dict:
    """One atomic test. Comparable things are compared with comparable things.

    Generating `rsi_14 > sma_200` is legal arithmetic and meaningless finance;
    it would fill the population with noise that the objective then has to
    reject one expensive backtest at a time.
    """
    family = rng.random()
    operator = rng.choice(("gt", "lt", "cross_up", "cross_down"))

    if family < 0.40:
        # Price against a level, optionally with a band around it. The two
        # sides must NAME different things: `low > low` is a constant, and
        # `high > high*0.998` is a constant wearing a comparison's clothes.
        # The first generator produced both, and each one costs four backtests
        # to discover it says nothing.
        left = _price_value(rng)
        for _ in range(8):
            right = _price_value(rng)
            if right.get("name") != left.get("name"):
                break
        else:
            right = {"t": "col", "name": rng.choice(PRICE_LIKE)}
        if rng.random() < 0.30:
            right = {
                "t": "mul",
                "a": right,
                "b": {"t": "num", "v": round(rng.uniform(0.90, 1.10), 4)},
            }
        return {"t": operator, "a": left, "b": right}

    if family < 0.70:
        name = rng.choice(sorted(OSCILLATORS))
        low, high = OSCILLATORS[name]
        return {
            "t": rng.choice(("gt", "lt")),
            "a": {"t": "col", "name": name},
            "b": {"t": "num", "v": round(rng.uniform(low, high), 3)},
        }

    if family < 0.90:
        name = rng.choice(sorted(RATIOS))
        low, high = RATIOS[name]
        return {
            "t": rng.choice(("gt", "lt")),
            "a": {"t": "col", "name": name},
            "b": {"t": "num", "v": round(rng.uniform(low, high), 4)},
        }

    # volume against its own average, as a multiple
    return {
        "t": rng.choice(("gt", "lt")),
        "a": {"t": "px", "name": "volume"},
        "b": {
            "t": "mul",
            "a": {"t": "col", "name": rng.choice(VOLUME_LIKE)},
            "b": {"t": "num", "v": round(rng.uniform(0.4, 6.0), 2)},
        },
    }


def _grow(rng: random.Random, depth: int) -> dict:
    if depth <= 0 or rng.random() < 0.35:
        return _comparison(rng)
    kind = "and" if rng.random() < 0.70 else "or"
    count = 2 if rng.random() < 0.75 else 3
    terms = [_grow(rng, depth - 1) for _ in range(count)]
    if rng.random() < 0.10:
        terms[0] = {"t": "not", "x": terms[0]}
    return {"t": kind, "xs": terms}


def random_rule(
    rng: random.Random, depth: int = 2, maximum_size: int = MAXIMUM_SIZE
) -> dict:
    """A tree, shallow by default, and never larger than the cap.

    Depth is capped low because expressive power is not the constraint here --
    evidence is. Two or three joined comparisons is already a mechanism nobody
    wrote; twelve is a curve fitted to four folds.

    Depth alone does not bound size: three branches of three at depth two
    reaches twenty-five nodes and the validator rejected it, so generation
    would hand the search dead genomes at random. It retries smaller instead.
    """
    for attempt in range(6):
        rule = _grow(rng, max(0, depth - attempt // 2))
        if size(rule) <= maximum_size and not degenerate(rule):
            return rule
    return _comparison(rng)


def _nodes(node: Any, path: tuple = ()) -> list[tuple]:
    """Every addressable subtree, so mutation can pick one uniformly."""
    found = [path]
    if isinstance(node, dict):
        for key in ("a", "b", "x"):
            if key in node:
                found += _nodes(node[key], path + (key,))
        for index, term in enumerate(node.get("xs") or []):
            found += _nodes(term, path + ("xs", index))
    return found


def _get(node: Any, path: tuple) -> Any:
    for step in path:
        node = node[step]
    return node


def _replace(node: Any, path: tuple, value: Any) -> Any:
    if not path:
        return value
    import copy

    out = copy.deepcopy(node)
    target = out
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    return out


def mutate_rule(node: dict, rng: random.Random, depth: int = 2) -> dict:
    """Replace one subtree. A local edit, not a re-roll.

    Re-rolling the whole rule throws away everything the parent knew, which is
    the same mistake uniform re-sampling makes on a numeric dimension.
    """
    # The ROOT is the empty path, and `p[-1]` on it raises. The first
    # version indexed it unconditionally and every mutation crashed.
    paths = [p for p in _nodes(node) if p]
    if not paths:
        return random_rule(rng, depth)
    target = rng.choice(paths)
    existing = _get(node, target)
    if not isinstance(existing, dict):
        return random_rule(rng, depth)
    # Replace a predicate with a predicate and a value with a value, or the
    # tree stops type-checking and every child is a dead genome.
    if existing.get("t") in ("num", "col", "px", "mul"):
        replacement = (
            _price_value(rng)
            if rng.random() < 0.5
            else {"t": "num", "v": round(rng.uniform(-1.0, 100.0), 3)}
        )
    else:
        replacement = random_rule(rng, max(0, depth - len(target) // 2))
    grown = _replace(node, target, replacement)
    # Mutation can push a tree past the cap or reintroduce a self-comparison.
    # Returning the parent is better than returning a genome the validator will
    # kill: the lineage survives and the next mutation tries again.
    if size(grown) > MAXIMUM_SIZE or degenerate(grown):
        return node
    return grown


def crossover_rules(a: dict, b: dict, rng: random.Random) -> dict:
    """Graft a predicate subtree of `b` onto `a`."""
    a_paths = [
        p
        for p in _nodes(a)
        if isinstance(_get(a, p), dict)
        and _get(a, p).get("t") not in ("num", "col", "px", "mul")
    ]
    b_paths = [
        p
        for p in _nodes(b)
        if isinstance(_get(b, p), dict)
        and _get(b, p).get("t") not in ("num", "col", "px", "mul")
    ]
    if not a_paths or not b_paths:
        return a
    child = _replace(a, rng.choice(a_paths), _get(b, rng.choice(b_paths)))
    if size(child) > MAXIMUM_SIZE or degenerate(child):
        return a
    return child


def _operand_name(node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    if node.get("t") == "mul":
        return _operand_name(node.get("a"))
    return node.get("name")


def _family(node: Any) -> str | None:
    """Which units this operand is in, or None when it is a bare number.

    A constant is comparable with anything -- that is what a threshold is.
    Two COLUMNS in different units are not: `di_plus < bb_upper` compares a
    0-60 index against a price level and is true for every asset above sixty
    dollars, for ever. The generator never builds one; mutation does, by
    replacing one side of a coherent comparison, and each one costs a full
    fold set to discover it says nothing.
    """
    name = _operand_name(node)
    if name is None:
        return None
    if name in PRICE_LIKE or name in CANDLE_FIELDS:
        return "price"
    if name in OSCILLATORS:
        return "oscillator"
    if name in RATIOS:
        return "ratio"
    if name in VOLUME_LIKE:
        return "volume"
    return None


def degenerate(node: Any) -> str | None:
    """Why this tree says nothing, or None if it says something.

    Checked before a genome is scored rather than after: a comparison of a
    thing with itself costs four full backtests to discover it is a constant,
    and mutation reintroduces it constantly.
    """
    if not isinstance(node, dict):
        return None
    kind = node.get("t")
    if kind in ("gt", "lt", "cross_up", "cross_down"):
        left, right = node.get("a"), node.get("b")
        left_name = _operand_name(left)
        if left_name is not None and left_name == _operand_name(right):
            return f"{left_name} compared with itself"
        # `close > close * 1.02` is also constant: same name, one scaled.
        if isinstance(right, dict) and right.get("t") == "mul":
            if left_name is not None and left_name == _operand_name(right.get("a")):
                return f"{left_name} compared with a multiple of itself"
        # Within one bar, low <= open <= high and low <= close <= high, always.
        # So `high > close` is not a signal, it is the definition of a bar --
        # true on every candle but a doji -- and `high crosses above low` can
        # never fire at all. The search paid four backtests each to discover
        # these, and mutation kept reintroducing them: `high > close`,
        # `high crosses below close`, `high crosses above low` all reached the
        # ledger as invented rules.
        if left_name in OHLC and _operand_name(right) in OHLC:
            return f"{left_name} against {_operand_name(right)} in the same bar"
        left_family, right_family = _family(left), _family(right)
        if left_family and right_family and left_family != right_family:
            # "volume" against "price" is the one legal cross: `volume >
            # volume_sma_20 * 3` is built that way on purpose.
            if {left_family, right_family} != {"price", "volume"}:
                return f"{left_family} compared with {right_family}"
    for key in ("a", "b", "x"):
        if key in node and (why := degenerate(node[key])):
            return why
    for term in node.get("xs") or []:
        if why := degenerate(term):
            return why
    return None


def validate(node: Any, maximum_size: int = MAXIMUM_SIZE) -> dict:
    """Reject a tree before it costs a backtest, not during one."""
    if size(node) > maximum_size:
        raise GrammarError(f"rule of {size(node)} nodes exceeds {maximum_size}")
    unknown = columns_used(node) - KNOWN_COLUMNS
    if unknown:
        raise GrammarError(f"unknown columns {sorted(unknown)}")
    if why := degenerate(node):
        raise GrammarError(f"the rule says nothing: {why}")
    # A dry run against an empty tick surfaces structural errors -- a missing
    # operand, an unknown node -- as an exception here rather than on bar 900
    # of a backtest.
    evaluate(node, {}, {}, {}, {})
    return node


def default_columns() -> Sequence[str]:
    return sorted(KNOWN_COLUMNS)
