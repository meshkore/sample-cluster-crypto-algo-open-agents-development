"""THE CLOCK: what a person standing on day D could actually have known.

This is the whole product. Everything else in the package is storage and convenience; this
module is the reason the archive is worth building, because it is the only place in this
laboratory where "no peeking" stops being a convention somebody has to remember.

THE RULE, stated once: `asof(stream, D)` returns the last observation whose `known_at` is on
or before D. Not the last one whose reference date is on or before D - that is the leak, and
it is a leak that flatters a model enormously. March's CPI is a fact about March; it was a
fact nobody had until the tenth of April; a model that reads it on the thirty-first of March
is reading the future and will report an information coefficient to match.

WHY A BISECT IS SUFFICIENT
`known_at = ref_date + lag` with a lag constant per stream, so `known_at` is non-decreasing
wherever `ref_date` is, and the store writes rows ascending by reference date. That makes the
as-of lookup a binary search on a sorted column rather than a scan, which matters: a panel of
a hundred streams over three thousand days is three hundred thousand of these.

When a stream carries REAL release timestamps (`vintage == "observed"`), the same search runs
over those timestamps instead, and the answer is exact rather than conservative. The code path
is identical because the store already wrote the third column; only its meaning changes.
"""

from __future__ import annotations

import bisect

from . import store
from .streams import get


class SealedWindowError(RuntimeError):
    """Raised when a research reader asks for a day inside the sealed forward window."""


def guard(day: str, sealed: bool) -> None:
    """The 2026 lock, applied here so that crossing it is always an explicit argument.

    Four sealed readings have already been spent in this laboratory, three of them on edges
    whose year-to-year spread straddled break-even. The lock is not bureaucracy; it is the
    only thing that keeps the last honest measurement honest.
    """
    if not sealed and day[:10] >= store.LOCK_DAY:
        raise SealedWindowError(
            f"{day[:10]} is inside the sealed forward window (from {store.LOCK_DAY}). "
            "Pass sealed=True if this reading is deliberate - it will show up in the diff, "
            "which is the point.")


def asof(stream_id: str, day: str, *, sealed: bool = False,
         allow_stale: bool = False) -> float | None:
    """The stream's value as it was knowable at the close of `day`, or None.

    None is a real answer and is returned rather than a zero or the first available value.
    A model that cannot tell "flat" from "not yet published" learns that the world began
    when our data did.

    AND A READING EXPIRES. Carrying the last observation forward forever is what an as-of
    reader does by default, and it is wrong in a specific, measured way: FRED stopped
    mirroring Japan's inflation series in June 2021, so a 2026 evaluation would silently be
    fed a five-year-old number as though it were today's. Past `Stream.stale_after` the
    answer is None - the stream has nothing to say - unless the caller says otherwise.
    """
    guard(day, sealed)
    refs, vals, known = store.load(stream_id)
    i = bisect.bisect_right(known, day[:10]) - 1
    if i < 0:
        return None
    if not allow_stale and _age(known[i], day) > get(stream_id).stale_after:
        return None
    return vals[i]


def _age(known: str, day: str) -> int:
    from datetime import date
    return (date.fromisoformat(day[:10]) - date.fromisoformat(known[:10])).days


def window(stream_id: str, day: str, n: int, *, sealed: bool = False) -> list[float]:
    """The last `n` values knowable at `day`, oldest first. Shorter near the start of record.

    This is what every trailing statistic should be built from - a percentile, a rolling
    change, a z-score - because it is the only version of the trailing window that contains
    nothing the model could not have seen.
    """
    guard(day, sealed)
    refs, vals, known = store.load(stream_id)
    i = bisect.bisect_right(known, day[:10])
    return vals[max(0, i - n):i]


def history(stream_id: str, days: list[str], *, sealed: bool = False,
            allow_stale: bool = False) -> list[float | None]:
    """`asof` down a whole column of days, in one pass rather than one search per day.

    Same expiry rule as `asof`, which is what turns a discontinued series into an honest
    column of NaN that `Panel.drop_sparse` can remove, rather than a flat line a model will
    happily learn as a regime marker.
    """
    if days:
        guard(max(days), sealed)
    refs, vals, known = store.load(stream_id)
    limit = get(stream_id).stale_after

    # The day list may be neither sorted nor unique - system 09's feature matrix is grouped
    # by symbol, so its day column restarts at 2017 fourteen times. A single forward pointer
    # over such a list reads the wrong row after every group boundary and cannot go back.
    # Resolving the unique days once and scattering is both correct and faster.
    uniq = sorted({d[:10] for d in days})
    at: dict[str, float | None] = {}
    i = 0
    for d in uniq:
        while i < len(known) and known[i] <= d:
            i += 1
        if i == 0:
            at[d] = None
        elif not allow_stale and _age(known[i - 1], d) > limit:
            at[d] = None
        else:
            at[d] = vals[i - 1]
    return [at[d[:10]] for d in days]


def staleness(stream_id: str, day: str, *, sealed: bool = False) -> int | None:
    """How many days old the freshest knowable reading is.

    Worth exposing as a feature in its own right: a monthly series is three days stale just
    after a release and thirty-three days stale just before the next one, and "how long since
    the world last told us anything" is information about the world.
    """
    guard(day, sealed)
    refs, vals, known = store.load(stream_id)
    i = bisect.bisect_right(known, day[:10]) - 1
    if i < 0:
        return None
    from datetime import date
    return (date.fromisoformat(day[:10]) - date.fromisoformat(known[i])).days


def audit(stream_id: str) -> dict:
    """Prove the clock is doing something: how far each row's publication lags its subject."""
    stream = get(stream_id)
    refs, vals, known = store.load(stream_id)
    from datetime import date
    lags = [(date.fromisoformat(k) - date.fromisoformat(r)).days
            for r, k in zip(refs, known)]
    return {"id": stream_id, "vintage": stream.vintage, "declared_lag": stream.lag_days,
            "rows": len(refs), "min_lag": min(lags) if lags else None,
            "max_lag": max(lags) if lags else None,
            "first_knowable": known[0] if known else None,
            "revised_only": stream.revised}
