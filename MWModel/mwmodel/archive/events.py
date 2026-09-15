"""THE CHRONICLE: what happened, in order, with the day it became known.

The operator's phrase for the whole archive was *"un almacén de datos de todas las noticias
del pasado ordenadas por orden cronológico"*. This is that record. It is built in three tiers,
cheapest and most reliable first, so that each one is useful before the next exists:

  TIER 1  the curated chronicle - THIS FILE. A few hundred hand-written, source-linked
          events: the bans, the hacks, the halvings, the bankruptcies, the approvals. Small,
          exact, no licensing question, and enough on its own to answer the question this lab
          has never been able to answer - "was that drawdown a regime break or a Tuesday?".
          It is editorial, so it is committed to git, unlike every other datum here.
  TIER 2  machine feeds - GDELT 2.0 tone and volume by country and theme (free, 2015 on) and
          Wikipedia pageviews as an attention proxy. These arrive as JSONL under the store
          and reduce to ordinary streams, which is the form a model wants anyway.
  TIER 3  full text, only from sources whose terms permit storage, and only if the first two
          prove insufficient. The record has `body` and `url` for it; nothing depends on it.

NEWS IS THE ONE THING WHOSE CLOCK IS EXACT. Every other series in this archive has a
publication lag we estimate. A news item's publication timestamp IS its known_at, measured to
the minute. That makes the chronicle the most trustworthy column in the store and the natural
anchor for checking the others.

ON ACCURACY: entries carry `verified`. True means the date has been checked against a primary
source. False means it was written from memory and is a candidate for correction - it is
still stored, because a dated candidate is more useful than a silence, but `strict()` filters
them out for any measurement that matters.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import store

CATEGORIES = ("regulation", "enforcement", "security_incident", "insolvency", "protocol",
              "macro", "adoption", "market_structure", "product")


@dataclass(frozen=True)
class Event:
    ref_ts: str                   # when it happened, ISO date or datetime
    headline: str
    category: str
    jurisdiction: str = "global"
    entities: tuple[str, ...] = ()
    weight: float = 0.5           # 0-1, how much the archive believes it mattered
    known_at: str = ""            # defaults to ref_ts: news is knowable when published
    source: str = ""
    url: str = ""
    body: str = ""
    verified: bool = False

    @property
    def event_id(self) -> str:
        return hashlib.sha256(
            f"{self.ref_ts}|{self.headline}".encode()).hexdigest()[:16]

    @property
    def knowable(self) -> str:
        return (self.known_at or self.ref_ts)[:10]


def E(ref, headline, cat, juris="global", w=0.5, ents=(), verified=True) -> Event:
    return Event(ref_ts=ref, headline=headline, category=cat, jurisdiction=juris,
                 weight=w, entities=tuple(ents), verified=verified)


#: TIER 1. Ordered by date. Weight is editorial and deliberately coarse: 1.0 is an event that
#: redefined the market's structure, 0.8 one that moved it for months, 0.5 one that moved it
#: for days. The weights exist to be argued with in a diff.
CHRONICLE: tuple[Event, ...] = (
    E("2013-12-05", "PBoC bars Chinese banks from handling bitcoin", "regulation", "CN", 0.8,
      ("BTC",)),
    E("2014-02-24", "Mt. Gox halts withdrawals and collapses; ~850,000 BTC missing",
      "insolvency", "JP", 1.0, ("BTC",)),
    E("2016-08-02", "Bitfinex hacked; 119,756 BTC stolen", "security_incident", "offshore",
      0.8, ("BTC",)),
    E("2017-07-25", "SEC's DAO report: some tokens are securities", "regulation", "US", 0.7),
    E("2017-09-04", "China bans initial coin offerings", "regulation", "CN", 0.9),
    E("2017-09-15", "China orders domestic exchanges to close", "regulation", "CN", 1.0),
    E("2017-12-10", "CBOE launches bitcoin futures", "market_structure", "US", 0.7, ("BTC",)),
    E("2017-12-18", "CME launches bitcoin futures; the cycle tops days later",
      "market_structure", "US", 0.9, ("BTC",)),
    E("2018-01-26", "Coincheck hacked; ~$530m of NEM stolen", "security_incident", "JP", 0.7),
    E("2018-01-30", "Facebook bans cryptocurrency advertising", "regulation", "US", 0.5),
    E("2018-03-14", "Google bans cryptocurrency advertising", "regulation", "US", 0.5),
    E("2019-06-18", "Facebook announces Libra; global regulators respond", "adoption",
      "global", 0.6),
    E("2020-03-12", "COVID crash: bitcoin falls ~50% in a day alongside every risk asset",
      "macro", "global", 1.0, ("BTC",)),
    E("2020-03-23", "Federal Reserve announces unlimited asset purchases", "macro", "US",
      1.0),
    E("2020-05-11", "Third bitcoin halving: issuance falls to 6.25 BTC per block",
      "protocol", "global", 0.8, ("BTC",)),
    E("2020-08-11", "MicroStrategy makes its first bitcoin purchase", "adoption", "US", 0.7,
      ("BTC",)),
    E("2020-10-21", "PayPal opens crypto buying to US users", "adoption", "US", 0.6),
    E("2021-02-08", "Tesla discloses a $1.5bn bitcoin position", "adoption", "US", 0.9,
      ("BTC",)),
    E("2021-04-14", "Coinbase lists directly on Nasdaq; the cycle's first top follows",
      "market_structure", "US", 0.8),
    E("2021-05-12", "Tesla suspends bitcoin payments on energy grounds", "adoption", "US",
      0.8, ("BTC",)),
    E("2021-05-21", "China's State Council orders a crackdown on mining and trading",
      "regulation", "CN", 1.0, ("BTC",)),
    E("2021-06-18", "Sichuan orders mining shut down; hash rate falls by half", "regulation",
      "CN", 0.9, ("BTC",)),
    E("2021-09-07", "El Salvador makes bitcoin legal tender", "adoption", "global", 0.7,
      ("BTC",)),
    E("2021-09-24", "PBoC declares all cryptocurrency transactions illegal", "regulation",
      "CN", 1.0),
    E("2021-10-19", "ProShares BITO, the first US bitcoin futures ETF, begins trading",
      "product", "US", 0.7, ("BTC",)),
    E("2021-11-10", "Cycle high near $69,000; the bear market begins", "market_structure",
      "global", 1.0, ("BTC",)),
    E("2022-05-09", "TerraUSD loses its peg; ~$40bn of value destroyed in a week",
      "insolvency", "global", 1.0, ("LUNA", "UST")),
    E("2022-06-12", "Celsius halts withdrawals", "insolvency", "US", 0.9),
    E("2022-07-01", "Three Arrows Capital files for bankruptcy protection", "insolvency",
      "offshore", 0.9),
    E("2022-09-15", "Ethereum's Merge: proof of work ends", "protocol", "global", 0.9,
      ("ETH",)),
    E("2022-11-08", "FTX halts withdrawals; Binance signs and abandons a letter of intent",
      "insolvency", "offshore", 1.0),
    E("2022-11-11", "FTX files for Chapter 11", "insolvency", "US", 1.0),
    E("2023-03-10", "Silicon Valley Bank fails", "macro", "US", 0.9),
    E("2023-03-11", "USDC breaks its peg over SVB exposure; bitcoin rallies as a hedge",
      "macro", "US", 0.9, ("USDC", "BTC")),
    E("2023-06-05", "SEC sues Binance", "enforcement", "US", 0.9),
    E("2023-06-06", "SEC sues Coinbase", "enforcement", "US", 0.9),
    E("2023-06-15", "BlackRock files for a spot bitcoin ETF", "product", "US", 1.0, ("BTC",)),
    E("2023-08-29", "Grayscale wins its appeal against the SEC", "enforcement", "US", 0.8,
      ("BTC",)),
    E("2023-11-21", "Binance and its founder settle with the US Department of Justice",
      "enforcement", "US", 0.8),
    E("2024-01-10", "SEC approves eleven spot bitcoin ETFs", "product", "US", 1.0, ("BTC",)),
    E("2024-01-11", "Spot bitcoin ETFs begin trading", "product", "US", 1.0, ("BTC",)),
    E("2024-04-19", "Fourth bitcoin halving: issuance falls to 3.125 BTC per block",
      "protocol", "global", 0.8, ("BTC",)),
    E("2024-05-23", "SEC approves spot ether ETF filings", "product", "US", 0.8, ("ETH",)),
    E("2024-07-23", "Spot ether ETFs begin trading", "product", "US", 0.7, ("ETH",)),
    E("2024-11-05", "US presidential election; the market prices a friendlier regime",
      "macro", "US", 1.0),
    E("2025-01-17", "A presidential memecoin launches days before the inauguration",
      "market_structure", "US", 0.7, (), False),
    E("2025-01-20", "US presidential inauguration", "macro", "US", 0.8, (), True),
    E("2025-03-06", "Executive order establishing a Strategic Bitcoin Reserve", "regulation",
      "US", 0.9, ("BTC",), False),
    E("2025-04-02", "Sweeping US tariffs announced; risk assets sell off", "macro", "US",
      0.9, (), False),
    E("2025-07-18", "The GENIUS Act, a US stablecoin framework, is signed into law",
      "regulation", "US", 0.8, ("USDC", "USDT"), False),
)


def strict() -> tuple[Event, ...]:
    """Only the entries whose date has been checked against a primary source."""
    return tuple(e for e in CHRONICLE if e.verified)


def between(since: str, until: str, *, category: str | None = None,
            jurisdiction: str | None = None, verified_only: bool = False,
            include_feeds: bool = True) -> list[Event]:
    """Everything knowable in `[since, until]`, chronological.

    The filter is on `knowable`, not on when it happened, for the same reason everything else
    in this package filters on `known_at`: a leaked news item is as damaging as a leaked
    number and considerably easier to write by accident.
    """
    rows = list(strict() if verified_only else CHRONICLE)
    if include_feeds:
        rows.extend(_feed_events(since, until))
    out = [e for e in rows if since[:10] <= e.knowable <= until[:10]
           and (category is None or e.category == category)
           and (jurisdiction is None or e.jurisdiction == jurisdiction)]
    return sorted(out, key=lambda e: (e.knowable, e.headline))


def _feed_events(since: str, until: str) -> list[Event]:
    """TIER 2/3: whatever an ingest run has written into the store. Empty until one has."""
    out: list[Event] = []
    if not store.EVENTS_DIR.is_dir():
        return out
    for year in range(int(since[:4]), int(until[:4]) + 1):
        p = store.EVENTS_DIR / f"{year}.jsonl"
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(Event(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue          # a malformed line is a defect in one row, not in the archive
    return out


def append(events: list[Event]) -> int:
    """Write feed events into the store, one file per year, deduplicated by event id."""
    store.EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, list[Event]] = {}
    for e in events:
        by_year.setdefault(e.knowable[:4], []).append(e)
    written = 0
    for year, rows in by_year.items():
        p = store.EVENTS_DIR / f"{year}.jsonl"
        seen = {e.event_id for e in _feed_events(f"{year}-01-01", f"{year}-12-31")}
        with p.open("a", encoding="utf-8") as fh:
            for e in sorted(rows, key=lambda x: x.knowable):
                if e.event_id in seen:
                    continue
                fh.write(json.dumps(asdict(e), separators=(",", ":")) + "\n")
                written += 1
    return written


def pressure(days: list[str], halflife: int = 30, **filters) -> list[float]:
    """The chronicle as a STREAM: decaying weighted event intensity per day.

    This is how text is supposed to reach a model - as a number with a clock, not as a string.
    Each event contributes its weight from the day it became knowable, decaying with a
    half-life, so "the market is in the middle of a regulatory episode" becomes a feature
    rather than a story told afterwards.
    """
    import math
    from datetime import date, timedelta
    if not days:
        return []
    # Events BEFORE the window are most of the signal - an episode that began three weeks ago
    # is precisely what "pressure" is meant to express - so the query reaches back six
    # half-lives, which is where the decay has fallen below two percent.
    reach = (date.fromisoformat(days[0][:10]) - timedelta(days=halflife * 6)).isoformat()
    rows = between(reach, days[-1], **filters)
    stamps = [(e.knowable, e.weight) for e in rows]
    lam = math.log(2) / max(1, halflife)
    out = []
    from datetime import date
    for d in days:
        today = date.fromisoformat(d[:10])
        total = 0.0
        for k, w in stamps:
            age = (today - date.fromisoformat(k)).days
            if 0 <= age <= halflife * 6:
                total += w * math.exp(-lam * age)
        out.append(total)
    return out
