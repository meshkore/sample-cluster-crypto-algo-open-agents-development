from __future__ import annotations

import json
import signal
import sqlite3
import subprocess
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import Settings
from .loop import ResearchDirector
from .models import utc_now
from .public_mirror import PublicStatePublisher
from .forward import ForwardEvaluator
from .historical import HistoricalUniverseEvaluator
from .universe import UniverseManager


DAEMON_SCHEMA = """
CREATE TABLE IF NOT EXISTS daemon_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, level TEXT NOT NULL,
  message TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS development_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, status TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, return_code INTEGER,
  log_path TEXT, summary TEXT
);
"""


def _score(row: dict[str, Any]) -> float:
    return (
        (row.get("net_return") or -1.0)
        - (row.get("drawdown") or 1.0)
        + 0.05 * (row.get("sharpe") or 0.0)
    )


class DashboardData:
    def __init__(self, settings: Settings):
        self.settings = settings
        # Initialize schema once. Re-running migrations on every 3-second poll
        # contends with the backtest writer and makes the monitor appear frozen.
        self.director = ResearchDirector(settings)

    def snapshot(self) -> dict[str, Any]:
        director = self.director
        experiments = director.memory.experiments()
        current = experiments[-1] if experiments else None
        eligible = [
            row for row in experiments if row["status"] in {"PROMOTE", "CHAMPION"}
        ]
        champion = max(eligible, key=_score) if eligible else None
        candidate = max(experiments, key=_score) if experiments else None
        state = director.status()
        forward = ForwardEvaluator(self.settings, director.memory)
        latest_forward = forward.latest()
        active_forward = forward.active()
        with director.memory.session() as db:
            last_dev = db.execute(
                "SELECT * FROM development_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            committee = db.execute(
                "SELECT * FROM development_runs ORDER BY id DESC LIMIT 4"
            ).fetchall()
            last_event = db.execute(
                "SELECT * FROM daemon_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
            coverage = db.execute(
                """SELECT count(*) total,
                sum(CASE WHEN research_path IS NOT NULL THEN 1 ELSE 0 END) research_ready,
                sum(CASE WHEN forward_path IS NOT NULL THEN 1 ELSE 0 END) forward_ready,
                sum(CASE WHEN last_error IS NOT NULL THEN 1 ELSE 0 END) errors
                FROM asset_universe WHERE status='TRADING'"""
            ).fetchone()
            activity_row = db.execute(
                "SELECT * FROM runtime_activity WHERE singleton=1"
            ).fetchone()
            current_number = current.get("strategy_number") if current else None
            current_view = self._strategy_view(db, current_number, current, False)
            if active_forward:
                current_view = self._forward_strategy_view(db, active_forward)
            best_view = self._forward_strategy_view(db, latest_forward)
        activity = (
            dict(activity_row)
            if activity_row
            else {
                "phase": "STARTING",
                "message": "Preparando el siguiente trabajo",
                "details_json": "{}",
                "updated_at": utc_now(),
            }
        )
        activity["details"] = json.loads(activity.pop("details_json"))
        return {
            "service": {"state": "running", "updated_at": utc_now()},
            "loop": {
                "state": state["state"],
                "cycle": state["cycle"],
                "experiments": state["experiments"],
            },
            "current": self._public_experiment(current),
            "champion": self._public_experiment(champion),
            "best_unvalidated_candidate": self._public_experiment(candidate)
            if champion is None
            else None,
            "development": dict(last_dev) if last_dev else None,
            "committee": [dict(row) for row in committee],
            "strategy": current_view["definition"] if current_view else None,
            "current_strategy": current_view,
            "best_strategy": best_view,
            "activity": activity,
            "forward_2026": latest_forward,
            "data_coverage": {key: int(coverage[key] or 0) for key in coverage.keys()},
            "forward_status": "EVALUATED"
            if latest_forward
            else (
                "WAITING_FOR_PROMOTED_STRATEGY"
                if forward.qualified_strategy() is None
                else "WAITING_FOR_2026_DATA"
            ),
            "last_event": dict(last_event) if last_event else None,
            "warning": None
            if best_view
            else "Todavía no existe una Fase 2 forward completada desde el 01/01/2026.",
        }

    def _forward_strategy_view(
        self, db: sqlite3.Connection, forward: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if not forward:
            return None
        number = int(forward["strategy_number"])
        definition_row = db.execute(
            "SELECT * FROM strategy_definitions WHERE strategy_number=?", (number,)
        ).fetchone()
        experiment_row = db.execute(
            "SELECT * FROM experiments WHERE strategy_number=? ORDER BY created_at DESC LIMIT 1",
            (number,),
        ).fetchone()
        definition = dict(definition_row)
        for key in ("signal_json", "execution_json", "money_management_json"):
            definition[key.removesuffix("_json")] = json.loads(definition.pop(key))
        run = {
            key: value
            for key, value in forward.items()
            if key not in {"assets", "trades_ledger", "equity_curve"}
        }
        target_end = forward.get("target_end") or forward["period_end"]
        current_date = forward.get("current_date") or forward["period_end"]
        calendar_days = max(
            1,
            (
                datetime.fromisoformat(target_end)
                - datetime.fromisoformat(forward["period_start"])
            ).days
            + 1,
        )
        run.update(
            {
                "period_end": target_end,
                "current_date": current_date,
                "current_equity": forward["final_equity"],
                "open_positions": forward.get("open_positions", 0),
                "total_days": (
                    forward["total_days"]
                    if forward.get("total_days") is not None
                    and forward["total_days"] > 0
                    else calendar_days
                ),
                "processed_days": (
                    forward["processed_days"]
                    if forward.get("processed_days") is not None
                    else calendar_days
                ),
                "assets_available": forward["assets_available"],
            }
        )
        active = forward["status"] in {"FORWARD_TESTING", "FORWARD_PREPARING"}
        return {
            "strategy_number": number,
            "label": f"S{number:05d}",
            "validated": not active,
            "phase": "FORWARD_2026_ACTIVE" if active else "FORWARD_2026",
            "definition": definition,
            "experiment": self._public_experiment(
                dict(experiment_row) if experiment_row else None
            ),
            "backtest": run,
            "assets": forward["assets"],
            "trades": forward["trades_ledger"],
            "equity_curve": forward["equity_curve"],
        }

    def _strategy_view(
        self,
        db: sqlite3.Connection,
        number: int | None,
        experiment: dict[str, Any] | None,
        validated: bool,
    ) -> dict[str, Any] | None:
        if not number:
            return None
        definition_row = db.execute(
            "SELECT * FROM strategy_definitions WHERE strategy_number=?", (number,)
        ).fetchone()
        if not definition_row:
            return None
        definition = dict(definition_row)
        for key in ("signal_json", "execution_json", "money_management_json"):
            definition[key.removesuffix("_json")] = json.loads(definition.pop(key))
        run_row = db.execute(
            "SELECT * FROM portfolio_backtest_runs WHERE strategy_number=?", (number,)
        ).fetchone()
        run = dict(run_row) if run_row else None
        if (
            run
            and run.get("return_pct") is not None
            and run.get("max_drawdown") is not None
        ):
            run["score"] = run["return_pct"] - run["max_drawdown"]
        assets = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM portfolio_asset_results WHERE strategy_number=? ORDER BY pnl DESC,symbol",
                (number,),
            )
        ]
        trades = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM portfolio_trades WHERE strategy_number=? ORDER BY exit_time DESC,symbol,sequence",
                (number,),
            )
        ]
        equity = [
            dict(row)
            for row in db.execute(
                "SELECT timestamp,equity,cash,open_positions FROM portfolio_equity WHERE strategy_number=? ORDER BY timestamp",
                (number,),
            )
        ]
        return {
            "strategy_number": number,
            "label": f"S{number:05d}",
            "validated": validated,
            "phase": "HISTORICAL_PHASE_1",
            "definition": definition,
            "experiment": self._public_experiment(experiment),
            "backtest": run,
            "assets": assets,
            "trades": trades,
            "equity_curve": equity,
        }

    @staticmethod
    def _public_experiment(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None

        def loaded(name: str):
            value = row.get(name)
            return json.loads(value) if value else None

        return {
            "experiment_id": row["experiment_id"],
            "strategy_number": row.get("strategy_number"),
            "status": row["status"],
            "dataset_version": row["dataset_version"],
            "features": loaded("features_json"),
            "parameters": loaded("parameters_json"),
            "assets": loaded("assets_json"),
            "training_period": row["training_period"],
            "validation_period": row["validation_period"],
            "test_period": row["test_period"],
            "trades": row["trades"],
            "net_return": row["net_return"],
            "drawdown": row["drawdown"],
            "sharpe": row["sharpe"],
            "sortino": row["sortino"],
            "profit_factor": row["profit_factor"],
            "turnover": row["turnover"],
            "exposure": row["exposure"],
            "robustness": loaded("robustness_results_json"),
            "critic": loaded("critic_report_json"),
            "failure_reason": row["failure_reason"],
        }


DASHBOARD_HTML = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantLab Autonomous</title><style>
:root{color-scheme:dark;--bg:#090d14;--panel:#111824;--line:#263246;--text:#e8edf5;--muted:#91a0b7;--good:#4ee0a1;--warn:#ffca62;--bad:#ff6b78}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 0,#16233a 0,transparent 40%),var(--bg);color:var(--text);font:15px ui-monospace,SFMono-Regular,Menlo,monospace}
main{max-width:1180px;margin:auto;padding:34px 22px 70px}header{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:28px}h1{font:700 30px system-ui;margin:0}h2{font:650 17px system-ui;margin:0 0 16px}.live{color:var(--good)}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.card{grid-column:span 4;background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:14px;padding:20px}.wide{grid-column:span 8}.full{grid-column:1/-1}.metric{font:700 26px system-ui;margin:6px 0}.muted{color:var(--muted)}.warning{color:var(--warn);border-left:3px solid var(--warn);padding-left:12px}.good{color:var(--good)}.bad{color:var(--bad)}dl{display:grid;grid-template-columns:1fr 1.5fr;gap:9px 18px;margin:0}dt{color:var(--muted)}dd{margin:0;text-align:right;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#bdd0ed;margin:0;font-size:12px}.empty{padding:28px 0;color:var(--muted)}@media(max-width:760px){.card,.wide{grid-column:1/-1}header{display:block}}
</style></head><body><main><header><div><div class="muted">AUTONOMOUS CRYPTO RESEARCH</div><h1>QuantLab Control Room</h1></div><div id="live" class="live">● conectando</div></header><div id="warning"></div><section class="grid" id="app"></section></main>
<script>
const f=(v,p=2)=>v==null?'—':(v*100).toFixed(p)+'%'; const n=v=>v==null?'—':Number(v).toFixed(3);
function expCard(title,e,wide=false){if(!e)return `<article class="card ${wide?'wide':''}"><h2>${title}</h2><div class="empty">Sin candidato elegible</div></article>`;return `<article class="card ${wide?'wide':''}"><h2>${title}</h2><dl><dt>ID</dt><dd>${e.experiment_id}</dd><dt>Estado</dt><dd class="${e.status==='PROMOTE'?'good':'bad'}">${e.status}</dd><dt>Retorno neto</dt><dd>${f(e.net_return)}</dd><dt>Sharpe</dt><dd>${n(e.sharpe)}</dd><dt>Drawdown</dt><dd>${f(e.drawdown)}</dd><dt>Operaciones</dt><dd>${e.trades??'—'}</dd><dt>Turnover</dt><dd>${n(e.turnover)}</dd><dt>Activos</dt><dd>${(e.assets||[]).join(', ')}</dd></dl></article>`}
async function refresh(){try{const d=await fetch('/api/dashboard',{cache:'no-store'}).then(r=>r.json());document.getElementById('live').textContent='● activo · '+new Date(d.service.updated_at).toLocaleTimeString();document.getElementById('warning').innerHTML=d.warning?`<p class="warning">${d.warning}</p>`:'';let shown=d.champion||d.best_unvalidated_candidate;document.getElementById('app').innerHTML=`<article class="card"><h2>Loop</h2><div class="metric">${d.loop.state}</div><div class="muted">ciclo ${d.loop.cycle} · ${d.loop.experiments} experimentos archivados</div></article>${expCard('Mejor versión',shown,true)}${expCard('Candidato actual',d.current)}<article class="card wide"><h2>Parámetros del mejor</h2><pre>${JSON.stringify(shown?.parameters||{},null,2)}</pre></article><article class="card full"><h2>Validación y crítica</h2><pre>${JSON.stringify({robustness:shown?.robustness,critic:shown?.critic},null,2)}</pre></article><article class="card full"><h2>Comité autónomo: crítico → constructor</h2><pre>${JSON.stringify(d.committee?.length?d.committee:{status:'esperando siguiente ronda'},null,2)}</pre></article>`}catch(e){document.getElementById('live').textContent='● reconectando';document.getElementById('live').className='bad'}}refresh();setInterval(refresh,5000);
</script></body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    data: DashboardData

    def _send(self, payload: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        if self.path == "/api/dashboard":
            payload = json.dumps(self.data.snapshot(), allow_nan=False).encode()
            self._send(payload, "application/json")
        elif self.path in {"/", "/index.html"}:
            dashboard_path = Path(__file__).with_name("dashboard.html")
            payload = (
                dashboard_path.read_text()
                if dashboard_path.exists()
                else DASHBOARD_HTML
            ).encode()
            self._send(payload, "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:
        return


class AutonomousService:
    def __init__(self, settings: Settings, root: Path | None = None):
        self.settings = settings
        self.root = (root or Path.cwd()).resolve()
        self.director = ResearchDirector(settings)
        self.options = settings.autonomous
        self.stop_event = threading.Event()
        self.evaluation_lock = threading.Lock()
        self.universe = UniverseManager(
            self.director.memory,
            settings.data_root,
            settings.splits["future_lock_start"],
            settings.universe,
        )
        with self.director.memory.session() as db:
            db.executescript(DAEMON_SCHEMA)
            db.execute(
                """UPDATE portfolio_backtest_runs SET status='INTERRUPTED',updated_at=?
                          WHERE status IN ('PREPARING_SIGNALS','BACKTESTING')""",
                (utc_now(),),
            )
            db.execute("""UPDATE forward_portfolio_runs SET status='FORWARD_INTERRUPTED'
                          WHERE status IN ('FORWARD_PREPARING','FORWARD_TESTING')""")

    def event(
        self, kind: str, message: str, level: str = "INFO", **details: Any
    ) -> None:
        with self.director.memory.transaction() as db:
            db.execute(
                "INSERT INTO daemon_events(kind,level,message,details_json,created_at) VALUES(?,?,?,?,?)",
                (kind, level, message, json.dumps(details, sort_keys=True), utc_now()),
            )

    def activity(self, phase: str, message: str, **details: Any) -> None:
        with self.director.memory.transaction() as db:
            db.execute(
                """INSERT INTO runtime_activity VALUES(1,?,?,?,?)
                   ON CONFLICT(singleton) DO UPDATE SET phase=excluded.phase,message=excluded.message,
                   details_json=excluded.details_json,updated_at=excluded.updated_at""",
                (phase, message, json.dumps(details, sort_keys=True), utc_now()),
            )

    def run_agent(self, role: str = "builder") -> bool:
        executable = Path(self.options.get("codex_executable", "codex"))
        role_enabled = self.options.get(f"{role}_enabled", True)
        if (
            not self.options.get("agent_enabled", True)
            or not role_enabled
            or not executable.exists()
        ):
            self.event(
                "development",
                f"Codex {role} unavailable or disabled",
                "WARNING",
                executable=str(executable),
            )
            return False
        logs = self.settings.research_root / "agent_runs"
        logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = logs / f"codex-{role}-{stamp}.log"
        prompt_file = (
            "ADVERSARIAL_REVIEW.md" if role == "critic" else "AUTONOMOUS_DEVELOPMENT.md"
        )
        prompt = (self.root / prompt_file).read_text()
        advisory = self.settings.research_root / "advisory" / "LATEST.md"
        advisory.parent.mkdir(parents=True, exist_ok=True)
        with self.director.memory.transaction() as db:
            cursor = db.execute(
                "INSERT INTO development_runs(agent,status,started_at,log_path) VALUES(?,?,?,?)",
                (f"codex:{role}", "RUNNING", utc_now(), str(log_path)),
            )
            run_id = cursor.lastrowid
        sandbox = "read-only" if role == "critic" else "workspace-write"
        command = [
            str(executable),
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "-s",
            sandbox,
            "-C",
            str(self.root),
        ]
        if role == "critic":
            command.extend(["-o", str(advisory)])
        command.append("-")
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=float(self.options.get("agent_timeout_seconds", 1800)),
            )
            output = completed.stdout + "\n" + completed.stderr
            log_path.write_text(output)
            status = "COMPLETE" if completed.returncode == 0 else "FAILED"
            summary = output[-2000:]
            return_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + "\n" + (exc.stderr or "")
            log_path.write_text(output)
            status, summary, return_code = (
                "TIMEOUT",
                "Agent exceeded its bounded turn timeout",
                None,
            )
        with self.director.memory.transaction() as db:
            db.execute(
                "UPDATE development_runs SET status=?,finished_at=?,return_code=?,summary=? WHERE id=?",
                (status, utc_now(), return_code, summary, run_id),
            )
        self.event(
            "development",
            f"Codex {role} turn {status}",
            return_code=return_code,
            log_path=str(log_path),
        )
        return True

    def run_committee(self) -> bool:
        outcomes: dict[str, bool] = {}

        def codex_critic() -> None:
            outcomes["codex"] = self.run_agent("critic")

        def claude_critic() -> None:
            outcomes["claude"] = self.run_claude_critic()

        critics = [
            threading.Thread(target=codex_critic, name="codex-critic"),
            threading.Thread(target=claude_critic, name="claude-critic"),
        ]
        for critic in critics:
            critic.start()
        for critic in critics:
            critic.join()
        critic_ran = any(outcomes.values())
        if critic_ran:
            self.event(
                "committee",
                "Independent Codex/Claude critiques completed; handing both to builder",
                outcomes=outcomes,
            )
        builder_ran = self.run_agent("builder")
        return critic_ran or builder_ran

    def run_claude_critic(self) -> bool:
        executable = Path(self.options.get("claude_executable", "claude"))
        if (
            not self.options.get("agent_enabled", True)
            or not self.options.get("claude_enabled", False)
            or not executable.exists()
        ):
            self.event(
                "development",
                "Claude critic unavailable or disabled",
                "WARNING",
                executable=str(executable),
            )
            return False
        prompt = (self.root / "ADVERSARIAL_REVIEW.md").read_text()
        advisory = self.settings.research_root / "advisory" / "CLAUDE.md"
        advisory.parent.mkdir(parents=True, exist_ok=True)
        logs = self.settings.research_root / "agent_runs"
        logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = logs / f"claude-critic-{stamp}.log"
        with self.director.memory.transaction() as db:
            cursor = db.execute(
                "INSERT INTO development_runs(agent,status,started_at,log_path) VALUES(?,?,?,?)",
                ("claude:critic", "RUNNING", utc_now(), str(log_path)),
            )
            run_id = cursor.lastrowid
        command = [
            str(executable),
            "-p",
            prompt,
            "--permission-mode",
            "plan",
            "--max-turns",
            "6",
            "--no-session-persistence",
            "--output-format",
            "text",
        ]
        try:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                cwd=self.root,
                timeout=float(self.options.get("agent_timeout_seconds", 1800)),
            )
            output = completed.stdout + "\n" + completed.stderr
            status = "COMPLETE" if completed.returncode == 0 else "FAILED"
            return_code = completed.returncode
            if completed.returncode == 0:
                advisory.write_text(completed.stdout)
        except (subprocess.TimeoutExpired, OSError) as exc:
            output = str(exc)
            status = (
                "TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "FAILED"
            )
            return_code = None
        log_path.write_text(output)
        with self.director.memory.transaction() as db:
            db.execute(
                "UPDATE development_runs SET status=?,finished_at=?,return_code=?,summary=? WHERE id=?",
                (status, utc_now(), return_code, output[-2000:], run_id),
            )
        self.event(
            "development",
            f"Claude critic turn {status}",
            return_code=return_code,
            log_path=str(log_path),
        )
        return status == "COMPLETE"

    def research_worker(self) -> None:
        interval = max(2.0, float(self.options.get("research_interval_seconds", 10)))
        while not self.stop_event.is_set():
            try:
                self.activity(
                    "RESEARCHING",
                    "Generando la siguiente combinación señal + ejecución",
                )
                reports = self.director.run(max_cycles=1, max_seconds=interval)
                self.event("research", "Research cycle completed", reports=reports)
                self.evaluate_pipeline()
            except Exception as exc:
                self.event(
                    "research", str(exc), "ERROR", traceback=traceback.format_exc()
                )
            self.stop_event.wait(interval)

    def evaluate_pipeline(self) -> None:
        with self.evaluation_lock:
            self.activity("PHASE1_PREPARING", "Preparando Fase 1 y cargando históricos")

            def historical_activity(phase: str, payload: str) -> None:
                point = json.loads(payload)
                if phase == "PREPARING_SIGNALS":
                    message = (
                        f"Preparando señales {point['prepared_assets']}/{point['total_assets']}"
                        f" · {point['symbol']}"
                    )
                else:
                    message = "Fase 1 · backtesting histórico"
                self.activity(phase, message, progress=point)

            historical = HistoricalUniverseEvaluator(
                self.settings, self.director.memory, historical_activity
            ).evaluate_latest()
            if not historical:
                return
            if historical["status"] == "ABORTED_DRAWDOWN":
                self.activity(
                    "PRUNED_DRAWDOWN",
                    "Variante cancelada al alcanzar el límite de drawdown",
                    historical=historical,
                )
                return
            forward_evaluator = ForwardEvaluator(
                self.settings,
                self.director.memory,
                lambda phase, message, details: self.activity(
                    phase, message, progress=details
                ),
            )
            promoted = forward_evaluator.qualified_strategy()
            if (
                not promoted
                or int(promoted["strategy_number"]) != historical["strategy_number"]
            ):
                self.activity(
                    "PHASE1_REJECTED",
                    "Fase 1 completada, pero sin evidencia suficiente para forward 2026",
                    historical=historical,
                )
                return
            self.activity(
                "PHASE2_PREPARING",
                "Fase 1 promovida; preparando forward 2026",
                strategy_number=historical["strategy_number"],
            )
            run_id = forward_evaluator.evaluate(historical["strategy_number"])
            if run_id:
                self.event("forward", "2026 forward evaluation updated", run_id=run_id)
            self.activity(
                "NEXT_VARIANT",
                "Evaluación terminada; preparando la siguiente variante",
                historical=historical,
                forward_run_id=run_id,
            )

    def data_worker(self) -> None:
        interval = max(60.0, float(self.options.get("download_interval_seconds", 300)))
        refresh_interval = max(
            interval, float(self.options.get("universe_refresh_seconds", 21600))
        )
        last_refresh: float | None = None
        while not self.stop_event.is_set():
            try:
                if (
                    last_refresh is None
                    or time.monotonic() - last_refresh >= refresh_interval
                ):
                    if not self.evaluation_lock.locked():
                        self.activity(
                            "REFRESHING_UNIVERSE",
                            "Consultando todos los pares Spot/USDT activos",
                        )
                    count = self.universe.refresh()
                    last_refresh = time.monotonic()
                    self.event("data", "Binance spot universe refreshed", symbols=count)

                def download_progress(symbol: str, index: int, total: int) -> None:
                    if not self.evaluation_lock.locked():
                        self.activity(
                            "DOWNLOADING_DATA",
                            f"Descargando histórico de {symbol}",
                            symbol=symbol,
                            item=index,
                            batch_total=total,
                        )

                batch = self.universe.download_batch(
                    int(self.options.get("download_batch_size", 3)), download_progress
                )
                self.event(
                    "data",
                    "Market-data batch completed",
                    results=batch,
                    coverage=self.universe.coverage(),
                )
            except Exception as exc:
                self.event("data", str(exc), "ERROR", traceback=traceback.format_exc())
            self.stop_event.wait(interval)

    def development_worker(self) -> None:
        interval = max(
            60.0, float(self.options.get("development_interval_seconds", 21600))
        )
        initial_delay = max(
            0.0, float(self.options.get("development_initial_delay_seconds", 60))
        )
        with self.director.memory.session() as db:
            row = db.execute(
                "SELECT finished_at FROM development_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row:
            elapsed = (
                datetime.now(timezone.utc) - datetime.fromisoformat(row["finished_at"])
            ).total_seconds()
            delay = max(0.0, interval - elapsed)
        else:
            delay = initial_delay
        self.stop_event.wait(delay)
        while not self.stop_event.is_set():
            try:
                executed = self.run_committee()
                if executed:
                    self.event(
                        "service", "Restart requested to load autonomous code changes"
                    )
                    self.stop_event.set()
                    return
            except Exception as exc:
                self.event(
                    "development", str(exc), "ERROR", traceback=traceback.format_exc()
                )
            self.stop_event.wait(interval)

    def serve_forever(self) -> None:
        host = str(self.options.get("dashboard_host", "127.0.0.1"))
        port = int(self.options.get("dashboard_port", 8765))
        DashboardHandler.data = DashboardData(self.settings)
        server = ThreadingHTTPServer((host, port), DashboardHandler)
        signal.signal(signal.SIGTERM, lambda *_: self.stop_event.set())
        signal.signal(signal.SIGINT, lambda *_: self.stop_event.set())
        threading.Thread(
            target=self.research_worker, name="research", daemon=True
        ).start()
        threading.Thread(target=self.data_worker, name="data", daemon=True).start()
        threading.Thread(
            target=self.development_worker, name="development", daemon=True
        ).start()
        publisher = PublicStatePublisher(
            self.settings, DashboardHandler.data.snapshot, self.stop_event
        )
        if publisher.enabled:
            threading.Thread(
                target=publisher.run, name="public-state-mirror", daemon=True
            ).start()
        self.event("service", "Autonomous service started", host=host, port=port)
        server.timeout = 1
        try:
            while not self.stop_event.is_set():
                server.handle_request()
        finally:
            server.server_close()
            self.event("service", "Autonomous service stopped")


def run_daemon(settings: Settings) -> None:
    AutonomousService(settings).serve_forever()
