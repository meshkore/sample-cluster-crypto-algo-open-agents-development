"""The local frontend is tested for the one property that matters: it cannot show a number
the phases did not produce.

A dashboard is the place where a laboratory lies to itself most cheaply - a placeholder that
looks like a result, a chart that draws a flat line when the data is missing, a total that is
computed twice with two different definitions. These tests are aimed at exactly that:

  * the payload carries every key the page reads, and the totals agree with the segments;
  * a 2026 section exists only when phase 3 has actually run;
  * the page never hard-codes a figure - every number on screen comes from `api/state`.

Run with `pytest research/system09/preview/test_frontend.py`. The reconstruction is cached, so
the first run is slow and the rest are not.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "trading-system"))

PAGE = HERE / "dashboard.html"
REPORT = ROOT / "research" / "system09" / "phase3_report.json"


@pytest.fixture(scope="module")
def payload():
    cache = ROOT / "research" / "system09" / "frontend.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    pytest.importorskip("quantlab_catalog")
    from quantlab_system09 import frontend_data
    try:
        return frontend_data.build()
    except FileNotFoundError as exc:
        pytest.skip(f"the reconstruction has not been run on this machine: {exc}")


def test_the_payload_has_everything_the_page_reads(payload):
    for key in ("totals", "series", "segments", "segment_order", "assets",
                "population", "generated_for"):
        assert key in payload, f"the page reads `{key}` and the payload has no such key"
    for key in ("players", "represents", "assets", "market_cap", "cash",
                "assets_value", "wealth"):
        assert key in payload["totals"]


def test_the_totals_agree_with_the_segments(payload):
    """Two definitions of one number is how a dashboard starts disagreeing with its source."""
    segs = payload["segments"]
    cash = sum(s["cash"] for s in segs.values())
    assets = sum(s["assets"] for s in segs.values())
    assert cash == pytest.approx(payload["totals"]["cash"], rel=1e-9)
    assert assets == pytest.approx(payload["totals"]["assets_value"], rel=1e-9)
    assert payload["totals"]["wealth"] == pytest.approx(cash + assets, rel=1e-9)
    for k, s in segs.items():
        assert s["total"] == pytest.approx(s["cash"] + s["assets"], rel=1e-9)


def test_the_crowd_is_the_right_way_up(payload):
    """The shape the first two versions had upside down. Real crypto is a pyramid: retail is
    the most numerous, then whales, then institutions, and market makers are a handful."""
    s = payload["segments"]
    assert s["retail"]["players"] > s["whales"]["players"] > s["institutional"]["players"], (
        "the agent pyramid is upside down again")
    assert s["institutional"]["players"] > s["market_makers"]["players"]
    assert s["retail"]["represents"] > s["whales"]["represents"] > \
        s["institutional"]["represents"] > s["market_makers"]["represents"], (
        "the represented crowd is upside down")
    assert s["retail"]["represents"] > 1_000_000, (
        "retail stands for fewer than a million people; that is not a crypto market")


def test_an_agent_is_not_reported_as_a_person(payload):
    """Two headcounts, and they must not be the same number: one is what was simulated, the
    other is what it is a model of."""
    t = payload["totals"]
    assert t["represents"] > t["players"] * 1000


def test_every_segment_is_present_and_labelled(payload):
    from quantlab_system09 import segments as SEG
    assert list(payload["segment_order"]) == list(SEG.ORDER)
    for k in SEG.ORDER:
        assert payload["segments"][k]["label"]
        assert payload["segments"][k]["description"]


def test_the_series_are_all_the_same_length(payload):
    s = payload["series"]
    n = len(s["days"])
    assert n > 100
    for key in ("market_cap", "players", "assets_listed", "btc"):
        assert len(s[key]) == n, f"series `{key}` is {len(s[key])} long against {n} days"
    for seg in s["segments"].values():
        for key in ("players", "cash", "assets"):
            assert len(seg[key]) == n


def test_the_2026_section_exists_only_when_phase_3_has_run(payload):
    """An empty chart that looks like a flat year is worse than an honest absence."""
    if REPORT.is_file():
        f = payload["forward_2026"]
        assert f is not None, "phase 3 has a report but the payload hides it"
        assert f["n_trades"] == f["wins"] + f["losses"]
        assert f["equity"] and f["market"]
        assert "BTCUSDT" in f["baselines"], "a result with no baseline is not a result"
    else:
        assert payload["forward_2026"] is None


def test_the_page_hard_codes_no_figures():
    """Every number on screen must come from the payload."""
    html = PAGE.read_text(encoding="utf-8")
    body = html.split("<script>")[-1]
    for suspect in ("$2.5", "$1.7", "trillion", "19,969,816", "87,664"):
        assert suspect not in body, f"the page hard-codes {suspect!r}"
    assert "fetch('api/state')" in body


def test_the_page_says_so_when_there_is_nothing_to_show():
    html = PAGE.read_text(encoding="utf-8")
    assert "has not been run" in html, (
        "the page must state that phase 3 is missing rather than drawing an empty chart")


def test_the_palette_is_the_validated_order():
    """Categorical hues are assigned in the fixed validated order, never cycled."""
    html = PAGE.read_text(encoding="utf-8")
    for slot in ("--s1:#3987e5", "--s2:#d95926", "--s3:#199e70",
                 "--s4:#c98500", "--s5:#d55181", "--s6:#008300"):
        assert slot in html.replace(" ", ""), f"palette slot {slot} is not the validated step"
    assert len(set(re.findall(r"--s\d:#[0-9a-f]{6}", html.replace(" ", "")))) == 6
