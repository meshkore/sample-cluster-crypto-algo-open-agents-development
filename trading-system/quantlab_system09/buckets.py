"""L0's input: the tape, compressed to the sufficient statistics the ledger actually reads.

The design document's answer to "the whole tape is multi-terabyte" is that the ledger does
not need ticks, it needs CONSERVED FLOW PER BUCKET. That claim is what this module makes
concrete, and it is worth being precise about why so little survives the compression.

WHAT THE LEDGER READS, AND NOTHING ELSE
  volume         coins that changed hands - every one of them had a buyer and a seller
  taker_buy      of those, the coins bought by the AGGRESSOR
  taker_sell     volume - taker_buy, the coins sold by the aggressor
  vwap           the price at which the transfer happened

That is the entire interface. `taker_buy` is the field the whole project rests on: it
splits the tape into the side that demanded immediacy and the side that supplied it, and
without it there is no behaviour to attribute to anybody. It is already in this
laboratory's 15m candles, from 2017-08-17, which is why an MVP that looked like it needed
a terabyte of aggTrades needs nothing downloaded at all.

WHY VOLUME BUCKETS RATHER THAN CLOCK BARS
Clock bars over-sample dead hours and under-sample the minutes that matter. Bucketing by
dollar volume gives each bucket roughly equal economic content, which is the standard
choice in the literature and, here, has a second and more important consequence: the
cohort allocation is a decision taken once per bucket, so equal-volume buckets mean the
model spends its decisions where the market spent its money.

WHY BUCKETS STILL BREAK AT MIDNIGHT
Every boundary series this system has - stablecoin float, ETF creations, coin issuance -
is daily. A bucket that straddled midnight would have to attribute one day's mint to two
days' trading, so the day boundary wins and the last bucket of a day is short. The books
close daily; the tape does not, and where they disagree the books win.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class Bucket:
    """One unit of conserved flow. Every field is an observation, none is a model output."""
    t_start: datetime
    t_end: datetime
    day: str                    # UTC date of t_start; the key every boundary series uses
    volume: float               # coins traded
    taker_buy: float            # coins bought aggressively
    taker_sell: float           # coins sold aggressively
    vwap: float                 # dollars per coin
    high: float
    low: float
    close: float
    n_bars: int

    @property
    def dollars(self) -> float:
        return self.volume * self.vwap


def _typical(bar) -> float:
    return (bar.high + bar.low + bar.close) / 3.0


def build(bars, dollars_per_bucket: float) -> list[Bucket]:
    """Aggregate candles into dollar-volume buckets that never cross a UTC midnight.

    `dollars_per_bucket` is a resolution choice, not a fitted parameter; `sizing` below
    derives it from the tape so that the caller states a target bucket COUNT and the
    threshold follows.
    """
    out: list[Bucket] = []
    cur: list = []
    cur_dollars = 0.0
    cur_day: str | None = None

    def flush() -> None:
        nonlocal cur, cur_dollars, cur_day
        if not cur:
            return
        vol = sum(b.volume for b in cur)
        tb = sum(b.taker_buy_volume for b in cur)
        dollars = sum(b.volume * _typical(b) for b in cur)
        # A bucket with no volume has no price of its own; it inherits the last close,
        # which is the only honest answer and is why `volume == 0` buckets are kept at
        # all - dead time is information about who was NOT trading.
        vwap = (dollars / vol) if vol > 0 else cur[-1].close
        out.append(Bucket(
            t_start=cur[0].timestamp, t_end=cur[-1].timestamp, day=cur_day or "",
            volume=vol, taker_buy=tb, taker_sell=max(0.0, vol - tb), vwap=vwap,
            high=max(b.high for b in cur), low=min(b.low for b in cur),
            close=cur[-1].close, n_bars=len(cur)))
        cur, cur_dollars, cur_day = [], 0.0, None

    for bar in bars:
        day = bar.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
        if cur_day is not None and day != cur_day:
            flush()
        cur_day = day
        cur.append(bar)
        cur_dollars += bar.volume * _typical(bar)
        if cur_dollars >= dollars_per_bucket:
            flush()
    flush()
    return out


def sizing(bars, buckets_per_day: float = 8.0) -> float:
    """The dollar threshold that yields roughly `buckets_per_day` buckets on average.

    Stated as a count rather than a dollar figure because the dollar figure means
    different things in 2020 and in 2025, and a threshold fixed in dollars would quietly
    give the late years ten times the resolution of the early ones.
    """
    total = sum(b.volume * _typical(b) for b in bars)
    days = max(1, len({b.timestamp.strftime("%Y-%m-%d") for b in bars}))
    return total / (days * buckets_per_day)


def window(bars, start: str | None = None, end: str | None = None):
    """Bars within [start, end), both UTC dates. The lab's 2026 lock lives in the catalogue."""
    lo = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) if start else None
    hi = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) if end else None
    return [b for b in bars
            if (lo is None or b.timestamp >= lo) and (hi is None or b.timestamp < hi)]
