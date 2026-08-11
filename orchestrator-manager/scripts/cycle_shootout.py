"""How long is a bull market? Dating the cycle instead of reading the tape.

The detector produced 74 episodes in 8.4 years -- a median of 28 days, 89% of
them under three months, the longest 136 days. Every published dating of the
same period finds six to ten phases: Coinbase's COIN50 200DMA chart shows eight
blocks across 2021-2025, and the Bitcoin halving cycles run 12-month bulls,
13-month bears and 22-month recoveries. A twenty-day bounce inside a fall is not
a bull market, and a detector that says it is will route the trading module
through six different opinions in a quarter.

WHAT THE RIGHT TOOL IS CALLED. Not Fourier -- that decomposes a periodic signal
and a market cycle is not periodic. The standard instrument is a TURNING-POINT
DATING ALGORITHM (Bry-Boschan 1971; Pagan & Sossounov 2003 for bull/bear
equity markets), and it is built from two ideas, both of which the current
detector lacks:

  * A SWING THRESHOLD. A bear market is a fall of x% from the peak, not a
    close below an average. This is the definition every published chart uses.
  * A MINIMUM PHASE DURATION. A phase shorter than n months is censored and
    absorbed into its neighbour. This is the part that kills the churn.

Pagan & Sossounov use an 8-month window for extrema, a 4-month minimum phase
and a 16-month minimum cycle. Those are equity numbers; crypto is faster and
the point of this script is to measure what this market wants instead of
importing them.

THE CAUSALITY PROBLEM, and it is the whole reason this is not just the textbook
algorithm. Bry-Boschan is RETROSPECTIVE: it finds a peak by looking at the bars
after it, which is exactly the lookahead this laboratory refuses. Every
consensus chart in the literature is drawn with hindsight.

A live detector cannot do that, so what is measured here is the CAUSAL cousin:

    running peak and trough, updated bar by bar
    BEAR when the composite is `bear_swing` below the running peak
    BULL when it is `bull_swing` above the running trough
    and no state change permitted before `minimum_phase` bars have passed

Every term reads only bars that have closed. It will always be later than the
retrospective dating -- that is the honest price of not cheating -- and the
question this script answers is how much later, and whether the phases it finds
are the right SHAPE.

One old objection, answered. `regime.py` records that a drawdown-from-high rule
was tried and rejected because it "stays true through every recovery" and
labelled the 2020 and 2023 rebounds as bear markets. That was true of a rule
with no way BACK: measuring only the fall from the peak, nothing ever ends a
bear. The symmetric rise-from-trough test is what fixes it, and it is why this
is not the same mechanism wearing a new name.

    python3 orchestrator-manager/scripts/cycle_shootout.py
"""

from __future__ import annotations

import sys
from statistics import median

from detector_diagnosis import trailing_average
from market_shootout import breadth, composite, load_all, turnover_averages
from quantlab_trading.regime import MarketDetector, MarketRegime, RegimeParameters

# Published datings of this period, for shape rather than for scoring. These are
# read off Coinbase's COIN50 200DMA chart and the Bitcoin halving-cycle chart the
# operator supplied; they are drawn with hindsight and are not a target to fit,
# only a sanity check on the ORDER OF MAGNITUDE of a phase.
CONSENSUS = "8 phases across 2021-2025 (COIN50) · 12-13 month bull and bear phases (BTC halving cycles)"


def cycle_labels(level, swing_down, swing_up, minimum_phase):
    """Causal turning-point dating. One pass, no bar read before it closes.

    `peak` and `trough` are running extremes SINCE THE LAST STATE CHANGE, not
    since the beginning: a bear that ends must forget the old high or the next
    bull is measured against a peak two years stale and can never start.
    """
    labels = []
    state = MarketRegime.UNKNOWN
    peak = trough = level[0]
    held = 0
    for value in level:
        peak = max(peak, value)
        trough = min(trough, value)
        held += 1
        fell = 1 - value / peak if peak else 0.0
        rose = value / trough - 1 if trough else 0.0
        want = state
        if state is not MarketRegime.BEAR and fell >= swing_down:
            want = MarketRegime.BEAR
        elif state is not MarketRegime.BULL and rose >= swing_up:
            want = MarketRegime.BULL
        # A phase shorter than the minimum is not a phase. This is the censoring
        # rule, and it is the single term that separates a cycle from a wiggle.
        if want is not state and (
            held >= minimum_phase or state is MarketRegime.UNKNOWN
        ):
            state = want
            held = 0
            peak = trough = value
        labels.append(state)
    return labels


