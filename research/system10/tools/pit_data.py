"""Candles for the point-in-time universe (audit 2026-10-15, item 1), from Binance's public
archive (data.binance.vision), which keeps klines of delisted pairs.

    screen   list every USDT spot pair in the archive, read each December's daily klines
             (2019-2025), keep pairs that could qualify for a year: about 540 days listed
             and >= 0.8 x the turnover floor over the month (the exact rule runs later on
             the 15m candles, in system010_conditioned_rl/universe_pit.py)
    fetch    download the 15m monthly klines of the screened pairs (pre-2026 only) into the
             catalogue's research store, in DataManager's format. A pair already on disk is
             never touched. A ticker re-used after a gap > 7 days (LUNA -> LUNA 2.0) is split:
             the last segment keeps the name, earlier ones become SYMBOL_YYYYMM (month it ended).

Raw zips stay in a scratch folder (default: <DATA_ROOT>/pit_archive, gitignored).
Run from the repo root with PYTHONPATH="trading-system;backtester".
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for sub in ("trading-system", "trading-system/systems", "backtester"):
    sys.path.insert(0, str(REPO / sub))

from quantlab_catalog.paths import DATA_ROOT, LOCK  # noqa: E402
from system006_oracle_net_15m.universe import DEFAULT_MIN_TURNOVER, STABLE_BASES  # noqa: E402

LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FILES = "https://data.binance.vision/"
PREFIX = "data/spot/monthly/klines/"
LEVERAGED = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")
SCREEN_YEARS = range(2019, 2026)          # Decembers that decide 2020..2026
SCREEN = DATA_ROOT / "universe" / "pit_screen.json"
GAP_SPLIT = timedelta(days=7)


def _get(url: str, tries: int = 4) -> bytes | None:
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "quantlab-pit/1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if k == tries - 1:
                raise
        except Exception:  # noqa: BLE001
            if k == tries - 1:
                raise
    return None


def _list(prefix: str) -> tuple[list[str], list[str]]:
    """(sub-prefixes, keys) under `prefix`, all pages."""
    dirs, keys, marker = [], [], ""
    while True:
        xml = _get(f"{LIST}?delimiter=/&prefix={prefix}&marker={marker}").decode()
        dirs += re.findall(r"<CommonPrefixes><Prefix>([^<]+)</Prefix>", xml)
        keys += re.findall(r"<Key>([^<]+)</Key>", xml)
        if "<IsTruncated>true</IsTruncated>" not in xml:
            return dirs, keys
        nxt = re.findall(r"<NextMarker>([^<]+)</NextMarker>", xml)
        marker = nxt[0] if nxt else (keys[-1] if keys else dirs[-1])


def _rows(blob: bytes) -> list[list[float]]:
    """Kline rows of an archive zip; open time in ms (the archive moved to us in 2025)."""
    out = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            for row in csv.reader(io.TextIOWrapper(z.open(name), encoding="utf-8")):
                if not row or not row[0].strip().isdigit():
                    continue          # header line in some files
                r = [float(x) for x in row[:11]]
                if r[0] > 1e14:
                    r[0] /= 1000.0
                out.append(r)
    out.sort(key=lambda r: r[0])
    return out


def usdt_symbols() -> list[str]:
    dirs, _ = _list(PREFIX)
    syms = [d[len(PREFIX):].strip("/") for d in dirs]
    return sorted(s for s in syms if s.isascii() and s.isalnum() and s.endswith("USDT") and not s.endswith(LEVERAGED)
                  and s[:-4] not in STABLE_BASES and s[:-4])


def months(symbol: str, interval: str) -> list[str]:
    _, keys = _list(f"{PREFIX}{symbol}/{interval}/")
    return sorted(k.rsplit("-", 2)[-2] + "-" + k.rsplit("-", 1)[-1][:2]
                  for k in keys if k.endswith(".zip"))


def _screen_one(symbol: str) -> dict:
    m = months(symbol, "1d")
    out = {"symbol": symbol, "first_month": m[0] if m else None, "dec": {}}
    for y in SCREEN_YEARS:
        if f"{y}-12" not in m:
            continue
        blob = _get(f"{FILES}{PREFIX}{symbol}/1d/{symbol}-1d-{y}-12.zip")
        rows = _rows(blob) if blob else []
        if rows:
            last30 = rows[-30:]
            out["dec"][str(y)] = round(sum(r[7] for r in last30) / 30.0, 0)
    return out


def screen(threads: int) -> dict:
    syms = usdt_symbols()
    print(f"{len(syms)} USDT spot pairs in the archive", flush=True)
    with ThreadPoolExecutor(threads) as ex:
        rows = list(ex.map(_screen_one, syms))
    floor = 0.8 * DEFAULT_MIN_TURNOVER
    cand: dict[str, list[int]] = {}
    for r in rows:
        if not r["first_month"]:
            continue
        first = datetime.strptime(r["first_month"], "%Y-%m")
        for y, tv in r["dec"].items():
            age = (datetime(int(y), 12, 31) - first).days
            if age >= 540 - 31 and tv >= floor:
                cand.setdefault(r["symbol"], []).append(int(y) + 1)
    doc = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "rule": "December mean daily quote volume >= 0.8 x floor and first month <= ~540 days before 31 Dec",
           "floor": DEFAULT_MIN_TURNOVER, "pairs": len(syms), "rows": rows,
           "candidates": dict(sorted(cand.items()))}
    SCREEN.parent.mkdir(parents=True, exist_ok=True)
    SCREEN.write_text(json.dumps(doc, indent=1))
    for y in range(2020, 2027):
        print(y, sum(y in v for v in cand.values()), flush=True)
    print(f"{len(cand)} candidates -> {SCREEN}")
    return doc


def _bars(rows: list[list[float]]):
    from quantlab_backtester.models import Bar
    out, last = [], None
    for r in rows:
        ts = datetime.fromtimestamp(r[0] / 1000.0, timezone.utc)
        if ts >= datetime.fromisoformat(LOCK) or (last is not None and ts <= last):
            continue
        o, h, lo, c, v, tb = r[1], r[2], r[3], r[4], r[5], r[9]
        if min(o, h, lo, c) <= 0:
            continue
        h, lo = max(h, o, c), min(lo, o, c)
        out.append(Bar(ts, o, h, lo, c, max(v, 0.0), min(max(tb, 0.0), max(v, 0.0))))
        last = ts
    return out


def fetch_one(symbol: str, cache: Path, threads: int) -> dict:
    from quantlab_backtester.data import DataManager
    research = DATA_ROOT / "research" / "processed" / "binance"
    if (research / symbol / "15m").is_dir() and any((research / symbol / "15m").glob("*.csv")):
        return {"symbol": symbol, "skipped": "already on disk"}
    m = [x for x in months(symbol, "15m") if x < "2026-01"]
    if not m:
        return {"symbol": symbol, "skipped": "no 15m months in the archive"}
    d = cache / symbol
    d.mkdir(parents=True, exist_ok=True)

    def one(mon: str):
        p = d / f"{symbol}-15m-{mon}.zip"
        if not p.is_file():
            blob = _get(f"{FILES}{PREFIX}{symbol}/15m/{symbol}-15m-{mon}.zip")
            if blob is None:
                return []
            p.write_bytes(blob)
        return _rows(p.read_bytes())

    with ThreadPoolExecutor(threads) as ex:
        rows = [r for part in ex.map(one, m) for r in part]
    rows.sort(key=lambda r: r[0])
    bars = _bars(rows)
    segs, start = [], 0
    for i in range(1, len(bars)):
        if bars[i].timestamp - bars[i - 1].timestamp > GAP_SPLIT:
            segs.append(bars[start:i])
            start = i
    segs.append(bars[start:])
    dm = DataManager(DATA_ROOT / "research", LOCK)
    saved = []
    for k, seg in enumerate(segs):
        name = symbol if k == len(segs) - 1 else f"{symbol}_{seg[-1].timestamp:%Y%m}"
        if len(seg) < 3 or any((research / name / "15m").glob("*.csv")):
            continue
        dm.save_csv(seg, "binance", name, "15m", dm.audit(seg, "15m"), require_clean_audit=False)
        saved.append({"name": name, "bars": len(seg), "first": seg[0].timestamp.isoformat(),
                      "last": seg[-1].timestamp.isoformat()})
    return {"symbol": symbol, "saved": saved}


def fetch(symbols: list[str], cache: Path, threads: int) -> None:
    for s in symbols:
        try:
            r = fetch_one(s, cache, threads)
        except Exception as e:  # noqa: BLE001
            r = {"symbol": s, "error": repr(e)}
        print(json.dumps(r), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("screen", "fetch"))
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--cache", default=str(DATA_ROOT / "pit_archive"))
    ap.add_argument("--symbols", nargs="*", help="fetch: these (default: every screened candidate)")
    a = ap.parse_args()
    if a.cmd == "screen":
        screen(a.threads)
    else:
        syms = a.symbols or list(json.loads(SCREEN.read_text())["candidates"])
        fetch(syms, Path(a.cache), a.threads)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
