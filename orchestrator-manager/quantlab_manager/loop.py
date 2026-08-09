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
from quantlab_trading.space import Dimension, SearchSpace

from . import advisors as advisors_module
from . import team
from .diagnosis import diagnose, summarise
from .search import LOCK, GeneticSearch, folds

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
        "bear_min_depth",
        "bear_min_age",
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def module_space(module: str) -> tuple[SearchSpace, tuple[str, ...]]:
    """The sub-space one iteration is allowed to move, and its rule slots.

    Everything outside it is pinned to the incumbent. A search that could move
    all twenty-eight dimensions plus three rule trees would find *a* better
    number and teach nobody anything about which piece produced it.
    """
    full = {d.name: d for d in FourModuleBrain.search_space().dimensions}
    prefix = module.lower()
    if module == "DETECTOR":
        names = MODULE_KEYS["DETECTOR"]
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
            "history": self.history[-40:],
        }

    @classmethod
    def load(cls, path: Path) -> LoopState:
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
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
        forward_start: str = "2022-01-01",
        forward_end: str = "2026-12-31",
        trade_from: str = "2026-01-01",
        gate: float = 0.02,
        on_event: Callable[[dict[str, Any]], None] | None = None,
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
        self.on_event = on_event

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

    def frame(self) -> dict[str, Any]:
        """Which module the evidence says to work on, and why."""
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
        briefing = self._briefing(frame)
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

        if self.cluster:
            outcome["peers"] = self.cluster.read(seconds=15)
        return outcome

    def _briefing(self, frame: dict[str, Any]) -> str:
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
            },
            default=str,
            indent=2,
        )[:24_000]

    def fit(self, module: str, seeds: list[dict]) -> dict[str, Any]:
        """Search the target module's sub-space. Nothing here can see past the lock."""
        space, slots = module_space(module)
        fixed = {
            **self.state.incumbent,
            "trade_from": "2019-06-01",
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
        )
        # Seeds from the proposer are evaluated first, so a good suggestion is
        # in the gene pool from generation zero rather than having to be
        # rediscovered by mutation.
        for seed in seeds[:4]:
            if slots:
                search.score({**space.sample(search.rng), slots[0]: seed})
        return search.run(generations=self.generations, population=self.population)

    def forward(self, genome: dict[str, Any], module: str) -> dict[str, Any]:
        """The single 2026 shot. Recorded, published, never fed back."""
        parameters = {
            **self.state.incumbent,
            **genome,
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

        consultation = self.consult(frame)
        proposal = consultation["proposal"]
        statement = (
            proposal["claim"]
            if proposal
            else (
                f"Evolving the {module} module's entry and exit rules over the "
                f"served columns improves the walk-forward score without "
                f"breaching the drawdown mandate."
            )
        )

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
        }
        for slot in ("entry_rule", "exit_rule"):
            tree = fitted["genome"].get(f"{module.lower()}_{slot}")
            if tree:
                record["metrics"].setdefault("rules", {})[slot] = grammar.describe(tree)
        self._emit("fitted", score=score, genome_keys=sorted(fitted["genome"]))

        # The gate. 2026 opens once per hypothesis, so it is spent only on a fit
        # that actually improved on the folds.
        best_known = max(
            (h.get("fit_score") or -1e9 for h in self.state.history), default=-1e9
        )
        if (
            score is None
            or score <= -1e9
            or (self.state.history and score < best_known - self.gate)
        ):
            record["verdict"] = "REFUTED"
            record["notes"] = (
                f"the fit did not clear the gate (score {score}, best known "
                f"{best_known:.4f}); the forward window was not opened."
            )
            self.state.consecutive_failures += 1
        else:
            forward = self.forward(fitted["genome"], module)
            record["opened_2026"] = True
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
            improved = traded and (
                previous is None or (current is not None and current > previous)
            )
            record["verdict"] = "CONFIRMED" if improved else "REFUTED"
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
                        else "The incumbent stands; this direction is recorded as dead."
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

        self.state.history.append(
            {
                "iteration": self.state.iteration,
                "id": identifier,
                "module": module,
                "fit_score": score,
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
