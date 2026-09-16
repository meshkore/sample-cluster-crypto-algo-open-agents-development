"""Adopt the width-192 champion: backup, promote, re-derive the bar, register.

    PYTHONPATH=trading-system python research/system06/tools/adopt_192.py

The decision this executes was made by the standing method, in this order, all on
record before the sealed year was opened:

  1. P35 verified width 192 on FOUR seeds - every seed improved, median research
     score +0.4611 against the +0.1001 bar, worst drawdown falling 28.8% -> 20.6%.
  2. The shipped seed (91002) was committed in tools/champion_192.py as the
     LOWER-MIDDLE of the four, before any further measurement - the anti-optimism
     rule this project adopted after being burned twice by headline draws.
  3. The build reproduced its P35 research score exactly (+0.4238 MATCH), and only
     then was sealed 2026 read ONCE: +32.24% at 22.5% drawdown, 91 trades - against
     the incumbent's +2.08% at 19.0%.

What it does, idempotently: backs up the incumbent's artefacts, promotes _w192/ to
the shipping paths, rewrites best.json with the full honest record (P35 verify
scores, the new reproducible bar = the P35 four-seed median, the sealed readout and
the supersession trail), stamps the model card, and registers ARCH-0005.

Stated fact, carried into every record rather than smoothed over: research 2025 is
-1.66%, so the all-years-green ideal is NOT met in research space. The score metric
prices that in (worst year + 0.1x CAGR) and still clears the bar by 4x; the
operator's governing criterion (2026-08-29) is the FORWARD year, where this book
does +32.24% vs +2.08%.
"""

from __future__ import annotations

import json
import shutil
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")
W192 = ROOT / "_w192"
BACKUP = ROOT / "prev_champion_64ch"
READOUT = json.loads(sorted(ROOT.glob("rnd/champion_192_*.json"))[-1].read_text(encoding="utf-8"))

SHIP = ("oracle_net.pt", "standardizer.json", "config.json", "model_card.json",
        "signals.npz", "meta.npz", "moneymodel.npz")
P35_SCORES = {"77101": 0.6008, "77102": 0.3857, "91001": 0.4983, "91002": 0.4238}


