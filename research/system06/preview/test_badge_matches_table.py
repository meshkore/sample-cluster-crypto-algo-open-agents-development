"""The consistency badge must never contradict the table printed beside it.

Three times now a derived value stored next to its inputs has gone stale because only
the LOOP updates it and the last champions were adopted by hand: champion_curves.json
(the equity paths), and best.json's `consistency` - which on 2026-09-03 claimed
"positive every year / worst year +5.1%" while its own annual_returns said 2025 = -2.96%.

The badge is the operator's consistency law rendered as one word, so a wrong one is the
most expensive wrong pixel on the page. mock_server now DERIVES it; this pins that.

Run: python research/system06/preview/test_badge_matches_table.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mock_server as ms

RESEARCH = [str(y) for y in range(2018, 2026)]     # 2026 is sealed, never counted


def _check(card, label):
    ann = card.get("annual") or {}
    rets = [v for y, v in ann.items() if y in RESEARCH and v is not None]
    if not rets:
        return []
    bad = []
    worst = min(rets)
    if card.get("min_year") is not None and abs(card["min_year"] - worst) > 1e-6:
        bad.append(f"{label}: worst-year says {card['min_year']:+.4f}, table says {worst:+.4f}")
    expected = worst > 0
    if bool(card.get("all_positive")) != expected and expected is False:
        bad.append(f"{label}: badge says all_positive={card.get('all_positive')} "
                   f"but {sum(1 for r in rets if r < 0)} year(s) are negative")
    return bad


def main() -> int:
    failures = []

    best = ms._best_card(ms._load(ms.BEST))
    if best:
        failures += _check(best, "champion")

    for card in ms._state().get("history", []):
        failures += _check(card, f"iter {card.get('iteration')}")

    # And the specific regression: the shipping champion has a losing year, so its badge
    # must not claim otherwise. If a future champion is genuinely all-green this asserts
    # the badge agrees with THAT, not that it stays False.
    if best:
        ann = best.get("annual") or {}
        neg = [y for y in RESEARCH if ann.get(y) is not None and ann[y] < 0]
        if neg and best.get("all_positive"):
            failures.append(f"champion: negative years {neg} but badge says all-positive")

    if failures:
        print("BADGE DISAGREES WITH ITS OWN TABLE:")
        for f in failures:
            print("  -", f)
        return 1
    print("OK: every card's badge matches the years it prints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
