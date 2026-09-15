"""Fetch the non-crypto reference series into the shared catalogue.

WHY THIS FILE EXISTS AT ALL

`reference.py` reads `reference_markets.json` and `external.py` serves it, but the code
that PRODUCED it was never in this tree - the bundle arrived from a job nobody could see.
A catalogue whose contents cannot be regenerated from the repository is not a catalogue, it
is an artefact somebody happens to have. This is the missing half, and it is deliberately a
separate command: nothing in the laboratory downloads as a side effect of a backtest.

WHY THESE SERIES

System 08's counterparty is named and it is specific: leveraged, momentum-chasing retail
crypto flow (Kogan, Makarov, Niessner & Schoar, JFE 2024), amplified by copy-trading
platforms that measurably raise risk taking. A counterparty that is LEVERAGED is fragile to
exactly two things - the price of money and the willingness of anyone to lend it - and both
are observable daily, for free, outside crypto.

So the additions are not a grab bag. They are the instruments that measure that fragility:

  liquidity      WALCL (Fed balance sheet), WM2NS (M2), RRPONTSYD (reverse repo). Crypto
                 cycles have tracked global liquidity more visibly than any fundamental,
                 and these are the series that define it.
  credit stress  BAMLH0A0HYM2 (high-yield spread) and BAMLC0A0CM (investment grade). The
                 bundle already held the first, but only from 2023 - FRED carries it from
                 1996, and three years of a credit series cannot see a credit cycle.
  conditions     NFCI and STLFSI4, two published composite measures of financial
                 conditions, which exist precisely so nobody has to build their own.
  policy         DFF, the effective funds rate: the price of the leverage our counterparty
                 is using.

FOUR THINGS THIS DOES NOT DO, AND EACH IS A RULE RATHER THAN AN OMISSION

  * It does not apply the publication lag. Series are stored raw with their timestamps
    untouched; applying the delay is the consumer's job and the measured delays live in
    `quantlab_system06.reference.SERIES_LAG_DAYS`. A series lagged at fetch time is a
    series nobody can re-lag correctly later.
  * It does not revise. FRED's fredgraph endpoint returns the CURRENT vintage, which for a
    revised series is not what was knowable at the time. Every series here is chosen to be
    non-revised or effectively so - rates, spreads, indices - and the ones that revise
    heavily are left out on purpose.
  * It does not overwrite on failure. A partial download must never replace a good bundle,
    so the merge is additive and the write happens once, at the end.
  * It does not need an API key, an account or a secret. Nothing in this laboratory stores
    an exchange or vendor credential, and this file does not become the exception.

Run it deliberately:
    PYTHONPATH=trading-system python -m quantlab_catalog.fetch_reference
    PYTHONPATH=trading-system python -m quantlab_catalog.fetch_reference --only WALCL NFCI
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .paths import external_file

# The observation window must be forced. fredgraph defaults to the series' own GRAPH
# window, which for the BAML credit spreads is the last three years - and three years of a
# credit series cannot see a credit cycle, which is the entire reason we fetch them.
FREDGRAPH = ("https://fred.stlouisfed.org/graph/fredgraph.csv"
             "?id={sid}&cosd=1900-01-01&coed=2099-12-31")

# id -> what it measures and why this design cares. The note is stored alongside the rows,
# because a series id with no explanation is a column nobody dares delete and nobody uses.
SERIES: dict[str, str] = {
    # --- already in the bundle; refetched so the history is full rather than recent.
    "DGS2": "2-year Treasury yield - the short end, the price of money",
    "DGS10": "10-year Treasury yield",
    "T10Y2Y": "10y-2y slope - the classic cycle signal",
    "VIXCLS": "VIX - equity implied volatility, the reference risk gauge",
    "NASDAQCOM": "Nasdaq Composite - the risk asset crypto is most often compared to",
    "SP500": "S&P 500",
    "DCOILWTICO": "WTI crude - the commodity leg",
    "DTWEXBGS": "Broad trade-weighted dollar - crypto is quoted against it",
    "DEXUSEU": "USD/EUR",
    # --- credit stress. MEASURED LIMITATION, not a bug of ours: FRED serves the ICE BofA
    # indices only about three years back without a licence, and forcing the observation
    # window with cosd does not widen it - the endpoint returns 2023 onward either way.
    # Three years cannot see a credit cycle, so anything built on these must say so, and
    # a longer history needs a different source rather than a different URL.
    "BAMLH0A0HYM2": "High-yield OAS - credit stress, the leveraged holder's oxygen",
    "BAMLC0A0CM": "Investment-grade OAS - the same signal one rung up the quality ladder",
    # --- liquidity. The series crypto cycles have tracked most visibly.
    "WALCL": "Fed balance sheet total assets - weekly, the liquidity tide",
    "WM2NS": "M2 money stock - weekly",
    "RRPONTSYD": "Overnight reverse repo - liquidity parked rather than deployed",
    # --- published composite financial conditions, so we do not build our own.
    "NFCI": "Chicago Fed National Financial Conditions Index - weekly",
    "STLFSI4": "St Louis Fed Financial Stress Index - weekly",
    # --- the policy rate itself: what our leveraged counterparty pays to stay leveraged.
    "DFF": "Effective federal funds rate - daily",

    # --- credit stress with a HISTORY. Measured 2026-09-15: FRED serves only the last three
    # years of BAMLH0A0HYM2 - ICE BofA licence terms, not a bug and not fixable by asking
    # differently - so the high-yield spread covers a third of our record and cannot see a
    # credit cycle. These two can, and they are free of that restriction.
    "BAA10Y": "Moody's Baa corporate yield minus the 10-year Treasury - forty years of the "
              "same channel the high-yield spread measures, without the licence window",
    "STLFSI4": "St. Louis Fed financial stress index - weekly, 1993 on, a composite of "
               "eighteen series designed for exactly this question",

    # --- INFLATION BY REGION, and the real rates that follow from it. The operator's point,
    # 2026-09-15: a holder in Frankfurt, one in Shanghai and one in Sao Paulo do not face the
    # same decision. Crypto's boundary - the money entering the sector - is where that shows
    # up, because the choice being made is always "this, or the alternative available to ME".
    # An investor with 5% real rates at home and one with negative real rates are not the
    # same buyer, and one global CPI cannot express it.
    "CPIAUCSL": "US CPI, all items - monthly",
    "CPILFESL": "US core CPI - monthly",
    "CP0000EZ19M086NEST": "Euro area HICP, all items - monthly",
    "CHNCPIALLMINMEI": "China CPI, all items - monthly",
    "JPNCPIALLMINMEI": "Japan CPI, all items - monthly",
    "INDCPIALLMINMEI": "India CPI, all items - monthly",
    "BRACPIALLMINMEI": "Brazil CPI, all items - monthly",
    "GBRCPIALLMINMEI": "UK CPI, all items - monthly",
    "TURCPIALLMINMEI": "Turkey CPI - the high-inflation case, where crypto adoption is a "
                       "currency decision rather than an investment one",
    "ARGCPIALLMINMEI": "Argentina CPI - the same, further along",
    "ZAFCPIALLMINMEI": "South Africa CPI - the African proxy the free sources actually carry",

    # --- regional money and rates, so the real rate can be computed per region.
    "ECBDFR": "ECB deposit facility rate",
    "IRLTLT01JPM156N": "Japan 10-year government bond yield",
    "IRLTLT01GBM156N": "UK 10-year government bond yield",
    "INTDSRCNM193N": "China discount rate",

    # --- regional currencies. A dollar-priced asset is a different proposition to someone
    # whose income is in a currency that is falling against it.
    "DEXCHUS": "USD/CNY", "DEXJPUS": "USD/JPY", "DEXUSUK": "GBP/USD",
    "DEXBZUS": "USD/BRL", "DEXINUS": "USD/INR", "DEXSFUS": "USD/ZAR",

    # --- regional equity, as the local risk appetite the crypto bid competes with.
    "NIKKEI225": "Nikkei 225",
}

TIMEOUT = 45


def fetch_series(sid: str) -> list[list]:
    """One series as [[date, value], ...], ascending, with missing points DROPPED.

    FRED writes "." for a missing observation. Dropping rather than forward-filling is
    deliberate: a forward fill invents an observation on a day the series did not print,
    and a consumer that wants one can do it knowingly.
    """
    url = FREDGRAPH.format(sid=sid)
    req = urllib.request.Request(url, headers={"User-Agent": "quantlab-catalog/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    rows: list[list] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or len(header) < 2:
        raise ValueError(f"{sid}: unexpected CSV header {header!r}")
    for row in reader:
        if len(row) < 2:
            continue
        day, raw = row[0].strip(), row[1].strip()
        if not day or raw in (".", "", "NA"):
            continue
        try:
            rows.append([day, float(raw)])
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"{sid}: no usable observations")
    rows.sort(key=lambda r: r[0])
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", default=None,
                        help="fetch just these series ids")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and report, but do not write the bundle")
    args = parser.parse_args(argv)

    path = external_file("reference_markets.json")
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bundle = {}
    if not isinstance(bundle, dict):
        bundle = {}

    wanted = args.only or list(SERIES)
    fetched, failed = {}, {}
    for sid in wanted:
        try:
            rows = fetch_series(sid)
        except (urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
            failed[sid] = str(exc)[:120]
            print(f"  {sid:<14} FAILED  {failed[sid]}", flush=True)
            continue
        fetched[sid] = rows
        had = len((bundle.get(sid) or {}).get("rows") or [])
        print(f"  {sid:<14} {len(rows):>6} rows  {rows[0][0]} .. {rows[-1][0]}"
              f"   (was {had})", flush=True)

    if args.dry_run:
        print(f"\ndry run: {len(fetched)} fetched, {len(failed)} failed, nothing written")
        return 0 if fetched else 1

    # Additive merge, written once. A partial download must never replace a good bundle,
    # so a series that failed keeps whatever was already on disk.
    for sid, rows in fetched.items():
        prev = bundle.get(sid) or {}
        bundle[sid] = {
            "id": sid,
            "title": SERIES.get(sid, prev.get("title", "")),
            "rows": rows,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": FREDGRAPH.format(sid=sid),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=1), encoding="utf-8")

    total = sum(len(v.get("rows") or []) for v in bundle.values() if isinstance(v, dict))
    print(f"\nwrote {path}")
    print(f"{len(bundle)} series, {total:,} observations, {len(failed)} failed")
    if failed:
        print("failed, and their previous contents were left untouched:")
        for sid, why in failed.items():
            print(f"  {sid}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
