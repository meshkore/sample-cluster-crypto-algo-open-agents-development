"""Every published card carries its 2026 readout - and the seal survives it.

The operator (2026-08-29): the forward year is the only untrained evidence of
quality, so no published backtest may omit it. That is now computed for EVERY
iteration, which puts the sealed year in front of the loop's eyes on every cycle.
These tests are the compensating guard: the readout must remain a READOUT.
"""
import inspect
import re

from quantlab_system06 import autoloop


def test_the_readout_is_computed_after_every_selection_decision():
    """Order is the seal: if the readout were computed before the promotion decision,
    a future edit could quietly branch on it."""
    src = inspect.getsource(autoloop.run)
    readout = src.index('record["forward_2026"] = {k: r26_ro.get(k)')
    decision = src.index("improved = (_promotion_survives(")
    score_written = src.index('record["score"] = score')
    assert decision < readout, "the promotion decision must be made BEFORE the readout"
    assert score_written < readout, "the score must be written BEFORE the readout"


def test_selection_functions_never_look_at_the_forward_year():
    """The scoring path must be blind to 2026 - checked on the parsed CODE, not the text.

    Docstrings and comments may discuss the seal (they should); what must never appear
    is an executable reference - the literal year, or the readout key.
    """
    import ast
    import textwrap

    for fn in (autoloop._consistency, autoloop._is_candidate, autoloop._promotion_survives,
               autoloop._select_risk_years):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                if node.value == 2026 or (isinstance(node.value, str)
                                          and "forward_2026" in node.value):
                    # a docstring is a Constant too - skip the ones that ARE docstrings
                    offenders.append(node)
            elif isinstance(node, ast.Name) and node.id == "forward_2026":
                offenders.append(node)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module,
                                 ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None and node.body:
                    first = node.body[0]
                    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                        docstrings.add(id(first.value))
        real = [n for n in offenders if id(n) not in docstrings]
        assert not real, (
            f"{fn.__name__} executes a reference to the sealed year - selection must be "
            f"blind to it (line {real[0].lineno} of the function)")


def test_research_years_stop_before_the_lock():
    assert max(autoloop.RESEARCH_YEARS) == 2025
    assert 2026 not in autoloop.RESEARCH_YEARS


def test_the_dashboard_prefers_the_per_iteration_readout():
    from pathlib import Path
    ms = Path(__file__).resolve().parents[2] / "research/system06/preview/mock_server.py"
    src = ms.read_text(encoding="utf-8", errors="ignore")
    assert 'rec.get("forward_2026")' in src, (
        "iteration cards must read their own readout, not only the promoted portfolio")
    html = (ms.parent / "dashboard.html").read_text(encoding="utf-8", errors="ignore")
    assert "only computed on promotion" not in html, (
        "that message is obsolete: every new card carries its 2026 figure")


def test_the_champion_card_shows_its_2026_figure():
    """The card that matters most was the only one without a 2026 number: iteration
    cards merge `forward_2026` into their annual row, the champion card did not, and
    the champion keeps its sealed readout there rather than in `annual_returns`."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2]
           / "research/system06/preview/mock_server.py").read_text(encoding="utf-8")
    best_fn = src[src.index("def _best_card"):src.index("def _variants")]
    assert '"2026" not in annual' in best_fn and "forward_2026" in best_fn, (
        "the champion card must merge its sealed readout into the annual row")