def episodes_of(labels, stamps):
    out, start = [], 0
    for i, label in enumerate(labels):
        last = i == len(labels) - 1
        if not (last or labels[i + 1] is not label):
            continue
        out.append((label, stamps[start], stamps[i], i - start + 1))
        start = i + 1
    return [e for e in out if e[0] is not MarketRegime.UNKNOWN]


def describe(name, episodes, years):
    if not episodes:
        print(f"  {name:<34} no phases")
        return
    lengths = [e[3] for e in episodes]
    print(
        f"  {name:<34} {len(episodes):>3} phases · {len(episodes) / years:>4.1f}/yr · "
        f"median {median(lengths):>4.0f}d · longest {max(lengths):>4}d · "
        f"under 90d {sum(1 for x in lengths if x < 90) / len(lengths):>4.0%}"
    )


VARIANTS = (
    # (name, smoothing, swing down, swing up, minimum phase in bars)
    #
    # The first pass used 20%/20% and a 120-bar floor and produced phases that
    # were EXACTLY 120 bars long over and over -- the floor holding a mechanism
    # that wanted to flip constantly, which is a censored wiggle and not a
    # cycle. It also dated 2020-09 to 2021-01 as a BEAR, which is the opening
    # of the largest bull run in the sample.
    #
    # The cause is that 20% is an equity-market number. A 20% bounce off the low
    # of a crypto bear happens several times inside every one of them, so the
    # rise-from-trough test fires on noise. This grid is mostly about finding
    # what this market's number is.
    ("smooth 30 · swing 20/20 · 120d", 30, 0.20, 0.20, 120),
    ("smooth 30 · swing 30/40 · 120d", 30, 0.30, 0.40, 120),
    ("smooth 30 · swing 35/50 · 120d", 30, 0.35, 0.50, 120),
    ("smooth 60 · swing 30/40 · 120d", 60, 0.30, 0.40, 120),
    ("smooth 60 · swing 35/50 · 150d", 60, 0.35, 0.50, 150),
    ("smooth 60 · swing 40/60 · 150d", 60, 0.40, 0.60, 150),
    ("smooth 90 · swing 35/50 · 150d", 90, 0.35, 0.50, 150),
    ("smooth 90 · swing 40/60 · 180d", 90, 0.40, 0.60, 180),
    ("smooth 90 · swing 50/80 · 180d", 90, 0.50, 0.80, 180),
)


def forward_by_label(labels, level, horizon):
    """Mean forward return of the composite under each label.

    A CYCLE detector is judged over months, not over twenty bars: its claim is
    about the phase, and a phase it is right about for a fortnight and wrong
    about for a quarter is not useful to anything downstream.
    """
    buckets: dict[str, list[float]] = {}
    for i, label in enumerate(labels):
        target = i + horizon
        if target >= len(level) or not level[i]:
            continue
        buckets.setdefault(label.value, []).append(level[target] / level[i] - 1)
    return {k: sum(v) / len(v) for k, v in buckets.items() if v}


