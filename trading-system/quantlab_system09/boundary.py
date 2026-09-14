"""The boundary: the only events that change how many coins and how many dollars exist.

Section 0 of the design document is the reason this file is short. Trades redistribute;
they never change a total. Totals change here, and nowhere else, through four channels:

    issuance      coins enter, paid to miners        chain_total-bitcoins, daily
    mint / burn   dollars enter or leave as stables  stablecoin_supply, daily
    ETF creation  dollars enter from outside crypto  etf_flow_btc, daily from 2024-01
    redemption    dollars leave crypto entirely      etf_flow_btc, daily from 2024-01

Every one of them is OBSERVED. That is the property that makes the whole project
identifiable rather than merely enormous: the inside of the system is a conservation law,
and the outside is a short list of series that can actually be downloaded.

THE ONE HONEST PROBLEM IN THIS FILE, stated here rather than buried

The stablecoin float is the cash of the WHOLE crypto sector, and this MVP models one pair.
Handing all of it to BTC cohorts would give them several times the dry powder they really
have, and dry powder is a capacity constraint - it decides who is still able to buy - so
the error would not be cosmetic. `btc_cash_share` therefore splits the float by BTC's
measured share of dollar volume across the laboratory's universe. It is a MEASUREMENT, not
a fitted parameter, and it is still an approximation: attention is not the same as
allocation. It is the largest modelling liberty taken in this MVP and it is recorded as
such in the documentation.

Before the stablecoin era, exchange cash balances were mostly fiat and are not observable
anywhere. That is why the reconstruction window opens in 2020 and not at the first Bitcoin
purchase in 2010: the ledger would have had to invent the cash side, and a conservation law
asserted against an invented total proves nothing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import quantlab_catalog as cat
from quantlab_catalog.paths import indicator_dir


def _daily(rows: list[dict], key: str = "value") -> dict[str, float]:
    """A `t_s`-stamped series keyed by UTC date string, which is how the ledger closes."""
    out: dict[str, float] = {}
    for r in rows:
        day = datetime.fromtimestamp(int(r["t_s"]), timezone.utc).strftime("%Y-%m-%d")
        out[day] = float(r[key])
    return out


def coin_float() -> dict[str, float]:
    """Bitcoin in existence, by day. The number every cohort's coins must sum to."""
    return _daily(cat.onchain("total-bitcoins"))


def stablecoin_float() -> dict[str, float]:
    """Total stablecoin supply in USD, by day. The sector's cash before any BTC split."""
    return _daily(cat.stablecoins())


def etf_flow() -> dict[str, float]:
    """US spot BTC ETF net creations in USD, by day. Farside publishes millions."""
    return {d: v * 1e6 for d, v in _daily(cat.etf_flows()).items()}


def btc_cash_share(force: bool = False) -> dict[str, float]:
    """BTC's share of dollar volume across the laboratory's universe, by day.

    Cached, because it costs a full load of every symbol in the universe and the answer
    does not change between runs. The cache lives with the other per-system derived data,
    not in the shared catalogue, because it is computed under this system's definition of
    "the market" and is not interchangeable with anybody else's.
    """
    path = indicator_dir("system09") / "btc_cash_share.json"
    if path.is_file() and not force:
        return json.loads(path.read_text(encoding="utf-8"))

    symbols = cat.load_universe()
    per_day: dict[str, list[float]] = {}
    btc_day: dict[str, float] = {}
    for sym in symbols:
        bars = cat.research([sym])[sym]
        acc: dict[str, float] = {}
        for b in bars:
            day = b.timestamp.strftime("%Y-%m-%d")
            acc[day] = acc.get(day, 0.0) + b.volume * (b.high + b.low + b.close) / 3.0
        for day, v in acc.items():
            per_day[day] = per_day.get(day, [])
            per_day[day].append(v)
            if sym == "BTCUSDT":
                btc_day[day] = v

    out = {day: (btc_day.get(day, 0.0) / s)
           for day, vals in per_day.items() if (s := sum(vals)) > 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out), encoding="utf-8")
    return out


class Boundary:
    """The four channels, resolved to per-day deltas the ledger can apply directly.

    `use_etf` is the switch the V2 anchor-recovery test turns off. With it on, ETF
    creations are injected as cash into the institutional cohort and the reconstruction
    has been TOLD what that cohort did. With it off, the institutional cohort acts on its
    behavioural rule alone and its inferred accumulation becomes a prediction that can be
    scored against the published series it never saw.
    """

    def __init__(self, *, use_etf: bool = True, cash_share: bool = True) -> None:
        self.coins = coin_float()
        self.stables = stablecoin_float()
        self.etf = etf_flow() if use_etf else {}
        self.use_etf = use_etf
        self.share = btc_cash_share() if cash_share else {}
        self._prev_day: str | None = None

    # ------------------------------------------------------------------ helpers
    def _cash_pool(self, day: str) -> float | None:
        s = self.stables.get(day)
        if s is None:
            return None
        return s * self.share.get(day, 1.0) if self.share else s

    def opening_totals(self, day: str) -> tuple[float, float]:
        """The coin and cash floats on the first day of the window."""
        coins = _nearest(self.coins, day)
        cash = self._cash_pool(day)
        if cash is None:
            cash = _nearest(self.stables, day) * (self.share.get(day, 1.0) if self.share else 1.0)
        return coins, cash

    def deltas(self, day: str, prev_day: str) -> dict[str, float]:
        """What the boundary did on `day`, relative to `prev_day`.

        A missing observation returns a zero delta rather than a guess. The series are
        published daily and gaps are rare, but a filled gap would show up in the ledger as
        a mint that never happened.
        """
        c_now, c_prev = self.coins.get(day), self.coins.get(prev_day)
        issuance = max(0.0, c_now - c_prev) if (c_now and c_prev) else 0.0

        s_now, s_prev = self._cash_pool(day), self._cash_pool(prev_day)
        d_cash = (s_now - s_prev) if (s_now is not None and s_prev is not None) else 0.0

        return {
            "issuance": issuance,
            "mint": max(0.0, d_cash),
            "burn": max(0.0, -d_cash),
            "etf_in": max(0.0, self.etf.get(day, 0.0)),
            "etf_out": max(0.0, -self.etf.get(day, 0.0)),
        }


def _nearest(series: dict[str, float], day: str) -> float:
    """The observation on `day`, or the last one before it. Raises rather than guessing."""
    if day in series:
        return series[day]
    earlier = [d for d in series if d <= day]
    if not earlier:
        raise KeyError(f"no observation at or before {day}; the window opens too early")
    return series[max(earlier)]
