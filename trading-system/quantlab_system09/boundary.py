"""The boundary: the only events that change how many units and how many dollars exist.

Section 0 of the design document is the reason this file is short. Trades redistribute; they
never change a total. Totals change here, and nowhere else, through five channels:

    issuance      units enter, paid to miners        chain_total-bitcoins, daily, observed
    listing       an asset joins the venue, bringing its holders with it       observed date
    mint / burn   dollars enter or leave as stables  stablecoin_supply, daily, observed
    ETF flow      dollars enter or leave crypto      etf_flow_btc, daily from 2024-01
    fiat ramp     dollars enter or leave as FIAT     NOT OBSERVED - inferred, see below

Four of the five are observed. That is the property that makes the project identifiable
rather than merely enormous.

THE FIFTH CHANNEL, AND WHY IT IS HONEST RATHER THAN A FUDGE

The first version of this system started in 2020 and used the stablecoin float as the whole
of the sector's cash. Over the full record that is untenable: in 2017 the stablecoin float
was a few hundred million dollars against a market turning over billions, because exchange
balances back then were mostly FIAT - dollars, euros and won sitting in exchange accounts -
and no public series has ever measured them.

The choice is to invent a number, to start the record late, or to treat the unobserved
cash as what it is: a residual. This module takes the third. The reconstruction tells the
boundary how many dollars of buying the population could not fund, and exactly that much
fiat is ramped in - no more. The resulting `fiat_ramped` series is therefore not an
assumption, it is a MEASUREMENT of how much cash the observed stablecoin float fails to
explain, and it can be checked against the world: it should dominate the early record and
fade as stablecoins take over. If it does not, the model is wrong and says so out loud.

ALT SUPPLY IS A SNAPSHOT, AND THAT IS THE LARGEST KNOWN LEVEL ERROR
Bitcoin has a true daily supply series. Every other asset's circulating supply is taken once
and held constant across the whole record, because free historical market-cap data stops at
one year. Assets still emitting - Solana, Near, Sui, Worldcoin - therefore hold too large a
float in the early years. Recorded here and in the documentation rather than smoothed over.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import quantlab_catalog as cat
from quantlab_catalog.paths import external_file

#: The only asset whose float is known day by day rather than as a snapshot.
MINTED = "BTCUSDT"


def _supply_series(daily_price: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """A daily supply series per asset, from the published record, on one definition.

    The definitions are not interchangeable and the V5 calibration measured how far apart
    they sit - XRP's issued supply is 100.0bn and its circulating supply 60.7bn, a 65% gap
    about a fact. This model floats **free float** where it exists: Coin Metrics'
    capitalisation with provably lost and never-moved coins removed, divided by their
    reference price. That is the closest published quantity to what this ledger actually
    represents, which is units that somebody could sell today.

    Where free float is not published the series falls back to issued supply, and where
    neither exists the caller falls back to the old snapshot. Gaps inside a series are left
    as gaps: `_at` walks back to the last real observation rather than inventing one.

    Six of the fourteen - Solana, Near, Sui, Worldcoin, Tron and one more - publish a free
    float CAPITALISATION in the open tier and no price to divide it by. The tape has a price
    for every one of those days, so `daily_price` closes the gap. Without it those assets
    fall silently back to the one-year window, and a one-year window used as a whole-record
    series is a constant by another name: Solana's float came out 75% too high in 2021 and
    Near's 107% too high, both of which V5 caught only because the earlier checkpoints exist.
    """
    try:
        full = cat.market_cap_full().get("assets", {})
    except FileNotFoundError:
        return {}
    try:
        one_year = cat.market_cap_1y()
    except FileNotFoundError:
        one_year = {}
    out: dict[str, dict[str, float]] = {}
    for sym, rec in full.items():
        series = {}
        tape = daily_price.get(sym, {})
        for day, vals in rec.get("days", {}).items():
            px = vals.get("PriceUSD") or tape.get(day)
            if vals.get("CapMrktEstUSD") and px:
                series[day] = vals["CapMrktEstUSD"] / px
            elif vals.get("SplyCur"):
                series[day] = vals["SplyCur"]
        if series:
            out[sym] = dict(sorted(series.items()))
    # CoinGecko's window is only a year, so it can never be the backbone of a series - but it
    # is the only source for an asset CoinMetrics does not carry at all, and one year of truth
    # beats eight years of a constant.
    for sym, rec in one_year.items():
        if sym in out:
            continue
        series = {d: v["supply"] for d, v in rec.get("days", {}).items() if v.get("supply")}
        if series:
            out[sym] = dict(sorted(series.items()))
    return out


def _daily(rows: list[dict], key: str = "value") -> dict[str, float]:
    """A `t_s`-stamped series keyed by UTC date string, which is how the ledger closes."""
    out: dict[str, float] = {}
    for r in rows:
        day = datetime.fromtimestamp(int(r["t_s"]), timezone.utc).strftime("%Y-%m-%d")
        out[day] = float(r[key])
    return out


def _forward_fill(series: dict[str, float], days: list[str]) -> dict[str, float]:
    """Carry the last observation forward across a daily grid.

    Used only for series that are genuinely sampled rather than daily - active addresses
    arrive a few times a week. Never used on a price and never used to fill a gap in a flow,
    where a filled value and a real zero mean opposite things.
    """
    out: dict[str, float] = {}
    keys = sorted(series)
    i, last = 0, None
    for d in days:
        while i < len(keys) and keys[i] <= d:
            last = series[keys[i]]
            i += 1
        if last is not None:
            out[d] = last
    return out


def circulating_supply() -> dict[str, dict]:
    path = external_file("circulating_supply.json")
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing; run `python -m quantlab_system09.harvest`")
    return json.loads(path.read_text(encoding="utf-8"))


class Boundary:
    """Every channel, resolved to per-day events the ledger can apply directly.

    `use_etf` is the switch the V2 anchor-recovery test turns off. With it on, ETF creations
    are injected as cash into the institutional cohort and the reconstruction has been TOLD
    what that cohort did. With it off, the cohort acts on its behavioural rule alone and its
    inferred accumulation becomes a prediction of a series it never saw.
    """

    def __init__(self, days: list[str], listings: dict[str, str], *,
                 use_etf: bool = True,
                 daily_price: dict[str, dict[str, float]] | None = None) -> None:
        self.days = days
        self.listings = listings                       # symbol -> first day in the record
        self.btc_float = _daily(cat.onchain("total-bitcoins"))
        self.supply = circulating_supply()
        self.supply_series = _supply_series(daily_price or {})
        self.stables = _daily(cat.stablecoins())
        self.etf = {d: v * 1e6 for d, v in _daily(cat.etf_flows()).items()} if use_etf else {}
        self.use_etf = use_etf
        self.addresses = _forward_fill(_daily(cat.onchain("n-unique-addresses")), days)
        try:
            self.oi = _daily(cat.open_interest(MINTED))
        except (FileNotFoundError, AttributeError):
            self.oi = {}
        # What the reconstruction had to ramp in because the observed cash did not cover the
        # observed tape. An output of the run, not an input to it.
        self.fiat_ramped: dict[str, float] = {}

    # ------------------------------------------------------------------ observed levels
    def listing_float(self, symbol: str) -> float:
        """How many units join the ledger the day an asset appears in the record.

        The modelled sector is "participants reachable by this venue", so an asset listing is
        a boundary event: its float does not spring into existence, it becomes visible.

        v1 used one number for the whole record - today's circulating supply, dragged back
        across eight years - and the V5 calibration priced that assumption: at 2025-12-31 it
        floated 35% too much Worldcoin and 31% too much Fusionist, and the error grows the
        further back you look, because an emitting asset had LESS supply in the past, not the
        same amount. Now the float is whatever the published series says on the listing day.
        """
        if symbol == MINTED:
            return self._at(self.btc_float, self.listings[symbol])
        series = self.supply_series.get(symbol)
        if series:
            day = self.listings[symbol]
            first = next(iter(series))
            # A published supply series can begin AFTER the asset began trading - Tron lists
            # here in June 2018 and its free-float series starts a year later. The earliest
            # published observation is then the closest honest answer: it is the same asset
            # one year older, which overstates the float of anything still emitting, but by
            # far less than today's number would. The alternative - refusing to list the
            # asset - would lose a real market from the record.
            return self._at(series, day) if day >= first else series[first]
        row = self.supply.get(symbol)
        if not row:
            raise KeyError(f"no circulating supply for {symbol}; cannot float it")
        return float(row["circulating_supply"])

    def issuance(self, day: str, prev_day: str) -> float:
        """New Bitcoin mined between two days. The only asset with MINERS in this model."""
        a, b = self.btc_float.get(day), self.btc_float.get(prev_day)
        return max(0.0, a - b) if (a and b) else 0.0

    def supply_delta(self, symbol: str, day: str, prev_day: str) -> float:
        """Units created or destroyed between two days, for any asset but Bitcoin.

        Positive is emission and vesting: tokens that existed on paper becoming tokens that
        can be sold. Negative is real - BNB burns quarterly, ETH burns every block - and a
        model that could only ever issue would drift up forever against the published float.

        Bitcoin is excluded because `issuance` already routes it to the miner cohort, which is
        the one asset where the receiving participant is known.
        """
        if symbol == MINTED:
            return 0.0
        series = self.supply_series.get(symbol)
        if not series:
            return 0.0
        first = next(iter(series))
        if prev_day < first:
            return 0.0
        # Read both ends as "the last published observation at or before", never as an exact
        # key. Published series have holes - BNB's free float has a 60-day hole in 2019 that
        # happens to span a 48-million-unit step - and a lookup that returns None on a hole
        # silently drops the whole move. The model then carried a permanent +48M offset in
        # that asset, which is exactly the kind of quiet level error V5 exists to find, and it
        # took four hours to find because nothing about the run looked wrong.
        a, b = self._at(series, day), self._at(series, prev_day)
        return a - b

    def cash_delta(self, day: str, prev_day: str) -> float:
        """Change in the OBSERVED cash float - the whole sector's stablecoins, in dollars.

        The whole float, not a share of it: this ledger models fourteen assets, so the fudge
        that split the float by BTC's volume share in the one-asset version is gone.
        """
        a, b = self.stables.get(day), self.stables.get(prev_day)
        return (a - b) if (a is not None and b is not None) else 0.0

    def etf_flow(self, day: str) -> float:
        return self.etf.get(day, 0.0)

    def open_interest(self, day: str) -> float | None:
        return self.oi.get(day)

    def active_addresses(self, day: str) -> float:
        return self.addresses.get(day, 0.0)

    def opening_cash(self, day: str) -> float:
        return self._at(self.stables, day, default=0.0)

    def first_cash(self) -> float:
        """The earliest observed stablecoin float.

        The record opens in 2017-08 and the stablecoin series does not begin until 2017-11,
        so asking it for the opening day returns nothing. Falling back to zero there quietly
        deleted the cash growth factor from the population driver, and the population then sat
        still for eight years while the market grew a thousandfold. The earliest OBSERVED
        float is the honest base: it says "as far back as anyone measured", which is exactly
        what it is.
        """
        return self.stables[min(self.stables)] if self.stables else 0.0

    # ------------------------------------------------------------------ the fifth channel
    def record_ramp(self, day: str, usd: float) -> None:
        """Remember how much unobserved fiat the reconstruction needed on this day."""
        if usd:
            self.fiat_ramped[day] = self.fiat_ramped.get(day, 0.0) + usd

    def ramp_summary(self) -> dict[str, float]:
        """The inferred fiat series, aggregated per year. The headline sanity check: this
        should dominate the early record and fade as the stablecoin float takes over."""
        out: dict[str, float] = {}
        for d, v in self.fiat_ramped.items():
            out[d[:4]] = out.get(d[:4], 0.0) + v
        return dict(sorted(out.items()))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _at(series: dict[str, float], day: str, default: float | None = None) -> float:
        if day in series:
            return series[day]
        earlier = [d for d in series if d <= day]
        if not earlier:
            if default is not None:
                return default
            raise KeyError(f"no observation at or before {day}")
        return series[max(earlier)]


def day_range(start: str, end: str) -> list[str]:
    """Every UTC date in [start, end], inclusive at both ends."""
    a = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    b = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    out = []
    while a <= b:
        out.append(a.strftime("%Y-%m-%d"))
        a += timedelta(days=1)
    return out
