"""The condition search on the point-in-time universe (review round 2, R6 steps 2-3). INERT.

Runs inside a search worker only when research/system10/ENABLE_PIT_SEARCH exists when the
worker starts (empty file: every worker; else the worker names it lists, e.g. "w4"). Then:

  world     ONE union world per worker (search.World(universe="union"), pit.load_union): every
            coin of any year's PIT list (top 14, 2020-2025: 32 coins), each bar a member only in
            its own year's list - gate, training rows, breadth, take-bar pool and book read
            members only. Research bars only; 2026 is never loaded.
  trials    every trial on BOTH seed sets (search.evaluate with SEEDS, then CONFIRM_SEEDS;
            score = the weaker), so the nested choice on the confirm seeds covers every row.
            Ledger rnd/search_trials_pit.jsonl; claims rnd/search_claims_pit.jsonl; events
            rnd/events_pit.jsonl. The current ledger, card, timeline and releases are not touched.
  draws     the incumbents first (every cfg in releases/, then each with take_bar "pooled" and
            "regime"), then search.next_config; take_bar is drawn only here.
  releases  releases_pit/release_NNNN.json, only for a champion of the PIT ledger whose
            nested reading passes (overfit.nested_failures on rnd/overfit_pit.json: both nested
            curves, every pick DD <= 25%, >= 50 trades, availability) and PBO <= 0.5; each one is
            added to releases_pit/approved.json, which the mirror can require (mirror.py,
            live-trading/state/REQUIRE_PIT_APPROVAL).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import overfit as O
from . import search as S

FLAG = S.OUT / "ENABLE_PIT_SEARCH"
TRIALS = S.OUT / "rnd/search_trials_pit.jsonl"
CLAIMS = S.OUT / "rnd/search_claims_pit.jsonl"
EVENTS = S.OUT / "rnd/events_pit.jsonl"
OVERFIT = S.OUT / "rnd/overfit_pit.json"
RELEASES = S.OUT / "releases_pit"
APPROVED = RELEASES / "approved.json"
MAIN_RELEASES = S.OUT / "releases"
GATE_EVERY_S = 1800


def enabled(worker: str) -> bool:
    if not FLAG.is_file():
        return False
    names = FLAG.read_text(encoding="utf-8", errors="replace").split()
    return not names or worker in names


def bind() -> None:
    """Point search's ledger, claims, events, releases and overfit cache at the PIT files.
    Module globals of THIS process only; a default worker never calls it."""
    S.TRIALS, S.CLAIMS, S.EVENTS, S.RELEASES, S.OVERFIT = TRIALS, CLAIMS, EVENTS, RELEASES, OVERFIT
    S.DRAW_TAKE_BAR = True


def incumbents() -> list[dict]:
    """Every released cfg (newest first), then the selector ones with each take-bar option."""
    rels = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(MAIN_RELEASES.glob("release_*.json"))]
    out, seen = [], set()
    for cfg in [r["cfg"] for r in reversed(rels)]:
        if S.cfg_id(cfg) not in seen:
            seen.add(S.cfg_id(cfg))
            out.append(cfg)
    out += [{**c, "take_bar": tb} for tb in S.TAKE_BAR_STEPS[1:] for c in list(out) if c.get("selector")]
    return out


def next_config(done: list[dict], skip: set | None = None) -> dict | None:
    seen = {r["id"] for r in done} | set(skip or ())
    for cfg in incumbents():
        if S.cfg_id(cfg) not in seen:
            return cfg
    return S.next_config(done, skip)


def evaluate_both(world, cfg: dict, device: str, evaluate=None) -> dict:
    """search.evaluate on the main seeds, then on the confirm seeds; ranked by the weaker."""
    evaluate = evaluate or S.evaluate
    r = evaluate(world, cfg, device)
    main_seeds, S.SEEDS = S.SEEDS, S.CONFIRM_SEEDS
    try:
        c = evaluate(world, cfg, device)
    finally:
        S.SEEDS = main_seeds
    r["confirm"] = {k: c[k] for k in ("score", "worst_year", "cagr", "max_dd", "eligible", "years")}
    r["score_first"] = r["score"]
    r["score"] = min(r["score"], c["score"])
    r["worst_year"] = min(r["worst_year"], c["worst_year"])
    r["max_dd"] = max(r["max_dd"], c["max_dd"])
    r["universe"] = "pit-union"
    return r


def gate(done: list[dict], path: Path | None = None) -> dict:
    """overfit.measure on the PIT ledger + the nested eligibility verdict -> overfit_pit.json."""
    path = path or OVERFIT
    doc = O.measure(done, S._champion_raw(done), S.guarded, S.operates)
    fails = O.nested_failures(doc, done)
    if doc.get("pbo") is not None and doc["pbo"] > O.PBO_MAX:
        fails.append(f"PBO {doc['pbo']} > {O.PBO_MAX}")
    doc["nested_gate"] = {"passes": not fails, "why": fails}
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return doc


def approve(rel: dict, doc: dict, path: Path | None = None) -> None:
    path = path or APPROVED
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cur = {"approved": []}
    if rel["id"] not in {a["id"] for a in cur["approved"]}:
        cur["approved"].append({"n": rel["n"], "id": rel["id"], "at": S._now(),
                                "nested": (doc.get("nested") or {}).get("curve"),
                                "nested_confirm": (doc.get("nested_confirm") or {}).get("curve"),
                                "pbo": doc.get("pbo")})
    cur["updated"] = S._now()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def publish(done: list[dict], worker: str) -> dict | None:
    """Release the PIT champion only if its nested reading passes; approve it."""
    champ = S._champion_raw(done)
    if champ is None or any(r["id"] == champ["id"] for r in S.releases()):
        return None
    doc = gate(done)
    if not doc["nested_gate"]["passes"]:
        return None
    rel = S.release(champ, worker)
    if rel is None:
        return None
    p = S.RELEASES / f"release_{rel['n']:04d}.json"
    row = {**rel, "universe": "pit-union", "pit_nested": doc["nested_gate"],
           "nested_confirm": (doc.get("nested_confirm") or {}).get("curve")}
    p.write_text(json.dumps(row, indent=1, default=str), encoding="utf-8")
    approve(rel, doc)
    return rel


def run(worker: str, hours: float, device: str) -> int:
    bind()
    started = time.time()
    print(f"[{S._now()}] worker {worker}: PIT search (ENABLE_PIT_SEARCH) - loading the union world", flush=True)
    world = S.World(universe="union")
    print(f"[{S._now()}] worker {worker}: {len(world.per)} coins, {len(S.ledger())} PIT trials", flush=True)
    last_gate = 0.0
    while time.time() - started < hours * 3600 and not S.STOP.exists():
        done = S.ledger()
        cfg = next_config(done, skip=S.claimed())
        if cfg is None:
            time.sleep(300)
            continue
        S.claim(cfg, worker)
        r = evaluate_both(world, cfg, device)
        r["worker"] = worker
        with S.TRIALS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r, default=str) + "\n")
        tag = ""
        if time.time() - last_gate > GATE_EVERY_S or (S._champion_raw(S.ledger()) or {}).get("id") == r["id"]:
            rel = publish(S.ledger(), worker)
            last_gate = time.time()
            tag = f"  <- PIT RELEASE {rel['n']} (approved)" if rel else ""
        print(f"[{S._now()}] {worker} PIT trial {r['id']} {json.dumps(cfg)} -> score {r['score']:+.4f} "
              f"worst {r['worst_year']:+.1%} dd {r['max_dd']:.0%} {'ELIGIBLE' if r['eligible'] else 'ineligible'}"
              f" [{r['minutes']:.1f}m]{tag}", flush=True)
    return 0
