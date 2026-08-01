from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .data import BinanceProvider, DataManager, ForwardDataManager
from .memory import ExperimentMemory
from .models import utc_now


class UniverseManager:
    def __init__(
        self, memory: ExperimentMemory, data_root: Path, future_lock_start: str
    ):
        self.memory, self.provider = memory, BinanceProvider()
        self.research = DataManager(data_root / "research", future_lock_start)
        self.forward = ForwardDataManager(data_root / "forward", future_lock_start)
        self.lock = datetime.fromisoformat(future_lock_start.replace("Z", "+00:00"))

    def refresh(self) -> int:
        symbols = self.provider.spot_usdt_symbols()
        now = utc_now()
        with self.memory.transaction() as db:
            for symbol in symbols:
                db.execute(
                    """INSERT INTO asset_universe(symbol,status,first_seen,last_seen,updated_at)
                       VALUES(?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET
                       status='TRADING',last_seen=excluded.last_seen,updated_at=excluded.updated_at""",
                    (symbol, "TRADING", now, now, now),
                )
            if symbols:
                placeholders = ",".join("?" for _ in symbols)
                db.execute(
                    f"UPDATE asset_universe SET status='INACTIVE',updated_at=? WHERE symbol NOT IN ({placeholders})",
                    (now, *symbols),
                )
        return len(symbols)

    def download_batch(
        self,
        batch_size: int = 3,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        with self.memory.session() as db:
            rows = db.execute(
                """SELECT symbol FROM asset_universe WHERE status='TRADING'
                   ORDER BY CASE WHEN research_path IS NULL THEN 0 ELSE 1 END,
                            CASE WHEN forward_path IS NULL THEN 0 ELSE 1 END, updated_at, symbol LIMIT ?""",
                (batch_size,),
            ).fetchall()
        results = []
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for index, row in enumerate(rows, 1):
            symbol = row["symbol"]
            if progress:
                progress(symbol, index, len(rows))
            research_path = forward_path = None
            try:
                historical = self.provider.bars(
                    symbol, "1d", datetime(2017, 1, 1, tzinfo=timezone.utc), self.lock
                )
                if historical:
                    audit = self.research.audit(historical, "1d")
                    research_path = str(
                        self.research.save_csv(
                            historical, "binance", symbol, "1d", audit
                        )
                    )
                if today > self.lock:
                    current = self.provider.bars(symbol, "1d", self.lock, today)
                    if current:
                        audit = self.forward.audit(current, "1d")
                        forward_path = str(
                            self.forward.save_csv(
                                current, "binance", symbol, "1d", audit
                            )
                        )
                with self.memory.transaction() as db:
                    db.execute(
                        "UPDATE asset_universe SET research_path=COALESCE(?,research_path),forward_path=COALESCE(?,forward_path),last_error=NULL,updated_at=? WHERE symbol=?",
                        (research_path, forward_path, utc_now(), symbol),
                    )
                results.append(
                    {
                        "symbol": symbol,
                        "research_path": research_path,
                        "forward_path": forward_path,
                        "ok": True,
                    }
                )
            except Exception as exc:
                with self.memory.transaction() as db:
                    db.execute(
                        "UPDATE asset_universe SET last_error=?,updated_at=? WHERE symbol=?",
                        (str(exc)[:1000], utc_now(), symbol),
                    )
                results.append({"symbol": symbol, "ok": False, "error": str(exc)})
        return results

    def coverage(self) -> dict[str, int]:
        with self.memory.session() as db:
            row = db.execute(
                """SELECT count(*) total,
                   sum(CASE WHEN research_path IS NOT NULL THEN 1 ELSE 0 END) research_ready,
                   sum(CASE WHEN forward_path IS NOT NULL THEN 1 ELSE 0 END) forward_ready,
                   sum(CASE WHEN last_error IS NOT NULL THEN 1 ELSE 0 END) errors
                   FROM asset_universe WHERE status='TRADING'"""
            ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}
