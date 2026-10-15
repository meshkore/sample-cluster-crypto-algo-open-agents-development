"""Freeze a release's signal layer for book-only work (book audit 2026-10-15, phase 0).

    dump   builds the World (bars through today), fits the release's walk-forward signals for
           every year 2020-2026 exactly as search.evaluate does, and writes
           rnd/book_inputs_<release>.npz (gitignored): ns, close, prob, year, size per coin and
           enter/keep/strength per year. Generalises health_study.dump (release 31 only).
    feats  the 44 market columns + breadth per bar (no fits) -> rnd/book_feats.npz, for the
           meta-labelling sizer.

Signals depend only on the non-book keys of the cfg, so any cache with the same signal id
serves every release that shares it (31, 34 and 43 share one; health_inputs.npz is reused).

    R=$(pwd -W); PYTHONPATH="$R/trading-system;$R/trading-system/systems;$R/research/system10/tools" \
        python research/system10/tools/book_inputs.py dump --release 43
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for sub in ("trading-system", "trading-system/systems", "research/system10/tools"):
    if str(REPO / sub) not in sys.path:
        sys.path.insert(0, str(REPO / sub))

RND = REPO / "research/system10/rnd"
LEGACY = RND / "health_inputs.npz"          # release 31's cache from health_study.dump
FEATS = RND / "book_feats.npz"
YEARS = (2020, 2021, 2022, 2023, 2024, 2025, 2026)
MIN_FREE_GB = 5.0


def path(n: int) -> Path:
    return RND / f"book_inputs_{int(n)}.npz"


def release(n: int | str | None = None) -> dict:
    """A release by number; None / "current" = the champion's release, read-only (unlike
    search.current_release this never publishes one)."""
    from system010_conditioned_rl import search as S
    if n in (None, "current"):
        rels = S.releases()
        champ = None if S.overfit_refusal() else S.champion(S.ledger())
        hit = [r for r in rels if champ and r["id"] == champ["id"]]
        if not (hit or rels):
            raise SystemExit("no release")
        return hit[-1] if hit else rels[-1]
    for r in S.releases():
        if int(r["n"]) == int(n):
            return r
    raise SystemExit(f"release {n} not found")


def signal_id(cfg: dict) -> str:
    from system010_conditioned_rl import search as S
    # veto and vol_target are book keys to the search but are baked into the cached masks/sizes
    return S.cfg_id({k: v for k, v in cfg.items() if k not in S.MM_KEYS or k in ("veto", "vol_target")})


def wait_for_ram(gb: float = MIN_FREE_GB, poll_s: int = 60) -> None:
    import psutil
    while True:
        free = psutil.virtual_memory().available / 1e9
        if free >= gb:
            return
        print(f"  {free:.1f} GB free < {gb:g} GB: waiting", flush=True)
        time.sleep(poll_s)


def _meta(p: Path) -> dict | None:
    try:
        with np.load(p) as z:
            return json.loads(str(z["meta"]))
    except Exception:  # noqa: BLE001
        return None


def find(cfg: dict) -> Path | None:
    """A cache whose signals match `cfg`'s signal keys and cover 2020-2025, or None."""
    sid = signal_id(cfg)
    for p in sorted(RND.glob("book_inputs_*.npz")) + [LEGACY]:
        m = _meta(p) if p.is_file() else None
        if m and signal_id(m["cfg"]) == sid and set(range(2020, 2026)) <= set(m["years"]):
            return p
    return None


def load(n: int | str | None = None) -> tuple[dict, dict, dict]:
    """(per, meta, release) for a release; meta["cfg"] is the RELEASE's cfg (its own book)."""
    rel = release(n)
    p = find(rel["cfg"])
    if p is None:
        raise SystemExit(f"no cached signals for release {rel['n']}: run `book_inputs.py dump --release {rel['n']}`")
    wait_for_ram(1.5)
    z = np.load(p)
    meta = json.loads(str(z["meta"]))
    per: dict = {}
    for k in z.files:
        if k != "meta":
            s, f = k.split("|")
            per.setdefault(s, {})[f] = z[k]
    meta = {**meta, "cfg": rel["cfg"], "source": p.name, "signal_id": signal_id(rel["cfg"])}
    return per, meta, rel


