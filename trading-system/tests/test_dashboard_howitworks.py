"""The strategy explainer the operator asked for must stay wired to real parameters."""
import re
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[2] / "research/system06/preview/dashboard.html"
HTML = PAGE.read_text(encoding="utf-8", errors="ignore")


def test_the_button_and_its_modal_exist():
    assert "how-btn" in HTML and "openHow()" in HTML
    assert 'id="howModal"' in HTML


def test_the_diagram_is_drawn_from_the_strategy_own_parameters():
    """A hand-written diagram would drift from what the strategy does; this one is
    generated from the card's risk layer and band, so an inactive stage cannot appear."""
    fn = HTML[HTML.index("function flowStages"):HTML.index("function flowSVG")]
    for lever in ("meta_margin", "breadth_gate", "fng_min", "min_age_days",
                  "max_positions", "regime_deploy", "money_model", "scale_in",
                  "stop_loss", "trail_stop", "max_drawdown"):
        assert lever in fn, f"the diagram ignores {lever}, so it could show a false picture"
    assert "risk_layer" in fn and "band" in fn


def test_the_forward_year_is_the_headline_of_the_modal():
    """Operator, 2026-08-30: 2026 leads every table - it is the only untrained evidence."""
    modal = HTML[HTML.index("function howModal"):HTML.index("function openHow")]
    assert "forward_2026" in modal
    assert modal.index("Forward year 2026") < modal.index("Universe"), (
        "the sealed forward year must come first in the spec grid")


def test_the_modal_states_the_real_sizing_formula():
    modal = HTML[HTML.index("function howModal"):HTML.index("function openHow")]
    assert "position_fraction + (regime_deploy" in modal
    assert "equity × deploy ÷ max_positions" in modal


def test_the_page_still_declares_long_only():
    assert "Long-only" in HTML or "long-only" in HTML


def test_braces_balance():
    assert HTML.count("{") == HTML.count("}"), "unbalanced braces would break the page"
