import re
from pathlib import Path

from system12.config import RECORD
from system12.web import pages

ROOT = Path(__file__).resolve().parent.parent


def test_markdown_renders_the_doc_subset():
    html = pages.markdown("# T\n\npara **b** `c`\n\n- one\n- two\n\n1. first\n\n| a | b |\n|---|---|\n| 1 | <x> |\n")
    assert "<h1>T</h1>" in html and "<strong>b</strong>" in html and "<code>c</code>" in html
    assert "<ul><li>one</li><li>two</li></ul>" in html and "<ol><li>first</li></ol>" in html
    assert "<td>&lt;x&gt;</td>" in html


def test_live_page_shows_state_and_years():
    state = {
        "updated": "2026-10-26T08:00:00+00:00",
        "start": "2026-10-22T16",
        "book_usd": 50_000.0,
        "ret": -0.01,
        "equity_usd": 49_500.0,
        "max_dd": 0.02,
        "curve": [["a", 1.0], ["b", 0.99]],
        "target": {"BTC": 0.2},
        "net_exposure": 0.2,
        "as_of_bar": "2026-10-26T04:00",
        "btc": 80_000.0,
    }
    html = pages.live(state, {2025: (0.09, 0.21, -0.06), 2026: (0.03, 0.11, -0.08)})
    assert "$49,500" in html and "2026 YTD" in html and "<svg" in html


def test_architecture_record_matches_record_json():
    md = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    row = next(line for line in md.splitlines() if line.startswith("| System 12 (champion v6)"))
    cells = [c.strip() for c in row.strip("|").split("|")[1:]]
    assert cells == [f"{RECORD['years'][y]['ret'] * 100:+.0f}%" for y in sorted(RECORD["years"])]


def test_docs_name_only_files_that_exist():
    for doc in ("README.md", "docs/ARCHITECTURE.md", "docs/RESULTS.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        for path in re.findall(r"`((?:system12|docs|tests|scripts)/[\w./-]+)`", text):
            assert (ROOT / path).exists(), f"{doc} names {path}"