def main() -> int:
    print("loading…", flush=True)
    market = load_all()
    stamps = sorted({s for series in market.values() for s in series})
    turnover = turnover_averages(market)
    broad = composite(market, stamps, "equal", turnover)
    years = (stamps[-1] - stamps[0]).days / 365.25

    print(f"\n{len(market)} assets · {len(stamps)} bars · {years:.1f} years")
    print(f"consensus for shape: {CONSENSUS}\n")

    # The incumbent, for the contrast.
    wide = breadth(market, stamps, 50)
    detector = MarketDetector(RegimeParameters())
    for stamp, value, share in zip(stamps, broad, wide):
        detector._level = value
        detector.stamps.append(stamp)
        detector.index.append(value)
        detector.breadth.append(share)
        detector._high = max(detector._high, value)
        detector._advance_average()
        detector._apply_hysteresis(detector._classify(share))
        detector.labels.append(detector.regime)
    print("THE DETECTOR AS IT SHIPS TODAY")
    describe("current (price vs average)", episodes_of(detector.labels, stamps), years)

    print("\nCAUSAL TURNING-POINT DATING")
    print("Wanted: 1.5-2.5 phases a year, nothing under 90 days, and the label")
    print("must still order the composite's next SIX MONTHS.\n")
    results = {}
    for name, window, down, up, floor in VARIANTS:
        smoothed = [v for v in trailing_average(broad, window) if v is not None]
        offset = len(broad) - len(smoothed)
        when = stamps[offset:]
        labels = cycle_labels(smoothed, down, up, floor)
        results[name] = (labels, when, smoothed)
        describe(name, episodes_of(labels, when), years)
        found = forward_by_label(labels, smoothed, 120)
        bear, bull = found.get("BEAR"), found.get("BULL")
        spread = (
            f"{bear:+.1%} vs {bull:+.1%}"
            if None not in (bear, bull)
            else "one label never fired"
        )
        verdict = (
            "ordered"
            if None not in (bear, bull) and bear < bull
            else "*** INVERTED ***"
        )
        print(f"  {'':<34} 120d forward  BEAR {spread}  {verdict}")

    print("\nWHAT THE BEST CANDIDATE ACTUALLY DATED")
    pick = "smooth 90 · swing 40/60 · 180d"
    labels, when, _ = results[pick]
    print(f"  ({pick})\n")
    for label, start, end, bars in episodes_of(labels, when):
        print(
            f"    {label.value:<9} {start:%Y-%m-%d} → {end:%Y-%m-%d}  "
            f"{bars:>4} days  ({bars / 30.4:>4.1f} months)"
        )

    # -- the middle level ---------------------------------------------------- #
    #
    # The cycle level is deliberately coarse: six phases in eight years is what
    # the operator asked the GLOBAL trend to look like. It is too coarse to
    # choose a trading module with -- inside a 24-month bear there are stretches
    # worth trading and stretches worth standing aside, and one label cannot
    # tell them apart.
    #
    # The middle level is the existing mechanism with the churn censored: same
    # price-versus-average and breadth test, but a label that does not survive
    # `floor` bars is absorbed into its neighbour. The floor is applied AFTER
    # the fact here to measure it; in the detector it has to be causal, which
    # means refusing to leave a state rather than rewriting one.
    print("\nTHE MIDDLE LEVEL: the current mechanism, with short phases censored")
    print("Wanted: two to three times the cycle's phase count, still ordered.\n")

    def censor(labels, floor):
        """Refuse to leave a state before `floor` bars. Causal by construction:
        it only ever declines a change, it never rewrites a past label."""
        out, current, held = [], labels[0], 0
        for label in labels:
            held += 1
            if label is not current and held >= floor:
                current, held = label, 0
            out.append(current)
        return out

    for floor in (1, 30, 45, 60, 90):
        held = censor(detector.labels, floor)
        found = forward_by_label(held, broad, 20)
        bear, bull = found.get("BEAR"), found.get("BULL")
        name = "no floor" if floor == 1 else f"{floor}-day floor"
        describe(name, episodes_of(held, stamps), years)
        if None not in (bear, bull):
            print(
                f"  {'':<34} 20d forward  BEAR {bear:+.2%} vs BULL {bull:+.2%}  "
                f"{'ordered' if bear < bull else '*** INVERTED ***'}"
            )

    print("\n  Retrospective datings are drawn with hindsight; this one is causal")
    print("  and will always be later. That is the price of not cheating.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
