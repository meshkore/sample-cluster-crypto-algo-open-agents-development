"""V5 CALIBRATION - does the model weigh what the world weighs?

Every test in v1 looked inward. V0 proves the books balance, which they would even if every
level were wrong by a factor of three; V2 compares the SHAPE of a flow against a held-out
anchor. Neither ever asked the question the operator asked on 2026-09-14: if crypto is worth
four trillion dollars at the end of 2025, is this model worth four trillion dollars?

The answer is a number per asset, not an average, and it decomposes into three errors that
have nothing to do with each other:

  SCOPE   assets the universe does not carry. Exactly knowable: the published global total
          minus the published total of our fourteen. It is not a modelling error at all -
          it is the price of choosing a universe - but it must be named, because a model
          holding 82% of the market's value is not "18% wrong".
  FLOAT   our units against the published circulating supply, per asset. This is where v1's
          held-constant supply snapshot shows up: every emitting asset floats too much coin
          in every year before the last.
  PRICE   our price against the published price. Should be zero by construction - the ledger
          settles at the tape's price - and is checked anyway, because "should be zero by
          construction" is how level errors survive.

A single blended percentage would hide all three, so this module refuses to compute one.

And one thing the first run taught, which changed the design of this module: **the world does
not publish one number.** CoinMetrics says XRP's circulating supply on 2025-12-31 was 100.0bn
and CoinGecko says 60.7bn - a 65% disagreement about a fact, because one counts escrowed
tokens and the other does not. Chainlink splits the same way (1.00bn against 0.71bn: total
issued versus circulating). Judging the model against whichever source was consulted first
would be scoring it against a coin flip, so every row carries BOTH readings, a row is DISPUTED
when they disagree by more than `SOURCE_SPREAD`, and the model passes if it lands inside the
range the world itself offers. A calibration cannot be more precise than the thing it
calibrates against.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import quantlab_catalog as catalog

#: The dates the calibration is judged at. The last is the operator's: the state the whole of
#: phase 1 exists to produce. The first two are only reachable for the assets CoinMetrics
#: covers, and the report says so rather than dropping them silently.
CHECKPOINTS = ("2018-12-31", "2021-12-31", "2025-12-31")

#: A float within this of the published supply is a pass. Circulating supply is itself a
#: judgement call - locked tokens, burned tokens, lost coins - and two published sources
#: routinely differ by a percent or two, so a tighter band would be measuring the sources'
#: disagreement rather than the model's error.
FLOAT_TOLERANCE = 0.02
PRICE_TOLERANCE = 0.005

#: Beyond this, the two sources are not measuring the same quantity and the row is DISPUTED.
#: The model is then judged against the range rather than against a point, and the gap is
#: reported as a property of the DATA, not of the model.
SOURCE_SPREAD = 0.05

#: The two sources do not keep the same clock, and this is the first thing the calibration
#: found. CoinMetrics stamps a day with that day's close. CoinGecko stamps a day with the
#: snapshot at 00:00 UTC, which is the PREVIOUS day's close - so the model's close of day d
#: must be read against CoinGecko's point at d+1. Measured over the fourteen assets at
#: 2025-12-31, honouring that shift moves the median absolute price error from 0.98% to
#: 0.20%; the residual is cross-venue spread, which is real and should not be zero.
CG_DAY_SHIFT = 1


@dataclass
class AssetRow:
    symbol: str
    day: str
    modelled_units: float
    modelled_price: float
    #: Every source that answered, by name. Kept plural on purpose - see the module docstring.
    supplies: dict[str, float] = field(default_factory=dict)
    prices: dict[str, float] = field(default_factory=dict)

    @property
    def sources(self) -> str:
        return "+".join(sorted(self.supplies)) or "none"

    @property
    def low(self) -> float | None:
        return min(self.supplies.values()) if self.supplies else None

    @property
    def high(self) -> float | None:
        return max(self.supplies.values()) if self.supplies else None

    @property
    def disputed(self) -> bool:
        """Do the sources disagree about the fact by more than they disagree about noise?"""
        return bool(self.low) and (self.high / self.low - 1.0) > SOURCE_SPREAD

    @property
    def published_price(self) -> float | None:
        """Price is not disputed in practice - the spread between sources is venue noise."""
        return sum(self.prices.values()) / len(self.prices) if self.prices else None

    @property
    def modelled_cap(self) -> float:
        return self.modelled_units * self.modelled_price

    @property
    def published_cap(self) -> float | None:
        """Capitalisation on the MIDPOINT of the published supplies, so a disputed asset does
        not get to pick the flattering end."""
        if not self.supplies or self.published_price is None:
            return None
        return (self.low + self.high) / 2.0 * self.published_price

    @property
    def float_error(self) -> float | None:
        """Distance to the nearest published reading - zero when inside the published range.

        An asset the world cannot agree on cannot be missed by more than the disagreement,
        and pretending otherwise would charge the model for someone else's definition.
        """
        if not self.supplies:
            return None
        if self.low <= self.modelled_units <= self.high:
            return 0.0
        if self.modelled_units < self.low:
            return self.modelled_units / self.low - 1.0
        return self.modelled_units / self.high - 1.0

    @property
    def price_error(self) -> float | None:
        if not self.published_price:
            return None
        return self.modelled_price / self.published_price - 1.0

    @property
    def verdict(self) -> str:
        if not self.supplies:
            return "NO DATA"
        if abs(self.float_error) > FLOAT_TOLERANCE:
            return "FLOAT"
        if self.price_error is not None and abs(self.price_error) > PRICE_TOLERANCE:
            return "PRICE"
        return "DISPUTED" if self.disputed else "PASS"


@dataclass
class CheckpointReport:
    day: str
    rows: list[AssetRow] = field(default_factory=list)
    global_cap: float | None = None
    global_as_of: str | None = None

    @property
    def modelled_total(self) -> float:
        return sum(r.modelled_cap for r in self.rows)

    @property
    def published_total(self) -> float:
        return sum(r.published_cap for r in self.rows if r.published_cap is not None)

    @property
    def covered(self) -> list[AssetRow]:
        return [r for r in self.rows if r.supplies]

    @property
    def disputed(self) -> list[AssetRow]:
        return [r for r in self.rows if r.disputed]

    @property
    def universe_error(self) -> float | None:
        """How wrong the model is about the assets it actually carries. The honest headline."""
        pub = self.published_total
        if not pub:
            return None
        modelled = sum(r.modelled_cap for r in self.covered)
        return modelled / pub - 1.0

    @property
    def scope_share(self) -> float | None:
        """What fraction of the whole market the universe represents, where that is knowable."""
        if not self.global_cap:
            return None
        return self.published_total / self.global_cap


def _shift(day: str, days: int) -> str:
    from datetime import date, timedelta
    y, m, d = (int(x) for x in day.split("-"))
    return (date(y, m, d) + timedelta(days=days)).isoformat()


def _published(symbol: str, day: str, one_year: dict, full: dict,
               modelled_price: float = 0.0) -> tuple[dict, dict]:
    """Every source that can answer for this asset on this day, each on its own clock.

    CoinMetrics stamps a day with that day's close; CoinGecko stamps it with 00:00 UTC, which
    is the previous close, hence `CG_DAY_SHIFT`. Ignoring that convention measures the
    convention instead of the model - it was worth 0.8 percentage points of apparent price
    error before it was fixed.
    """
    supplies, prices = {}, {}
    deep = full.get("assets", {}).get(symbol, {}).get("days", {}).get(day) or {}
    px = deep.get("PriceUSD")
    if px:
        prices["coinmetrics"] = px
    if deep.get("SplyCur"):
        supplies["issued"] = deep["SplyCur"]
    if deep.get("CapMrktEstUSD") and (px or modelled_price):
        # Free float: Coin Metrics' capitalisation with provably lost and never-moved coins
        # removed, turned back into units at the price that produced it. For six assets this
        # is the only deep series the open tier carries, and it is closer to what a market
        # model should float than issued supply is.
        supplies["free float"] = deep["CapMrktEstUSD"] / (px or modelled_price)
    year = one_year.get(symbol, {}).get("days", {}).get(_shift(day, CG_DAY_SHIFT))
    if year and year.get("supply"):
        supplies["circulating"] = year["supply"]
        prices["coingecko"] = year["price"]
    return supplies, prices


def calibration(traj, symbols: list[str],
                checkpoints: tuple[str, ...] = CHECKPOINTS) -> list[CheckpointReport]:
    """Compare the model's float and price against the published ones, asset by asset."""
    one_year = catalog.market_cap_1y()
    full = catalog.market_cap_full()
    try:
        glob = catalog.global_market_cap()
    except FileNotFoundError:
        glob = {}

    index = {d: i for i, d in enumerate(traj.days)}
    out = []
    for day in checkpoints:
        if day not in index:
            continue
        i = index[day]
        units: dict[str, float] = {}
        for cohort in traj.state[i].values():
            for sym, q in cohort["coins"].items():
                units[sym] = units.get(sym, 0.0) + q
        report = CheckpointReport(day=day,
                                  global_cap=glob.get("total_market_cap_usd"),
                                  global_as_of=glob.get("as_of"))
        for sym in symbols:
            if sym not in units:
                continue
            supplies, prices = _published(sym, day, one_year, full,
                                          traj.prices[i].get(sym, 0.0))
            report.rows.append(AssetRow(
                symbol=sym, day=day, modelled_units=units[sym],
                modelled_price=traj.prices[i].get(sym, 0.0),
                supplies=supplies, prices=prices))
        out.append(report)
    return out


