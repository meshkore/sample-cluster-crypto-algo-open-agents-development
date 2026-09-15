"""`python -m quantlab_world.ingest.dbnomics` - inflation for the countries FRED abandoned.

WHY THIS EXISTS, measured on 2026-09-15. Every national inflation series adopted from FRED is
a mirror of the OECD's Main Economic Indicators, and FRED stopped updating them. The last
observation is June 2021 for Japan, November 2023 for Korea, and March or April 2025 for
China, India, Brazil, the UK, Turkey and South Africa. A regional inflation block whose
readings stop before the window being evaluated is not a regional inflation block; it is a
constant, and a constant across an era is how a model learns the calendar.

DBnomics is a free, keyless aggregator that re-publishes the IMF's own monthly CPI dataset.
It reaches July 2025 for most of the same countries - not current, but four years better for
Japan and a live source rather than a dead mirror.

AND IT IS STILL NOT ENOUGH, which the archive says out loud rather than hiding. Free monthly
inflation for the whole world, published promptly, does not exist without a key. So:

    US        FRED, current to last month. Good.
    euro area + European members + Turkey   Eurostat, current. Good.
    everywhere else   IMF via DBnomics, roughly a year behind, and marked as such by the
                      staleness guard, which will return None rather than let a 2025 reading
                      stand for a 2026 day.

The fast, current, genuinely regional variable we DO have for every one of these countries is
the currency and the local bond and equity market - daily, never revised, never late. That is
where "what does a holder in Sao Paulo actually face" is legible today; inflation is the slow
confirmation that arrives afterwards.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from ..store import WORLD_ROOT

RAW = WORLD_ROOT / "raw" / "dbnomics"
API = "https://api.db.nomics.world/v22/series/{provider}/{dataset}/{code}?observations=true"
TIMEOUT = 45

#: country -> the IMF's monthly consumer price INDEX (not the rate; the archive differences
#: it itself, so that the lookback is ours and is stated).
IMF_CPI = {
    "JP": "M.JP.PCPI_IX", "CN": "M.CN.PCPI_IX", "IN": "M.IN.PCPI_IX",
    "BR": "M.BR.PCPI_IX", "ZA": "M.ZA.PCPI_IX", "KR": "M.KR.PCPI_IX",
    "TR": "M.TR.PCPI_IX", "GB": "M.GB.PCPI_IX", "CA": "M.CA.PCPI_IX",
    "ID": "M.ID.PCPI_IX", "RU": "M.RU.PCPI_IX", "AE": "M.AE.PCPI_IX",
    "US": "M.US.PCPI_IX",
}


def fetch(provider: str, dataset: str, code: str) -> list[list]:
    """One series as `[[YYYY-MM-DD, value], ...]`, ascending, missing observations dropped."""
    url = API.format(provider=provider, dataset=dataset, code=code)
    req = urllib.request.Request(url, headers={"User-Agent": "quantlab-world/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        blob = json.loads(resp.read().decode("utf-8", errors="replace"))
    docs = blob.get("series", {}).get("docs") or []
    if not docs:
        raise ValueError(f"{provider}/{dataset}/{code}: no series returned")
    doc = docs[0]
    out = []
    for period, value in zip(doc.get("period", []), doc.get("value", [])):
        if value is None or value == "NA":
            continue
        day = f"{period}-01" if len(period) == 7 else str(period)[:10]
        try:
            out.append([day, float(value)])
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda r: r[0])
    return out


def save(name: str, rows: list[list], meta: dict) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{name}.json").write_text(
        json.dumps({"meta": meta, "rows": rows}, separators=(",", ":")), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    print("WORLD ARCHIVE - ingest: IMF monthly CPI via DBnomics (free, keyless)")
    print(f"  into {RAW}\n")
    ok = fail = 0
    for cc, code in IMF_CPI.items():
        try:
            rows = fetch("IMF", "CPI", code)
            save(f"imf_cpi_{cc}", rows, {"provider": "IMF", "dataset": "CPI", "code": code})
            print(f"  {cc:<4s}{len(rows):>7,} rows  {rows[0][0]} .. {rows[-1][0]}")
            ok += 1
        except (urllib.error.URLError, ValueError, KeyError) as exc:
            print(f"  {cc:<4s}FAILED  {type(exc).__name__}: {str(exc)[:60]}")
            fail += 1
        time.sleep(0.5)                 # a free service; do not hammer it
    print(f"\n  {ok} saved, {fail} failed. Run `python -m quantlab_world.build` to adopt them.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