def main() -> int:
    sys.path.insert(0, "trading-system")
    from system006_oracle_net_15m import registry

    assert READOUT["clears_bar"] and READOUT["reproduced"], "adoption without basis"
    now = datetime.now(timezone.utc).isoformat()

    # ---- 1. backup the incumbent, once ---------------------------------------------
    BACKUP.mkdir(exist_ok=True)
    for name in SHIP:
        src = ROOT / name
        if src.is_file() and not (BACKUP / name).is_file():
            shutil.copy2(src, BACKUP / name)
    print(f"incumbent backed up -> {BACKUP}")

    # ---- 2. stamp the model card BEFORE promoting, so the shipped card is complete -
    best_old = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    card = json.loads((W192 / "model_card.json").read_text(encoding="utf-8"))
    annual = {**{y: {"return_pct": r} for y, r in READOUT["research"].items()
               if r is not None},
              "2026": dict(READOUT["sealed_2026"])}
    card["risk_layer"] = {**best_old["band"], **best_old["risk"]}
    card["risk_layer"]["meta_signals"] = str(ROOT / "meta.npz")
    card["annual_returns"] = {y: annual[y].get("return_pct") for y in sorted(annual)}
    card["consistency"] = READOUT["consistency"]
    card["selection_years"] = list(range(2018, 2026))
    card["forward_2026"] = READOUT["sealed_2026"]
    card["incumbent_2026"] = best_old["forward_2026"]["return_pct"]
    card["channels"] = READOUT["channels"]
    card["seed"] = READOUT["seed"]
    card["seed_rule"] = READOUT["selection_rule"]
    (W192 / "model_card.json").write_text(json.dumps(card, indent=2, default=str),
                                          encoding="utf-8")

    # ---- 3. promote ---------------------------------------------------------------
    for stale in ROOT.glob("oracle_net_*.pt"):   # ensemble leftovers from older champs
        stale.unlink()
    for name in SHIP:
        shutil.copy2(W192 / name, ROOT / name)
    best_dir = ROOT / "best"
    for name in ("oracle_net.pt", "standardizer.json", "config.json", "model_card.json"):
        shutil.copy2(W192 / name, best_dir / name)
    print("promoted _w192 -> shipping paths")

    # ---- 4. best.json: the full honest record --------------------------------------
    bar = round(statistics.median(P35_SCORES.values()), 4)
    best = dict(best_old)
    best["score"] = READOUT["consistency"]["score"]
    best["config"] = {**best_old["config"], "channels": READOUT["channels"]}
    best["band"] = {**best_old["band"], "meta_signals": str(ROOT / "meta.npz")}
    best["annual_returns"] = {y: r for y, r in READOUT["research"].items()}
    best["forward_2026"] = READOUT["sealed_2026"]
    best["verify_scores"] = P35_SCORES
    best["reproducible_bar"] = bar
    best["reproducible_bar_note"] = (
        "Median research score of the four P35 seeds at width 192, all four improving "
        "on the old champion. The bar a future candidate must beat is what THIS recipe "
        "reproducibly does, not what its luckiest draw did once.")
    best["superseded_2026-09-02"] = {
        "score": best_old["score"], "forward_2026": best_old["forward_2026"],
        "reproducible_bar": best_old.get("reproducible_bar"),
        "note": "64-channel incumbent; artefacts in prev_champion_64ch/"}
    best["adoption"] = {
        "at": now, "what": "model capacity 64x3 -> 192x3 channels (P34/P35/P38)",
        "seed": READOUT["seed"], "seed_rule": READOUT["selection_rule"],
        "sealed_2026": READOUT["sealed_2026"],
        "sealed_2026_incumbent": best_old["forward_2026"],
        "research_2025_negative": READOUT["research"].get("2025"),
        "note": ("First candidate to cross the operator's +30% forward target. "
                 "Research 2025 is -1.66% - the all-years-green ideal is not met in "
                 "research space and is recorded, not hidden. Drawdown 22.5% vs 19.0%: "
                 "gain per drawdown point is disproportionate (BALANCE criterion).")}
    best["at"] = now
    (ROOT / "best.json").write_text(json.dumps(best, indent=1, default=str),
                                    encoding="utf-8")
    print(f"best.json updated: score {best['score']:+.4f}, bar {bar:+.4f}")

    # ---- 5. the registry: capacity is structure ------------------------------------
    spec = {
        "title": "Narrow trend book, high-capacity net (192x3) + extreme-fear veto",
        "modules": ["oracle-nn", "meta", "stops", "regime", "sizing/money-model", "crowd"],
        "labeller": "zigzag-3pct",
        "features": ["ohlcv-causal", "trend", "vol", "momentum"],
        "universe_id": "universe.json:14",
        "timeframe": "15m",
        "universe_size": 14,
        "model": "TCN 192x192x192 (window 96, 255,937 params)",
        "pipeline": "generate(TCN-192x3)>filter>rank>size>survive",
        "status": "active",
        "levers": {"fng_min": 25, "channels": [192, 192, 192]},
    }
    row = registry.register(spec, parent="ARCH-0002", explanation=(
        "Identical decision path to ARCH-0002 - same modules, same labeller, same "
        "universe, same risk layer - with the network's capacity tripled from three "
        "64-channel layers to three 192-channel ones (36k -> 256k parameters).\n\n"
        "Why this is a new architecture and not a value change: the 64-channel net was "
        "inherited from the first version of this system and never questioned, and P35 "
        "proved it was the BINDING CONSTRAINT - every seed improved at 192, the gain "
        "was monotone in width, and drawdown FELL. Every refutation in the project "
        "ledger was measured through that too-small net, so capacity changes what the "
        "whole pipeline can express, not merely a number.\n\n"
        "Evidence: P34 (two seeds, exploratory), P35 (four seeds, median +0.4611 vs "
        "bar +0.1001), P38 champion build at seed 91002 (lower-middle of the four, "
        "committed in advance): research +0.4238 REPRODUCED, sealed 2026 +32.24% at "
        "22.5% drawdown vs incumbent +2.08% at 19.0%. Research 2025 is -1.66%: the "
        "all-years-green ideal is not met and is recorded here rather than hidden."),
        note="capacity discovery: P34/P35; champion P38")
    arch_id = row["id"]
    registry.attach_backtest(arch_id, {
        "at": now, "kind": "research-per-year", "source": "P38 tools/champion_192.py",
        "seed": READOUT["seed"], "years": READOUT["research"],
        "consistency": READOUT["consistency"], "bar": READOUT["bar"],
        "clears_bar": True, "reproduces_p35": True})
    registry.attach_backtest(arch_id, {
        "at": now, "kind": "sealed-2026-readout", "source": "P38 tools/champion_192.py",
        "seed": READOUT["seed"], "result": READOUT["sealed_2026"],
        "incumbent": READOUT["incumbent_2026"],
        "note": "single readout, opened after the research table was on record"})
    if arch_id != "ARCH-0002":
        registry.set_status("ARCH-0002", "superseded",
                            reason=f"capacity-tripled child {arch_id} adopted 2026-09-02")
    print(f"registered {arch_id} (parent ARCH-0002)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