def render(reports: list[CheckpointReport]) -> str:
    lines = []
    for rep in reports:
        lines.append(f"\nV5 CALIBRATION - {rep.day}")
        lines.append(f"  {'asset':10}{'modelled units':>18}{'published low':>18}"
                     f"{'published high':>18}{'float err':>11}{'price err':>11}"
                     f"{'cap':>12}  sources / verdict")
        for r in sorted(rep.rows, key=lambda r: -r.modelled_cap):
            fe = f"{r.float_error:+.2%}" if r.float_error is not None else "-"
            pe = f"{r.price_error:+.3%}" if r.price_error is not None else "-"
            lo = f"{r.low:,.0f}" if r.low else "-"
            hi = f"{r.high:,.0f}" if r.high else "-"
            lines.append(f"  {r.symbol:10}{r.modelled_units:>18,.0f}{lo:>18}{hi:>18}"
                         f"{fe:>11}{pe:>11}{r.modelled_cap / 1e9:>10,.1f}B  {r.sources}"
                         f"  {'' if r.verdict == 'PASS' else r.verdict}")
        ue = rep.universe_error
        if rep.disputed:
            lines.append("  DISPUTED by the sources themselves: " + ", ".join(
                f"{r.symbol.replace('USDT', '')} {r.low / 1e9:,.2f}bn vs {r.high / 1e9:,.2f}bn"
                for r in sorted(rep.disputed, key=lambda r: -r.modelled_cap)))
        lines.append(f"  covered {len(rep.covered)}/{len(rep.rows)} assets"
                     f"   modelled {rep.modelled_total / 1e12:.3f}T"
                     f"   published {rep.published_total / 1e12:.3f}T"
                     + (f"   UNIVERSE ERROR {ue:+.2%}" if ue is not None else ""))
        if rep.scope_share is not None:
            lines.append(f"  scope: the universe is {rep.scope_share:.1%} of the published "
                         f"global {rep.global_cap / 1e12:.3f}T (as of {rep.global_as_of}) - "
                         f"the rest of the market is NOT modelled")
    return "\n".join(lines)


def main() -> int:
    from system009_participant_ledger import pipeline
    print("SYSTEM 09 - V5 CALIBRATION: does the model weigh what the world weighs?")
    ctx, traj = pipeline.reconstruct(end="2025-12-31", sealed=False, use_etf=True, cache=True)
    reports = calibration(traj, ctx.symbols)
    if not reports:
        print("  no checkpoint falls inside the reconstruction")
        return 1
    print(render(reports))
    last = reports[-1]
    worst = max((abs(r.float_error) for r in last.rows if r.float_error is not None),
                default=0.0)
    failing = [r.symbol.replace("USDT", "") for r in last.rows if r.verdict == "FLOAT"]
    print(f"\n  at {last.day}: worst float error {worst:.1%} against a {FLOAT_TOLERANCE:.0%} "
          f"tolerance   verdict "
          f"{'CALIBRATED' if worst <= FLOAT_TOLERANCE else 'NOT CALIBRATED'}")
    if failing:
        print(f"  outside the published range: {', '.join(failing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
