"""The strategy explainer the operator asked for must stay wired to real parameters."""
import re
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[2] / "research/system06/preview/dashboard.html"
HTML = PAGE.read_text(encoding="utf-8", errors="ignore")


def test_the_theory_and_the_diagram_are_tabs_on_every_strategy():
    """They used to live behind a modal button reachable only from a strategy card.

    Operator, 2026-09-03: "tanto la teoria como el diagrama deben formar parte no solo
    del desarrollo en curso, sino de las estrategias que se han quedado ya registradas" -
    he wants to read the CHAMPION's reasoning and flow in order to suggest improvements
    to it. So both are first-class panels, on the live view and on every archived
    strategy, and each gets the whole pane instead of sharing a scroll with the figures.
    """
    assert "function theoryPanel" in HTML and "function diagramPanel" in HTML
    assert "setDetailTab('teo')" in HTML and "setDetailTab('dia')" in HTML
    assert "setLiveTab('theory')" in HTML and "setLiveTab('diagram')" in HTML
    # the modal is gone, and nothing may still call into it
    for dead in ("openHow(", "closeHow(", 'id="howModal"'):
        assert dead not in HTML, f"{dead} survived the move to tabs"


def test_the_diagram_is_drawn_from_the_strategy_own_parameters():
    """A hand-written diagram would drift from what the strategy does; this one is
    generated from the card's risk layer and band, so an inactive stage cannot appear."""
    fn = HTML[HTML.index("function flowGraph"):HTML.index("function flowChartSVG")]
    for lever in ("meta_margin", "breadth_gate", "fng_min", "min_age_days",
                  "max_positions", "regime_deploy", "money_model",
                  "stop_loss", "trail_stop", "max_drawdown"):
        assert lever in fn, f"the diagram ignores {lever}, so it could show a false picture"
    assert "risk_layer" in fn and "band" in fn


def test_the_forward_year_is_the_headline_of_the_theory_panel():
    """Operator, 2026-08-30: 2026 leads every table - it is the only untrained evidence."""
    panel = HTML[HTML.index("function theoryPanel"):]
    assert "forward_2026" in panel
    assert panel.index("2026 (sealed)") < panel.index("Universe"), (
        "the sealed forward year must come first in the spec grid")


def test_the_theory_panel_states_the_real_sizing_formula():
    panel = HTML[HTML.index("function theoryPanel"):]
    assert "position_fraction + (regime_deploy" in panel
    assert "equity × deploy ÷ max_positions" in panel
    # market impact is part of what every order actually pays; it belongs in the formulas
    assert "√(order ÷ candle volume)" in panel


def test_the_diagram_shows_rejection_and_the_cycle_not_just_a_column():
    """The old drawing was a single vertical chain. The operator rejected it: a trading
    system fans a candidate out to every filter, sends refusals BACK, and loops. Those
    three edge kinds are what make it a flow chart rather than a list."""
    fn = HTML[HTML.index("function flowGraph"):HTML.index("function flowChartSVG")]
    for kind in ('"fan"', '"reject"', '"cycle"', '"pass"'):
        assert kind in fn, f"the diagram has no {kind} edges, so it is still a list"
    assert 'node("reject"' in fn, "a refused candidate must have somewhere to go ON the page"


def test_no_diagram_text_is_clipped_by_its_box():
    """Box height follows the wrapped text, not the other way round - the first pass cut
    'para salir' off three boxes and the operator asked for readable type."""
    fn = HTML[HTML.index("const FLOW_WRAP"):HTML.index("function flowChartSVG")]
    assert "const flowH = sub =>" in fn, "boxes must be sized from their own text"
    assert "flowH(g.s)" in fn, "the gate stack must use each gate's own height"


def test_the_page_still_declares_long_only():
    assert "Long-only" in HTML or "long-only" in HTML


def test_braces_balance():
    assert HTML.count("{") == HTML.count("}"), "unbalanced braces would break the page"


def test_the_public_page_is_in_english():
    """The page is a public, open experiment and has always been English-facing.

    Operator, 2026-09-04: "revisa que todo lo que exponemos publicamente en el front end
    esta en ingles". Two days of new panels went in in Spanish purely because that is the
    language we were talking in - a conversation language is not a product language, and
    the distinction is easy to lose when the same person writes both.

    Only USER-VISIBLE text is checked. Source comments may quote the operator verbatim:
    a quotation is evidence of why the code is the way it is, and translating it would
    destroy that.
    """
    import re

    body = HTML[HTML.index("<body>"):]
    # strip block comments and single-line // notes before looking for Spanish
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    body = re.sub(r"^\s*//.*$", " ", body, flags=re.M)

    spanish = re.compile(
        r"\b(el|la|los|las|del|una|unos|para|con|que|cada|todos|todas|nuestro|nuestra|"
        r"desde|hasta|sobre|entre|sin|mismo|misma|año|años|vela|velas|dinero|"
        r"beneficio|operaciones|estrategia|mercado|sellado|iteraciones)\b", re.I)
    hits = sorted({m.group(0).lower() for m in spanish.finditer(body)})
    assert not hits, f"Spanish reached the public page: {hits}"


def test_the_iterations_page_is_in_english_too():
    """The full-log page is public as well and was written entirely in Spanish."""
    page = (Path(__file__).resolve().parents[2]
            / "research/system06/preview/iterations.html").read_text(encoding="utf-8")
    for spanish in ("Todas las iteraciones", "Volver al panel", "Peor año",
                    "Hipótesis", "Cargando", "iteraciones ·"):
        assert spanish not in page, f"{spanish!r} is still on the public iterations page"
    assert "Every iteration" in page and "Worst year" in page
