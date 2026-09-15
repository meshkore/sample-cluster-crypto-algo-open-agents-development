"""`python -m quantlab_world.inventory` - what is here, what is missing, and how late it is.

Three tables, and the third is the one nobody else prints:

    COVERAGE     rows, first observation and earliest date, by category and by region
    CLOCK        the declared publication lag of every stream, and whether it was measured,
                 estimated from the release cadence, or zero by nature
    GAPS         registered streams with no data, regions with no inflation series, decades
                 with no coverage - the shape of what we do not have

The third table exists because of a specific failure: a catalogue that lets you believe in
data it does not have is worse than no catalogue. Absence has to be as visible as presence or
it gets discovered halfway through a result.
"""

from __future__ import annotations

import sys

from . import coverage, store
from .streams import REGIONS, get, registry


def main(argv: list[str] | None = None) -> int:
    cov = coverage()
    reg = registry()
    entries = store.read_manifest().get("streams", {})

    print("THE WORLD ARCHIVE - inventory")
    print(f"  {cov['streams_registered']} streams registered, {cov['streams_built']} built, "
          f"last build {cov['built_at'] or 'never'}\n")

    print("  COVERAGE BY CATEGORY")
    print(f"    {'category':<20s}{'built/reg':>12s}{'rows':>12s}{'earliest':>12s}")
    for name, s in sorted(cov["by_category"].items()):
        print(f"    {name:<20s}{s['built']:>5d}/{s['registered']:<6d}{s['rows']:>12,}"
              f"{str(s['earliest'] or '-'):>12s}")

    print("\n  COVERAGE BY REGION  (an investor's world is regional; one global CPI is not)")
    print(f"    {'region':<10s}{'built/reg':>12s}{'rows':>12s}{'earliest':>12s}")
    for name in REGIONS:
        s = cov["by_region"].get(name)
        if not s:
            continue
        print(f"    {name:<10s}{s['built']:>5d}/{s['registered']:<6d}{s['rows']:>12,}"
              f"{str(s['earliest'] or '-'):>12s}")

    print("\n  THE CLOCK  (how late each kind of number arrives)")
    buckets: dict[str, list[int]] = {}
    for sid, s in reg.items():
        buckets.setdefault(s.vintage, []).append(s.lag_days)
    for mode in ("observed", "estimated", "assumed"):
        lags = buckets.get(mode, [])
        if not lags:
            continue
        print(f"    {mode:<12s}{len(lags):>4d} streams   lag "
              f"{min(lags)}-{max(lags)} days")
    worst = sorted(((s.lag_days, sid) for sid, s in reg.items()), reverse=True)[:5]
    print("    latest arrivals: " + ", ".join(f"{sid} ({lag}d)" for lag, sid in worst))

    print("\n  STALE  (an expired reading says NOTHING; its column is NaN, not a flat line)")
    from datetime import date
    today = date.today()
    stale = []
    for sid, e in entries.items():
        last = e.get("last")
        if not last:
            continue
        # Age is measured from when the reading became KNOWABLE, exactly as the clock does.
        age = (today - date.fromisoformat(get(sid).known_at(last))).days
        limit = get(sid).stale_after
        if age > limit:
            stale.append((age, sid, last, limit))
    if stale:
        print(f"    {len(stale)} of {len(entries)} streams have expired as of today:")
        for age, sid, last, limit in sorted(stale, reverse=True)[:12]:
            print(f"      {sid:<24s}last {last}   {age:>5d}d old   (expires at {limit}d)")
    else:
        print("    none - every built stream still has something current to say")

    print("\n  GAPS")
    missing = cov.get("missing", {})
    if missing:
        print(f"    {len(missing)} registered streams have no harvested source:")
        for sid in sorted(missing)[:10]:
            print(f"      {sid}")
    regions_with_cpi = {get(sid).region for sid in reg
                        if get(sid).category == "inflation" and sid in entries}
    absent = [r for r in REGIONS if r not in regions_with_cpi
              and r not in ("global", "offshore", "DE", "CH")]
    if absent:
        print(f"    no inflation series for: {', '.join(absent)}")
    if not any(get(sid).category in ("attention", "regulation", "security_incident")
               and sid in entries for sid in reg):
        print("    no news-derived streams yet - the chronicle is tier 1 only "
              "(see events.py); GDELT tone and Wikipedia attention are the next ingest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
