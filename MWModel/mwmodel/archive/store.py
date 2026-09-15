"""THE STORE: append-only, bitemporal, one file per stream, and never in git.

    backtester/data/world/
        manifest.json            every stream: rows, first, last, sha256, built_at
        series/<stream_id>.json  {"id":…, "meta":{…}, "obs":[[ref_date, value, known_at], …]}
        events/<YYYY>.jsonl      one event per line, ascending by ref_ts

JSON, deliberately. `pyarrow` is not installed on this machine, every other store in this lab
is JSON, and the whole series archive is tens of megabytes. Events are JSONL because they grow
without bound and must be appendable and streamable. When the news feed makes that choice
wrong the format changes HERE and no consumer notices, which is the only reason this module
exists as a layer rather than as a pathname.

THE THIRD COLUMN IS THE POINT. Every row carries `known_at` alongside `ref_date`, written
once at build time from the stream's declared lag, so that no reader can forget to apply it
and no reader can apply it twice.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import adapters
from .streams import Stream, get, registry

_HERE = Path(__file__).resolve()
#: MWModel's own root - the folder that contains `mwmodel/`, `data/`, `docs/`, `server/`.
#: Found by walking up from this file rather than assumed from a working directory, because
#: this laboratory has already lost an afternoon to a loader that silently fell back when run
#: from the wrong place.
MW_ROOT = Path(os.environ.get("MWMODEL_ROOT") or _HERE.parents[2])
WORLD_ROOT = MW_ROOT / "data" / "archive"
SERIES_DIR = WORLD_ROOT / "series"
EVENTS_DIR = WORLD_ROOT / "events"
MANIFEST = WORLD_ROOT / "manifest.json"

#: The sealed forward window, the same instant the candle catalogue locks on. The store HOLDS
#: observations past it - it must, or 2026 could never be evaluated - and the readers refuse
#: to cross it unless asked in a way that shows up in a diff.
LOCK_DAY = "2026-01-01"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def path_for(stream_id: str) -> Path:
    return SERIES_DIR / f"{stream_id}.json"


# ------------------------------------------------------------------------------- writing
def build(stream: Stream, *, quiet: bool = True) -> dict:
    """Materialise one stream from its adapter, stamping every row with `known_at`.

    Returns the manifest entry. Writing is idempotent: the same inputs produce the same file
    and the same digest, which is what makes the manifest a useful thing to compare across
    machines.
    """
    obs = adapters.read(stream)
    rows = [[ref, value, stream.known_at(ref)] for ref, value in obs]
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    blob = {"id": stream.id, "meta": asdict(stream), "built_at": _now(), "obs": rows}
    payload = json.dumps(blob, separators=(",", ":"))
    path_for(stream.id).write_text(payload, encoding="utf-8")
    entry = {"rows": len(rows),
             "first": rows[0][0] if rows else None,
             "last": rows[-1][0] if rows else None,
             "sha256": hashlib.sha256(
                 json.dumps(rows, separators=(",", ":")).encode()).hexdigest()[:16],
             "built_at": blob["built_at"], "vintage": stream.vintage,
             "lag_days": stream.lag_days, "source": stream.source}
    if not quiet:
        print(f"  {stream.id:<34s}{len(rows):>8,} rows  "
              f"{entry['first'] or '-'} .. {entry['last'] or '-'}")
    return entry


def build_all(*, only: list[str] | None = None, quiet: bool = False) -> dict:
    """Rebuild the archive from the sources already on disk. Downloads nothing."""
    manifest = read_manifest()
    ids = only or sorted(registry())
    missing: dict[str, str] = {}
    for sid in ids:
        stream = get(sid)
        try:
            manifest["streams"][sid] = build(stream, quiet=quiet)
        except FileNotFoundError as exc:
            # A registered stream whose source has not been harvested yet is the NORMAL
            # state of a catalogue, and saying so is more useful than a traceback.
            missing[sid] = str(exc).split("\n")[0]
            manifest["streams"].pop(sid, None)
    manifest["built_at"] = _now()
    manifest["missing"] = missing
    write_manifest(manifest)
    return manifest


def read_manifest() -> dict:
    if MANIFEST.is_file():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            pass          # a corrupt manifest is rebuildable; never let it block a run
    return {"streams": {}, "missing": {}, "built_at": None}


def write_manifest(manifest: dict) -> None:
    WORLD_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")


# ------------------------------------------------------------------------------- reading
_CACHE: dict[str, tuple[list[str], list[float], list[str]]] = {}


def load(stream_id: str) -> tuple[list[str], list[float], list[str]]:
    """`(ref_dates, values, known_ats)`, ascending by ref_date. Cached per process.

    Raises `FileNotFoundError` with an instruction rather than a mystery: a stream that is
    registered but not built is a build away, and the message says so.
    """
    hit = _CACHE.get(stream_id)
    if hit is not None:
        return hit
    p = path_for(stream_id)
    if not p.is_file():
        raise FileNotFoundError(
            f"{stream_id} is registered but not built. Run "
            f"`python -m mwmodel.archive.build` - it downloads nothing, it only adopts what "
            f"is already in the catalogue.")
    blob = json.loads(p.read_text(encoding="utf-8-sig"))
    refs = [r[0] for r in blob["obs"]]
    vals = [float(r[1]) for r in blob["obs"]]
    known = [r[2] for r in blob["obs"]]
    _CACHE[stream_id] = (refs, vals, known)
    return _CACHE[stream_id]


def have(stream_id: str) -> bool:
    return path_for(stream_id).is_file()


def built() -> list[str]:
    if not SERIES_DIR.is_dir():
        return []
    return sorted(p.stem for p in SERIES_DIR.glob("*.json"))
