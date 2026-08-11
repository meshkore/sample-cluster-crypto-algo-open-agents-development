"""The never-ending loop: diagnose, propose, consult, fit, one forward shot, record.

This is the thing the operator asked for. Not a script that runs a backtest, but
a process that decides *what to run next* from what the last run did, argues
about it in public, tries it, records the verdict whichever way it falls, and
goes again. There is no terminal state. A better result is always reachable, so
"done" is not a condition this can be in.

    FRAME     read the ledger and diagnose the last forward run -> target module
    CONSULT   post the framed hypothesis; ask the proposer; let the critic refute
    COMPOSE   build the population: the incumbent, plus seeds, plus invention
    FIT       genetic search over four disjoint folds, everything <= 2025-12-31
    FORWARD   if the fit clears the gate, open 2026 ONCE
    OBSERVE   attribute the forward run: which module, which exit, how much
    RECORD    append the ledger, post the result, update the incumbent or not

**What makes it converge rather than wander.** Three things. The diagnosis picks
the target module from arithmetic rather than from a guess, so effort lands
where the money is being lost. The incumbent only moves when a candidate beats
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
from . import team
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


@dataclass
class LoopState:
    """What survives between iterations. Small on purpose: everything else is
    recoverable from the ledger and the database."""

    iteration: int = 0
    incumbent: dict[str, Any] = field(default_factory=dict)
    incumbent_forward: float | None = None
    incumbent_backtest_id: str | None = None
    last_forward_id: str | None = None
    consecutive_failures: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def document(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "incumbent": self.incumbent,
            "incumbent_forward": self.incumbent_forward,
            "incumbent_backtest_id": self.incumbent_backtest_id,
            "last_forward_id": self.last_forward_id,
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
            "incumbent_forward",
            "incumbent_backtest_id",
            "last_forward_id",
            "consecutive_failures",
            "history",
        ):
            if key in payload:
                setattr(state, key, payload[key])
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
        on_event: Callable[[dict[str, Any]], None] | None = None,
        publish: Callable[[dict[str, Any]], None] | None = None,
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
        self.generations = generations
        self.population = population
        self.fold_count = fold_count
        self.fit_start = fit_start
        self.forward_start = forward_start
        self.forward_end = forward_end
        self.trade_from = trade_from
        # How much better than the incumbent a fit must be before the forward
        # window is spent on it. 2026 opens once per hypothesis and there are
        # only so many hypotheses worth spending it on.
        self.gate = gate
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
        self._beat_started: str | None = None
        self._beat_module: str | None = None
        self._beat_fit: dict[str, Any] | None = None
        self._beat_last: dict[str, Any] | None = None

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
        self.state = LoopState.load(self.state_path)

    # -- plumbing ------------------------------------------------------------ #

    def _emit(self, stage: str, **payload: Any) -> None:
        event = {
            "at": _now(),
            "iteration": self.state.iteration,
            "stage": stage,
            **payload,
        }
        if self.on_event:
            self.on_event(event)
        else:
            print(json.dumps(event, default=str)[:600], flush=True)
        self._beat(event)

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
        "opening": "opening the sealed 2026 window",
        "forward": "the 2026 result is in",
        "recorded": "recording the verdict",
        "error": "an iteration failed",
    }

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
        document = {
            "at": event.get("at"),
            "iteration": self.state.iteration,
            "stage": stage,
            "phase": self.PHASE_LABELS.get(stage, stage),
            "module": self._beat_module,
            "started_at": self._beat_started,
            "fit": self._beat_fit,
            "last_backtest": self._beat_last,
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

    def ledger_tail(self, count: int = 12) -> list[dict[str, Any]]:
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
        return records[-count:]

    def _record(self, record: dict[str, Any]) -> None:
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a") as handle:
                handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        except OSError as exc:
            self._emit("warning", detail=f"cannot append the ledger: {exc}")

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

        forward_id = self.state.last_forward_id
        if not forward_id:
            recent = [
                r
                for r in self.store.runs(limit=60)
                if str(r.get("window_end") or "") >= "2026-01-01"
                and (r.get("trades") or 0) >= 0
            ]
            forward_id = recent[0]["backtest_id"] if recent else None
        if not forward_id:
            return {
                "target_module": "BEAR",
                "diagnosis": None,
                "why": (
                    "no forward run on record yet; starting on the bear module, "
                    "which is the piece the standing hypothesis calls the hard one"
                ),
            }
        report = diagnose(self.store, forward_id)
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

        if self.proposer is not None and self.proposer.available:
            raw = self.proposer.ask(briefing)
            proposal = advisors_module.validate_proposal(raw)
            outcome["proposal"] = proposal
            outcome["advisors"][self.proposer.handle] = (
                "answered"
                if proposal
                else (self.proposer.last_error or "unusable reply")
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

        return outcome

    def _briefing(self, frame: dict[str, Any], peers: list[Any] | None = None) -> str:
        tail = [
            {
                "id": r.get("id"),
                "verdict": r.get("verdict"),
                "statement": str(r.get("statement", ""))[:280],
                "notes": str(r.get("notes", ""))[:400],
            }
            for r in self.ledger_tail(10)
        ]
        return json.dumps(
            {
                "target_module": frame["target_module"],
                "diagnosis": frame["why"],
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
            "evaluations": fitted.get("evaluations"),
            "seed": fitted.get("seed"),
            "folds": self.fold_signature(),
        }
        for slot in ("entry_rule", "exit_rule"):
            tree = fitted["genome"].get(f"{module.lower()}_{slot}")
            if tree:
                record["metrics"].setdefault("rules", {})[slot] = grammar.describe(tree)
        self._emit("fitted", score=score, genome_keys=sorted(fitted["genome"]))

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
            # The training curve for the same genome, launched AFTER the choice
            # is made and inside the lock. It is a rendering of a decision, not
            # an input to one -- nothing reads its return.
            companion = self.training(fitted["genome"], module)
            if companion:
                record["metrics"]["training"] = {
                    "backtest_id": companion.get("backtest_id"),
                    "return_pct": companion.get("return_pct"),
                    "max_drawdown": companion.get("max_drawdown"),
                    "trades": companion.get("trades"),
                }
            record["metrics"]["forward"] = {
                "backtest_id": forward.get("backtest_id"),
                "return_pct": forward.get("return_pct"),
                "max_drawdown": forward.get("max_drawdown"),
                "trades": forward.get("trades"),
                "win_rate": forward.get("win_rate"),
            }
            self.state.last_forward_id = forward.get("backtest_id")
            self._emit(
                "forward",
                backtest_id=forward.get("backtest_id"),
                return_pct=forward.get("return_pct"),
            )

            try:
                observation = diagnose(self.store, forward["backtest_id"])
                record["metrics"]["attribution"] = observation["by_module"]
                record["notes_observation"] = summarise(observation)
            except Exception as exc:  # noqa: BLE001
                record["notes_observation"] = f"attribution failed: {exc}"

            previous = self.state.incumbent_forward
            current = forward.get("return_pct")
            traded = int(forward.get("trades") or 0) > 0
            # A run that took no trades returned 0.00% by standing aside. That
            # beats a negative incumbent arithmetically and it is not an
            # improvement -- it is the absence of a result. The first iteration
            # recorded CONFIRMED on exactly that and moved the incumbent to a
            # configuration whose gate refuses to trade at all.
            # Did 2026 exercise the piece this iteration moved, or did it just
            # measure the incumbent again under a different name?
            acted = tested_the_module(module, record["metrics"].get("attribution"))
            improved = (
                traded
                and acted
                and (previous is None or (current is not None and current > previous))
            )
            record["verdict"] = verdict_of(traded, acted, improved)
            record["notes"] = (
                f"forward {current:+.2%} on {forward.get('trades') or 0} trades, "
                f"against incumbent "
                f"{'none' if previous is None else format(previous, '+.2%')}. "
                + (
                    "The incumbent moves."
                    if improved
                    else (
                        "No trades: the configuration stood aside rather than "
                        "performed, so it is not an improvement."
                        if not traded
                        else (
                            f"The {module} module took no trades in 2026, so this "
                            "run measured the incumbent rather than the "
                            "hypothesis: nothing about this direction was tested."
                            if not acted
                            else "The incumbent stands; this direction is "
                            "recorded as dead."
                        )
                    )
                )
            )
            if improved:
                self.state.incumbent = {**self.state.incumbent, **fitted["genome"]}
                self.state.incumbent_forward = current
                self.state.incumbent_backtest_id = forward.get("backtest_id")
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

    def run_forever(
        self, pause_seconds: float = 5.0, maximum_iterations: int | None = None
    ) -> None:
        """There is no terminal state. A better result is always reachable.

        An iteration that raises is recorded and the loop continues: the failure
        mode this must not have is stopping quietly at 3am with nobody watching.
        """
        while maximum_iterations is None or self.state.iteration < maximum_iterations:
            try:
                self.iterate()
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
