from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import ExperimentSpec, ResearchState, utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS loop_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  state TEXT NOT NULL, cycle INTEGER NOT NULL, context_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hypotheses (
  id TEXT PRIMARY KEY, hypothesis_hash TEXT NOT NULL UNIQUE,
  structural_fingerprint TEXT NOT NULL, document_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
  experiment_id TEXT PRIMARY KEY, parent_ids_json TEXT NOT NULL,
  hypothesis_id TEXT NOT NULL, hypothesis_hash TEXT NOT NULL,
  code_commit TEXT NOT NULL, dataset_version TEXT NOT NULL,
  features_json TEXT NOT NULL, parameters_json TEXT NOT NULL,
  training_period TEXT NOT NULL, validation_period TEXT NOT NULL,
  test_period TEXT NOT NULL, assets_json TEXT NOT NULL,
  trades INTEGER, gross_return REAL, net_return REAL, drawdown REAL,
  sharpe REAL, sortino REAL, profit_factor REAL, turnover REAL, exposure REAL,
  slippage_model TEXT NOT NULL, robustness_results_json TEXT,
  novelty_score REAL, failure_reason TEXT, critic_report_json TEXT,
  status TEXT NOT NULL, spec_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
  FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(id)
);
CREATE TABLE IF NOT EXISTS state_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, cycle INTEGER NOT NULL,
  from_state TEXT, to_state TEXT NOT NULL, context_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hypothesis_fingerprint
  ON hypotheses(structural_fingerprint);
