"""The never-ending loop: diagnose, propose, consult, fit, one forward shot, record.

This is the thing the operator asked for. Not a script that runs a backtest, but
a process that decides *what to run next* from what the last run did, argues
about it in public, tries it, records the verdict whichever way it falls, and
goes again. There is no terminal state. A better result is always reachable, so
"done" is not a condition this can be in.

    FRAME     diagnose the last TRAINING run -> which module is losing money
    CONSULT   post the framed hypothesis; ask the proposer; let the critic refute
              it; let the reviewer check it against the code
    COMPOSE   build the population: the incumbent, plus seeds, plus invention
    FIT       genetic search over four disjoint folds, everything <= 2025-12-31
    DECIDE    the fold score against the incumbent's, and the training
              attribution for whether the module was exercised. The verdict is
              settled here.
    FORWARD   if the fit cleared the gate, open 2026 ONCE and record what it says
    RECORD    append the ledger, post the result, update the incumbent or not

**2026 IS REPORTED AND NEVER WEIGHED.** The fit was always clean -- the folds
end at the lock and the service they fit against cannot serve a later bar. The
SELECTION was not: `improved` compared the 2026 return against the incumbent's
2026 return, the incumbent moved on that comparison, and COMPOSE seeds every
subsequent population from the incumbent. So the sealed window chose the genome
that shaped the next search, and FRAME read the same window to choose what to
work on next. Eighty-seven iterations were selected that way before the Codex
reviewer named it in public on iteration 87.

Each individual fit was honest and the sequence of them was not, which is what
makes this kind of leak hard to see: there is no single run to point at. The
verdict is now settled before the forward window opens -- not as a style
choice, but so that a reader can see 2026 could not have been consulted,
because at that point it has not happened yet.

**What makes it converge rather than wander.** Three things. The diagnosis picks
the target module from arithmetic rather than from a guess, so effort lands
where the money is being lost -- arithmetic over the fittable era. The incumbent only moves when a candidate beats
it on the folds, so a bad iteration costs time and nothing else. And the ledger
is consulted before every proposal, so iteration forty knows what one through
thirty-nine already killed -- re-running dead ideas is the only way a loop like
this actually fails.

**What it may not do, ever.** It cannot write code: it composes rule trees,
which are data validated by the grammar. It cannot see past 2025-12-31 while
fitting: the fold windows refuse it and the service it fits against cannot serve
those bars. It opens the forward window at most once per hypothesis, and it
records the number before forming an opinion about it. If an iteration produces
a worse forward result, that is a recorded refutation and the loop continues --
which is the normal case and is the point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import hashlib
import json
import time
import traceback

from quantlab_trading import grammar
from quantlab_trading.regime_system import BRANCHES, FourModuleBrain
from quantlab_trading.seeds import seeds_for
from quantlab_trading.space import Dimension, SearchSpace

from . import advisors as advisors_module
from . import benchmarks
from . import diary
from . import search
from . import team
from . import evolve as evolve_module
from . import tuning
from .backtests import era_of
from .diagnosis import diagnose, summarise
from .search import HISTORY_BEGINS, LOCK, GeneticSearch, folds

# Which genome keys belong to which module, so an iteration can move one piece
# and hold the other three still. Improving a system by changing everything at
# once produces a number nobody can attribute.
MODULE_KEYS: dict[str, tuple[str, ...]] = {
    "BULL": ("bull_rule", "bull_weight", "bull_entry_rule", "bull_exit_rule"),
    "SIDEWAYS": (
        "sideways_rule",
        "sideways_weight",
        "sideways_entry_rule",
        "sideways_exit_rule",
    ),
    "BEAR": ("bear_rule", "bear_weight", "bear_entry_rule", "bear_exit_rule"),
    "DETECTOR": (
        "trend_period",
        "slope_period",
        "confirmation_bars",
        "bull_breadth",
        "bear_breadth",
        # The two levers H-L081D added. Without them the search's best
        # REACHABLE detector still had a BEAR label whose forward return was
        # positive: the mandatory slope test was a cage no range could open,
        # and breadth was pinned to a 200-bar window. Leaving them out of this
        # tuple would ship the levers and never move them.
        "breadth_key",
        "require_slope",
        # What "the market" is, and how assets are weighted into it. The
        # detector read six survivors and called that the market; H-L086M
        # measured that the whole listed universe orders the market's own
        # forward return correctly where the basket does not.
        "market_scope",
        "weighting",
        # The three levels (H-L087C). The detector produced 74 phases in 8.4
        # years -- a median of 28 days, so a fortnight's bounce could rename the
        # market and reroute the trading module. `minimum_phase` floors the
        # routing level; the `cycle_*` four date the global trend the chart
        # colours by, which now runs six phases with a 14-month median.
        "minimum_phase",
        "cycle_smoothing",
        "cycle_bear_swing",
        "cycle_bull_swing",
        "cycle_minimum_phase",
        "bear_min_depth",
        "bear_min_age",
        # How a symbol gets its regime: from the market-wide detector, or from
        # its own. Never moved in 58 iterations, and it is the difference
        # between "2026 is a bear market so hold nothing" and "this asset is
        # rising inside a falling market". The ledger records that in 2026 the
        # median asset fell 47% while 40 of 399 rose, several above +100%; at
        # market scope not one of them is reachable, because every bar of that
        # year classifies BEAR and only the bear branch is ever asked.
        "regime_scope",
    ),
    # Sizing, stops and how much of the book one idea may hold. CONTRACT.md:
    # "Sizing, stops and the drawdown mandate are decisions, so they are part of
    # the hypothesis space." They were outside it for 58 iterations -- no
    # iteration could reach a single one of them -- while the champion ran at
    # 3.1% average exposure and 7.65% time in market. The system's problem is
    # not that it cannot find trades; it is that it barely takes any.
    "POLICY": (
        "risk_per_trade",
        "risk_distance_pct",
        "stop_loss_pct",
        "take_profit_pct",
        "maximum_position_fraction",
        "maximum_concurrent_assets",
        "maximum_holding_days",
    ),
}

# Modules that take no trades under their own name. The DETECTOR decides which
# branch acts; POLICY decides how much every branch commits. Both change the
# result without ever appearing in an attribution, so neither can be asked to
# show up there before its hypothesis counts as tested.
UNATTRIBUTED_MODULES: frozenset[str] = frozenset({"DETECTOR", "POLICY"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tested_the_module(module: str, attribution: dict[str, Any] | None) -> bool:
    """Did the sealed window actually exercise the piece this iteration moved?

    A forward run can trade ninety-six times and still say nothing about the
    module under test. On H-L057 every one of those trades belonged to BEAR:
    the sideways module never fired in 2026, so the run came back bit-identical
    to the incumbent's -- same return to four decimals, same trade count -- and
    was recorded REFUTED. That claims 2026 rejected a sideways idea. 2026 never
    saw one.

    DETECTOR and POLICY are exempt by construction. Neither takes a trade under
    its own name -- the detector decides which branch acts, policy decides how
    much every branch commits -- so their effect shows up as a change in the MIX
    of attributions, or in the size of what is already there, rather than as a
    key of their own.
    """
    if module in UNATTRIBUTED_MODULES:
        return True
    return int(((attribution or {}).get(module) or {}).get("trades") or 0) > 0


def statement_for(module: str, proposal: dict[str, Any] | None) -> str:
    """What this iteration will be recorded as having tried.

    The claim is only adopted when the proposal is about the module the
    iteration is actually moving. Attaching a sentence about BEAR to a run that
    moved position sizing would make the ledger describe something that did not
    happen -- latent until POLICY existed and the proposer, whose schema did not
    list it, answered about something else.

    The fallback has to fit the module too. DETECTOR and POLICY have no rule
    trees, so claiming an iteration evolved their "entry and exit rules" is a
    false statement in a record whose whole purpose is to be true.
    """
    if proposal and proposal.get("module") == module:
        return str(proposal.get("claim") or "")
    _, slots = module_space(module)
    if slots:
        return (
            f"Evolving the {module} module's entry and exit rules over the "
            f"served columns improves the walk-forward score without breaching "
            f"the drawdown mandate."
        )
    return (
        f"Moving the {module} module's parameters improves the walk-forward "
        f"score without breaching the drawdown mandate."
    )


def verdict_of(traded: bool, acted: bool, improved: bool) -> str:
    """What the ledger is entitled to claim about this iteration.

    The distinction the ledger exists for: a hypothesis that was tested and
    failed is evidence, and a hypothesis that was never tested is not. Calling
    the second one REFUTED spends a real refutation on nothing and tells the
    next contributor a direction is dead when nobody has been down it.
    """
    if improved:
        return "CONFIRMED"
    if not traded:
        # A configuration that stood aside for the whole of 2026 HAS been
        # tested: standing aside is what it does. That is a refutation, and it
        # is the verdict every such run in this ledger already carries.
        return "REFUTED"
    if not acted:
        return "INCONCLUSIVE"
    return "REFUTED"


def module_space(module: str) -> tuple[SearchSpace, tuple[str, ...]]:
    """The sub-space one iteration is allowed to move, and its rule slots.

    Everything outside it is pinned to the incumbent. A search that could move
    all twenty-eight dimensions plus three rule trees would find *a* better
    number and teach nobody anything about which piece produced it.
    """
    full = {d.name: d for d in FourModuleBrain.search_space().dimensions}
    prefix = module.lower()
    # These two are named lists rather than prefixes: their dimensions are not
    # called `detector_*` or `policy_*`, and prefix matching silently returned
    # an empty sub-space for anything it did not recognise.
    if module in ("DETECTOR", "POLICY"):
        names = MODULE_KEYS[module]
        return SearchSpace(tuple(full[n] for n in names if n in full)), ()

    dimensions = [d for name, d in full.items() if name.startswith(f"{prefix}_")]
    # The branch is forced to `evolved` so the iteration is about the SHAPE of
    # the rule. Leaving the rule name free would let the search escape into the
    # six hand-written mechanisms and never exercise the grammar at all.
    dimensions = [d for d in dimensions if d.name != f"{prefix}_rule"]
    dimensions.append(Dimension(f"{prefix}_rule", choices=("evolved",)))
    return (
        SearchSpace(tuple(dimensions)),
        (f"{prefix}_entry_rule", f"{prefix}_exit_rule"),
    )


# How many iterations the loop keeps in mind. The gate reads this history, so
# the bound is not merely a disk-size choice: it is how far back "the best score
# for this module" looks.
#
# It has to be applied in memory as well as on disk. It was applied only when
# writing the file, so a long-lived process kept every iteration it had ever run
# while a restarted one reloaded the last forty -- and the gate therefore
# answered differently depending on how recently the process had been restarted.
# The bear module was refused against a score from iteration 1 that no restarted
# process could even see.
HISTORY_LIMIT = 40

# Sizing knobs and the bounds the search may move them between, mirrored from
# `regime_system`'s dimensions. Duplicated deliberately: this migration must not
# be able to write a value the search would then refuse to carry.
RISK_PER_TRADE_CEILING = 0.05

# The v1 objective paid for shrinking, and the incumbent obliged: by iteration 91
# it risked 0.54% per trade at a 34% sizing distance -- 1.58% of the book per
# position. That genome is an artefact of a defect rather than a finding, and it
# is not merely a small version of a good strategy. Measured over 2018-2025:
#
#     size   return   worst dd   return/dd
#       1x    -2.29%    10.33%       -0.22   <- where v1 left it: it LOSES
#       2x   +26.16%    15.46%       +1.69   <- here
#       3x   +43.79%    20.55%       +2.13
#       4x   +68.20%    23.01%       +2.96   <- 2% from the mandate
#
# `notional_for` returns zero below `minimum_position_fraction`, so shrinking
# deletes positions rather than scaling them; at 1x enough of the strategy is
# missing that it stops working. 4x scores best and is not the choice: a 23%
# worst-fold drawdown against a 25% abort is not a place to put an incumbent by
# decree. 2x is already positive with half the drawdown, and the v2 objective
# rewards climbing further on the search's own evidence, which is the difference
# between a migration and a decision.
SIZING_MIGRATION_MULTIPLE = 2.0


def lift_sizing_to_the_floor(incumbent: dict[str, Any]) -> dict[str, Any]:
    """One-time v1 -> v2 migration of the incumbent's position size.

    Changing an incumbent by hand is not something this loop does, and it is
    justified once: the objective that produced this genome rewarded shrinking
    it, so the genome is an artefact of a defect rather than a finding. Left
    alone the search would start from a configuration that loses money and
    scores -0.22, and every population is seeded from the incumbent.

    Only `risk_per_trade` moves, and only upward. The rules, the detector, the
    exits and the universe are untouched -- whatever edge this genome has is
    preserved, and the change is one number a reader can see and undo.
    """
    risk = incumbent.get("risk_per_trade")
    if not isinstance(risk, (int, float)) or risk <= 0:
        return incumbent
    lifted = min(risk * SIZING_MIGRATION_MULTIPLE, RISK_PER_TRADE_CEILING)
    if lifted <= risk:
        return incumbent
    return {**incumbent, "risk_per_trade": lifted}


@dataclass
class LoopState:
    """What survives between iterations. Small on purpose: everything else is
    recoverable from the ledger and the database."""

    iteration: int = 0
    incumbent: dict[str, Any] = field(default_factory=dict)
    # What the incumbent was SELECTED on: its walk-forward score over the
    # fitting folds, every one of them ending on or before 2025-12-31.
    #
    # `incumbent_forward` is still carried, and is now display only. It used to
    # be the selection criterion, and that was the leak: the sealed window
    # chose which genome became the incumbent, and the incumbent seeds every
    # subsequent population, so 2026 was steering the search from inside. The
    # reviewer named it on iteration 87 -- "stop promoting forward winners into
    # the incumbent that seeds subsequent research" -- and it was right.
    incumbent_score: float | None = None
    # Which `objective()` produced `incumbent_score`. Carried so a state written
    # under one scoring function cannot be silently ranked against candidates
    # scored by another -- see `load`, where a mismatch discards the score
    # rather than converting it.
    #
    # The default is 1, not the current version: a state file written before
    # this field existed was scored by v1, and defaulting to "whatever is
    # current" would assert the one thing that cannot be true and skip the
    # migration entirely.
    objective_version: int = 1
    incumbent_forward: float | None = None
    incumbent_backtest_id: str | None = None
    last_forward_id: str | None = None
    # The training run of the last accepted genome. This is what the diagnosis
    # reads to pick the next module, because it ends at the lock.
    last_training_id: str | None = None
    consecutive_failures: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def document(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "incumbent": self.incumbent,
            "incumbent_score": self.incumbent_score,
            "objective_version": self.objective_version,
            "incumbent_forward": self.incumbent_forward,
            "incumbent_backtest_id": self.incumbent_backtest_id,
            "last_forward_id": self.last_forward_id,
            "last_training_id": self.last_training_id,
            "consecutive_failures": self.consecutive_failures,
            "history": self.history[-HISTORY_LIMIT:],
        }

    @classmethod
    def load(cls, path: Path) -> LoopState:
        """Resume, start fresh, or refuse -- but never quietly start fresh.

        This used to catch OSError alongside ValueError and return a blank
        state, which reads as defensive and is the opposite. A blank state
        means iteration 0, so the next id is H-L001 -- an id the ledger already
        holds -- and an append-only research record ends up carrying two
        different hypotheses under one name, with the incumbent silently reset
        to "anything beats nothing". The failure is invisible at the moment it
        happens and unrecoverable afterwards.

        It is not hypothetical. Under launchd the loop could not read its own
        state: the repository lives under ~/Documents, macOS gates that
        directory for background agents, and `read_text` raised
        PermissionError. The loop announced itself, said nothing, and began
        iteration 1 on top of a ledger with seventy-eight records in it.

        So: a file that is absent is a first run and returns defaults. A file
        that EXISTS and cannot be read or parsed stops the loop. Refusing to
        start is recoverable; starting on a lie is not.
        """
        try:
            text = path.read_text()
        except FileNotFoundError:
            return cls()
        except OSError as exc:
            raise RuntimeError(
                f"the loop state at {path} exists but could not be read: {exc}. "
                "Refusing to start, because starting would mean resuming from "
                "iteration 0 and overwriting the ledger's own history. If this "
                "is a LaunchAgent, it needs Full Disk Access to reach that "
                "directory."
            ) from exc
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise RuntimeError(
                f"the loop state at {path} is not readable JSON: {exc}. "
                "Refusing to start rather than resume from iteration 0."
            ) from exc
        state = cls()
        for key in (
            "iteration",
            "incumbent",
            "incumbent_score",
            "objective_version",
            "incumbent_forward",
            "incumbent_backtest_id",
            "last_training_id",
            "last_forward_id",
            "consecutive_failures",
            "history",
        ):
            if key in payload:
                setattr(state, key, payload[key])
        # RESUMING ACROSS THE FIX. A state written before selection moved to the
        # folds has no `incumbent_score`, and `None` means "anything beats
        # nothing" -- so the first iteration after the change would promote
        # whatever it found, on one fit, unopposed.
        #
        # The score is recoverable: history records `fit_score` and `folds` for
        # every iteration, so the incumbent's score is the one from the last
        # iteration that moved it. Only a score measured on the CURRENT fold
        # layout is comparable, which is the same rule `clears_gate` applies.
        if state.incumbent_score is None:
            for entry in reversed(state.history):
                if (
                    entry.get("verdict") == "CONFIRMED"
                    and entry.get("fit_score") is not None
                ):
                    state.incumbent_score = entry["fit_score"]
                    break

        # RESUMING ACROSS AN OBJECTIVE CHANGE. A score is a number in the units
        # of whatever function produced it. v1 was `median - drawdown`, in
        # returns, and typically negative; v2 is `median / drawdown`, a ratio,
        # and typically greater than one. Ranking one against the other decides
        # the incumbent on units alone -- every v2 candidate would beat every v1
        # incumbent instantly, and the gate would be meaningless for exactly one
        # iteration, which is the iteration that sets the next incumbent.
        #
        # So the old score is DISCARDED rather than converted. There is no
        # conversion: the two functions are not monotone in each other, which is
        # the whole reason the objective was changed. `None` means the next
        # iteration establishes the baseline, on the current objective, honestly.
        if state.objective_version != search.OBJECTIVE_VERSION:
            state.incumbent_score = None
            state.incumbent = lift_sizing_to_the_floor(state.incumbent)
            state.objective_version = search.OBJECTIVE_VERSION
        return state


class ResearchLoop:
    """One object, one method that matters: `iterate()`. Called for ever."""

    def __init__(
        self,
        lab_fit: Any,
        lab_forward: Any,
        store: Any,
        symbols: list[str],
        repository: Path | str,
        cluster: Any | None = None,
        proposer: Any | None = None,
        critic: Any | None = None,
        reviewer: Any | None = None,
        # The seat that reviews the LOOP rather than the hypothesis. Usually the
        # same kind of object as the proposer, asked a different question.
        reviewer_of_self: Any | None = None,
        # A proposer with read-only web access, asked only on exploration
        # turns. Absent, exploration turns fall back to the normal seat.
        explorer: Any | None = None,
        evolve_every: int = 10,
        state_path: Path | str | None = None,
        ledger_path: Path | str | None = None,
        generations: int = 5,
        population: int = 14,
        fold_count: int = 4,
        fit_start: str = "2018-01-01",
        # The forward run is LOADED from the first bar this laboratory holds and
        # SCORED from `trade_from`. The detector is stateful, so the label it
        # puts on 2026-01-01 is a claim about the cycle, not about January: it
        # needs 2021's top and 2022's bottom to make it. Starting the tape in
        # 2022 handed it a running high set in early 2022 and a hysteresis
        # streak with nothing behind it.
        forward_start: str = HISTORY_BEGINS,
        forward_end: str = "2026-12-31",
        trade_from: str = "2026-01-01",
        gate: float = 0.02,
        deployment: dict[str, Any] | None = None,
        # The laboratory's own configuration, used for one thing: finding the
        # candles the benchmark is computed from. Optional because a loop can
        # run without a benchmark -- it just cannot say whether its return was
        # skill or weather, which is the state this laboratory spent ninety
        # iterations in.
        config: Any | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        publish: Callable[[dict[str, Any]], None] | None = None,
        publish_journal: Callable[[str, list], None] | None = None,
    ):
        # Two laboratories on purpose. `lab_fit` talks to a service that cannot
        # serve a bar past the lock; `lab_forward` talks to one that can. The
        # separation is what makes "the fit never saw 2026" a property of the
        # process rather than a promise in a docstring.
        self.lab_fit = lab_fit
        self.lab_forward = lab_forward
        self.store = store
        self.symbols = list(symbols)
        self.repository = Path(repository)
        self.cluster = cluster
        self.proposer = proposer
        self.critic = critic
        # The third seat, and the only one that reads the working copy. See
        # `consult` for why a reviewer is not just a second refuter.
        self.reviewer = reviewer
        self.generations = generations
        self.population = population
        # Where the loop's own settings live. Small JSON beside the ledger, so
        # a person can read it, edit it or delete it, and the loop picks the
        # change up at the next iteration without a restart.
        self.tuning_path = (
            Path(state_path).parent / "tuning.json" if state_path else None
        )
        self.memory_path = (
            Path(state_path).parent.parent / "MEMORY.md" if state_path else None
        )
        self.reviewer_of_self = reviewer_of_self
        self.explorer = explorer
        # What each seat answered last time, so a self-review can see that
        # a member has been failing for twenty iterations. Nothing else
        # reads it; without it, a dead advisor is invisible to the only
        # turn whose job is noticing that kind of thing.
        self.last_advisors: dict[str, Any] = {}
        self.evolve_every = evolve_every
        self.fold_count = fold_count
        self.fit_start = fit_start
        self.forward_start = forward_start
        self.forward_end = forward_end
        self.trade_from = trade_from
        # How much better than the incumbent a fit must be before the forward
        # window is spent on it. 2026 opens once per hypothesis and there are
        # only so many hypotheses worth spending it on.
        self.gate = gate
        self.config = config
        # Where the system is deployed: the liquidity floor an asset must clear
        # to be bought at all, and how wide a book we are willing to run. These
        # are pinned into every launch, fit and forward alike, and they OVERRIDE
        # the incumbent -- an incumbent recorded under a different deployment
        # scope must not carry the old scope forward into a new one. No module
        # in MODULE_KEYS can reach them, which is the point: the universe is not
        # a knob to tune until the past looks better.
        self.deployment = dict(deployment or {})
        self.on_event = on_event
        # Where the heartbeat goes beyond this machine. Optional: the loop must
        # run identically with no edge to publish to.
        self.publish = publish
        self.publish_journal = publish_journal
        self._journal_sent = 0.0
        self._journal_node: str | None = None
        self._beat_started: str | None = None
        self._beat_module: str | None = None
        self._beat_fit: dict[str, Any] | None = None
        self._beat_last: dict[str, Any] | None = None
        # The two halves of the iteration in flight, for the monitor's card.
        self._beat_pair: dict[str, Any] = {"training": None, "forward": None}

        # Can we actually SEE the repository we were pointed at?
        #
        # macOS does not deny a background agent access to ~/Documents; it hides
        # it. `read_text` raised FileNotFoundError, not PermissionError, so a
        # missing-file check reads that as a legitimate first run -- and the
        # loop began iteration 1 on top of a ledger holding seventy-eight
        # records, under a LaunchAgent, silently. Refusing on an unreadable file
        # does not catch it, because there is no file to be unreadable.
        #
        # A marker that is committed to this repository and cannot be absent
        # from a real checkout is the only thing that distinguishes "a fresh
        # clone with no research yet" from "I cannot see the research at all".
        marker = self.repository / "CONTRACT.md"
        if not marker.exists():
            raise RuntimeError(
                f"the repository at {self.repository} does not contain "
                "CONTRACT.md, so it is either not a QuantLab checkout or this "
                "process cannot see it. Refusing to start: resuming from here "
                "would mean beginning at iteration 0 and writing hypothesis ids "
                "the ledger already holds. A LaunchAgent reaching a directory "
                "under ~/Documents needs Full Disk Access; macOS hides the path "
                "rather than denying it, which is why this is checked and not "
                "merely caught."
            )

        research = self.repository / "orchestrator-manager" / "loop"
        self.state_path = (
            Path(state_path) if state_path else research / "ledger" / "loop-state.json"
        )
        self.ledger_path = (
            Path(ledger_path)
            if ledger_path
            else research / "ledger" / "hypotheses.jsonl"
        )
        # Which trading system this loop is researching. One string, used to
        # stamp every ledger record and to group the diary, so a second system
        # can run its own loop without its results being filed under this one's.
        self.system = "four-module"
        # One file per hypothesis, beside the ledger it explains.
        self.journal_dir = self.ledger_path.parent.parent / "journal"
        # The readable account, grouped by trading system. Derived from the two
        # above and safe to delete: the next iteration rebuilds it.
        self.diary_dir = self.ledger_path.parent.parent / "diary"
        self._journal_id: str | None = None
        self.state = LoopState.load(self.state_path)

    # -- plumbing ------------------------------------------------------------ #

    def _emit(self, stage: str, **payload: Any) -> None:
        event = {
            "at": _now(),
            "iteration": self.state.iteration,
            "stage": stage,
            # Which box on the live diagram this belongs to, decided here rather
            # than in the page. The page must not have to know that `fit` and
            # `backtest` are the same box, or that `opening` and `forward` are
            # two moments of one: a stage added here and not taught to the page
            # would silently light nothing.
            "node": self.STAGE_NODES.get(stage, "record"),
            "say": self.PHASE_LABELS.get(stage, stage),
            **payload,
        }
        if self.on_event:
            self.on_event(event)
        else:
            print(json.dumps(event, default=str)[:600], flush=True)
        self._journal(event)
        self._beat(event)

    # -- the journal ---------------------------------------------------------- #

    def _journal(self, event: dict[str, Any]) -> None:
        """Every event of one hypothesis, in order, kept for ever.

        The ledger records what an iteration CONCLUDED -- one line, a verdict.
        This records what it DID: each stage, each generation, each advisor
        reply, each backtest that moved the best score. A ledger line cannot
        answer "is this loop exploring or is it circling the same idea", and
        that question is the whole point of watching it.

        Append-only, one file per hypothesis, and deliberately unbounded -- an
        iteration is an hour of work and its record is worth kilobytes. Never
        allowed to raise: this observes the research and must not be able to
        stop it.
        """
        try:
            identifier = self._journal_id or f"H-L{self.state.iteration:03d}"
            path = self.journal_dir / f"{identifier}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as handle:
                handle.write(json.dumps(event, default=str) + "\n")
        except Exception:  # noqa: BLE001 - the observer never breaks the observed
            pass
        self._publish_journal(event)

    def _publish_journal(self, event: dict[str, Any]) -> None:
        """Send the journal to the edge, but not on every event.

        A fit emits a `backtest` event every few seconds for most of an hour, and
        pushing the whole file each time would be hundreds of uploads to say
        "the counter moved". So: always when the loop crosses into a new box on
        the diagram, always when the iteration ends, and otherwise at most every
        twenty seconds. A public reader is never more than twenty seconds behind
        the stage they are watching, and never misses a stage entirely.
        """
        if not self.publish_journal or not self._journal_id:
            return
        node = str(event.get("node") or "")
        moved = node != self._journal_node
        ending = event.get("stage") in ("recorded", "error", "stopped")
        elapsed = time.time() - self._journal_sent
        if not (moved or ending or elapsed > 20):
            return
        self._journal_node = node
        self._journal_sent = time.time()
        try:
            self.publish_journal(self._journal_id, self.journal(self._journal_id))
        except Exception:  # noqa: BLE001 - the observer never breaks the observed
            pass

    def journal(self, identifier: str | None = None) -> list[dict[str, Any]]:
        """One hypothesis's events, oldest first. The current one by default."""
        identifier = identifier or self._journal_id
        if not identifier:
            return []
        events = []
        try:
            for line in (
                (self.journal_dir / f"{identifier}.jsonl").read_text().splitlines()
            ):
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        except OSError:
            return []
        return events

    # -- the heartbeat -------------------------------------------------------- #

    # What a reader should see on the page for each stage. A fit is thirteen of
    # every fourteen minutes, so it is the one that must carry real progress.
    # Said in terms of what is HAPPENING, not what the stage is called. A reader
    # asked what "fitting" meant and could not tell from the card whether the
    # machine was downloading data, computing indicators, writing code or
    # running backtests. It is always the last of those: the data was downloaded
    # once, the seventy-nine indicator columns were computed once, and no code
    # is ever written -- the loop composes rule trees the grammar validates.
    PHASE_LABELS = {
        "begin": "opening a hypothesis",
        "frame": "reading the last 2026 run to find the losing module",
        "consulting": "asking the cluster and the advisors for ideas",
        "consulted": "advice in, building the population",
        "fit": "searching — a generation finished",
        "backtest": "running backtests, all of them before 2026",
        "fitted": "search finished, checking it against this module's best",
        "observed": "attributing the 2026 result to the modules that earned it",
        "trained": "the training result of the accepted fit is in",
        "opening": "opening the sealed 2026 window",
        "forward": "the 2026 result is in",
        "recorded": "recording the verdict",
        "error": "an iteration failed",
    }

    # The seven boxes of the live diagram, and which stage lights which.
    #
    # Seven, not eleven: FIT is one box that a search sits inside for most of an
    # hour, and FORWARD is one box whether the window is opening or its result
    # has landed. The names match `docs/architecture/research-loop.md`, which is
    # the same seven, so the drawing and the prose cannot drift.
    #
    # COMPOSE is deliberately not called "write the code". This loop cannot
    # write code and the distinction is load-bearing: it composes expression
    # trees over the 79 served columns, which are DATA that the grammar
    # validates before anything runs them.
    STAGE_NODES = {
        "begin": "frame",
        "frame": "frame",
        "consulting": "consult",
        "consulted": "compose",
        "evolve": "consult",
        # SEARCH and EVALUATE are two boxes because the loop turns back between
        # them: a backtest is one candidate over one fold, and a finished
        # generation is a score that decides which candidates breed the next
        # one. Drawn as a single box, the hundreds of times an hour this loop
        # iterates its own values were invisible.
        "backtest": "search",
        "fit": "evaluate",
        "fitted": "gate",
        "trained": "train",
        "training-failed": "train",
        "opening": "forward",
        "forward": "forward",
        "observed": "observe",
        "recorded": "record",
        "error": "record",
        "warning": "record",
        "stopped": "record",
    }
    NODE_ORDER = (
        "frame",
        "consult",
        "compose",
        "search",
        "evaluate",
        "gate",
        "train",
        "forward",
        "observe",
        "record",
    )

    def _beat(self, event: dict[str, Any]) -> None:
        """Publish what the loop is doing right now, locally and to the edge.

        Never allowed to raise: a monitor is an observer, and an observer that
        can stop the research is worse than no monitor. Failures degrade to a
        stale heartbeat, which the page renders as such.
        """
        stage = str(event.get("stage") or "")
        if stage == "begin":
            self._beat_started = event.get("at")
            self._beat_fit = None
            self._beat_last = None
            self._beat_module = None
            # Cleared with the rest: the previous iteration's two results must
            # not be read as this one's while the search is still running.
            self._beat_pair = {"training": None, "forward": None}
        if event.get("module"):
            self._beat_module = event["module"]
        if stage == "fit":
            self._beat_fit = {
                "generation": event.get("generation"),
                "of": self.generations,
                "best": event.get("best"),
                "viable": event.get("viable"),
                "population": event.get("population"),
                "evaluations": event.get("evaluations"),
            }
        if stage == "backtest":
            # The last backtest that finished, and how far through the search we
            # are. `planned` is an upper bound: the search memoises, so a
            # converging population re-proposes genomes it has already paid for.
            self._beat_last = {
                "window": event.get("window"),
                "fold": event.get("fold"),
                "folds": event.get("folds"),
                "return_pct": event.get("return_pct"),
                "trades": event.get("trades"),
                "max_drawdown": event.get("max_drawdown"),
                "backtests": event.get("backtests"),
                "planned": self.generations * self.population * self.fold_count,
                "best": event.get("best"),
            }
        # The iteration's two RESULTS, as opposed to the arithmetic that produced
        # them. `last_backtest` above is one fold of one candidate out of some
        # hundreds and changes every few seconds; these two are the pair the
        # hypothesis is finally recorded on -- the accepted genome over the years
        # before the lock, and the single 2026 shot if the fit earned one. The
        # page shows both on the card, so both have to reach it.
        if stage in ("trained", "forward"):
            self._beat_pair["training" if stage == "trained" else "forward"] = {
                "backtest_id": event.get("backtest_id"),
                "return_pct": event.get("return_pct"),
                "max_drawdown": event.get("max_drawdown"),
                "trades": event.get("trades"),
            }
        document = {
            "at": event.get("at"),
            # WHO is doing this work, and it is the same handle the runs this
            # loop launches are submitted under. That identity is what lets the
            # page draw one card per job: a run whose `submitted_by` matches
            # belongs to this heartbeat and is not a second piece of work. It
            # also means a contributor running their own backtest from their own
            # machine appears as their own job rather than merging into ours.
            "owner": team.LOOP.handle,
            "iteration": self.state.iteration,
            "stage": stage,
            # Which box is lit on the live diagram, and which journal explains
            # it. Both derived here so the page reads an answer rather than
            # re-deriving one from the stage slug.
            "node": event.get("node") or self.STAGE_NODES.get(stage, "record"),
            "hypothesis": self._journal_id,
            "phase": self.PHASE_LABELS.get(stage, stage),
            "module": self._beat_module,
            "started_at": self._beat_started,
            "fit": self._beat_fit,
            "last_backtest": self._beat_last,
            "pair": dict(self._beat_pair),
            "detail": str(event.get("detail") or event.get("why") or "")[:300],
            "symbols": len(self.symbols),
            "incumbent_forward": self.state.incumbent_forward,
            "consecutive_failures": self.state.consecutive_failures,
            "recent": self.state.history[-6:],
        }
        try:
            if hasattr(self.store, "set_activity"):
                self.store.set_activity(document)
            if self.publish:
                self.publish(document)
        except Exception:  # noqa: BLE001 - the observer never breaks the observed
            pass

    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps(self.state.document(), indent=2, default=str)
            )
        except OSError as exc:
            self._emit("warning", detail=f"cannot write loop state: {exc}")

    def tried(self) -> set[str]:
        """Every hypothesis fingerprint the ledger already holds.

        Re-running a recorded configuration is the one way a loop like this
        genuinely wastes a day, so the check happens before the backtest rather
        than after it.
        """
        seen: set[str] = set()
        try:
            lines = self.ledger_path.read_text().splitlines()
        except OSError:
            return seen
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                # Skip the bad line and keep reading. Wrapping the whole loop in
                # one try meant a single malformed record silently discarded
                # every hypothesis after it, and a loop that has forgotten what
                # it tried will cheerfully re-run it.
                continue
            if fingerprint := record.get("config_fingerprint"):
                seen.add(str(fingerprint))
        return seen

    def ledger_all(self) -> list[dict[str, Any]]:
        records = []
        try:
            lines = self.ledger_path.read_text().splitlines()
        except OSError:
            return []
        for line in lines:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
        return records

    def ledger_tail(self, count: int = 12) -> list[dict[str, Any]]:
        return self.ledger_all()[-count:]

    def attempts_by_module(self) -> dict[str, dict[str, Any]]:
        """How much evidence each module has, and how recent it is.

        The loop has spent 35 of 102 iterations on BEAR and 10 on POLICY. That
        is not a judgement about where the money is -- it is what a greedy rule
        does when it always picks the worst performer: the worst performer stays
        the worst performer while it is being worked on, so it gets picked
        again.
        """
        counts: dict[str, dict[str, Any]] = {}
        for record in self.ledger_all():
            iteration = int(record.get("iteration") or 0)
            if not iteration:
                continue
            piece = str(record.get("piece") or "unknown").upper()
            slot = counts.setdefault(
                piece,
                {
                    "tried": 0,
                    "confirmed": 0,
                    "refuted": 0,
                    "inconclusive": 0,
                    "best_fit_score": None,
                    "last_iteration": 0,
                },
            )
            slot["tried"] += 1
            verdict = str(record.get("verdict") or "").upper()
            if verdict == "CONFIRMED":
                slot["confirmed"] += 1
            elif verdict == "REFUTED":
                slot["refuted"] += 1
            elif verdict == "INCONCLUSIVE":
                slot["inconclusive"] += 1
            slot["last_iteration"] = max(slot["last_iteration"], iteration)
            fit = (record.get("metrics") or {}).get("fit") or {}
            score = fit.get("score")
            # Only scores from the current objective. This figure is shown to
            # the proposer as "the best anyone has reached on this module", and
            # a v1 return quoted beside v2 ratios is not a harder target, it is
            # a different unit presented as the same one.
            comparable = fit.get("objective_version", 1) == search.OBJECTIVE_VERSION
            if (
                score is not None
                and comparable
                and (slot["best_fit_score"] is None or score > slot["best_fit_score"])
            ):
                slot["best_fit_score"] = score
        return counts

    def ledger_digest(self, dead_ends: int = 10) -> dict[str, Any]:
        """The whole ledger, compressed -- not the last ten lines of it.

        THE AMNESIA THIS FIXES. The briefing carried `ledger_tail(10)`. The
        ledger holds 122 records, 88 of them refutations, so the proposer was
        shown eight percent of what this laboratory has learned and then asked
        not to repeat itself -- which is not a request it was equipped to
        honour. It re-proposed closed directions because nothing told it they
        were closed.

        A tail is the wrong SHAPE regardless of its length. What a proposer
        needs is not the most recent ten attempts but the standing state of the
        question: which modules are exhausted, which are barely touched, what
        the best score anyone has reached looks like, and which specific
        directions are already dead. That is a digest, and it compresses all
        122 into fewer tokens than the ten cost.

        Read from the append-only ledger every time, so it cannot drift from the
        record: there is no second store to keep in sync.
        """
        loops = [r for r in self.ledger_all() if r.get("iteration")]

        def brief(record: dict[str, Any]) -> dict[str, Any]:
            metrics = record.get("metrics") or {}
            return {
                "id": record.get("id"),
                "module": str(record.get("piece") or "?").upper(),
                "tried": str(record.get("statement", ""))[:160],
                "why": str(record.get("notes", ""))[:160],
                # The expectation and the outcome, side by side. "What looked
                # promising and then did not survive" is the most useful thing
                # in a research record, and it appeared nowhere in the briefing.
                "fit_score": (metrics.get("fit") or {}).get("score"),
                "forward_return": (metrics.get("forward") or {}).get("return_pct"),
            }

        scored = [
            r for r in loops if ((r.get("metrics") or {}).get("fit") or {}).get("score")
        ]
        scored.sort(key=lambda r: r["metrics"]["fit"]["score"], reverse=True)
        return {
            "iterations_recorded": len(loops),
            "by_module": self.attempts_by_module(),
            "best_attempts_ever": [brief(r) for r in scored[:8]],
            "dead_ends": [
                brief(r)
                for r in reversed(loops)
                if str(r.get("verdict") or "").upper() == "REFUTED"
            ][:dead_ends],
            "still_open": [
                brief(r)
                for r in reversed(loops)
                if str(r.get("verdict") or "").upper() in ("OPEN", "INCONCLUSIVE")
            ][:6],
        }

    def _record(self, record: dict[str, Any]) -> None:
        # Which system this belongs to, stamped at the source. The laboratory
        # runs more than one now, and a ledger that does not say which one a
        # result came from lets a four-module finding be read as evidence about
        # the intraday system, which it is not.
        record.setdefault("system", self.system)
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a") as handle:
                handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        except OSError as exc:
            self._emit("warning", detail=f"cannot append the ledger: {exc}")
        self._refresh_diary()

    def _refresh_diary(self) -> None:
        """Rebuild the readable diary from the ledger and the journals.

        Derived, never authored: regenerated in full each time, so a page cannot
        keep a verdict the ledger has since changed. Never allowed to raise --
        this observes the research exactly like `_journal`, and an observer that
        can stop the loop is worse than no observer.
        """
        try:
            diary.write(self.ledger_path, self.journal_dir, self.diary_dir)
        except Exception:  # noqa: BLE001 - the observer never breaks the observed
            pass

    # -- the stages ---------------------------------------------------------- #

    # The order a stuck loop walks when the diagnosis has stopped being useful.
    #
    # POLICY and DETECTOR come before BULL and SIDEWAYS deliberately. The
    # diagnosis can only ever name a branch that traded, so it never reaches
    # either of them, and rotation is the only way they get a turn. Meanwhile
    # every bar of the forward window classifies BEAR, so a bull or sideways
    # iteration cannot produce forward evidence at all (H-L057C): it re-measures
    # the incumbent and returns its number exactly. Spending the sealed window
    # on the two that can move something comes first.
    ROTATION: tuple[str, ...] = ("BEAR", "POLICY", "DETECTOR", "SIDEWAYS", "BULL")

    # One iteration in five ignores the diagnosis and works the module with the
    # least evidence behind it.
    #
    # WHY A GREEDY LOOP STALLS. The diagnosis picks the module losing the most
    # money, which is the right question to ask once and the wrong one to ask a
    # hundred times in a row: the worst performer is still the worst performer
    # while it is being worked on, so it is picked again, and again. After 102
    # iterations this loop had spent 35 on BEAR and 10 on POLICY -- not because
    # BEAR was more promising, but because it was losing when the loop started.
    # That is the exploitative baseline the open-ended-discovery literature
    # reports losing to surprise- and coverage-driven selection, and the shape
    # of the failure here is exactly the one described: a search that keeps
    # confirming what it already believes about where the problem is.
    #
    # Coverage rather than a random jump, and deterministic rather than
    # sampled: the same ledger always produces the same choice, which keeps an
    # iteration reproducible from its record.
    EXPLORE_EVERY: int = 5

    def least_explored_module(self) -> dict[str, Any] | None:
        """On an exploration turn, the module with the least evidence behind it.

        Returns a frame, or None when this is not an exploration turn. Ties go
        to whichever was worked on longest ago, so two untouched modules do not
        deadlock on alphabetical order.

        The frame it returns is honest about itself: `selection` says
        `exploration`, and the `why` says nobody has looked here, rather than
        dressing a coverage decision up as a diagnosis. A proposer told "target
        module BULL" with a diagnosis attached will reason about why BULL must
        be at fault; told the truth, it can reason about what has never been
        tried there.
        """
        if self.EXPLORE_EVERY <= 0:
            return None
        # `iteration` is the count already completed; the turn about to run is
        # the next one.
        if (self.state.iteration + 1) % self.EXPLORE_EVERY:
            return None
        counts = self.attempts_by_module()
        ranked = sorted(
            self.ROTATION,
            key=lambda name: (
                (counts.get(name) or {}).get("tried", 0),
                (counts.get(name) or {}).get("last_iteration", 0),
            ),
        )
        if not ranked:
            return None
        target = ranked[0]
        seen = counts.get(target) or {}
        busiest = max(
            ((counts.get(name) or {}).get("tried", 0) for name in self.ROTATION),
            default=0,
        )
        return {
            "target_module": target,
            "diagnosis": None,
            "selection": "exploration",
            "why": (
                f"Exploration turn (one in {self.EXPLORE_EVERY}). This is NOT a "
                f"diagnosis: {target} was chosen because it has the least "
                f"evidence behind it, not because it is the piece losing money. "
                f"It has been the subject of {seen.get('tried', 0)} iterations "
                f"against {busiest} for the most-worked module, and was last "
                f"touched at iteration {seen.get('last_iteration', 0)}.\n\n"
                "Propose the most informative thing that has never been tried "
                "here -- something whose result would change what this "
                "laboratory believes, whichever way it falls. A mechanism that "
                "is merely a small variation on the incumbent teaches nothing "
                "on a turn that exists to widen the search."
            ),
        }

    def frame(self) -> dict[str, Any]:
        """Which module the evidence says to work on, and why.

        The diagnosis reads the LAST FORWARD RUN, and a forward run only happens
        when a fit clears the gate. So a loop whose fits keep missing has a
        frozen diagnosis: it re-reads the same run and re-picks the same module,
        for ever. Iterations 2 through 5 were all DETECTOR for exactly that
        reason.

        After two barren iterations the diagnosis has stopped being evidence
        about anything current, so the loop rotates instead of trusting it. That
        is exploration, and it is what stops a rut from being permanent.
        """
        explore = self.least_explored_module()
        if explore is not None:
            return explore

        stale = self.state.consecutive_failures >= 2
        if stale and self.state.history:
            recent = [h.get("module") for h in self.state.history[-4:]]
            for candidate in self.ROTATION:
                if candidate not in recent:
                    return {
                        "target_module": candidate,
                        "diagnosis": None,
                        "why": (
                            f"{self.state.consecutive_failures} iterations in a row "
                            f"opened no forward window, so the diagnosis is stale: it "
                            f"keeps re-reading a run nothing has replaced. Rotating to "
                            f"{candidate}, which the last four iterations did not touch."
                        ),
                    }

        # Nothing has been measured under THIS deployment scope yet, which is
        # the state the loop is in the moment the universe changes. Sizing is
        # the only module that can move exposure, and exposure is exactly what
        # a change of universe changes: the incumbent's policy was fitted
        # against a 20-name book at 3% average exposure, and the same
        # per-position sizing across a 54-name book is a different amount of
        # risk. Iteration 69 measured what that costs -- nine complete
        # candidates, all nine rejected by the 30% mandate, and a BEAR search
        # cannot reach a single sizing dimension to do anything about it.
        #
        # So the first question under a new scope is the sizing question. This
        # picks WHICH question to ask, never what the answer is: the search
        # still has to find a policy that clears the mandate on its own.
        if not any(h.get("folds") == self.fold_signature() for h in self.state.history):
            return {
                "target_module": "POLICY",
                "diagnosis": None,
                "why": (
                    "nothing has been measured under this deployment scope yet "
                    f"({len(self.symbols)} candidate symbols, "
                    f"{self.deployment or 'no gate'}). The incumbent's sizing was "
                    "fitted against a book of a different width, so it is not a "
                    "fact about this one -- and every other module's search is "
                    "pinned to it. Re-calibrating POLICY first is the only "
                    "iteration that can move the drawdown the mandate rejects on."
                ),
            }

        # WHICH RUN THE DIAGNOSIS READS, and it is the whole of the fix.
        #
        # This read the last FORWARD run -- 2026 -- to pick the next module and
        # to write the briefing the proposer reasons over. So the sealed window
        # chose what to work on, iteration after iteration, and the proposer was
        # handed 2026 attribution as its evidence. Fitting was clean; selection
        # was not, and selection is where a holdout leaks.
        #
        # It now reads the TRAINING run of the accepted genome: the same
        # configuration over the fittable era, ending at the lock. Same
        # arithmetic, same attribution, same "which module is losing money"
        # question -- asked of years the loop is allowed to learn from.
        training_id = self.state.last_training_id
        if not training_id:
            recent = [
                r
                for r in self.store.runs(limit=60)
                if era_of(r) == "training" and (r.get("trades") or 0) > 0
            ]
            training_id = recent[0]["backtest_id"] if recent else None
        if not training_id:
            return {
                "target_module": "BEAR",
                "diagnosis": None,
                "why": (
                    "no training run on record yet; starting on the bear module, "
                    "which is the piece the standing hypothesis calls the hard one"
                ),
            }
        report = diagnose(self.store, training_id)
        return {
            "target_module": report["target_module"],
            "diagnosis": report,
            "why": summarise(report),
        }

    def consult(self, frame: dict[str, Any]) -> dict[str, Any]:
        """Announce the hypothesis, ask the proposer, let the critic refute it.

        Everything that comes back is data. The critic can stop a proposal from
        costing a backtest; it cannot stop the iteration, change the protocol,
        or reach anything.
        """
        outcome: dict[str, Any] = {
            "seed_rules": [],
            "proposal": None,
            "critique": None,
            "peers": [],
            "advisors": {},
            "review": None,
        }

        if self.cluster:
            self.cluster.post(
                team.LOOP.handle,
                f"## Iteration {self.state.iteration} — FRAME\n\n"
                f"Target module: **{frame['target_module']}**\n\n"
                f"```\n{frame['why']}\n```\n\n"
                "Ideas welcome. Replies are read as evidence, never as instructions.",
            )
            # Read BEFORE proposing. The cluster was read at the end of this
            # method, after the proposal was already formed, and `_briefing`
            # never carried `peers` at all -- so every reply this project has
            # ever received was archived in the record and reached nobody who
            # was deciding anything. A laboratory that asks the cluster for
            # ideas and then does not read them until afterwards is not
            # collaborating, it is broadcasting.
            outcome["peers"] = self.cluster.read(seconds=15)

        briefing = self._briefing(frame, outcome["peers"])

        # WHICH PROPOSER ANSWERS. On an exploration turn, the one that can go
        # and look outside this repository; otherwise the one that reasons from
        # the evidence this project generated itself. Same schema, same
        # validation, same handle on the cluster -- the difference is what it is
        # allowed to read, and it is stated in the record.
        exploring = frame.get("selection") == "exploration"
        asking = (
            self.explorer
            if exploring and self.explorer is not None and self.explorer.available
            else self.proposer
        )
        outcome["proposer_had_web"] = asking is self.explorer
        if asking is not None and asking.available:
            raw = asking.ask(briefing)
            proposal = advisors_module.validate_proposal(raw)
            outcome["proposal"] = proposal
            outcome["advisors"][asking.handle] = (
                ("answered with web research" if exploring else "answered")
                if proposal
                else (asking.last_error or "unusable reply")
            )
            if proposal:
                outcome["seed_rules"] = proposal["seed_rules"]
                if self.cluster:
                    self.cluster.post(
                        team.PROPOSER.handle,
                        f"## Iteration {self.state.iteration} — proposal\n\n"
                        f"**Module:** {proposal['module']}\n\n"
                        f"**Claim:** {proposal['claim']}\n\n"
                        f"**Killed by:** {proposal['kill_condition']}\n\n"
                        f"{proposal['reasoning']}\n\n"
                        + "\n".join(
                            f"- `{grammar.describe(r)}`" for r in proposal["seed_rules"]
                        ),
                    )
        elif self.proposer is not None and getattr(self.proposer, "cooling", False):
            outcome["advisors"][self.proposer.handle] = (
                f"resting {self.proposer.cooldown_remaining // 60}m (out of tokens)"
            )
        else:
            outcome["advisors"][team.PROPOSER.handle] = "unavailable"

        if outcome["proposal"] and self.critic is not None and self.critic.available:
            raw = self.critic.ask(
                briefing
                + "\n\nPROPOSAL TO REFUTE:\n"
                + json.dumps(outcome["proposal"], default=str)
            )
            critique = advisors_module.validate_critique(raw)
            outcome["critique"] = critique
            outcome["advisors"][self.critic.handle] = (
                "answered" if critique else (self.critic.last_error or "unusable reply")
            )
            if critique and self.cluster:
                verdict = "REFUTED" if critique["refuted"] else "let it run"
                self.cluster.post(
                    team.CRITIC_GLM.handle,
                    f"## Iteration {self.state.iteration} — critique: {verdict}\n\n"
                    + "\n".join(f"- {r}" for r in critique["reasons"])
                    + (
                        f"\n\nSalvage: {critique['salvage']}"
                        if critique.get("salvage")
                        else ""
                    ),
                )
            if critique and critique["refuted"]:
                # The critic only removes the SEEDS. The iteration still runs on
                # invention, because an iteration that produces nothing teaches
                # nothing and the loop's job is to keep producing evidence.
                outcome["seed_rules"] = []
        elif self.critic is not None and getattr(self.critic, "cooling", False):
            outcome["advisors"][self.critic.handle] = (
                f"resting {self.critic.cooldown_remaining // 60}m (out of tokens)"
            )
        else:
            outcome["advisors"].setdefault(team.CRITIC_GLM.handle, "unavailable")

        # -- the reviewer ---------------------------------------------------- #
        #
        # A third opinion, and not a second refuter. The proposer and the
        # refuter argue about the IDEA; this one opens the repository and asks
        # whether the idea is runnable against the code as it actually stands.
        # The two questions catch different things, and the first live round
        # proved it: the reviewer found that the proposed `bear_breadth` sat
        # above `bull_breadth`, which `regime.py` rejects on construction, so
        # the iteration would have spent a fit to raise a `ValueError`. No
        # amount of reasoning about the hypothesis finds that.
        #
        # It blocks the SEEDS, exactly like the refuter, and nothing else. It
        # cannot stop the iteration, edit a file, or change the protocol -- it
        # runs `codex exec --sandbox read-only` and returns validated JSON.
        if (
            outcome["proposal"]
            and self.reviewer is not None
            and self.reviewer.available
        ):
            raw = self.reviewer.ask(
                briefing
                + "\n\nPROPOSAL TO REVIEW AGAINST THE CODE:\n"
                + json.dumps(outcome["proposal"], default=str)
            )
            review = advisors_module.validate_review(raw)
            outcome["review"] = review
            outcome["advisors"][self.reviewer.handle] = (
                "answered" if review else (self.reviewer.last_error or "unusable reply")
            )
            if review and self.cluster:
                verdict = "BLOCKING" if review["blocking"] else "no objection"
                self.cluster.post(
                    team.CRITIC_CODEX.handle,
                    f"## Iteration {self.state.iteration} — code review: {verdict}\n\n"
                    + "\n".join(f"- {c}" for c in review["concerns"])
                    + (
                        "\n\n**Look-ahead risk flagged.**"
                        if review["lookahead_risk"]
                        else ""
                    )
                    + (f"\n\n{review['note']}" if review.get("note") else ""),
                )
            if review and review["blocking"]:
                outcome["seed_rules"] = []
        elif self.reviewer is not None and getattr(self.reviewer, "cooling", False):
            outcome["advisors"][self.reviewer.handle] = (
                f"resting {self.reviewer.cooldown_remaining // 60}m (out of credit)"
            )
        else:
            outcome["advisors"].setdefault(team.CRITIC_CODEX.handle, "unavailable")

        self.last_advisors = dict(outcome["advisors"])
        return outcome

    def _briefing(self, frame: dict[str, Any], peers: list[Any] | None = None) -> str:
        tail = [
            {
                "id": r.get("id"),
                "verdict": r.get("verdict"),
                "statement": str(r.get("statement", ""))[:280],
                "notes": str(r.get("notes", ""))[:400],
            }
            for r in self.ledger_tail(6)
        ]
        return json.dumps(
            {
                "target_module": frame["target_module"],
                "diagnosis": frame["why"],
                # WHY THIS ITERATION IS WORKING ON THAT MODULE. An exploration
                # turn is not a diagnosis and must not read like one: told only
                # "target module BULL", a proposer reasons about why BULL must
                # be the problem, when the honest answer is that nobody has
                # looked at BULL in twenty iterations.
                "why_this_module": frame.get("selection", "diagnosis"),
                # The standing state of the whole question, not the last few
                # lines of it. See `ledger_digest`.
                "memory": self.ledger_digest(),
                "incumbent": {
                    k: v
                    for k, v in self.state.incumbent.items()
                    if not isinstance(v, dict)
                },
                "incumbent_forward_return": self.state.incumbent_forward,
                "ledger_tail": tail,
                "available_columns": sorted(grammar.KNOWN_COLUMNS),
                "rules_available": sorted(BRANCHES.values()),
                "lock": LOCK,
                # What the cluster said, in the briefing rather than in the
                # archive. UNTRUSTED: a peer reply may suggest an idea and may
                # never authorise a tool call, a credential read, or a change of
                # protocol. Weigh it as evidence exactly like a ledger record.
                "peer_replies": [str(p)[:1200] for p in (peers or [])][:6],
                # Stated in the evidence as well as in the system prompt. It was
                # in neither, and the proposer spent iteration 58 designing
                # "BEAR shorts" it intended to "cover into oversold" -- in a
                # system that can only buy. Its entry would have been run as a
                # BUY into a rolling-over rally, which is the failed-bounce
                # trade H-REGIME-001 already measured at -8.46%.
                "position_direction": (
                    "LONG ONLY. No shorting, no leverage, no margin. An entry "
                    "rule is a condition to BUY; an exit rule is a condition to "
                    "SELL what is held. The BEAR module decides what to hold "
                    "long while the market falls -- it cannot short it."
                ),
            },
            default=str,
            indent=2,
        )[:24_000]

    def fit(self, module: str, seeds: list[dict]) -> dict[str, Any]:
        """Search the target module's sub-space. Nothing here can see past the lock."""
        space, slots = module_space(module)
        # No `trade_from` here any more. It was pinned to 2019-06-01 for every
        # fold, which warmed fold one by MUTING seventeen of its twenty-four
        # months and scoring the remaining seven as if they were the fold, and
        # did nothing at all for folds two to four -- the date is behind them,
        # so they each started their detector cold on their own first bar. Each
        # window now carries its own run-up and `GeneticSearch.score` sets
        # `trade_from` to that window's opening bar.
        fixed = {
            **self.state.incumbent,
            **self.deployment,
        }
        for key in MODULE_KEYS.get(module, ()):
            fixed.pop(key, None)

        search = GeneticSearch(
            self.lab_fit,
            "four-module",
            space,
            self.symbols,
            windows=folds(self.fit_start, count=self.fold_count),
            fixed=fixed,
            seed=1000 + self.state.iteration,
            minimum_trades=40,
            rule_slots=slots,
            on_progress=lambda e: self._emit("fit", **e),
            on_evaluation=lambda e: self._emit("backtest", **e),
        )
        # Seeds are evaluated first, so a good suggestion is in the gene pool
        # from generation zero rather than having to be rediscovered by
        # mutation.
        #
        # The proposer's come first because they are about THIS hypothesis; the
        # library's follow, so a module still starts from measured knowledge on
        # the iterations where the advisor is resting on tokens or the grammar
        # refused everything it said. Both are starting points the search is
        # free to move away from, never defaults: `seeds.py` records what each
        # one measured on our own folds before it was written down.
        library = [s for s in seeds_for(module) if s not in seeds]
        for seed in (list(seeds) + library)[:8]:
            if slots:
                search.score({**space.sample(search.rng), slots[0]: seed})
        return search.run(generations=self.generations, population=self.population)

    def _remember(self, entry: dict[str, Any]) -> None:
        """Append one iteration to the history the gate reads, bounded.

        The bound belongs here and not only in `document()`. Applied on write
        alone, a long-lived process gated against every iteration it had ever
        run while a restarted one saw the last forty -- the same fit could open
        the forward window or not depending on when the process was last
        restarted, which is not a property research should have.
        """
        self.state.history.append(entry)
        del self.state.history[:-HISTORY_LIMIT]

    def fold_signature(self) -> str:
        """What a fit score was measured on, so two of them can be compared.

        A score is a number about a set of windows AND a set of assets. Change
        either and the number means something else -- the same configuration
        measured over three folds and over four is two different measurements,
        and so is the same configuration measured on 55 symbols and on 386.

        The windows half of this was added after the BEAR module sat locked out
        for sixteen iterations, gated against scores from a fold count it had
        never been measured under. The universe half is here so that the same
        mistake cannot be made again on the axis we are about to change: every
        score in the ledger was measured on an alphabetical 55, and none of
        them is a fact about the universe the loop trades from now on.
        """
        windows = folds(self.fit_start, count=self.fold_count)
        scope = ":".join(
            f"{key}={self.deployment[key]}" for key in sorted(self.deployment)
        )
        # The indicator catalogue is deliberately NOT in here, and I put it in
        # once before measuring. Adding columns does not change the ones that
        # were already there: VERSION 4 added twelve and every shared column is
        # bit-identical at three sample bars, warmup included
        # (`test_an_additive_catalogue_change_leaves_old_columns_alone`). A
        # score is a measurement of a configuration, and that measurement did
        # not move -- so an old score is still a bar a new fit must clear, and
        # discarding it would throw away real evidence for a change that
        # demonstrably changed nothing.
        #
        # A change to how an EXISTING column is computed is a different matter
        # and does invalidate. CONTRACT.md already covers it: bump VERSION, say
        # what it invalidates, re-run the ledger.
        # The RUN-UP is part of the measurement too, and this is the third axis
        # to teach that lesson. A fold scored from a cold start and the same
        # fold scored with four hundred bars of tape behind it are two different
        # measurements of the same configuration: the detector reaches the first
        # scored bar with an opinion in one and with nothing in the other, and
        # `depth` measures from a running high that the cold start put on the
        # fold's own opening bar. Fold one moved further still -- it used to be
        # muted to its last seven months by a global `trade_from` and is now
        # scored over all of itself.
        #
        # Without this, every score in the ledger would go on gating a search
        # that can no longer reproduce the conditions they were taken under.
        warm = ",".join(w.loaded for w in windows)
        return (
            f"{self.fit_start}:{windows[-1].end}:{len(windows)}"
            f"|{len(self.symbols)}{'|' + scope if scope else ''}"
            f"|warm={warm}"
        )

    def clears_gate(
        self, module: str, score: float | None
    ) -> tuple[bool, float | None]:
        """May this fit spend the forward window? And what was it measured against?

        2026 opens once per hypothesis, so it is spent only on a fit that
        improved -- compared against the best score for THIS MODULE, never
        against the best score anywhere.

        Comparing across modules is apples to oranges and it deadlocks. Each
        module searches a different sub-space with a different pinned context,
        so a good score in one locks the others out by construction: four
        consecutive DETECTOR iterations were refused for scoring -0.12 against a
        BEAR score of +0.02 that no DETECTOR fit could have reached.

        Comparing across FOLD SETS is the same mistake one level finer, and it
        cost sixteen iterations. `H-L001` was measured on three folds; every fit
        since has used four, over different windows and therefore different
        data. Its +0.0209 became the bear module's permanent high-water mark,
        and no four-fold bear fit ever came near it -- so BEAR, the module the
        loop's own diagnosis names as the one that is losing, did not open the
        forward window once in sixteen attempts while every other module did.
        A score is a number about a set of windows; change the windows and it is
        not the same measurement.

        A module with no comparable history has nothing to beat and opens on its
        first viable fit -- otherwise it could never get a first measurement.
        """
        if score is None or score <= -1e9:
            return False, None
        signature = self.fold_signature()
        seen = [
            h.get("fit_score")
            for h in self.state.history
            if h.get("module") == module
            and h.get("fit_score") is not None
            and h.get("folds") == signature
            # Entries written before this field existed carry v1 scores, which
            # are in returns rather than ratios. Defaulting the absent value to
            # the CURRENT version would admit exactly the numbers this filter
            # exists to exclude, so absent means old.
            and h.get("objective_version", 1) == search.OBJECTIVE_VERSION
        ]
        if not seen:
            return True, None
        best = max(seen)
        return score >= best - self.gate, best

    def training(self, genome: dict[str, Any], module: str) -> dict[str, Any] | None:
        """The same genome over the whole fittable era, recorded as one curve.

        Everything this laboratory knew about a promoted genome's training
        behaviour was four fold SCORES -- three numbers each, no curve, and the
        folds are evaluated rather than launched so nothing about them is
        persisted as a run. "How did this thing actually do from 2018 to 2025"
        was a question with no answer on screen, which is why the monitor could
        only ever show 2026.

        This is NOT a second opinion on the fit and it never feeds back: it is
        launched after the genome is already chosen, its return is recorded
        beside the forward result and read by nobody, and the search never sees
        it. It is a rendering of a decision already made.

        It ends at the lock like every fitting window, and it is loaded from the
        first bar held so the detector reaches its first trading bar warm --
        the same treatment the folds and the forward run now get.

        Failure here is not allowed to cost the iteration. The forward result is
        the one that matters and a companion curve is a convenience; returning
        `None` loses a chart, while raising would lose the 2026 run.
        """
        parameters = {
            **self.state.incumbent,
            **genome,
            **self.deployment,
            "trade_from": self.fit_start,
        }
        try:
            return self.lab_fit.launch(
                "four-module",
                symbols=self.symbols,
                start=HISTORY_BEGINS,
                end=LOCK,
                parameters=parameters,
                label=f"loop-{self.state.iteration:03d}-{module.lower()}-training",
                submitted_by=team.LOOP.handle,
            )
        except Exception as exc:  # noqa: BLE001
            self._emit("training-failed", detail=str(exc)[:200])
            return None

    def forward(self, genome: dict[str, Any], module: str) -> dict[str, Any]:
        """The single 2026 shot. Recorded, published, never fed back."""
        parameters = {
            **self.state.incumbent,
            **genome,
            **self.deployment,
            "trade_from": self.trade_from,
        }
        return self.lab_forward.launch(
            "four-module",
            symbols=self.symbols,
            start=self.forward_start,
            end=self.forward_end,
            parameters=parameters,
            label=f"loop-{self.state.iteration:03d}-{module.lower()}-2026",
            submitted_by=team.LOOP.handle,
            # The one run per iteration a person might actually be watching.
            progress=True,
        )

    # -- one whole iteration ------------------------------------------------- #

    def iterate(self) -> dict[str, Any]:
        self.state.iteration += 1
        started = time.time()
        identifier = f"H-L{self.state.iteration:03d}"
        # Set BEFORE the first emit, so `begin` lands in this hypothesis's
        # journal rather than the previous one's.
        self._journal_id = identifier
        self._emit("begin", id=identifier)

        frame = self.frame()
        module = frame["target_module"]
        self._emit("frame", module=module, why=frame["why"][:400])

        # Announced before it happens, not after. Consulting the cluster and the
        # advisors takes minutes, and a heartbeat that only moves on completion
        # leaves a reader watching the previous stage wondering if it hung.
        self._emit("consulting", module=module)
        consultation = self.consult(frame)
        self._emit(
            "consulted",
            module=module,
            detail=(
                f"{len(consultation['seed_rules'])} seed rules · "
                f"{len(consultation['peers'])} peer replies"
                # Named, because zero seeds from a working advisor and zero
                # seeds from a grammar that refused everything it said are the
                # same line otherwise.
                + (
                    f" · {len(rejected)} rejected by the grammar: {rejected[0]}"
                    if (
                        rejected := (consultation.get("proposal") or {}).get(
                            "rejected_rules"
                        )
                        or []
                    )
                    else ""
                )
            ),
            # The consultation itself, for the diagram and the journal. Who was
            # asked and what each one said back; whether the proposer was the
            # one allowed to go and read outside this repository; the claim it
            # is actually proposing, and the rules it wants seeded. Counts alone
            # cannot answer "is this loop being fed new ideas or its own" --
            # which is the question the whole observability effort exists for.
            advisors=consultation.get("advisors") or {},
            peers=len(consultation.get("peers") or []),
            peer_handles=[
                str(p.get("handle") or p.get("from") or "?")
                for p in (consultation.get("peers") or [])
            ][:12],
            web=bool(consultation.get("proposer_had_web")),
            claim=str((consultation.get("proposal") or {}).get("claim") or "")[:400],
            seed_rules=[str(r)[:200] for r in (consultation.get("seed_rules") or [])][
                :8
            ],
            critique=str((consultation.get("critique") or {}).get("verdict") or "")[
                :200
            ],
        )
        proposal = consultation["proposal"]
        # A proposal about a different module is advice, not this iteration's
        # hypothesis. The claim is what the ledger records as the thing tried,
        # and attaching a sentence about BEAR to a run that moved sizing would
        # make the record say something that did not happen. Latent until POLICY
        # existed and the proposer -- whose schema did not list it -- answered
        # about something else.
        on_target = bool(proposal) and proposal.get("module") == module
        statement = statement_for(module, proposal)

        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "module": module,
                    "seeds": consultation["seed_rules"],
                    "iteration": self.state.iteration,
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()[:16]

        record: dict[str, Any] = {
            "id": identifier,
            "iteration": self.state.iteration,
            "piece": module.lower(),
            "statement": statement,
            "config_fingerprint": fingerprint,
            "consulted_cluster": bool(self.cluster),
            "advisors": consultation["advisors"],
            "peers": consultation["peers"][:8],
            "opened_2026": False,
            "commit": "",
            "recorded": _now(),
            "metrics": {},
        }
        if proposal:
            record["proposal"] = proposal
            if not on_target:
                # Kept, because it is still advice worth having, and named,
                # because a reader must be able to tell it was not what this
                # iteration tested.
                record["proposal_off_target"] = proposal.get("module")
        if consultation["critique"]:
            record["critique"] = consultation["critique"]

        try:
            fitted = self.fit(module, consultation["seed_rules"])
        except Exception as exc:  # noqa: BLE001 - one bad iteration must not end the loop
            self.state.consecutive_failures += 1
            record["verdict"] = "ABANDONED"
            record["notes"] = f"the fit failed: {type(exc).__name__}: {exc}"
            self._emit(
                "error", detail=record["notes"], trace=traceback.format_exc()[:800]
            )
            self._record(record)
            self._save()
            return record

        score = (fitted.get("score") or {}).get("value")
        record["metrics"]["fit"] = {
            "score": score,
            "returns": (fitted.get("score") or {}).get("returns"),
            "drawdowns": (fitted.get("score") or {}).get("drawdowns"),
            "trades": (fitted.get("score") or {}).get("trades"),
            # How much of the book the folds actually deployed, and under which
            # objective the score above was computed. Both are recorded because
            # a score is meaningless without them: v1 numbers are returns and v2
            # numbers are ratios, and a run at 0.2% exposure is an abstention
            # whatever it scored.
            "exposure": (fitted.get("score") or {}).get("exposure"),
            "objective_version": (fitted.get("score") or {}).get("objective_version"),
            "rejected": (fitted.get("score") or {}).get("rejected"),
            "evaluations": fitted.get("evaluations"),
            "seed": fitted.get("seed"),
            "folds": self.fold_signature(),
        }
        for slot in ("entry_rule", "exit_rule"):
            tree = fitted["genome"].get(f"{module.lower()}_{slot}")
            if tree:
                record["metrics"].setdefault("rules", {})[slot] = grammar.describe(tree)
        self._emit("fitted", score=score, genome_keys=sorted(fitted["genome"]))

        previous_score = self.state.incumbent_score
        opens, best_known = self.clears_gate(module, score)
        if not opens:
            record["verdict"] = "REFUTED"
            record["notes"] = (
                f"the fit did not clear the gate (score {score}, best known for "
                f"{module} "
                + ("none" if best_known is None else f"{best_known:.4f}")
                + "); the forward window was not opened."
            )
            self.state.consecutive_failures += 1
        else:
            # THE VERDICT IS DECIDED HERE, BEFORE 2026 IS OPENED AT ALL.
            #
            # Everything below this point that touches the sealed window is
            # reporting. The training run is the same genome over the fittable
            # era; its attribution answers "did the piece I moved actually
            # trade", and the fold score answers "is it better than the
            # incumbent". Both end at the lock, and together they are the whole
            # decision. Ordering it this way is not a stylistic choice: while
            # the verdict came after the forward run, every reader of this
            # function had to check by hand whether 2026 had been consulted.
            # Now it cannot have been, because it has not happened yet.
            companion = self.training(fitted["genome"], module)
            if companion:
                record["metrics"]["training"] = {
                    "backtest_id": companion.get("backtest_id"),
                    "return_pct": companion.get("return_pct"),
                    "max_drawdown": companion.get("max_drawdown"),
                    "trades": companion.get("trades"),
                }
                # Announced, because the card shows this iteration's two results
                # side by side and this is the first of them. Without it the
                # training figure had to fall back to whichever fold of whichever
                # candidate the search finished last.
                self._emit("trained", **record["metrics"]["training"])
            try:
                trained = diagnose(self.store, companion["backtest_id"])
                record["metrics"]["attribution"] = trained["by_module"]
            except Exception as exc:  # noqa: BLE001
                record["metrics"]["attribution"] = {}
                record["notes_training"] = f"training attribution failed: {exc}"

            traded = int((companion or {}).get("trades") or 0) > 0
            # Did the fittable era exercise the piece this iteration moved, or
            # did it just measure the incumbent again under a different name?
            acted = tested_the_module(module, record["metrics"].get("attribution"))
            # The selection criterion, and the only one: the walk-forward score
            # over four disjoint folds, none of which can serve a bar past
            # 2025-12-31. `clears_gate` already compares like with like via the
            # fold signature, so a score from a different fold layout cannot
            # promote anything.
            improved = (
                traded
                and acted
                and (
                    previous_score is None
                    or (score is not None and score > previous_score)
                )
            )

            # The one moment worth watching live: the sealed window opening on
            # this hypothesis, once, whatever it says.
            self._emit("opening", module=module, detail="2026 is opening on this fit")
            try:
                forward = self.forward(fitted["genome"], module)
            except Exception as exc:  # noqa: BLE001 - same contract as the fit above
                # A fit that raised has been recorded ABANDONED since the loop
                # was written; a forward that raised was not, and the whole
                # iteration vanished. H-L069 is the gap that proves it: thirty
                # minutes of fitting, a policy at -0.171, the window announced
                # as opening, and then nothing -- no record, no id, and a
                # ledger that skips from H-L068U to H-L070 without saying why.
                # An append-only research record with an unexplained hole in it
                # is worse than one with a failure in it.
                self.state.consecutive_failures += 1
                record["verdict"] = "ABANDONED"
                record["notes"] = (
                    f"the fit cleared the gate (score {score}) and the forward "
                    f"window was announced, but the run itself failed: "
                    f"{type(exc).__name__}: {exc}. 2026 was NOT spent on this "
                    "hypothesis -- the run never started, so the window remains "
                    "unopened and the hypothesis may be tried again."
                )
                self._emit(
                    "error", detail=record["notes"], trace=traceback.format_exc()[:800]
                )
                self._record(record)
                self._save()
                return record
            record["opened_2026"] = True
            record["metrics"]["forward"] = {
                "backtest_id": forward.get("backtest_id"),
                "return_pct": forward.get("return_pct"),
                "max_drawdown": forward.get("max_drawdown"),
                "trades": forward.get("trades"),
                "win_rate": forward.get("win_rate"),
                "average_exposure": forward.get("average_exposure"),
                "time_in_market": forward.get("time_in_market"),
            }
            # What the market did over the same window. Reported beside a result
            # already decided, exactly like the forward return itself, and read
            # by nothing that selects. Without it the archive cannot tell a book
            # that correctly refused to participate from one that did nothing --
            # they are the same number and opposite findings.
            record["metrics"]["forward_benchmark"] = (
                benchmarks.market(
                    self.config,
                    self.trade_from,
                    self.forward_end,
                    strategy_return=forward.get("return_pct"),
                    symbols=self.symbols or None,
                )
                if self.config is not None
                else None
            )
            self.state.last_forward_id = forward.get("backtest_id")
            self._emit(
                "forward",
                backtest_id=forward.get("backtest_id"),
                return_pct=forward.get("return_pct"),
                # Carried so the card can put trades and drawdown under the 2026
                # figure. A return with no trade count beside it is the shape
                # that let a run which stood aside all year read as a result.
                max_drawdown=forward.get("max_drawdown"),
                trades=forward.get("trades"),
            )

            # The FORWARD attribution is recorded and read by nobody. It is
            # kept because a reader of the archive wants to know which module
            # produced the 2026 number; it is not consulted by the verdict, the
            # incumbent, or the next frame.
            try:
                observation = diagnose(self.store, forward["backtest_id"])
                record["metrics"]["forward_attribution"] = observation["by_module"]
                record["notes_observation"] = summarise(observation)
                self._emit(
                    "observed",
                    module=module,
                    detail=record["notes_observation"][:400],
                    by_module=observation["by_module"],
                )
            except Exception as exc:  # noqa: BLE001
                record["notes_observation"] = f"attribution failed: {exc}"
                self._emit("observed", detail=f"attribution failed: {exc}"[:200])

            current = forward.get("return_pct")
            record["verdict"] = verdict_of(traded, acted, improved)
            record["notes"] = (
                f"walk-forward score {score}, against incumbent "
                f"{'none' if previous_score is None else format(previous_score, '.4f')}"
                f" -- which is what this verdict is made of. "
                + (
                    "The incumbent moves."
                    if improved
                    else (
                        "The training era took no trades: the configuration "
                        "stood aside rather than performed, so it is not an "
                        "improvement."
                        if not traded
                        else (
                            f"The {module} module took no trades before the "
                            "lock, so this run measured the incumbent rather "
                            "than the hypothesis: nothing about this direction "
                            "was tested."
                            if not acted
                            else "The incumbent stands; this direction is "
                            "recorded as dead."
                        )
                    )
                )
                # Reported, never weighed. It is the one number this laboratory
                # is trying to move and the one number that may not be allowed
                # to move the search.
                + f" Forward 2026, for the record and for nothing else: "
                f"{current:+.2%} on {forward.get('trades') or 0} trades at "
                f"{(forward.get('average_exposure') or 0):.2%} average exposure. "
                # Against what the market did over the same window, because
                # "+1.12%" and "+1.12% while the basket fell 31%" are different
                # findings and the laboratory reported only the first for
                # ninety iterations.
                 + benchmarks.describe(record["metrics"].get("forward_benchmark") or {})
            )
            if improved:
                self.state.incumbent = {**self.state.incumbent, **fitted["genome"]}
                self.state.incumbent_score = score
                # Carried for display, and written only when the genome it
                # describes has already been chosen on the folds. Reading it
                # back into a decision is the leak this iteration closed.
                self.state.incumbent_forward = current
                self.state.incumbent_backtest_id = forward.get("backtest_id")
                self.state.last_training_id = (
                    record["metrics"].get("training") or {}
                ).get("backtest_id")
                self.state.consecutive_failures = 0
            else:
                self.state.consecutive_failures += 1

        self._remember(
            {
                "iteration": self.state.iteration,
                "id": identifier,
                "module": module,
                "fit_score": score,
                # What the score was measured on. Without it a later fit cannot
                # tell whether an earlier number is comparable, and the gate
                # silently compares measurements of different things.
                "folds": self.fold_signature(),
                # And by WHAT it was measured. Same argument one level up: v1
                # scores are returns and v2 scores are ratios, so a v2 fit
                # compared against a v1 high-water mark clears a gate it never
                # met. In this direction the failure is permissive rather than
                # blocking -- ratios are numerically larger than returns, so
                # every candidate would pass and the sealed window would be
                # spent on hypotheses that beat nothing.
                "objective_version": search.OBJECTIVE_VERSION,
                "forward": (record["metrics"].get("forward") or {}).get("return_pct"),
                "verdict": record["verdict"],
                "at": _now(),
                "seconds": round(time.time() - started),
            }
        )
        self._record(record)
        self._save()

        if self.cluster:
            self.cluster.post(
                team.LOOP.handle,
                f"## Iteration {self.state.iteration} — {record['verdict']}\n\n"
                f"**Module:** {module}\n\n"
                f"**Hypothesis:** {statement}\n\n"
                f"**Fit:** score {score}\n\n"
                f"**Forward 2026:** "
                + (
                    f"{record['metrics']['forward']['return_pct']:+.2%} on "
                    f"{record['metrics']['forward']['trades']} trades"
                    if record["opened_2026"]
                    else "not opened -- the fit did not clear the gate"
                )
                + f"\n\n{record['notes']}\n\n"
                + "\n".join(
                    f"- {slot}: `{text}`"
                    for slot, text in (record["metrics"].get("rules") or {}).items()
                ),
            )
        self._emit("recorded", id=identifier, verdict=record["verdict"])
        return record

    def settings(self) -> dict[str, Any]:
        """The loop's own knobs, re-read every iteration.

        Re-read rather than cached so a change -- whether an evolve session's or
        a person's -- takes effect at the next iteration without restarting a
        process that may be thirty minutes into a fit.
        """
        if self.tuning_path is None:
            return tuning.defaults()
        return tuning.load(self.tuning_path)

    def apply_settings(self) -> None:
        current = self.settings()
        self.EXPLORE_EVERY = int(current["explore_every"])
        self.generations = int(current["generations"])
        self.population = int(current["population"])
        self.gate = float(current["gate"])

    def evolve(self) -> dict[str, Any] | None:
        """One turn where the subject is the loop rather than the market.

        Returns what it did, or None when there is no reviewer or nothing came
        back. Never raises into `run_forever`: a failed self-review is not a
        research event and must not cost an iteration.

        The two outputs are deliberately asymmetric. Knob changes are numbers
        from a whitelist, range-checked twice and written to the ledger, so they
        are auditable and reversible. The memory note is prose appended to a
        notebook that is never rewritten -- a process that can edit its own
        account of being wrong can delete the evidence, and the deletion looks
        exactly like tidying up.
        """
        reviewer = self.reviewer_of_self
        if reviewer is None or not getattr(reviewer, "available", False):
            return None
        brief = evolve_module.briefing(
            self.ledger_digest(),
            self.settings(),
            self.state.history,
            self.last_advisors,
        )
        answer = evolve_module.validate(reviewer.ask(brief))
        if answer is None:
            self._emit(
                "evolve",
                detail=f"no usable reply: {getattr(reviewer, 'last_error', None)}",
            )
            return None

        changes = (
            tuning.apply(self.tuning_path, answer["knobs"]) if self.tuning_path else []
        )
        if changes:
            self.apply_settings()
        wrote = (
            evolve_module.append_memory(
                self.memory_path, answer["memory_note"], self.state.iteration
            )
            if self.memory_path
            else False
        )

        # An unattended process that retunes itself and leaves no trace is one
        # nobody can audit, and afterwards is the only time anyone looks.
        record = {
            "id": f"H-EVOLVE-{self.state.iteration:03d}",
            "iteration": self.state.iteration,
            "piece": "loop",
            "verdict": "NOTE",
            "statement": "self-review of the loop's own behaviour",
            "notes": answer["reasoning"][:800],
            "recorded": _now(),
            "metrics": {"knob_changes": changes, "memory_note_written": wrote},
            "observations": answer["observations"],
        }
        self._record(record)
        self._emit(
            "evolve",
            detail=(
                f"{len(changes)} knob change(s)"
                + (", memory note written" if wrote else "")
            ),
            changes=changes,
        )
        if self.cluster:
            self.cluster.post(
                team.LOOP.handle,
                f"## Iteration {self.state.iteration} — the loop reviewed itself\n\n"
                + (
                    "\n".join(
                        f"- `{c['knob']}` {c['from']} → {c['to']}" for c in changes
                    )
                    or "- no settings changed"
                )
                + f"\n\n{answer['reasoning']}"
                + (
                    "\n\n" + "\n".join(f"- {o}" for o in answer["observations"])
                    if answer["observations"]
                    else ""
                ),
            )
        return record

    def run_forever(
        self, pause_seconds: float = 5.0, maximum_iterations: int | None = None
    ) -> None:
        """There is no terminal state. A better result is always reachable.

        An iteration that raises is recorded and the loop continues: the failure
        mode this must not have is stopping quietly at 3am with nobody watching.
        """
        while maximum_iterations is None or self.state.iteration < maximum_iterations:
            try:
                # Settings first: a knob an evolve session moved, or a person
                # edited, takes effect here and not one iteration later.
                self.apply_settings()
                self.iterate()
                # The subject of every Nth turn is the loop itself. After the
                # iteration rather than before, so the review reads a record
                # that includes the run it is reviewing.
                if (
                    self.evolve_every > 0
                    and self.state.iteration % self.evolve_every == 0
                ):
                    self.evolve()
            except KeyboardInterrupt:
                self._emit("stopped", detail="interrupted by the operator")
                return
            except Exception as exc:  # noqa: BLE001
                self.state.consecutive_failures += 1
                self._emit(
                    "error",
                    detail=f"{type(exc).__name__}: {exc}",
                    trace=traceback.format_exc()[:1200],
                )
                self._save()
                # Back off as failures repeat, so a broken dependency does not
                # become a hot loop hammering the backtester and the Wall.
                time.sleep(
                    min(
                        300.0,
                        pause_seconds * (2 ** min(self.state.consecutive_failures, 6)),
                    )
                )
                continue
            time.sleep(pause_seconds)
