"""The validation ladder, as far up as the MVP is entitled to climb: V0 and V2.

V0 ACCOUNTING is binary and it is not interesting when it passes. It is here because every
other number this system will ever produce is worthless if it fails, and because a
conservation law that is only checked at the end tells you that something broke rather than
where.

V2 ANCHOR RECOVERY is the one that matters, and it is the only test in this MVP that can
embarrass us. The recipe: reconstruct the market WITHOUT telling it what the ETF cohort
did, then ask the inferred institutional cohort what it thinks the ETFs did, and score that
against the published series. Nothing else in this package can distinguish a reconstruction
from a story; this can.

THE BASELINE IS THE POINT OF THE TEST, AND IT IS WHERE MOST PROJECTS LIKE THIS CHEAT.
The institutional cohort's rule reads the slow trend. ETF flows chase the slow trend. So a
naive predictor - "institutions bought because price went up" - will already correlate with
the published series, and reporting the reconstruction's correlation on its own would be
claiming credit for the trend. `anchor_recovery` therefore scores THREE things on the same
days:

    inferred   what the ledger says the institutional cohort actually managed to do,
               after capacity, turnover budgets and competition for the tape's flow
    baseline   the raw desire that drove it, before the ledger constrained anything
    actual     the published ETF series

and the question is not whether `inferred` correlates with `actual`. It is whether
`inferred` correlates with `actual` MORE THAN `baseline` does. If it does not, the ledger
machinery added nothing to a moving average, and that is a result to write down rather than
to bury.

Daily, weekly and cumulative agreement are all reported because they answer different
questions and because picking the flattering one afterwards is how this laboratory has
fooled itself before.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import cohorts as C
from .ledger import ConservationError, Ledger
from .reconstruct import Trajectory


# --------------------------------------------------------------------------- statistics

def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 3:
        return float("nan")
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def _rank(v: list[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def _spearman(x: list[float], y: list[float]) -> float:
    return _pearson(_rank(x), _rank(y))


def _sign_agreement(x: list[float], y: list[float]) -> float:
    pairs = [(a, b) for a, b in zip(x, y) if a != 0 and b != 0]
    if not pairs:
        return float("nan")
    return sum(1 for a, b in pairs if (a > 0) == (b > 0)) / len(pairs)


def _weekly(days: list[str], v: list[float], width: int = 7) -> list[float]:
    return [sum(v[i:i + width]) for i in range(0, len(v) - width + 1, width)]


def _cumulative(v: list[float]) -> list[float]:
    out, run = [], 0.0
    for x in v:
        run += x
        out.append(run)
    return out


# --------------------------------------------------------------------------- V0

@dataclass
class AccountingReport:
    passed: bool
    buckets: int
    coin_drift: float
    cash_drift: float
    shortfall_events: int
    shortfall_coins: float
    funding_unpaid: float
    min_fill: float
    mean_fill: float
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        head = "V0 ACCOUNTING  " + ("PASS" if self.passed else "FAIL")
        return "\n".join([
            head,
            f"  buckets settled          {self.buckets:,}",
            f"  unit total drift         {self.coin_drift:+.6g} (worst asset, relative)",
            f"  cash total drift         {self.cash_drift:+.6g} USD",
            f"  sell shortfalls          {self.shortfall_events} events, "
            f"{self.shortfall_coins:,.4f} BTC",
            f"  funding left unpaid      ${self.funding_unpaid:,.0f}",
            f"  fill ratio               mean {self.mean_fill:.4f}, worst {self.min_fill:.4f}",
            *[f"  ! {n}" for n in self.notes],
        ])


def accounting(ledger: Ledger, traj: Trajectory) -> AccountingReport:
    """V0. Re-derives every total from the agents and compares them to the boundary.

    With many assets there is one unit total per symbol, so the reported drift is the worst
    of them: an average would let one broken asset hide behind thirteen sound ones.
    """
    notes: list[str] = []
    coin_drift = 0.0
    for sym, want in ledger.total_coins.items():
        got = sum(a.coins.get(sym, 0.0) for a in ledger.agents)
        rel = (got - want) / max(abs(want), 1.0)
        if abs(rel) > abs(coin_drift):
            coin_drift = rel
    cash = sum(a.cash for a in ledger.agents)
    cash_drift = cash - ledger.total_cash
    try:
        ledger.check("V0")
        ok = True
    except ConservationError as exc:
        ok = False
        notes.append(str(exc))
    if traj.shortfall_events:
        notes.append(f"{traj.shortfall_events} buckets asked a cohort to sell coins it did "
                     f"not hold; the allocator is mis-specified there")
    fills = traj.fill_ratio or [0.0]
    if min(fills) < 0.99:
        notes.append(f"worst day filled only {min(fills):.3f} of observed volume")
    return AccountingReport(
        passed=ok and not traj.shortfall_events,
        buckets=traj.buckets, coin_drift=coin_drift, cash_drift=cash_drift,
        shortfall_events=traj.shortfall_events, shortfall_coins=ledger.shortfall_coins,
        funding_unpaid=ledger.funding_unpaid,
        min_fill=min(fills), mean_fill=sum(fills) / len(fills), notes=notes)


# --------------------------------------------------------------------------- V2

@dataclass
class AnchorReport:
    days: int
    daily: dict[str, float]
    weekly: dict[str, float]
    cumulative: dict[str, float]
    beats_baseline: bool
    margin: float
    wins: int = 0
    scored: int = 9

    def render(self) -> str:
        def block(name: str, d: dict[str, float]) -> list[str]:
            return [f"  {name}",
                    f"    pearson   inferred {d['pearson_inferred']:+.4f}   "
                    f"baseline {d['pearson_baseline']:+.4f}",
                    f"    spearman  inferred {d['spearman_inferred']:+.4f}   "
                    f"baseline {d['spearman_baseline']:+.4f}",
                    f"    sign      inferred {d['sign_inferred']:.4f}    "
                    f"baseline {d['sign_baseline']:.4f}"]
        verdict = "RECOVERED" if self.beats_baseline else "NOT RECOVERED"
        return "\n".join([
            f"V2 ANCHOR RECOVERY  {verdict}  (ETF flows held out of the reconstruction)",
            f"  scored on {self.days} days",
            *block("daily", self.daily),
            *block("weekly", self.weekly),
            *block("cumulative path", self.cumulative),
            f"  beat the baseline on {self.wins} of {self.scored} statistics",
            f"  margin over baseline (weekly pearson)  {self.margin:+.4f}",
        ])


def anchor_recovery(traj: Trajectory, actual_usd: dict[str, float],
                    baseline: dict[str, float], cohort: str = C.INSTITUTIONAL,
                    symbol: str = "BTCUSDT", start: str | None = None) -> AnchorReport:
    """V2. Score the inferred cohort flow against a held-out published series.

    `actual_usd` is the published net flow in dollars; it is converted to coins at the
    day's price so that both sides are the same quantity. `baseline` is the unconstrained
    desire that drove the cohort's rule, and it is what the reconstruction has to beat to
    have earned anything.
    """
    days, inf, act, base = [], [], [], []
    prev = None
    for d, prices, st in zip(traj.days, traj.prices, traj.state):
        px = prices.get(symbol, 0.0)
        held = st.get(cohort, {}).get("coins", {}).get(symbol, 0.0)
        if prev is not None and d in actual_usd and (start is None or d >= start):
            days.append(d)
            inf.append(held - prev)
            act.append(actual_usd[d] / px if px else 0.0)
            base.append(baseline.get(d, 0.0))
        prev = held

    def score(i: list[float], a: list[float], b: list[float]) -> dict[str, float]:
        return {
            "pearson_inferred": _pearson(i, a), "pearson_baseline": _pearson(b, a),
            "spearman_inferred": _spearman(i, a), "spearman_baseline": _spearman(b, a),
            "sign_inferred": _sign_agreement(i, a), "sign_baseline": _sign_agreement(b, a),
        }

    daily = score(inf, act, base)
    weekly = score(_weekly(days, inf), _weekly(days, act), _weekly(days, base))
    cumul = score(_cumulative(inf), _cumulative(act), _cumulative(base))
    margin = weekly["pearson_inferred"] - weekly["pearson_baseline"]
    # The verdict is a VOTE over every statistic scored, not the best one. Declaring
    # recovery on whichever of nine numbers happened to come out ahead is the selection
    # optimism this laboratory has already paid for twice; a reconstruction that genuinely
    # knows something beats a moving average on most measures, not on one.
    wins = 0
    for block in (daily, weekly, cumul):
        for stat in ("pearson", "spearman", "sign"):
            inf_v, base_v = block[f"{stat}_inferred"], block[f"{stat}_baseline"]
            if inf_v == inf_v and base_v == base_v and inf_v > base_v:
                wins += 1
    return AnchorReport(days=len(days), daily=daily, weekly=weekly, cumulative=cumul,
                        beats_baseline=wins > 4, margin=margin, wins=wins, scored=9)
