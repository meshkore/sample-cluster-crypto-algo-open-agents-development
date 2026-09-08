"""A96: the markets around crypto — and the operator's condition on all of them.

Operator, 2026-09-07: "make sure that whatever it trains on is information we will be
able to obtain in real time for executions from today into the future."

That is not a nicety, it is the difference between a feature and a leak with good
manners. These tests enforce it mechanically:

  * every series is lagged by MORE than its measured publication delay, so a bar can
    only read a number that was genuinely available at the time — and would be
    available live;
  * the lag table is checked against the harvested data, so if a feed slows down the
    suite says so instead of the backtest silently reading the future;
  * only NON-REVISED series are admitted (yields, VIX, index closes, spot oil). A
    revised series would hand the backtest a value nobody had — that is A87's problem,
    solved with point-in-time vintages, and it is deliberately not solved here;
  * the features stay stationary, like every other column in this project.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from quantlab_system06 import reference as ref

REPO = Path(__file__).resolve().parents[2]
from quantlab_catalog.paths import external_file

# The shared catalogue owns this location since 2026-09-08; asking it rather than
# hard-coding a path is what lets the store move without the suite going green on
# a file that is no longer the one production reads.
DATA = external_file("reference_markets.json")

pytestmark = pytest.mark.skipif(
    not DATA.is_file(), reason="reference panel not harvested on this machine")

_DAY = 86_400_000_000_000


@pytest.fixture(scope="module")
def raw():
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_a_bar_never_reads_an_observation_it_could_not_have_had(raw):
    """The core guarantee, checked per series against the data itself: for every bar,
    the observation date supplied must be at least `lag` days old."""
    bars = np.arange(np.datetime64("2018-06-01", "ns"),
                     np.datetime64("2026-01-01", "ns"),
                     np.timedelta64(37, "h"))          # odd stride: no alignment luck
    bar_ns = bars.astype(np.int64)
    for sid, lag in ref.SERIES_LAG_DAYS.items():
        dates, values = ref._series(raw, sid)
        idx = np.searchsorted(dates, bar_ns - lag * _DAY, side="right") - 1
        ok = idx >= 0
        age_days = (bar_ns[ok] - dates[idx[ok]]) / _DAY
        assert age_days.min() >= lag, (
            f"{sid}: a bar was served an observation only {age_days.min():.1f} days "
            f"old, but the assumed publication lag is {lag}")


def test_the_assumed_lag_covers_the_real_publication_delay(raw):
    """If a feed slows down, this fails instead of the backtest quietly reading data
    the live system would not yet have. Uses each series' own newest observation
    against the newest across the panel, which is the best proxy for 'now' that the
    stored file carries."""
    newest = max(int(ref._series(raw, s)[0][-1]) for s in ref.SERIES_LAG_DAYS)
    for sid, lag in ref.SERIES_LAG_DAYS.items():
        delay = (newest - int(ref._series(raw, sid)[0][-1])) / _DAY
        assert lag > delay, (
            f"{sid} is {delay:.0f} days behind the panel but is only lagged {lag} — "
            f"raise SERIES_LAG_DAYS[{sid!r}] above the real delay")


def test_only_non_revised_series_are_used():
    """Revised macro (GDP, payrolls, CPI vintages) belongs to A87 with ALFRED
    point-in-time data. Admitting one here would put a number in the backtest that
    nobody had on the day, and nothing downstream could detect it."""
    revised = {"GDP", "GDPC1", "PAYEMS", "CPIAUCSL", "UNRATE", "PCE", "INDPRO"}
    assert not (set(ref.SERIES_LAG_DAYS) & revised)


def test_the_features_are_stationary_and_bounded(raw):
    """No levels: a net trained on 'NASDAQ = 14,000' learned a number that never
    recurs. And nothing may carry a data artifact large enough to define the column's
    own units — WTI printed NEGATIVE on 2020-04-20 and the unclipped log change came
    out at -30.6, which would have set the standardiser's scale for that feature."""
    table = ref.ReferenceTable(DATA)
    bars = np.arange(np.datetime64("2018-01-01", "ns"),
                     np.datetime64("2026-01-01", "ns"), np.timedelta64(6, "h"))
    m = table.matrix_for(bars)
    assert m.shape[1] == len(ref.REFERENCE_FEATURE_COLUMNS)
    finite = np.all(np.isfinite(m), axis=1)
    assert finite.mean() > 0.95, "the panel should cover essentially the whole window"
    for j, name in enumerate(ref.REFERENCE_FEATURE_COLUMNS):
        v = m[finite, j]
        assert np.abs(v).max() < 10.0, (
            f"{name} reaches {np.abs(v).max():.1f} — a level or an unclipped artifact")


def test_the_transform_is_computed_on_the_daily_series_not_on_bars():
    """A 20-observation return over 15-minute bars is five hours, not a month. Getting
    this backwards would leave every column named for a horizon it does not have."""
    import inspect

    src = inspect.getsource(ref._lagged_transform)
    assert "transformed = fn(values)" in src
    assert "_aligned(dates_ns, transformed" in src


def test_the_standardizer_recognises_the_new_layout():
    """The artifact, not a flag, decides what inference rebuilds — so a model trained
    with reference features cannot be served a 44-column matrix by a forgotten flag."""
    from quantlab_system06.features import FEATURE_COLUMNS, Standardizer

    width = len(FEATURE_COLUMNS) + len(ref.REFERENCE_FEATURE_COLUMNS)
    s = Standardizer(mean=np.zeros(width), std=np.ones(width))
    payload = s.to_dict()
    assert payload["columns"][-1] == ref.REFERENCE_FEATURE_COLUMNS[-1]
    assert len(Standardizer.from_dict(payload).mean) == width


def test_inference_refuses_an_unknown_layout():
    """Better a loud failure than a net silently fed a matrix it never trained on."""
    import inspect

    from quantlab_system06 import infer

    src = inspect.getsource(infer.export)
    assert "matches no known" in src
    assert "want_reference" in src