CREATE TABLE IF NOT EXISTS strategy_definitions (
  strategy_number INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_hash TEXT NOT NULL UNIQUE, family TEXT NOT NULL,
  signal_json TEXT NOT NULL, execution_json TEXT NOT NULL,
  money_management_json TEXT NOT NULL, long_only INTEGER NOT NULL CHECK(long_only=1),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forward_runs (
  run_id TEXT PRIMARY KEY, strategy_number INTEGER NOT NULL,
  period_start TEXT NOT NULL, period_end TEXT NOT NULL, as_of TEXT NOT NULL,
  initial_capital REAL NOT NULL, final_equity REAL NOT NULL,
  net_profit REAL NOT NULL, return_pct REAL NOT NULL, trades INTEGER NOT NULL,
  wins INTEGER NOT NULL, losses INTEGER NOT NULL, win_rate REAL NOT NULL,
  assets_tested INTEGER NOT NULL, assets_survived INTEGER NOT NULL,
  assets_capital_preserved INTEGER NOT NULL,
  status TEXT NOT NULL, FOREIGN KEY(strategy_number) REFERENCES strategy_definitions(strategy_number)
);
CREATE TABLE IF NOT EXISTS forward_assets (
  run_id TEXT NOT NULL, symbol TEXT NOT NULL, allocated_capital REAL NOT NULL,
  final_equity REAL NOT NULL, return_pct REAL NOT NULL, trades INTEGER NOT NULL,
  wins INTEGER NOT NULL, losses INTEGER NOT NULL, win_rate REAL NOT NULL,
  survived INTEGER NOT NULL, capital_preserved INTEGER NOT NULL,
  PRIMARY KEY(run_id,symbol),
  FOREIGN KEY(run_id) REFERENCES forward_runs(run_id)
);
CREATE TABLE IF NOT EXISTS forward_trades (
  run_id TEXT NOT NULL, symbol TEXT NOT NULL, sequence INTEGER NOT NULL,
  entry_time TEXT NOT NULL, exit_time TEXT NOT NULL, duration_seconds REAL NOT NULL,
  entry_price REAL NOT NULL, exit_price REAL NOT NULL, invested_capital REAL NOT NULL,
  pnl REAL NOT NULL, pnl_pct REAL NOT NULL, exit_reason TEXT NOT NULL,
  PRIMARY KEY(run_id,symbol,sequence), FOREIGN KEY(run_id) REFERENCES forward_runs(run_id)
);
CREATE TABLE IF NOT EXISTS asset_universe (
  symbol TEXT PRIMARY KEY, status TEXT NOT NULL, first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL, research_path TEXT, forward_path TEXT,
  last_error TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_liquidity (
  symbol TEXT PRIMARY KEY, quote_volume_24h REAL NOT NULL,
  trade_count_24h INTEGER NOT NULL, eligible INTEGER NOT NULL,
  checked_at TEXT NOT NULL,
  FOREIGN KEY(symbol) REFERENCES asset_universe(symbol)
);
CREATE TABLE IF NOT EXISTS strategy_asset_results (
  strategy_number INTEGER NOT NULL, symbol TEXT NOT NULL,
  evaluated_through TEXT NOT NULL, initial_capital REAL NOT NULL,
  final_equity REAL NOT NULL, return_pct REAL NOT NULL, trades INTEGER NOT NULL,
  wins INTEGER NOT NULL, losses INTEGER NOT NULL, win_rate REAL NOT NULL,
  capital_preserved INTEGER NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(strategy_number,symbol),
  FOREIGN KEY(strategy_number) REFERENCES strategy_definitions(strategy_number)
);
CREATE TABLE IF NOT EXISTS strategy_trade_ledger (
  strategy_number INTEGER NOT NULL, symbol TEXT NOT NULL, sequence INTEGER NOT NULL,
  entry_time TEXT NOT NULL, exit_time TEXT NOT NULL, duration_seconds REAL NOT NULL,
  invested_capital REAL NOT NULL, pnl REAL NOT NULL, pnl_pct REAL NOT NULL,
  exit_reason TEXT NOT NULL, PRIMARY KEY(strategy_number,symbol,sequence),
  FOREIGN KEY(strategy_number) REFERENCES strategy_definitions(strategy_number)
);
CREATE TABLE IF NOT EXISTS portfolio_backtest_runs (
  strategy_number INTEGER PRIMARY KEY, status TEXT NOT NULL,
  period_start TEXT, period_end TEXT, current_date TEXT,
  initial_capital REAL NOT NULL, current_equity REAL NOT NULL,
  final_equity REAL, net_profit REAL, return_pct REAL, max_drawdown REAL,
  total_days INTEGER NOT NULL, processed_days INTEGER NOT NULL,
  assets_available INTEGER NOT NULL, assets_traded INTEGER NOT NULL DEFAULT 0,
  trades INTEGER NOT NULL, wins INTEGER NOT NULL, losses INTEGER NOT NULL,
  win_rate REAL NOT NULL, open_positions INTEGER NOT NULL, cash REAL NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(strategy_number) REFERENCES strategy_definitions(strategy_number)
);
CREATE TABLE IF NOT EXISTS portfolio_asset_results (
  strategy_number INTEGER NOT NULL, symbol TEXT NOT NULL,
  pnl REAL NOT NULL, return_on_deployed REAL NOT NULL,
  capital_deployed REAL NOT NULL, peak_capital_at_risk REAL NOT NULL,
  trades INTEGER NOT NULL, wins INTEGER NOT NULL, losses INTEGER NOT NULL,
  win_rate REAL NOT NULL, capital_preserved INTEGER NOT NULL,
  PRIMARY KEY(strategy_number,symbol)
);
CREATE TABLE IF NOT EXISTS portfolio_trades (
  strategy_number INTEGER NOT NULL, symbol TEXT NOT NULL, sequence INTEGER NOT NULL,
  entry_time TEXT NOT NULL, exit_time TEXT NOT NULL, entry_price REAL NOT NULL,
  exit_price REAL NOT NULL, duration_seconds REAL NOT NULL,
  invested_capital REAL NOT NULL, pnl REAL NOT NULL, pnl_pct REAL NOT NULL,
  exit_reason TEXT NOT NULL, PRIMARY KEY(strategy_number,symbol,sequence)
);
CREATE TABLE IF NOT EXISTS portfolio_equity (
  strategy_number INTEGER NOT NULL, timestamp TEXT NOT NULL,
  equity REAL NOT NULL, cash REAL NOT NULL, open_positions INTEGER NOT NULL,
  PRIMARY KEY(strategy_number,timestamp)
);
CREATE TABLE IF NOT EXISTS runtime_activity (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1), phase TEXT NOT NULL,
  message TEXT NOT NULL, details_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forward_portfolio_runs (
  run_id TEXT PRIMARY KEY, strategy_number INTEGER NOT NULL,
  period_start TEXT NOT NULL, period_end TEXT NOT NULL, as_of TEXT NOT NULL,
  initial_capital REAL NOT NULL, final_equity REAL NOT NULL,
  net_profit REAL NOT NULL, return_pct REAL NOT NULL, max_drawdown REAL NOT NULL,
  score REAL NOT NULL, trades INTEGER NOT NULL, wins INTEGER NOT NULL,
  losses INTEGER NOT NULL, win_rate REAL NOT NULL, assets_available INTEGER NOT NULL,
  assets_traded INTEGER NOT NULL, cash REAL NOT NULL, status TEXT NOT NULL,
  benchmark_buy_and_hold REAL, benchmark_equal_weight REAL,
  benchmark_reference REAL, benchmark_reference_name TEXT, excess_return REAL,
  engine_version INTEGER NOT NULL DEFAULT 1,
  current_date TEXT, target_end TEXT, processed_days INTEGER NOT NULL DEFAULT 0,
  total_days INTEGER NOT NULL DEFAULT 0, open_positions INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(strategy_number) REFERENCES strategy_definitions(strategy_number)
);
CREATE TABLE IF NOT EXISTS forward_portfolio_assets (
  run_id TEXT NOT NULL, symbol TEXT NOT NULL, pnl REAL NOT NULL,
  return_on_deployed REAL NOT NULL, capital_deployed REAL NOT NULL,
  peak_capital_at_risk REAL NOT NULL, trades INTEGER NOT NULL,
  wins INTEGER NOT NULL, losses INTEGER NOT NULL, win_rate REAL NOT NULL,
  capital_preserved INTEGER NOT NULL, PRIMARY KEY(run_id,symbol)
);
CREATE TABLE IF NOT EXISTS forward_portfolio_trades (
  run_id TEXT NOT NULL, symbol TEXT NOT NULL, sequence INTEGER NOT NULL,
  entry_time TEXT NOT NULL, exit_time TEXT NOT NULL, entry_price REAL NOT NULL,
  exit_price REAL NOT NULL, duration_seconds REAL NOT NULL,
  invested_capital REAL NOT NULL, pnl REAL NOT NULL, pnl_pct REAL NOT NULL,
  exit_reason TEXT NOT NULL, PRIMARY KEY(run_id,symbol,sequence)
);
CREATE TABLE IF NOT EXISTS forward_portfolio_equity (
  run_id TEXT NOT NULL, timestamp TEXT NOT NULL, equity REAL NOT NULL,
  cash REAL NOT NULL, open_positions INTEGER NOT NULL,
  PRIMARY KEY(run_id,timestamp)
);
CREATE TABLE IF NOT EXISTS champion_records (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  strategy_number INTEGER NOT NULL, label TEXT NOT NULL, evidence TEXT NOT NULL,
  evidence_rank INTEGER NOT NULL, score REAL NOT NULL, source_run_id TEXT,
  crowned_at TEXT NOT NULL, evaluations_considered INTEGER NOT NULL DEFAULT 0,
  replaced_strategy_number INTEGER, view_json TEXT NOT NULL,
  profitable INTEGER NOT NULL DEFAULT 0, return_pct REAL NOT NULL DEFAULT 0,
  max_drawdown REAL NOT NULL DEFAULT 0, benchmark REAL, benchmark_name TEXT,
  excess_return REAL
);
CREATE TABLE IF NOT EXISTS champion_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, decided_at TEXT NOT NULL,
  strategy_number INTEGER NOT NULL, evidence TEXT NOT NULL,
  evidence_rank INTEGER NOT NULL, score REAL NOT NULL,
  previous_strategy_number INTEGER, previous_evidence TEXT, previous_score REAL,
  replaced INTEGER NOT NULL, reason TEXT NOT NULL, profitable INTEGER
);
-- Everything below is third-party input. It is stored verbatim, shown to
-- agents as quoted untrusted data, and never executed or interpolated into a
-- command. `answered_at` is what stops newcomers being ignored.
CREATE TABLE IF NOT EXISTS cluster_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, wall_id TEXT UNIQUE,
  agent TEXT NOT NULL, body TEXT NOT NULL, posted_at TEXT,
  received_at TEXT NOT NULL, ours INTEGER NOT NULL DEFAULT 0,
  answered_at TEXT, answered_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_cluster_messages_unanswered
  ON cluster_messages(ours,answered_at,id);
CREATE TABLE IF NOT EXISTS contributions (
  number INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL,
  head_sha TEXT NOT NULL, url TEXT NOT NULL, files_changed INTEGER NOT NULL,
  additions INTEGER NOT NULL, deletions INTEGER NOT NULL,
  state TEXT NOT NULL, verdict TEXT, blocked_reason TEXT,
  first_seen TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contribution_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT, number INTEGER NOT NULL,
  head_sha TEXT NOT NULL, reviewer TEXT NOT NULL, verdict TEXT NOT NULL,
  findings_json TEXT NOT NULL, summary TEXT NOT NULL, reviewed_at TEXT NOT NULL,
  FOREIGN KEY(number) REFERENCES contributions(number)
);
CREATE INDEX IF NOT EXISTS idx_contribution_reviews_head
  ON contribution_reviews(number,head_sha);
"""


class ExperimentMemory:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self.session() as db:
            db.executescript(SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(experiments)")}
            if "strategy_number" not in columns:
                db.execute("ALTER TABLE experiments ADD COLUMN strategy_number INTEGER")
            forward_run_columns = {
                row[1] for row in db.execute("PRAGMA table_info(forward_runs)")
            }
            if "assets_capital_preserved" not in forward_run_columns:
                db.execute(
                    "ALTER TABLE forward_runs ADD COLUMN assets_capital_preserved INTEGER NOT NULL DEFAULT 0"
                )
            forward_asset_columns = {
                row[1] for row in db.execute("PRAGMA table_info(forward_assets)")
            }
            if "capital_preserved" not in forward_asset_columns:
                db.execute(
                    "ALTER TABLE forward_assets ADD COLUMN capital_preserved INTEGER NOT NULL DEFAULT 0"
                )
            portfolio_forward_columns = {
                row[1]
                for row in db.execute("PRAGMA table_info(forward_portfolio_runs)")
            }
            for name, declaration in (
                ("current_date", "TEXT"),
                ("target_end", "TEXT"),
                ("processed_days", "INTEGER NOT NULL DEFAULT 0"),
                ("total_days", "INTEGER NOT NULL DEFAULT 0"),
                ("open_positions", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if name not in portfolio_forward_columns:
                    db.execute(
                        f"ALTER TABLE forward_portfolio_runs ADD COLUMN {name} {declaration}"
                    )
            # The champion gained a profitability class and its raw numbers when
            # the ranking stopped being a single score, so existing databases
            # need the columns before the registry can write them.
            # QUANT8. Runs now carry what they were measured against and which
            # engine produced them. The engine version matters because results
            # from before the sizing lookahead was removed are inflated, and
            # must stay readable for audit without being eligible to win.
            for table in ("forward_portfolio_runs", "portfolio_backtest_runs"):
                existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for name, declaration in (
                    ("benchmark_buy_and_hold", "REAL"),
                    ("benchmark_equal_weight", "REAL"),
                    ("benchmark_reference", "REAL"),
                    ("benchmark_reference_name", "TEXT"),
                    ("excess_return", "REAL"),
                    ("engine_version", "INTEGER NOT NULL DEFAULT 1"),
                ):
                    if name not in existing:
                        db.execute(
                            f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"
                        )
            champion_columns = {
                row[1] for row in db.execute("PRAGMA table_info(champion_records)")
            }
            for name, declaration in (
                ("profitable", "INTEGER NOT NULL DEFAULT 0"),
                ("return_pct", "REAL NOT NULL DEFAULT 0"),
                ("max_drawdown", "REAL NOT NULL DEFAULT 0"),
                ("benchmark", "REAL"),
                ("benchmark_name", "TEXT"),
                ("excess_return", "REAL"),
            ):
                if name not in champion_columns:
                    db.execute(
                        f"ALTER TABLE champion_records ADD COLUMN {name} {declaration}"
                    )
            decision_columns = {
                row[1] for row in db.execute("PRAGMA table_info(champion_decisions)")
            }
            if "profitable" not in decision_columns:
                db.execute(
                    "ALTER TABLE champion_decisions ADD COLUMN profitable INTEGER"
                )
            legacy = db.execute(
                """SELECT e.experiment_id,e.features_json,e.parameters_json,h.document_json
                   FROM experiments e JOIN hypotheses h ON h.id=e.hypothesis_id
                   WHERE e.strategy_number IS NULL ORDER BY e.created_at"""
            ).fetchall()
            for row in legacy:
                hypothesis = json.loads(row["document_json"])
                document = {
                    "family": hypothesis["family"],
                    "signal": {
                        "features": json.loads(row["features_json"]),
                        "parameters": json.loads(row["parameters_json"]),
                    },
                    "execution": {"engine": "next-open-v1", "legacy": True},
                    "money_management": {"legacy_max_position_fraction": 1.0},
                    "long_only": True,
                }
                digest = hashlib.sha256(
                    json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                db.execute(
                    "INSERT OR IGNORE INTO strategy_definitions(strategy_hash,family,signal_json,execution_json,money_management_json,long_only,created_at) VALUES(?,?,?,?,?,1,?)",
                    (
                        digest,
                        hypothesis["family"],
                        json.dumps(document["signal"], sort_keys=True),
                        json.dumps(document["execution"], sort_keys=True),
                        json.dumps(document["money_management"], sort_keys=True),
                        utc_now(),
                    ),
                )
                number = db.execute(
                    "SELECT strategy_number FROM strategy_definitions WHERE strategy_hash=?",
                    (digest,),
                ).fetchone()[0]
                db.execute(
                    "UPDATE experiments SET strategy_number=? WHERE experiment_id=?",
                    (number, row["experiment_id"]),
                )
            db.execute(
                "INSERT OR IGNORE INTO loop_state VALUES (1, ?, 1, '{}', ?)",
                (ResearchState.OBSERVE.value, utc_now()),
            )

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """Short-lived connection that is always committed and closed."""
        db = self.connect()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def load_state(self) -> tuple[ResearchState, int, dict[str, Any]]:
        with self.session() as db:
            row = db.execute("SELECT * FROM loop_state WHERE singleton=1").fetchone()
        return (
            ResearchState(row["state"]),
            row["cycle"],
            json.loads(row["context_json"]),
        )

    def save_transition(
        self,
        from_state: ResearchState,
        to_state: ResearchState,
        cycle: int,
        context: dict[str, Any],
    ) -> None:
        payload = json.dumps(context, sort_keys=True)
        with self.transaction() as db:
            current = db.execute(
                "SELECT state, cycle FROM loop_state WHERE singleton=1"
            ).fetchone()
            if current["state"] != from_state.value or current["cycle"] != cycle:
                raise RuntimeError("state changed concurrently")
            db.execute(
                "UPDATE loop_state SET state=?, context_json=?, updated_at=? WHERE singleton=1",
                (to_state.value, payload, utc_now()),
            )
            db.execute(
                "INSERT INTO state_events(cycle,from_state,to_state,context_json,created_at) VALUES(?,?,?,?,?)",
                (cycle, from_state.value, to_state.value, payload, utc_now()),
            )

    def start_next_cycle(self, cycle: int) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE loop_state SET state=?,cycle=?,context_json='{}',updated_at=? WHERE singleton=1",
                (ResearchState.OBSERVE.value, cycle + 1, utc_now()),
            )
            db.execute(
                "INSERT INTO state_events(cycle,from_state,to_state,context_json,created_at) VALUES(?,?,?,?,?)",
                (
                    cycle,
                    ResearchState.DOCUMENT.value,
                    ResearchState.OBSERVE.value,
                    "{}",
                    utc_now(),
                ),
            )

    @staticmethod
    def hypothesis_hash(document: dict[str, Any]) -> str:
        raw = json.dumps(document, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def structural_fingerprint(document: dict[str, Any]) -> str:
        raw = json.dumps(document, sort_keys=True).lower()
        normalized = re.sub(r"(?<![a-z])[-+]?\d+(?:\.\d+)?", "#", raw)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def store_hypothesis(self, document: dict[str, Any]) -> tuple[str, bool]:
        digest = self.hypothesis_hash(document)
        fingerprint = self.structural_fingerprint(document)
        with self.transaction() as db:
            existing = db.execute(
                "SELECT id FROM hypotheses WHERE hypothesis_hash=? OR id=?",
                (digest, document["id"]),
            ).fetchone()
            if existing:
                return existing["id"], False
            db.execute(
                "INSERT INTO hypotheses VALUES(?,?,?,?,?)",
                (
                    document["id"],
                    digest,
                    fingerprint,
                    json.dumps(document, sort_keys=True),
                    utc_now(),
                ),
            )
        return document["id"], True

    def similar_hypotheses(
        self, document: dict[str, Any], limit: int = 5
    ) -> list[dict[str, Any]]:
        stop = {"the", "and", "or", "a", "of", "to", "in", "when"}
        tokens = set(re.findall(r"[a-z_]{3,}", json.dumps(document).lower())) - stop
        results: list[tuple[float, dict[str, Any]]] = []
        with self.session() as db:
            rows = db.execute("SELECT document_json FROM hypotheses").fetchall()
        for row in rows:
            other = json.loads(row["document_json"])
            other_tokens = (
                set(re.findall(r"[a-z_]{3,}", row["document_json"].lower())) - stop
            )
            score = len(tokens & other_tokens) / max(1, len(tokens | other_tokens))
            results.append((score, other))
        return [
            {"score": score, "hypothesis": doc}
            for score, doc in sorted(results, reverse=True, key=lambda x: x[0])[:limit]
        ]

    def experiment_by_hash(self, spec_hash: str) -> dict[str, Any] | None:
        with self.session() as db:
            row = db.execute(
                "SELECT * FROM experiments WHERE spec_hash=?", (spec_hash,)
            ).fetchone()
        return dict(row) if row else None

    def register_strategy(
        self,
        family: str,
        signal: dict[str, Any],
        execution: dict[str, Any],
        money_management: dict[str, Any],
    ) -> int:
        document = {
            "family": family,
            "signal": signal,
            "execution": execution,
            "money_management": money_management,
            "long_only": True,
        }
        digest = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.transaction() as db:
            row = db.execute(
                "SELECT strategy_number FROM strategy_definitions WHERE strategy_hash=?",
                (digest,),
            ).fetchone()
            if row:
                return int(row["strategy_number"])
            cursor = db.execute(
                "INSERT INTO strategy_definitions(strategy_hash,family,signal_json,execution_json,money_management_json,long_only,created_at) VALUES(?,?,?,?,?,1,?)",
                (
                    digest,
                    family,
                    json.dumps(signal, sort_keys=True),
                    json.dumps(execution, sort_keys=True),
                    json.dumps(money_management, sort_keys=True),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def strategies(self) -> list[dict[str, Any]]:
        with self.session() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM strategy_definitions ORDER BY strategy_number"
                )
            ]

    def create_experiment(
        self,
        spec: ExperimentSpec,
        code_commit: str = "uncommitted",
        strategy_number: int | None = None,
    ) -> bool:
        if self.experiment_by_hash(spec.digest()):
            return False
        h = spec.hypothesis
        with self.transaction() as db:
            db.execute(
                """INSERT INTO experiments(
                experiment_id,parent_ids_json,hypothesis_id,hypothesis_hash,code_commit,
                dataset_version,features_json,parameters_json,training_period,
                validation_period,test_period,assets_json,slippage_model,status,spec_hash,created_at
                ,strategy_number) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    spec.experiment_id,
                    json.dumps(spec.parent_ids),
                    h.id,
                    self.hypothesis_hash(h.canonical()),
                    code_commit,
                    spec.dataset_version,
                    json.dumps(h.features),
                    json.dumps(spec.parameters, sort_keys=True),
                    spec.training_period,
                    spec.validation_period,
                    spec.test_period,
                    json.dumps(spec.assets),
                    "adverse-fixed-bps-next-open",
                    "RUNNING",
                    spec.digest(),
                    utc_now(),
                    strategy_number,
                ),
            )
        return True

    def finish_experiment(
        self,
        experiment_id: str,
        result: dict[str, Any],
        robustness: dict[str, Any],
        critic: dict[str, Any],
        status: str,
        failure_reason: str | None = None,
    ) -> None:
        with self.transaction() as db:
            db.execute(
                """UPDATE experiments SET trades=?,gross_return=?,net_return=?,drawdown=?,
                sharpe=?,sortino=?,profit_factor=?,turnover=?,exposure=?,
                robustness_results_json=?,novelty_score=?,failure_reason=?,
                critic_report_json=?,status=? WHERE experiment_id=?""",
                (
                    result["trades"],
                    result["gross_return"],
                    result["net_return"],
                    result["drawdown"],
                    result["sharpe"],
                    result["sortino"],
                    result["profit_factor"],
                    result["turnover"],
                    result["exposure"],
                    json.dumps(robustness, sort_keys=True),
                    robustness.get("novelty_score", 1.0),
                    failure_reason,
                    json.dumps(critic, sort_keys=True),
                    status,
                    experiment_id,
                ),
            )

    def experiments(self) -> list[dict[str, Any]]:
        with self.session() as db:
            return [
                dict(row)
                for row in db.execute("SELECT * FROM experiments ORDER BY created_at")
            ]