def dump(n, device: str) -> Path:
    from system010_conditioned_rl import search as S
    rel = release(n)
    if (p := find(rel["cfg"])) is not None:
        print(f"release {rel['n']}: signals already cached in {p.name} (signal id {signal_id(rel['cfg'])})")
        return p
    cfg = rel["cfg"]
    wait_for_ram()
    t0 = time.time()
    print("building the World (bars through today)...", flush=True)
    world = S.World(include_sealed=True)
    if cfg.get("features") == "full":
        world.full()
        world.x = None
    g, regime = S.gate(world, cfg)
    size = S.sizing(world, cfg)
    out: dict = {}
    for s, d in world.per.items():
        out.update({f"{s}|ns": d["ns"], f"{s}|close": d["close"], f"{s}|prob": d["prob"], f"{s}|year": d["year"],
                    f"{s}|size": size[s] if size is not None else np.ones(len(d["ns"]))})
    for N in YEARS:
        t1 = time.time()
        share, masks, keep = S.signals(world, cfg, N, g, regime, device)
        st = S.strength(world, cfg, N, g, regime, device)
        if cfg.get("veto") == "pareto":
            veto, _ = S.pareto_veto(world, cfg, N, g, regime, device)
            masks = {s: masks[s] & ~veto[s] for s in masks} if veto else masks
        for s, d in world.per.items():
            out[f"{s}|enter{N}"] = masks[s].astype(bool)
            out[f"{s}|keep{N}"] = (keep[s] if keep is not None else np.ones(len(d["ns"]), bool)).astype(bool)
            out[f"{s}|strength{N}"] = (st[s] if st is not None else np.zeros(len(d["ns"]))).astype(np.float32)
        print(f"{N}: share {share} [{(time.time() - t1) / 60:.1f} min]", flush=True)
        S._SIGNALS.clear()
    meta = {"band": world.band, "risk": world.risk, "cfg": cfg, "years": list(YEARS), "release": rel["n"],
            "symbols": list(world.per), "exit_min_hold": S.EXIT_MIN_HOLD,
            "has_keep": cfg.get("exit") == "learned"}
    out["meta"] = np.array(json.dumps(meta, default=float))
    p = path(rel["n"])
    np.savez_compressed(p, **out)
    print(f"written {p} in {(time.time() - t0) / 60:.1f} min", flush=True)
    return p


def feats() -> Path:
    """The 44 columns (float16) and breadth per bar, aligned to the inputs' bars."""
    import conditions as C
    wait_for_ram()
    t0 = time.time()
    data = C.load(C.ENGINE, include_sealed=True)
    out = {}
    for s, d in data["per"].items():
        out[f"{s}|ns"] = d["ns"]
        out[f"{s}|X"] = np.nan_to_num(d["X"], nan=0.0).astype(np.float16)
        out[f"{s}|breadth"] = d["breadth"].astype(np.float32)
    np.savez_compressed(FEATS, **out)
    print(f"written {FEATS} in {(time.time() - t0) / 60:.1f} min", flush=True)
    return FEATS


def load_feats() -> dict:
    wait_for_ram(1.5)
    z = np.load(FEATS)
    per: dict = {}
    for k in z.files:
        s, f = k.split("|")
        per.setdefault(s, {})[f] = z[k]
    return per


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=("dump", "feats", "which"))
    ap.add_argument("--release", default="current")
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    if a.stage == "dump":
        dump(a.release, a.device)
    elif a.stage == "feats":
        feats()
    else:
        r = release(a.release)
        print(r["n"], r["id"], signal_id(r["cfg"]), find(r["cfg"]))
