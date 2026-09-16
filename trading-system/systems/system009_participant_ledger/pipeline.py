"""One place that builds the tapes and runs the ledger, so the phases cannot drift apart.

The reconstruction is expensive - minutes - and everything downstream needs the same
trajectory: the features, the training set, the forward simulation and the frontend. Running
it from four call sites is how two phases end up quietly disagreeing about what the market
did, so there is exactly one function that does it and one cache that holds the answer.

WHAT IS CACHED, AND WHY IT IS NOT THE WHOLE RECONSTRUCTION

The first version pickled the `Reconstruction` object. That object holds every bucket twice -
once in `tapes`, once in the merged timeline - so the cache was fifty megabytes and took a
quarter of an hour to write, most of it spent serialising two hundred thousand dataclasses
that nothing downstream ever reads. What the later phases actually need is the trajectory and
four small facts about the run, so that is what `Context` carries and that is what is stored.

THE SEALED WINDOW IS AN ARGUMENT, NOT A DEFAULT. `research()` in the catalogue cannot serve
2026 at all; reaching the forward window takes `sealed=True`, which is visible in the diff and
at the call site, and this laboratory treats the reading it produces as spent once taken.
"""

from __future__ import annotations

import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import quantlab_catalog as cat
from quantlab_catalog.paths import indicator_dir

from . import buckets
from . import segments as SEG
from .boundary import Boundary, day_range
from .reconstruct import Reconstruction

#: The first day the record exists at all - Binance's first tape.
RECORD_START = "2017-08-17"
#: The last day of the research era. Everything at or after 2026-01-01 is the sealed window.
RESEARCH_END = "2025-12-31"
BUCKETS_PER_DAY = 6


@dataclass
class Context:
    """The small facts about a run that the later phases need, without the tape itself."""
    symbols: list[str] = field(default_factory=list)
    listings: dict[str, str] = field(default_factory=dict)
    ranks: dict[str, int] = field(default_factory=dict)
    #: Dollars that crossed per asset per day. Phase 3's capacity cap reads this, and it is
    #: three hundred thousand floats rather than two hundred thousand objects.
    day_dollars: dict[tuple[str, str], float] = field(default_factory=dict)
    fiat_ramped_by_year: dict[str, float] = field(default_factory=dict)
    segmentation: str = SEG.SEGMENTATION

    def funding(self) -> dict[str, list[dict]]:
        """Funding read fresh from the catalogue - it is small and never worth caching."""
        out = {}
        for sym in self.symbols:
            try:
                out[sym] = cat.funding(sym)
            except FileNotFoundError:
                pass
        return out


def _exclusive(day: str) -> str:
    d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def build_tapes(start: str = RECORD_START, end: str = RESEARCH_END, *,
                sealed: bool = False) -> dict[str, list]:
    """Dollar-volume buckets per symbol over [start, end], inclusive.

    With `sealed`, the 2026 forward store is appended to the research bars so the ledger can
    walk from the first day of the record straight through the sealed window without a seam.
    The bucket threshold is sized on the RESEARCH era only and then applied to both, because a
    threshold that had seen 2026 would make the forward buckets a different object from the
    ones the model was trained on.
    """
    syms = cat.load_universe()
    research = cat.research(syms)
    forward = cat.forward(syms) if sealed else {}
    out: dict[str, list] = {}
    for sym in syms:
        bars = buckets.window(research.get(sym, []), start, _exclusive(RESEARCH_END))
        threshold = buckets.sizing(bars, BUCKETS_PER_DAY) if bars else 0.0
        if sealed:
            bars = bars + buckets.window(forward.get(sym, []), "2026-01-01", _exclusive(end))
        if not bars or threshold <= 0:
            continue
        out[sym] = buckets.build(bars, threshold, symbol=sym)
    return out


def _daily_close(tapes: dict[str, list]) -> dict[str, dict[str, float]]:
    """The last bucket's price on each day, per symbol.

    The boundary needs it to turn a published free-float capitalisation back into units. It
    is the same price the ledger settles at, which is the point: the float it derives is then
    consistent with the book it is floating.
    """
    out: dict[str, dict[str, float]] = {}
    for sym, buckets in tapes.items():
        day_px: dict[str, float] = {}
        for b in buckets:
            day_px[b.day] = b.vwap
        out[sym] = day_px
    return out


def reconstruct(end: str = RESEARCH_END, *, sealed: bool = False, use_etf: bool = True,
                cache: bool = True, quiet: bool = False) -> tuple[Context, object]:
    """Run the ledger over the whole record and return `(context, trajectory)`."""
    key = (f"run_{end}_{'sealed' if sealed else 'research'}"
           f"_{'etf' if use_etf else 'noetf'}_{SEG.SEGMENTATION}.pkl")
    path = indicator_dir("system09") / key
    if cache and path.is_file():
        with path.open("rb") as fh:
            return pickle.load(fh)

    tapes = build_tapes(end=end, sealed=sealed)
    bnd = Boundary(day_range(RECORD_START, end),
                   {s: bk[0].day for s, bk in tapes.items()}, use_etf=use_etf,
                   daily_price=_daily_close(tapes))
    funding = {}
    for sym in tapes:
        try:
            funding[sym] = cat.funding(sym)
        except FileNotFoundError:
            pass
    t0 = time.time()
    rec = Reconstruction(tapes, boundary=bnd, funding=funding, check_daily=True)
    traj = rec.run(until=end)
    if not quiet:
        print(f"  reconstruction  {traj.buckets:,} buckets  {len(traj.days):,} days  "
              f"{time.time() - t0:6.1f}s  fill {traj.overall_fill:.4f}")

    ctx = Context(
        symbols=sorted(tapes), listings=dict(rec.listings), ranks=dict(rec.ranks),
        day_dollars={(s, b.day): 0.0 for s, bk in tapes.items() for b in bk},
        fiat_ramped_by_year=bnd.ramp_summary(), segmentation=SEG.SEGMENTATION)
    for s, bk in tapes.items():
        for b in bk:
            ctx.day_dollars[(s, b.day)] += b.dollars
    if cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump((ctx, traj), fh, protocol=pickle.HIGHEST_PROTOCOL)
    return ctx, traj
