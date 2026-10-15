"""System 10 point-in-time universe (audit 2026-10-15, item 1): the list of year N reads nothing
after 31 Dec N-1, and a coin later delisted is in while it qualifies."""

from __future__ import annotations

import json

import numpy as np

from system010_conditioned_rl import universe_pit as U
from system010_conditioned_rl.pit import breadth_from_candles

DAY = U.DAY_NS
BAR = DAY // 96


def _series(first: str, last: str, notional_per_day: float):
    """15m bars from `first` to `last` (inclusive days) with constant close 1 and the given
    daily turnover."""
    a = int(np.datetime64(f"{first}T00:00:00", "ns").astype(np.int64))
    b = int(np.datetime64(f"{last}T23:45:00", "ns").astype(np.int64))
    ns = np.arange(a, b + BAR // 2, BAR, dtype=np.int64)
    return ns, np.ones(len(ns)), np.full(len(ns), notional_per_day / 96)


def _stats(series: dict, years) -> dict:
    return {s: {y: U.stats_at(*v, y) for y in years} for s, v in series.items()}


def test_cut_is_new_year_midnight():
    assert U.cut_ns(2023) == int(np.datetime64("2023-01-01T00:00:00", "ns").astype(np.int64))


def test_nothing_after_the_cut_is_read():
    ns, c, v = _series("2019-01-01", "2023-06-30", 1e6)          # thin up to the cut
    after = ns >= U.cut_ns(2022)
    v2 = v.copy()
    v2[after] = 1e12                                              # a boom after 31 Dec 2021
    assert U.stats_at(ns, c, v, 2022) == U.stats_at(ns, c, v2, 2022)
    assert U.eligible(_stats({"X": (ns, c, v2)}, [2022]), 2022) == []
    # a listing that starts after the cut is invisible to that year
    ns3, c3, v3 = _series("2022-01-01", "2025-12-31", 1e9)
    assert U.stats_at(ns3, c3, v3, 2022) == {"age_days": 0.0, "turnover30": 0.0}


def test_history_rule_540_days():
    cut = np.datetime64("2022-01-01")
    young = str(cut - np.timedelta64(539, "D"))
    old = str(cut - np.timedelta64(541, "D"))
    st = _stats({"YOUNG": _series(young, "2023-12-31", 5e7), "OLD": _series(old, "2023-12-31", 5e7)}, [2022])
    assert U.eligible(st, 2022) == ["OLD"]


def test_turnover_floor_and_ranking():
    st = _stats({"A": _series("2018-01-01", "2023-12-31", 2e7), "B": _series("2018-01-01", "2023-12-31", 9e6),
                 "C": _series("2018-01-01", "2023-12-31", 5e7)}, [2022])
    assert U.eligible(st, 2022) == ["C", "A"]                     # B under the 10M floor
    assert U.eligible(st, 2022, cap=1) == ["C"]


def test_delisted_coin_is_in_while_it_qualifies():
    # trades until 2022-05-12 (a LUNA-like collapse and delisting)
    st = _stats({"DEAD": _series("2019-01-01", "2022-05-12", 5e8),
                 "LIVE": _series("2019-01-01", "2025-12-31", 5e7)}, [2021, 2022, 2023])
    assert U.eligible(st, 2022) == ["DEAD", "LIVE"]               # qualified on 31 Dec 2021
    assert U.eligible(st, 2023) == ["LIVE"]                       # gone by 31 Dec 2022


def test_trailing_window_is_30_days():
    ns, c, v = _series("2018-01-01", "2021-12-31", 1e6)
    last30 = ns >= U.cut_ns(2022) - 30 * DAY
    v = v.copy()
    v[last30] = 2e7 / 96                                          # only the last 30 days are hot
    assert U.stats_at(ns, c, v, 2022)["turnover30"] == 2e7
    v[ns < U.cut_ns(2022) - 30 * DAY] = 0.0
    assert U.stats_at(ns, c, v, 2022)["turnover30"] == 2e7         # older bars do not count


def test_artefact_respects_the_rule():
    if not U.ARTEFACT.is_file():
        return
    doc = json.loads(U.ARTEFACT.read_text())
    for y, rows in doc["years"].items():
        assert all(r["age_days"] >= doc["min_days"] and r["turnover30_musd"] * 1e6 >= doc["floor"] * 0.999
                   for r in rows), y
        t = [r["turnover30_musd"] for r in rows]
        assert t == sorted(t, reverse=True)


def test_breadth_counts_only_present_coins():
    ns = np.arange(4, dtype=np.int64)
    per = {"A": {"ns": ns, "trend": np.array([1.0, 1, 0, 1]), "present": np.array([True, True, True, True])},
           "B": {"ns": ns, "trend": np.array([1.0, 1, 1, 0]), "present": np.array([False, True, True, True])}}
    breadth_from_candles(per)
    assert per["A"]["breadth"].tolist() == [1.0, 1.0, 0.5, 0.5]
    assert per["B"]["breadth"].tolist() == [0.0, 1.0, 0.5, 0.5]   # 0 before its first row
    assert per["B"]["trend"].tolist() == [0.0, 1.0, 1.0, 0.0]


def test_default_world_is_untouched():
    """Inert by default: World() still loads today's 14 coins; PIT only on an explicit universe=N."""
    import inspect

    from system010_conditioned_rl import evaluator as E
    from system010_conditioned_rl import paper as P
    from system010_conditioned_rl import search as S
    sig = inspect.signature(S.World.__init__)
    assert sig.parameters["universe"].default is None
    assert sig.parameters["include_sealed"].default is False
    for src in (inspect.getsource(S.main), inspect.getsource(E), inspect.getsource(P)):
        assert "universe=" not in src          # no running job opts in
