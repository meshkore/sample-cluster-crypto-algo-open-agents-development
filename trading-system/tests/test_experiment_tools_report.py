"""An experiment tool must be able to report the arms it actually ran.

2026-09-07: both recency tools crashed in their final block with
KeyError: 'wf23_single' - an arm name from the experiment they had been copied
from. Every training, every backtest and every printed exam number was fine; the
adjudication and the json were lost, and the crash arrived HOURS after launch, at
the one moment the run had something to say.

The class of bug is copy-and-rewrite tool authoring: a string replacement that
silently matches nothing leaves the previous experiment's report block in place, and
nothing complains until the arms have already cost their GPU hours. A syntax check
does not catch it because the code is valid; only running to the end does, and that
is exactly what is expensive.

So this greps every research tool for the arm names its report block indexes, and
requires them to exist in that file's own ARMS table. Cheap, textual, and it fails at
commit time rather than after a six-hour run.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "research/system06/tools"


def _tools_with_arms():
    for path in sorted(TOOLS.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^ARMS\s*=", text, re.M):
            yield path, text


def test_there_are_arm_based_tools_to_check():
    assert list(_tools_with_arms()), "no ARMS-based tools found; the guard would be vacuous"


@pytest.mark.parametrize("path", [p for p, _ in _tools_with_arms()],
                         ids=lambda p: p.stem)
def test_every_results_key_the_report_uses_is_an_arm_of_that_tool(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text)

    arms: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "ARMS" for t in node.targets):
            if isinstance(node.value, ast.Dict):
                arms = {k.value for k in node.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert arms, f"{path.name}: ARMS is not a literal dict of string keys"

    used = set(re.findall(r'results\[\s*"([^"]+)"\s*\]', text))
    unknown = used - arms
    assert not unknown, (
        f"{path.name}: the report indexes results{sorted(unknown)} but its ARMS are "
        f"{sorted(arms)} - almost certainly a report block copied from another "
        f"experiment, which crashes only after every arm has run")
