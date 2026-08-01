from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import Bar


class DataError(ValueError):
    pass


@dataclass(frozen=True)
class DataAudit:
    """Deterministic quality evidence attached to every persisted dataset."""

    schema_version: str
    interval: str
    expected_step_seconds: float
    bar_count: int
    requested_start: str | None
    requested_end: str | None
    observed_start: str
    observed_end: str
    missing_intervals: list[dict[str, Any]]
    off_grid_timestamps: list[str]
    irregular_intervals: list[dict[str, Any]]
    boundary_issues: list[str]

    @property
    def passed(self) -> bool:
        return not any(
            (
                self.missing_intervals,
                self.off_grid_timestamps,
                self.irregular_intervals,
                self.boundary_issues,
            )
        )

    def document(self) -> dict[str, Any]:
        result = asdict(self)
        result["passed"] = self.passed
        return result


class MarketDataProvider(ABC):
    @abstractmethod
    def bars(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[Bar]:
        raise NotImplementedError


class SyntheticProvider(MarketDataProvider):
    """Seeded regime-changing data for infrastructure tests, never alpha claims."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def bars(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[Bar]:
        step = {"1d": timedelta(days=1), "1h": timedelta(hours=1)}.get(interval)
        if not step:
            raise DataError(f"unsupported synthetic interval: {interval}")
        rng = random.Random(
            f"{self.seed}:{symbol}:{interval}:{start.isoformat()}:{end.isoformat()}"
        )
        output: list[Bar] = []
        timestamp, price, index = start, 100.0, 0
        while timestamp < end:
            regime = (index // 70) % 4
            drift = (0.0015, -0.0012, 0.0, 0.0004)[regime]
            volatility = (0.012, 0.018, 0.006, 0.025)[regime]
            shock = rng.gauss(drift, volatility)
            open_price = price
            close = max(0.01, open_price * math.exp(shock))
            spread = abs(rng.gauss(0.006, 0.003))
            high = max(open_price, close) * (1 + spread)
            low = min(open_price, close) * max(0.01, 1 - spread)
            volume = 1000 * (1 + abs(shock) * 20) * rng.uniform(0.7, 1.3)
            taker_ratio = min(0.95, max(0.05, 0.5 + shock * 6 + rng.gauss(0, 0.08)))
            output.append(
                Bar(
                    timestamp,
                    open_price,
                    high,
                    low,
                    close,
                    volume,
                    volume * taker_ratio,
                    10_000 * (1 + regime * 0.08),
                    0.0001 * regime,
                )
            )
            price, timestamp, index = close, timestamp + step, index + 1
        return output


class BinanceProvider(MarketDataProvider):
    """Public Binance spot kline provider. Download is explicit and paginated."""

    base_url = "https://api.binance.com/api/v3/klines"
    exchange_info_url = "https://api.binance.com/api/v3/exchangeInfo"

    def spot_usdt_symbols(self) -> list[str]:
        request = urllib.request.Request(
            self.exchange_info_url, headers={"User-Agent": "quantlab/0.2"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                document = json.load(response)
        except Exception as exc:
            raise DataError(f"Binance universe download failed: {exc}") from exc
        leveraged_suffixes = ("UP", "DOWN", "BULL", "BEAR")
        symbols = []
        for item in document.get("symbols", []):
            base = item.get("baseAsset", "")
            if (
                item.get("status") == "TRADING"
                and item.get("quoteAsset") == "USDT"
                and item.get("isSpotTradingAllowed", True)
                and not base.endswith(leveraged_suffixes)
            ):
                symbols.append(item["symbol"])
        return sorted(set(symbols))

    def bars(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[Bar]:
        cursor = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        output: list[Bar] = []
        while cursor < end_ms:
            query = urllib.parse.urlencode(
                {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_ms - 1,
                    "limit": 1000,
                }
            )
            request = urllib.request.Request(
                f"{self.base_url}?{query}", headers={"User-Agent": "quantlab/0.1"}
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    rows = json.load(response)
            except Exception as exc:
                raise DataError(f"Binance download failed: {exc}") from exc
            if not rows:
                break
            for row in rows:
                timestamp = datetime.fromtimestamp(row[0] / 1000, timezone.utc)
                if timestamp >= end:
                    break
                output.append(
                    Bar(
                        timestamp, *map(float, row[1:6]), taker_buy_volume=float(row[9])
                    )
                )
            next_cursor = int(rows[-1][0]) + 1
            if next_cursor <= cursor:
                raise DataError("Binance pagination did not advance")
            cursor = next_cursor
        return output


class DataManager:
    def __init__(self, root: Path | str, future_lock_start: str):
        self.root = Path(root)
        self.future_lock = datetime.fromisoformat(
            future_lock_start.replace("Z", "+00:00")
        )

    def validate(self, bars: list[Bar]) -> None:
        if len(bars) < 3:
            raise DataError("at least three bars are required")
        previous = None
        for bar in bars:
            if bar.timestamp >= self.future_lock:
                raise DataError("future-locked 2026 data cannot enter research")
            if previous is not None and bar.timestamp <= previous:
                raise DataError("timestamps must be unique and strictly increasing")
            required = (bar.open, bar.high, bar.low, bar.close, bar.volume)
            optional = (bar.taker_buy_volume, bar.open_interest, bar.funding_rate)
            if not all(math.isfinite(value) for value in required):
                raise DataError("bar values must be finite")
            if any(
                value is not None and not math.isfinite(value) for value in optional
            ):
                raise DataError("optional bar values must be finite when present")
            if min(bar.open, bar.high, bar.low, bar.close) <= 0 or bar.volume < 0:
                raise DataError("prices must be positive and volume non-negative")
            if (
                bar.taker_buy_volume is not None
                and not 0 <= bar.taker_buy_volume <= bar.volume
            ):
                raise DataError("taker buy volume must be within total volume")
            if bar.open_interest is not None and bar.open_interest < 0:
                raise DataError("open interest must be non-negative")
            if bar.high < max(bar.open, bar.close) or bar.low > min(
                bar.open, bar.close
            ):
                raise DataError("invalid OHLC envelope")
            previous = bar.timestamp

    @staticmethod
    def interval_step(interval: str) -> timedelta:
        units = {"m": 60, "h": 3_600, "d": 86_400, "w": 604_800}
        if len(interval) < 2 or interval[-1] not in units:
            raise DataError(f"unsupported fixed interval: {interval}")
        try:
            count = int(interval[:-1])
        except ValueError as exc:
            raise DataError(f"unsupported fixed interval: {interval}") from exc
        if count <= 0:
            raise DataError(f"unsupported fixed interval: {interval}")
        return timedelta(seconds=count * units[interval[-1]])

    def audit(
        self,
        bars: list[Bar],
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> DataAudit:
        self.validate(bars)
        step = self.interval_step(interval)
        step_us = int(step.total_seconds() * 1_000_000)
        missing: list[dict[str, Any]] = []
        irregular: list[dict[str, Any]] = []
        off_grid: list[str] = []
        boundaries: list[str] = []
        for bar in bars:
            if int(bar.timestamp.timestamp() * 1_000_000) % step_us:
                off_grid.append(bar.timestamp.isoformat())
        for previous, current in zip(bars, bars[1:]):
            delta_us = int(
                (current.timestamp - previous.timestamp).total_seconds() * 1_000_000
            )
            if delta_us == step_us:
                continue
            detail = {
                "after": previous.timestamp.isoformat(),
                "before": current.timestamp.isoformat(),
                "elapsed_seconds": delta_us / 1_000_000,
            }
            if delta_us > step_us and delta_us % step_us == 0:
                detail["missing_bars"] = delta_us // step_us - 1
                missing.append(detail)
            else:
                irregular.append(detail)
        if start is not None or end is not None:
            if start is None or end is None:
                raise DataError("audit coverage requires both start and end")
            if start.tzinfo is None or end.tzinfo is None:
                raise DataError("audit boundaries must be timezone-aware")
            self.validate_window(start, end)
            if bars[0].timestamp != start:
                boundaries.append(
                    f"first bar {bars[0].timestamp.isoformat()} does not equal requested start {start.isoformat()}"
                )
            if bars[-1].timestamp + step != end:
                boundaries.append(
                    f"last bar ends at {(bars[-1].timestamp + step).isoformat()}, not requested end {end.isoformat()}"
                )
        return DataAudit(
            "quantlab-data-audit-v1",
            interval,
            step.total_seconds(),
            len(bars),
            start.isoformat() if start else None,
            end.isoformat() if end else None,
            bars[0].timestamp.isoformat(),
            bars[-1].timestamp.isoformat(),
            missing,
            off_grid,
            irregular,
            boundaries,
        )

    def validate_window(self, start: datetime, end: datetime) -> None:
        if start >= end:
            raise DataError("download start must precede end")
        if end > self.future_lock:
            raise DataError("requested window crosses the future-locked 2026 boundary")

    @staticmethod
    def version(bars: list[Bar], provider: str, symbol: str, interval: str) -> str:
        digest = hashlib.sha256()
        digest.update(f"quantlab-bars-v2:{provider}:{symbol}:{interval}\n".encode())
        for bar in bars:
            row = [
                bar.timestamp.isoformat(),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.taker_buy_volume,
                bar.open_interest,
                bar.funding_rate,
            ]
            digest.update(
                json.dumps(row, separators=(",", ":"), allow_nan=False).encode()
            )
            digest.update(b"\n")
        return digest.hexdigest()

    def save_csv(
        self,
        bars: list[Bar],
        provider: str,
        symbol: str,
        interval: str,
        audit: DataAudit | None = None,
    ) -> Path:
        self.validate(bars)
        audit = audit or self.audit(bars, interval)
        if not audit.passed:
            raise DataError(
                "data audit failed; refusing to persist a processed dataset"
            )
        dataset_version = self.version(bars, provider, symbol, interval)
        path = (
            self.root
            / "processed"
            / provider
            / symbol
            / interval
            / f"{dataset_version}.csv"
        )
        manifest_path = path.with_suffix(".manifest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        manifest_temporary = manifest_path.with_suffix(".tmp")
        with temporary.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "taker_buy_volume",
                    "open_interest",
                    "funding_rate",
                ]
            )
            for b in bars:
                writer.writerow(
                    [
                        b.timestamp.isoformat(),
                        b.open,
                        b.high,
                        b.low,
                        b.close,
                        b.volume,
                        b.taker_buy_volume,
                        b.open_interest,
                        b.funding_rate,
                    ]
                )
        file_checksum = hashlib.sha256(temporary.read_bytes()).hexdigest()
        manifest = {
            "schema_version": "quantlab-dataset-manifest-v1",
            "dataset_version": dataset_version,
            "provider": provider,
            "symbol": symbol,
            "interval": interval,
            "format": "csv",
            "file": path.name,
            "file_sha256": file_checksum,
            "audit": audit.document(),
        }
        manifest_temporary.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        temporary.replace(path)
        manifest_temporary.replace(manifest_path)
        return path

    @staticmethod
    def verify_csv(path: Path | str) -> dict[str, Any]:
        path = Path(path)
        manifest_path = path.with_suffix(".manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise DataError(
                f"dataset manifest is missing or invalid: {manifest_path}"
            ) from exc
        if manifest.get("schema_version") != "quantlab-dataset-manifest-v1":
            raise DataError("unsupported dataset manifest schema")
        if (
            manifest.get("file") != path.name
            or manifest.get("dataset_version") != path.stem
        ):
            raise DataError("dataset manifest identity does not match the file")
        try:
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise DataError(f"dataset file cannot be read: {path}") from exc
        if checksum != manifest.get("file_sha256"):
            raise DataError("dataset checksum does not match its manifest")
        if not manifest.get("audit", {}).get("passed"):
            raise DataError("dataset manifest does not contain a passing audit")
        return manifest

    @staticmethod
    def load_csv(path: Path | str) -> list[Bar]:
        path = Path(path)
        output: list[Bar] = []
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):

                def optional(name: str) -> float | None:
                    value = row.get(name)
                    return float(value) if value not in (None, "", "None") else None

                output.append(
                    Bar(
                        datetime.fromisoformat(row["timestamp"]),
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["volume"]),
                        optional("taker_buy_volume"),
                        optional("open_interest"),
                        optional("funding_rate"),
                    )
                )
        return output


class ForwardDataManager(DataManager):
    """Isolated 2026+ shadow-evaluation store; never accepted by research code."""

    def validate(self, bars: list[Bar]) -> None:
        original_lock = self.future_lock
        self.future_lock = datetime.max.replace(tzinfo=timezone.utc)
        try:
            super().validate(bars)
        finally:
            self.future_lock = original_lock
        if bars[0].timestamp < original_lock:
            raise DataError("forward datasets must begin at the 2026 lock boundary")
        if bars[-1].timestamp > datetime.now(timezone.utc) + timedelta(days=1):
            raise DataError("forward dataset contains timestamps beyond the present")

    def validate_window(self, start: datetime, end: datetime) -> None:
        if start < self.future_lock:
            raise DataError("forward window cannot include pre-2026 research data")
        if start >= end:
            raise DataError("forward start must precede end")
        if end > datetime.now(timezone.utc) + timedelta(days=1):
            raise DataError("forward window cannot extend beyond the present")
