"""`python -m mwmodel.archive.ingest.eia` - the real energy balance, free and keyless.

Phase 1 of the master plan is "the energy chain, properly", and it begins by deleting the
round numbers in `seed/facts.py`. The EIA publishes its entire international database as a
single 24 MB bulk file with no key and no licence restriction, updated within the month:

    Petroleum and other liquids production          monthly, thousand barrels per day
    Refined petroleum products consumption          annual, thousand barrels per day
    Crude oil including lease condensate imports    annual
    Crude oil including lease condensate exports    annual

That is the quantity side of the world oil market for every country that has one, in the
units the market actually quotes, needing no conversion and therefore inviting no conversion
error. The alternative sources were checked and rejected on 2026-09-15: JODI's direct CSV is
404, OWID publishes energy in terawatt-hours whose barrel equivalence is ambiguous by a third,
and the IEA's balances are paid.

CAPACITY IS NOT PRODUCTION, and the difference is the whole of OPEC. What a country pumps is a
decision; what it *could* pump is a constraint, and only the second belongs in an agent's
parameters. There is no free published series of productive capacity, so it is inferred - the
highest month of the last five years, plus a small allowance - and the countries that
deliberately hold spare capacity carry a declared figure instead, marked as declared. Anything
inferred says so, because a capacity that is really just last year's peak will understate
exactly the producers who matter most in a crisis.
"""

from __future__ import annotations

import json
import sys
import urllib.request
import zipfile
from pathlib import Path

from ..store import WORLD_ROOT

BULK = "https://www.eia.gov/opendata/bulk/INTL.zip"
RAW = WORLD_ROOT / "raw" / "eia"
CACHE = WORLD_ROOT.parent / "raw" / "INTL.zip"

#: name prefix -> (short key, wanted unit). Everything else in the file is ignored.
FAMILIES = {
    "Petroleum and other liquids production": ("production", "thousand barrels per day"),
    "Refined petroleum products consumption": ("consumption", "thousand barrels per day"),
    # Crude alone, alongside total liquids, because the declared OPEC capacities are CRUDE
    # capacities and the production series is TOTAL LIQUIDS. Mixing the two silently makes
    # every Gulf producer look as though it has no spare capacity at all.
    "Crude oil including lease condensate production": ("crude", "thousand barrels per day"),
    # STOCKS, which turn out to matter more than any coefficient. The clearing prices days of
    # cover, and until now every replay started at exactly sixty days of it - which is to say
    # the model was told nothing about whether the world was tight or comfortable on the day
    # the run began. That is the single largest piece of information it was missing.
    "Petroleum and other liquids stocks": ("stocks", "millions barrels"),
    "Crude oil including lease condensate imports": ("imports", "thousand barrels per day"),
    "Crude oil including lease condensate exports": ("exports", "thousand barrels per day"),
}

#: Declared sustainable capacity, mb/d, for the producers who hold spare on purpose. These are
#: policy statements rather than measurements and they are listed here so that they can be
#: argued with rather than discovered inside a result.
DECLARED_CAPACITY = {
    "SAU": 12.0, "ARE": 4.85, "KWT": 2.9, "IRQ": 5.0, "IRN": 3.9, "RUS": 11.0,
}


def download(force: bool = False) -> Path:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if force or not CACHE.exists():
        req = urllib.request.Request(BULK, headers={"User-Agent": "mwmodel/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            CACHE.write_bytes(r.read())
    return CACHE


def extract(path: Path) -> dict[str, dict[str, list]]:
    """`{family: {ISO3: [[period, value], ...]}}`, monthly where published, else annual."""
    out: dict[str, dict[str, list]] = {k: {} for _, (k, _) in FAMILIES.items()}
    best_freq: dict[tuple[str, str], str] = {}
    with zipfile.ZipFile(path) as z:
        with z.open("INTL.txt") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                name = d.get("name") or ""
                head = name.split(",")[0]
                spec = FAMILIES.get(head)
                if not spec:
                    continue
                key, unit = spec
                if d.get("units") != unit:
                    continue
                iso = (d.get("geography") or "").upper()
                if len(iso) != 3:
                    continue
                freq = (d.get("f") or "A").upper()
                # Monthly beats annual when both exist: a model that ticks daily wants the
                # finest grain published, and the annual figure is only a fallback.
                prev = best_freq.get((key, iso))
                if prev == "M" and freq != "M":
                    continue
                rows = []
                for r in d.get("data") or []:
                    if not isinstance(r, (list, tuple)) or len(r) < 2:
                        continue
                    v = r[1]
                    if v in (None, "", "--", "NA", "(s)", "W"):
                        continue
                    try:
                        rows.append([str(r[0]), float(v)])
                    except (TypeError, ValueError):
                        continue
                if not rows:
                    continue
                rows.sort(key=lambda x: x[0])
                out[key][iso] = rows
                best_freq[(key, iso)] = freq
    return out


def _to_day(period: str) -> str:
    """EIA periods are YYYY, YYYYMM or YYYYQn. A quarter is dated at the quarter's END.

    Dating a period at its end rather than its start is the same rule the World Archive
    learned the hard way: a figure that summarises a quarter does not exist until the quarter
    is over, and stamping it at the start is a three-month leak.
    """
    p = str(period).strip()
    if "Q" in p.upper() and len(p) == 6:
        q = int(p.upper().split("Q")[1])
        return f"{p[:4]}-{q * 3:02d}-{(31 if q in (1, 4) else 30):02d}"
    if len(p) == 4:
        return f"{p}-12-31"
    if len(p) == 6:
        return f"{p[:4]}-{p[4:6]}-01"
    return p[:10]


def save(data: dict[str, dict[str, list]]) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    summary = {}
    for family, by_iso in data.items():
        blob = {iso: [[_to_day(p), v] for p, v in rows] for iso, rows in by_iso.items()}
        (RAW / f"{family}.json").write_text(
            json.dumps({"meta": {"source": BULK, "family": family}, "by_iso": blob},
                       separators=(",", ":")), encoding="utf-8")
        summary[family] = {"countries": len(blob),
                           "last": max((r[-1][0] for r in blob.values() if r), default=None)}
    return summary


def load(family: str) -> dict[str, list]:
    p = RAW / f"{family}.json"
    if not p.is_file():
        raise FileNotFoundError(
            f"{p} has not been harvested. Run `python -m mwmodel.archive.ingest.eia`.")
    return json.loads(p.read_text(encoding="utf-8-sig"))["by_iso"]


def main(argv: list[str] | None = None) -> int:
    print("MWModel - ingest: EIA international energy data (free, keyless)")
    path = download(force="--force" in (argv or sys.argv[1:]))
    print(f"  bulk file {path.stat().st_size / 1e6:.1f} MB")
    data = extract(path)
    summary = save(data)
    for family, s in summary.items():
        print(f"  {family:<14s}{s['countries']:>5d} countries, latest {s['last']}")
    print(f"  written to {RAW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
