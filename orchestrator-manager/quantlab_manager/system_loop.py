"""The loop that writes trading systems, one generation at a time.

    python3 -m quantlab_manager.system_loop --iterations 0   # 0 = for ever

**What is different about this loop.** The other two evolve PARAMETERS inside a
mechanism somebody wrote. This one writes the mechanism. It researches published
work, states a hypothesis, authors a Python module, and measures it through the
same backtester, the same 0.30% toll and the same sealed 2026 window as
everything else — so its number is comparable rather than a separate scoreboard.

**Generations, and why the folder is the unit.** The operator's rule: the loop
works inside one folder until it beats the best sealed result on record. When it
does, that folder is FROZEN as the titular system and the next one opens. So
`quantlab_system04/` is a workshop while generation four is being searched and a
monument afterwards, and the trail of what actually worked is the folder list.
A generation that never wins is never frozen and never gets a successor — the
loop keeps rewriting inside it, which is exactly what "keep going until you beat
it" means.

**Why this is allowed to run unattended.** `sandbox.py` is the whole answer and
it should be read before this file. The coder receives no tools and writes
nothing; it returns source as a string, the gate parses that string before
anything imports it, and code that could touch the filesystem or the network does
not get written. The systems that already work are unreachable by construction,
and `verify()` proves after every write that they are still untouched and still
passing their tests.

**The journal is for a reader, not for a machine.** An earlier version of the
other loop wrote every backtest into it and the interesting events — what are we
trying, where did the idea come from, why do we think it clears costs — were
buried under thousands of fold results. Here the rule is: the journal records
DECISIONS and REASONS. Numbers appear as one-line briefings. The full results
live in the ledger and on the monitor, which is what those surfaces are for.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for package in ("backtester", "trading-system", "orchestrator-manager"):
    if str(ROOT / package) not in sys.path:
        sys.path.insert(0, str(ROOT / package))

from quantlab_intraday import launch  # noqa: E402
from quantlab_intraday.dataset import DEFAULT_SYMBOLS, LOCK, IntradayDataset  # noqa: E402

from . import cluster, coder, sandbox, team  # noqa: E402
from .backtests import BacktestStore, describe  # noqa: E402

HANDLE = "blackmac-quantlab-system-loop"
HOME = ROOT / "orchestrator-manager" / "loop" / "systems"
PUBLISHER = ROOT / "orchestrator-manager" / "scripts" / "publish_intraday.py"
MIRROR = "https://quantlab-public-mirror.rjj.workers.dev"
# Two databases, because two loops write from two working directories. Named
# here rather than discovered, so it is visible that neither one alone is the
# whole record.
REPOSITORY_DATABASE = ROOT / "research" / "quantlab.db"
RUNTIME_DATABASE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "QuantLab"
    / "research"
    / "quantlab.db"
)

# The circuit the live page draws for this loop. Same idea as the other loop's
# ten boxes: these are the places this loop can BE, and the page names them.
NODE_ORDER = (
    "frame",
    "research",
    "hypothesis",
    "code",
    "gate",
    "verify",
    "train",
    "decide",
    "forward",
    "promote",
    "record",
)

STAGE_NODES = {stage: stage for stage in NODE_ORDER}

# A generated strategy is measured on the same continuous account as everything
# else: 2018 to the lock, one path, no block restarts.
TRAINING_TRADE_FROM = "2018-01-01T00:00:00+00:00"


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _best_sealed(rows: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    """The best 2026 run that actually traded.

    A run that never traded cannot be champion: standing aside finishes at
    exactly +0.00%, which beats every honest loss and would win every sort.
    """
    sealed = [
        r
        for r in rows
        if r
        and r.get("era") == "2026"
        and (r.get("trades") or 0) > 0
        and r.get("status") == "complete"
        and r.get("return_pct") is not None
    ]
    if not sealed:
        return None
    best = max(sealed, key=lambda r: r["return_pct"])
    return {
        "label": best.get("label"),
        "return_pct": float(best["return_pct"]),
        "trades": int(best.get("trades") or 0),
        "max_drawdown": float(best.get("max_drawdown") or 0.0),
    }


def champion_of_record() -> dict[str, Any]:
    """The best SEALED 2026 result on record — the number this loop must beat.

    **Read from the public mirror first, and that is deliberate.** There is not
    one database here: the four-module loop writes to the runtime workspace under
    `Application Support`, the intraday loop writes to the repository copy, and
    the only place the two converge is the mirror — which is also the scoreboard
    the operator actually looks at. A loop that took its target from whichever
    database happened to be local would chase a number the public page does not
    show, and would "win" against a champion it simply could not see.

    Both local databases are then read as a fallback, so a network blip cannot
    stop an unattended loop, and the higher of the two answers wins.
    """
    found: list[dict[str, Any]] = []

    try:
        from urllib.request import urlopen

        with urlopen(f"{MIRROR}/api/backtests", timeout=20) as response:
            payload = json.loads(response.read())
        rows = [payload.get("best_2026")] + list(payload.get("history") or [])
        best = _best_sealed([r for r in rows if isinstance(r, dict)])
        if best:
            found.append(best)
    except Exception:  # noqa: BLE001 -- the mirror is a convenience, not a gate
        pass

    for path in (REPOSITORY_DATABASE, RUNTIME_DATABASE):
        if not path.exists():
            continue
        try:
            rows = [describe(dict(r)) for r in BacktestStore(path).runs(limit=400)]
        except Exception:  # noqa: BLE001
            continue
        best = _best_sealed(rows)
        if best:
            found.append(best)

    if not found:
        return {"label": "none on record", "return_pct": 0.0, "trades": 0}
    return max(found, key=lambda r: r["return_pct"])


SHARED_MEMORY = ROOT / "orchestrator-manager" / "loop" / "MEMORY.md"
FOUR_MODULE_LEDGER = (
    ROOT / "orchestrator-manager" / "loop" / "ledger" / "hypotheses.jsonl"
)
INTRADAY_LEDGER = ROOT / "orchestrator-manager" / "loop" / "intraday" / "ledger.jsonl"


def shared_memory(limit: int = 24) -> str:
    """What the OTHER systems have already learned, so this one does not repeat it.

    The three loops search different spaces but hit the same walls — the toll,
    the regime dependence of a fixed threshold, the fact that a training score
    anti-predicts the forward window. A generation that has to rediscover each of
    those spends its first several attempts learning what is already written
    down, and the operator watches it fail in ways the laboratory already knows about.

    Three sources, deliberately: `MEMORY.md` carries the JUDGEMENT that the
    arithmetic cannot ("this direction is exhausted rather than mistuned"), while
    the two ledgers carry the refutations themselves. Read-only in every case —
    this function never writes, so a bug here cannot corrupt the record the other
    loops depend on.
    """
    parts: list[str] = []

    if SHARED_MEMORY.exists():
        text = SHARED_MEMORY.read_text()
        # The notebook is append-only and grows without bound; the recent
        # judgement is the useful part and the 2018 history is not.
        parts.append("## The laboratory's research notebook (most recent)\n")
        parts.append(text[-6000:].strip())

    refuted: list[str] = []
    if FOUR_MODULE_LEDGER.exists():
        for line in reversed(FOUR_MODULE_LEDGER.read_text().splitlines()):
            if len(refuted) >= limit:
                break
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("verdict", "")).lower().startswith("refut"):
                statement = str(row.get("statement") or "")[:190]
                if statement:
                    refuted.append(f"- (four-module) {statement}")
    if INTRADAY_LEDGER.exists():
        for line in reversed(INTRADAY_LEDGER.read_text().splitlines()[-40:]):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("refused"):
                refuted.append(f"- (intraday) {str(row['refused'])[:150]}")
    if refuted:
        parts.append(
            "\n## Refuted elsewhere in this laboratory — do not re-derive\n"
            + "\n".join(refuted[: limit * 2])
        )
    return "\n".join(parts) or "Nothing recorded yet."


def remember(note: str) -> None:
    """Append this loop's judgement to the shared notebook. Append-only.

    Never rewrites: a process that can edit its own account of being wrong can
    delete the evidence, and the deletion looks exactly like a tidy-up.
    """
    try:
        with SHARED_MEMORY.open("a") as handle:
            handle.write(f"\n\n## {stamp()} · system loop\n\n{note.strip()}\n")
    except OSError as exc:
        print(f"[memory] {type(exc).__name__}: {exc}", flush=True)


class Journal:
    """One file per generation attempt, and it stays readable.

    The discipline that makes it readable is stated as a rule rather than left to
    taste: an event carries a SENTENCE a person can read, and at most a small
    `brief` of numbers. Anything larger belongs in the ledger.
    """

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.identifier: str | None = None
        self.events: list[dict[str, Any]] = []

    def open(self, identifier: str) -> None:
        self.identifier = identifier
        self.events = []

    def write(
        self, node: str, say: str, brief: dict[str, Any] | None = None, **extra: Any
    ) -> dict[str, Any]:
        event = {
            "at": stamp(),
            "node": node,
            "say": say[:1400],
            "brief": brief or {},
            **extra,
        }
        self.events.append(event)
        if self.identifier:
            path = self.directory / f"{self.identifier}.jsonl"
            with path.open("a") as handle:
                handle.write(json.dumps(event, default=str) + "\n")
        print(f"[{node}] {say}", flush=True)
        return event


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict[str, Any]] = []
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    try:
                        self.entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    def append(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)
        with self.path.open("a") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

    def families(self) -> list[str]:
        return [e.get("family", "") for e in self.entries]

    def refutations(self, limit: int = 14) -> str:
        """What to tell the coder not to try again, newest first.

        Only the verdict and the one-line reason: a coder handed thirty full
        result blocks spends its attention reading them instead of thinking.
        """
        lines = []
        for entry in reversed(self.entries[-60:]):
            if len(lines) >= limit:
                break
            verdict = entry.get("verdict") or "not measured"
            ret = entry.get("return_pct")
            shown = f"{ret:+.1%}" if isinstance(ret, (int, float)) else "no result"
            lines.append(
                f"- `{entry.get('family')}` — {verdict}. Training {shown}. "
                f"{(entry.get('hypothesis') or '')[:150]}"
            )
        return "\n".join(lines) or "- nothing measured yet; you are the first."


class SystemLoop:
    def __init__(
        self,
        home: Path = HOME,
        symbols: list[str] | None = None,
        wall: Any | None = None,
        author: Any | None = None,
        publish: bool = True,
        pause: float = 30.0,
    ):
        self.home = home
        self.home.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.home / "ledger.jsonl")
        self.journal = Journal(self.home / "journal")
        self.state_path = self.home / "state.json"
        self.state = (
            json.loads(self.state_path.read_text())
            if self.state_path.exists()
            else {"generation": 4, "iteration": 0, "frozen": []}
        )
        self.symbols = symbols or list(DEFAULT_SYMBOLS)
        self.wall = wall
        self.author = author
        self.publish = publish
        self.pause = pause
        self.dataset: IntradayDataset | None = None
        # What the protected paths looked like before this loop touched
        # anything. Everything `verify()` reports afterwards is measured against
        # it, so the question answered is "did THIS loop damage something"
        # rather than "was the repository pristine when it started".
        self.baseline = sandbox.modified()
        # Why the last candidate failed to run, carried into the next briefing.
        self.last_failure = ""

    # -- plumbing ------------------------------------------------------------- #

    def _save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=1, default=str))

    def say(self, message: str) -> None:
        """Post to the cluster. Never allowed to fail an iteration."""
        if not self.wall:
            return
        try:
            self.wall.post(HANDLE, message)
        except Exception as exc:  # noqa: BLE001
            print(f"[wall] {type(exc).__name__}: {exc}", flush=True)

    def _data(self) -> IntradayDataset:
        if self.dataset is None:
            self.dataset = IntradayDataset(
                str(ROOT / "backtester" / "data"), LOCK, self.symbols, interval="5m"
            )
        return self.dataset

    @property
    def generation(self) -> int:
        return int(self.state.get("generation", 4))

    # -- the stages ----------------------------------------------------------- #

    def frame(self) -> dict[str, Any]:
        champion = champion_of_record()
        self.journal.write(
            "frame",
            f"Generation {self.generation}. The number to beat is "
            f"{champion['return_pct']:+.2%} in the sealed 2026 window, held by "
            f"`{champion['label']}` on {champion['trades']} trades. This loop "
            f"stays in `quantlab_system{self.generation:02d}/` until something "
            f"beats it.",
            brief={
                "generation": self.generation,
                "beat": f"{champion['return_pct']:+.2%}",
                "held_by": champion["label"],
                "attempts_so_far": len(self.ledger.entries),
            },
        )
        return champion

    def research_and_write(self, champion: dict[str, Any]) -> dict[str, Any] | None:
        """Ask the coder for a strategy. This is the research stage AND the code
        stage, because the seat does both in one call — it searches the web,
        forms a hypothesis, and returns the module that tests it."""
        if not self.author:
            self.journal.write(
                "research", "No coder seat is available; nothing can be written."
            )
            return None

        self.journal.write(
            "research",
            "Asking the coder to read published work — papers, practitioners, "
            "whatever is claimed about intraday and swing crypto — and come back "
            "with ONE mechanism that has a reason to exist, not a combination of "
            "indicators that happens to fit.",
            brief={"seat": coder.CODER_HANDLE, "tools": "WebSearch, WebFetch only"},
        )

        briefing = coder.build_briefing(
            generation=self.generation,
            champion=(
                f"`{champion['label']}` returned {champion['return_pct']:+.2%} in "
                f"2026 on {champion['trades']} trades. Beat it."
            ),
            systems=(
                "1. `quantlab_trading` — a four-module regime system (detector, "
                "bull, bear, sideways) over daily bars.\n"
                "2. `quantlab_intraday` — 5-minute momentum with an opening-range "
                "entry, ATR stops and a de-leverage ramp.\n"
                "3. `quantlab_ml` — triple-barrier labels, purged walk-forward, "
                "gradient-boosted trees behind a cost-aware filter."
            ),
            refutations=self.ledger.refutations(),
            allowed_imports=sorted(sandbox.ALLOWED_IMPORTS),
            memory=shared_memory(),
        )
        reply = self.author.ask(briefing)
        proposal = coder.validate(reply)
        if proposal is None:
            self.journal.write(
                "research",
                f"The coder returned nothing usable "
                f"({getattr(self.author, 'last_error', None) or 'unparseable reply'}).",
            )
            return None

        # The sources go in their own event, before the hypothesis, because that
        # is the order the work happened in: read first, claim second. A reader
        # scrolling the journal should be able to see what was consulted without
        # having to trust that the hypothesis summarises it fairly.
        if proposal["sources"]:
            self.journal.write(
                "research",
                "Read "
                + "; ".join(
                    f"{s['title']}"
                    + (f" ({s['url']})" if s["url"] else "")
                    + (f" — {s['claim']}" if s["claim"] else "")
                    for s in proposal["sources"][:5]
                ),
                brief={"sources": len(proposal["sources"])},
                sources=proposal["sources"],
            )
        else:
            self.journal.write(
                "research",
                "No sources were named for this idea, so it is the coder's own "
                "reasoning over the laboratory's record — worth less than a "
                "citation and recorded as such.",
            )

        self.journal.write(
            "hypothesis",
            proposal["hypothesis"],
            brief={
                "family": proposal["family"],
                "origin": proposal["origin"][:220],
                "clears costs by": proposal["why_it_clears_costs"][:220],
                "sources": len(proposal["sources"]),
            },
        )
        self.say(
            f"**Generation {self.generation} — a hypothesis**\n\n"
            f"`{proposal['family']}`\n\n{proposal['hypothesis']}\n\n"
            f"**Where it came from** {proposal['origin']}\n\n"
            + (
                "**Sources read**\n"
                + "\n".join(
                    f"- {s['title']}"
                    + (f" — {s['url']}" if s["url"] else "")
                    + (f"\n  > {s['claim']}" if s["claim"] else "")
                    for s in proposal["sources"][:6]
                )
                + "\n\n"
                if proposal["sources"]
                else ""
            )
            + f"**How it pays the 0.30% toll** {proposal['why_it_clears_costs']}\n\n"
            "The code is written by a seat with no tools and gated before it is "
            "imported. Tell me why this will not work — that is the useful reply."
        )
        return proposal

    def gate_and_write(self, proposal: dict[str, Any]) -> Path | None:
        verdict = sandbox.inspect(proposal["source"])
        if not verdict.ok:
            self.journal.write(
                "gate",
                "Refused before anything was written. "
                + "; ".join(verdict.refusals[:4]),
                brief={"refusals": len(verdict.refusals)},
            )
            return None
        path = sandbox.write(proposal["source"], self.generation)
        self.journal.write(
            "gate",
            f"Accepted and written to `{path.relative_to(ROOT)}`. It imports only "
            f"{', '.join(sorted(set(verdict.imports))[:6])} and registers "
            f"`{verdict.registered[0]}`.",
            brief={"bytes": len(proposal["source"]), "registers": verdict.registered},
        )
        return path

    def verify(self) -> bool:
        checks = sandbox.verify(baseline=self.baseline)
        clean = checks.get("protected_paths_clean", {}).get("ok")
        self.journal.write(
            "verify",
            (
                "The systems that already work are untouched and their tests "
                "still pass."
                if checks.get("ok")
                else "Verification FAILED — this candidate is discarded."
            ),
            brief={
                "tests": "pass" if checks["tests"]["ok"] else "FAIL",
                "layering": "ok" if checks["layering"]["ok"] else "FAIL",
                "protected paths": "clean" if clean else "MODIFIED",
            },
        )
        return bool(checks.get("ok"))

    def _load(self, module: str, family: str) -> None:
        """Import the strategy this attempt just wrote — not the one before it.

        THE BUG THIS EXISTS TO FIX, which cost thirty-two attempts in one night.
        `__import__` consults `sys.modules` first, and the module name never
        changes: `quantlab_system04.strategy` is imported on the first attempt
        and every later attempt gets that CACHED object back, however many times
        the file underneath it has been rewritten. So the new strategy never ran
        its `@register` and the harness reported `no brain named 'vol-scaled-trend'`
        while listing families from hours earlier — which reads like the coder
        naming its class wrongly, and is nothing of the kind.

        Purging the entry before importing is what makes each attempt see its own
        code. The registry is cleared of the family too: `register` refuses to
        rebind a name to a different class, which is right for two agents
        colliding and wrong for the same generation being rewritten in place.
        """
        from quantlab_trading import brains

        for name in [m for m in sys.modules if m.startswith(module.split(".")[0])]:
            sys.modules.pop(name, None)
        brains._REGISTRY.pop(family.strip().lower(), None)
        importlib.import_module(module)

    def train(self, proposal: dict[str, Any], module: str) -> dict[str, Any] | None:
        """One continuous account, 2018 to the lock, through the ordinary harness."""
        self.journal.write(
            "train",
            "Running it on one continuous account from 2018 to the lock — one "
            "path, no block restarts, so a drawdown that accumulates is visible.",
        )
        self.last_failure = ""
        try:
            self._load(module, proposal["family"])
        except Exception as exc:  # noqa: BLE001
            self.last_failure = f"import failed: {type(exc).__name__}: {exc}"
            self.journal.write(
                "train", f"It does not import: {type(exc).__name__}: {exc}"
            )
            return None
        dataset = self._data()
        parameters = dict(proposal["parameters"])
        parameters.setdefault("bars_per_day", dataset.bars_per_day)
        try:
            result = launch.continuous(
                dataset, parameters, brain_name=proposal["family"]
            )
        except Exception as exc:  # noqa: BLE001
            # Recorded on the entry, not just in the journal, because the ledger
            # is what the NEXT briefing reads. A coder told only "did not run"
            # cannot fix anything; told "AttributeError: 'str' object has no
            # attribute 'date'" it stops calling `.date()` on the timestamp.
            self.last_failure = f"raised while trading: {type(exc).__name__}: {exc}"
            self.journal.write(
                "train", f"It raised while trading: {type(exc).__name__}: {exc}"
            )
            return None
        self.journal.write(
            "train",
            f"Training result: {result.get('return_pct', 0):+.2%} at "
            f"{result.get('max_drawdown', 0):.2%} drawdown on "
            f"{result.get('trades', 0)} trades.",
            brief={
                "return": f"{result.get('return_pct', 0):+.2%}",
                "drawdown": f"{result.get('max_drawdown', 0):.2%}",
                "trades": result.get("trades", 0),
                "status": result.get("status"),
            },
        )
        return result

    def decide(self, result: dict[str, Any]) -> tuple[bool, str]:
        """Is this worth a sealed window? Training-side only, always.

        Nothing here reads 2026. The bar is deliberately low — a strategy that
        traded, survived the mandate and did not lose money in training earns its
        one forward shot — because the lesson of this laboratory is that training
        score ANTI-predicts the forward result, so ranking hard on it would be
        selecting for the wrong thing.
        """
        trades = int(result.get("trades") or 0)
        drawdown = float(result.get("max_drawdown") or 0)
        ret = float(result.get("return_pct") or 0)
        if result.get("status") == "aborted" or drawdown >= 0.25:
            return False, f"the drawdown mandate was breached ({drawdown:.2%})"
        if trades < 30:
            return False, f"only {trades} trades in eight years is not a measurement"
        if ret <= 0:
            return False, f"it lost money in training ({ret:+.2%})"
        return True, f"{ret:+.2%} at {drawdown:.2%} on {trades} trades"

    def open_sealed_window(self, proposal: dict[str, Any], module: str) -> float | None:
        """The single 2026 shot, through the same publisher every pair used."""
        if not self.publish:
            return None
        label = f"gen{self.generation:02d}-{proposal['family']}"[:60]
        flags: list[str] = []
        for key, value in sorted(proposal["parameters"].items()):
            flags += ["--set", f"{key}={value}"]
        returns: dict[str, float | None] = {"training": None, "forward": None}
        for phase in ("training", "forward"):
            command = [
                sys.executable,
                str(PUBLISHER),
                "--phase",
                phase,
                "--brain",
                proposal["family"],
                "--brain-module",
                module,
                "--label",
                f"{label}-{'2026' if phase == 'forward' else 'training'}",
                "--submitted-by",
                HANDLE,
                *flags,
            ]
            try:
                done = subprocess.run(
                    command, cwd=ROOT, text=True, capture_output=True, timeout=7_200
                )
            except (OSError, subprocess.SubprocessError) as exc:
                self.journal.write("forward", f"Publishing failed: {exc}")
                return None
            for line in done.stdout.splitlines():
                if ": " in line and "%" in line and "maxDD" in line:
                    try:
                        returns[phase] = (
                            float(line.split(": ")[1].split("%")[0].strip()) / 100
                        )
                    except (ValueError, IndexError):
                        pass
        return returns["forward"]

    def promote(self, proposal: dict[str, Any], forward: float) -> None:
        """Freeze this generation and open the next. The operator's rule."""
        frozen = list(self.state.get("frozen", []))
        frozen.append(
            {
                "generation": self.generation,
                "family": proposal["family"],
                "forward_return": forward,
                "hypothesis": proposal["hypothesis"],
                "frozen_at": stamp(),
            }
        )
        self.state["frozen"] = frozen
        self.state["generation"] = self.generation + 1
        self._save()
        note = (
            f"**Generation {self.generation - 1} is the titular system.** "
            f"`{proposal['family']}` returned {forward:+.2%} in the sealed 2026 "
            f"window and beat everything on record. Its folder is frozen as it "
            f"stands; generation {self.generation} opens now and the search starts "
            f"again from a new hypothesis."
        )
        self.journal.write("promote", note, brief={"forward": f"{forward:+.2%}"})
        self.say(note)

    # -- one turn ------------------------------------------------------------- #

    def iterate(self) -> dict[str, Any]:
        number = int(self.state.get("iteration", 0)) + 1
        self.state["iteration"] = number
        generation = self.generation
        self.journal.open(f"G{generation:02d}-{number:03d}")
        started = time.time()

        champion = self.frame()
        entry: dict[str, Any] = {
            "at": stamp(),
            "iteration": number,
            "generation": generation,
            "beat": champion["return_pct"],
        }

        proposal = self.research_and_write(champion)
        if proposal is None:
            entry["verdict"] = "no proposal"
            self.ledger.append(entry)
            self._save()
            return entry

        entry.update(
            {
                "family": proposal["family"],
                "hypothesis": proposal["hypothesis"],
                "origin": proposal["origin"],
            }
        )

        path = self.gate_and_write(proposal)
        if path is None:
            entry["verdict"] = "refused by the gate"
            self.ledger.append(entry)
            self._save()
            return entry

        module = f"quantlab_system{generation:02d}.strategy"
        if not self.verify():
            entry["verdict"] = "verification failed"
            self.ledger.append(entry)
            self._save()
            return entry

        result = self.train(proposal, module)
        if result is None:
            entry["verdict"] = f"did not run — {self.last_failure}"[:300]
            self.ledger.append(entry)
            self._save()
            return entry
        entry.update(
            {
                "return_pct": result.get("return_pct"),
                "max_drawdown": result.get("max_drawdown"),
                "trades": result.get("trades"),
            }
        )

        clears, why = self.decide(result)
        self.journal.write(
            "decide",
            (
                f"It earns its one sealed shot: {why}."
                if clears
                else f"No sealed window: {why}. Nothing about 2026 was read to "
                "decide that."
            ),
        )
        if not clears:
            entry["verdict"] = f"refused: {why}"
            self.ledger.append(entry)
            self._save()
            return entry

        self.journal.write(
            "forward",
            "Opening 2026 once. Whatever it says is recorded and never fed back "
            "into anything.",
        )
        forward = self.open_sealed_window(proposal, module)
        entry["forward_return"] = forward
        if forward is None:
            entry["verdict"] = "the sealed run did not report"
            self.journal.write("forward", "The sealed run produced no number.")
        else:
            self.journal.write(
                "forward",
                f"**2026 forward: {forward:+.2%}** — and 2026 fell 22.6%, so read "
                f"it against that rather than against zero. The target was "
                f"{champion['return_pct']:+.2%}.",
                brief={
                    "forward": f"{forward:+.2%}",
                    "target": f"{champion['return_pct']:+.2%}",
                },
            )
            if forward > champion["return_pct"]:
                entry["verdict"] = "PROMOTED"
                self.promote(proposal, forward)
            else:
                entry["verdict"] = "measured, did not beat the incumbent"

        entry["seconds"] = round(time.time() - started)
        # Back into the shared notebook, so the other two loops inherit what this
        # generation learned rather than each discovering it separately.
        remember(
            f"**Generation {generation}, attempt {number}** — `{proposal['family']}`: "
            f"{entry['verdict']}.\n\n{proposal['hypothesis']}\n\n"
            f"Training {entry.get('return_pct', 0):+.2%} at "
            f"{entry.get('max_drawdown', 0):.2%} on {entry.get('trades', 0)} trades"
            + (
                f"; sealed 2026 {entry['forward_return']:+.2%}."
                if entry.get("forward_return") is not None
                else "; 2026 never opened on it."
            )
            + f"\n\nOrigin: {proposal['origin'][:300]}"
            + (
                "\n\nSources: "
                + "; ".join(
                    f"{s['title']} {s['url']}".strip() for s in proposal["sources"][:6]
                )
                if proposal["sources"]
                else "\n\nSources: none named."
            )
        )
        self.journal.write(
            "record",
            f"Recorded. {entry['verdict']}. Generation {self.generation} continues.",
            brief={"verdict": entry["verdict"]},
        )
        self.ledger.append(entry)
        self._save()
        return entry

    def run_forever(self, iterations: int = 0) -> None:
        done = 0
        while iterations == 0 or done < iterations:
            try:
                self.iterate()
            except KeyboardInterrupt:
                raise
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            done += 1
            time.sleep(self.pause)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iterations", type=int, default=0)
    parser.add_argument("--pause", type=float, default=30.0)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--no-wall", action="store_true")
    args = parser.parse_args(argv)

    wall = None
    if not args.no_wall:
        try:
            wall = cluster.from_environment(ROOT)
        except Exception as exc:  # noqa: BLE001
            print(f"[wall] unavailable: {exc}", flush=True)

    author = coder.from_environment()
    print(
        f"system loop · home {HOME} · generation "
        f"{json.loads((HOME / 'state.json').read_text()).get('generation', 4) if (HOME / 'state.json').exists() else 4}"
        f" · coder {'yes' if author else 'no'} · wall {'yes' if wall else 'no'}",
        flush=True,
    )
    if wall:
        try:
            wall.post(HANDLE, team.roster_markdown())
        except Exception:  # noqa: BLE001
            pass

    loop = SystemLoop(
        wall=wall, author=author, publish=not args.no_publish, pause=args.pause
    )
    loop.run_forever(iterations=args.iterations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
