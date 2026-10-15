"""System 10 review round 2, items 4-5 (R6 steps 2-3, take-bar option): the PIT search and the
take-bar choice are INERT without ENABLE_PIT_SEARCH; the default draws and selector are pinned
to the code before the change."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research/system10/tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from system010_conditioned_rl import search as S  # noqa: E402
from test_system010_round2_nested import CFG100, _ledger  # noqa: E402

# Digests of the code BEFORE round 2 (HEAD fa3dd5a), computed with the same helpers.
PIN_DRAWS = "e182754f7a117b6234ad0f06d5d2313fbc789f72"
PIN_SELECTOR = {100: "0.2:6b0e69cb87fea0de45c52f223eaaa7696f9cb82b|0.2:facde62426181f000c04ef977bf3b726291948d1",
                None: "0.2:9ab85d391888b91eb053b9c21f42f323345b0b3d|0.2:257cf8690ad17140c8976bfe5f39cd8f9d257a86"}
CFG1 = {"regime_ma": None, "b_up": 0.5, "b_down": 0.5, "selector": True, "horizon": 384}


# ------------------------------------------------------------------ a small fake World

class FakeWorld:
    """Enough of search.World for selector_masks: 3 coins, 2016-2023, 400 bars a year."""

    def __init__(self, seed=0):
        rng = np.random.default_rng(seed)
        self.per, self.x, self.valid, self._out = {}, {}, {}, {}
        years = np.repeat(np.arange(2016, 2024), 400)
        for k, s in enumerate(("BTCUSDT", "AAAUSDT", "BBBUSDT")):
            X = rng.normal(0, 1, (len(years), 5)).astype(np.float32)
            self.per[s] = {"X": X, "year": years, "breadth": rng.uniform(0, 1, len(years)),
                           "ns": np.arange(len(years), dtype=np.int64)}
            self.x[s] = X
            self.valid[s] = np.ones(len(years), bool)
            net = 0.01 * X[:, 0] + rng.normal(0, 0.01, len(years))
            self._out[s] = {"idx": np.arange(len(years)), "net": net, "mae": np.abs(rng.normal(0, 0.005, len(years))),
                            "end_year": years}

    def feats(self, cfg):
        return self.x

    def outcomes(self, horizon):
        return self._out

    def book(self, masks, year, horizon, size=None, *a, **k):
        """trades = bars taken; q = mean of the first column on them minus a cost per trade."""
        took = np.concatenate([masks[s][self.per[s]["year"] == year] for s in self.per])
        col = np.concatenate([self.per[s]["X"][self.per[s]["year"] == year, 0] for s in self.per])
        n = int(took.sum())
        return {"trades": n, "q": round(float(col[took].mean()) - 0.002 * n / 100 if n else -1.0, 4)}


def _stub_models(monkeypatch):
    """Deterministic scorers instead of torch fits: a seed-fixed linear map of the features."""
    class M:
        def __init__(self, w):
            self.w = w

    def fit(X, Y, seed, device, epochs=6):
        w = np.random.default_rng(seed + len(X)).normal(0, 1, X.shape[1])
        w[0] += 2 * float(np.sign(np.corrcoef(X[:, 0], Y)[0, 1]))
        return M(w)

    monkeypatch.setattr(S.B, "fit", fit)
    monkeypatch.setattr(S.B, "score", lambda m, x, device: (x @ m.w).astype(np.float32))


def _gate(world, regime_ma=100):
    g = {s: np.ones(len(d["year"]), bool) for s, d in world.per.items()}
    up = {s: (np.arange(len(d["year"])) // 150) % 3 != 0 for s, d in world.per.items()}
    if regime_ma is None:
        up = {s: np.ones(len(d["year"]), bool) for s, d in world.per.items()}
    return g, up


def _mask_digest(masks) -> str:
    h = hashlib.sha1()
    for s in sorted(masks):
        h.update(np.packbits(masks[s]).tobytes())
    return h.hexdigest()


def _selector_digest(monkeypatch, cfg=None) -> str:
    _stub_models(monkeypatch)
    w = FakeWorld()
    cfg = cfg or {"regime_ma": 100, "b_up": 0.5, "b_down": 0.0, "selector": True, "horizon": 384}
    g, up = _gate(w, cfg["regime_ma"])
    out = []
    for N in (2022, 2023):
        share, masks_for = S.selector_masks(w, cfg, g, up, N - 2, N - 1, "cpu")
        out.append(f"{share}:{_mask_digest(masks_for(share, N - 1))}")
    return "|".join(out)


def _draws_digest() -> str:
    cfgs = [{"regime_ma": 100, "b_up": 0.5, "b_down": 0.0, "selector": True, "horizon": 768, "size_down": 0.75,
             "exit": "learned", "features": "full", "slots": 5, "size_signal": 0.01, "dd_scale": 0.35,
             "scale_in": True, "stop": 0.12, "mom_days": 90, "mom_rank": 7}] + S.SEED_CONFIGS
    h = hashlib.sha1()
    for c in cfgs:
        for n in S.neighbours(c):
            h.update(json.dumps(n, sort_keys=True).encode())
    rng = np.random.default_rng(123)
    for _ in range(200):
        h.update(json.dumps(S.random_config(rng), sort_keys=True).encode())
    return h.hexdigest()


# ------------------------------------------------------------------ item 5: take-bar option

def test_default_draws_pinned():
    assert not S.DRAW_TAKE_BAR
    assert _draws_digest() == PIN_DRAWS


def test_default_selector_pinned(monkeypatch):
    assert _selector_digest(monkeypatch, CFG100) == PIN_SELECTOR[100]
    assert _selector_digest(monkeypatch, CFG1) == PIN_SELECTOR[None]


def test_take_bar_is_drawn_only_in_a_pit_search(monkeypatch):
    rng = np.random.default_rng(7)
    assert not any("take_bar" in c for c in S.neighbours(CFG100))
    assert not any("take_bar" in S.random_config(rng) for _ in range(300))
    monkeypatch.setattr(S, "DRAW_TAKE_BAR", True)
    assert {c.get("take_bar") for c in S.neighbours(CFG100)} >= {"pooled", "regime"}
    assert not any("take_bar" in c for c in S.neighbours({**CFG100, "selector": False}))
    assert any("take_bar" in S.random_config(rng) for _ in range(300))


def test_pick_share_pooled_ignores_one_regime_year():
    bull = {(None, s): (500, 8.0 if s == 0.1 else 5.5) for s in S.SHARES}            # 2021: 10% wins
    earlier = [{(None, s): (500 if s >= 0.3 else 20, 4.0 if s == 0.5 else 1.0) for s in S.SHARES}] * 3
    assert S.pick_share([bull], None) == 0.1                   # one year = today's choice
    assert S.pick_share(earlier + [bull], None) == 0.5        # pooled: the share that trades every year


def test_take_bar_pooled_and_regime_on_a_fake_world(monkeypatch):
    _stub_models(monkeypatch)
    S._SHARE_KEYS.clear()
    w = FakeWorld()
    for cfg in (CFG100, CFG1):
        g, up = _gate(w, cfg["regime_ma"])
        sh, mf = S.selector_masks(w, {**cfg, "take_bar": "pooled"}, g, up, 2021, 2022, "cpu")
        assert sh in S.SHARES and mf(sh, 2022)["AAAUSDT"].dtype == bool
    assert {y for (_, y) in S._SHARE_KEYS} >= {2020, 2021, 2022}      # every choose-year since TAKE_BAR_FROM
    g, up = _gate(w, 100)
    sh, mf = S.selector_masks(w, {**CFG100, "take_bar": "regime"}, g, up, 2021, 2022, "cpu")
    assert set(sh) == {"up", "down"} and sh["up"] in S.SHARES and sh["down"] in S.SHARES
    m = mf(sh, 2022)
    assert all((m[s] <= g[s]).all() for s in m)
    assert _selector_digest(monkeypatch, CFG100) == PIN_SELECTOR[100]   # default untouched by the caches



# ------------------------------------------------------------------ item 4: PIT search

from system010_conditioned_rl import pit as PIT  # noqa: E402
from system010_conditioned_rl import pit_search as PS  # noqa: E402


def test_pit_search_is_off_without_its_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(PS, "FLAG", tmp_path / "ENABLE_PIT_SEARCH")
    assert not PS.enabled("w1")
    PS.FLAG.write_text("")
    assert PS.enabled("w1") and PS.enabled("w4")
    PS.FLAG.write_text("w4\n")
    assert PS.enabled("w4") and not PS.enabled("w1")
    # importing it changed nothing in search
    assert S.TRIALS.name == "search_trials.jsonl" and S.RELEASES.name == "releases" and not S.DRAW_TAKE_BAR


def test_bind_points_search_at_the_pit_files(monkeypatch):
    for k in ("TRIALS", "CLAIMS", "EVENTS", "RELEASES", "OVERFIT", "DRAW_TAKE_BAR"):
        monkeypatch.setattr(S, k, getattr(S, k))
    PS.bind()
    assert S.TRIALS.name == "search_trials_pit.jsonl" and S.RELEASES.name == "releases_pit"
    assert S.OVERFIT.name == "overfit_pit.json" and S.CLAIMS.name == "search_claims_pit.jsonl" and S.DRAW_TAKE_BAR


def test_incumbents_first_then_take_bar_variants(tmp_path, monkeypatch):
    for n, cfg in ((1, CFG1), (2, CFG100), (3, CFG100)):
        (tmp_path / f"release_{n:04d}.json").write_text(json.dumps({"n": n, "cfg": cfg}))
    monkeypatch.setattr(PS, "MAIN_RELEASES", tmp_path)
    inc = PS.incumbents()
    assert inc[:2] == [CFG100, CFG1] and {c.get("take_bar") for c in inc[2:]} == {"pooled", "regime"}
    assert PS.next_config([{"id": S.cfg_id(CFG100)}]) == CFG1


def test_evaluate_both_runs_the_confirm_seeds_and_restores_them():
    seen = []

    def ev(world, cfg, device):
        seen.append(S.SEEDS)
        k = 0.3 if S.SEEDS == S.CONFIRM_SEEDS else 0.5
        return {"score": k, "worst_year": k, "cagr": k, "max_dd": k / 2, "eligible": True, "years": {}}
    r = PS.evaluate_both(None, CFG100, "cpu", ev)
    assert seen == [S.SEEDS, S.CONFIRM_SEEDS] and S.SEEDS != S.CONFIRM_SEEDS
    assert r["score"] == 0.3 and r["score_first"] == 0.5 and r["confirm"]["score"] == 0.3


def _pit_env(tmp_path, monkeypatch, rows):
    led = tmp_path / "trials.jsonl"
    led.write_text("".join(json.dumps(r) + "\n" for r in rows))
    for k, v in (("TRIALS", led), ("EVENTS", tmp_path / "events.jsonl"), ("RELEASES", tmp_path / "rel"),
                 ("OVERFIT", tmp_path / "of.json"), ("NESTED_FLAG", tmp_path / "nope")):
        monkeypatch.setattr(S, k, v)
    monkeypatch.setattr(PS, "OVERFIT", tmp_path / "of.json")
    monkeypatch.setattr(PS, "APPROVED", tmp_path / "rel" / "approved.json")


def test_pit_release_only_when_the_nested_reading_passes(tmp_path, monkeypatch):
    bad = _ledger(n=12)
    for r in bad:
        r["years"]["2024"]["trades"] = 10
        r["confirm"]["years"]["2024"]["trades"] = 10
    _pit_env(tmp_path, monkeypatch, bad)
    assert PS.publish(S.ledger(), "w4") is None and not S.RELEASES.exists()
    assert not json.loads(PS.OVERFIT.read_text())["nested_gate"]["passes"]

    good = _ledger(n=12)
    for i, r in enumerate(good):        # a consistent ranking, so PBO is low too
        for side in (r["years"], r["confirm"]["years"]):
            for v in side.values():
                v["return"] = 0.05 + 0.02 * i
        r["score"] = S.law(r["years"], max(v["max_dd"] for v in r["years"].values()))
    _pit_env(tmp_path, monkeypatch, good)
    rel = PS.publish(S.ledger(), "w4")
    assert rel and rel["n"] == 1
    row = json.loads((S.RELEASES / "release_0001.json").read_text())
    assert row["pit_nested"]["passes"] and row["universe"] == "pit-union"
    assert [a["id"] for a in json.loads(PS.APPROVED.read_text())["approved"]] == [rel["id"]]
    assert PS.publish(S.ledger(), "w4") is None                        # released once


def test_membership_and_member_breadth():
    y = np.repeat([2019, 2020, 2021], 4)
    ns = np.arange(len(y), dtype=np.int64)
    per = {s: {"year": y, "ns": ns, "present": np.ones(len(y), bool), "trend": np.full(len(y), t)}
           for s, t in (("BTCUSDT", 1.0), ("AAAUSDT", 1.0), ("BBBUSDT", -1.0))}
    lists = {2020: ["BTCUSDT", "AAAUSDT"], 2021: ["BTCUSDT", "BBBUSDT"]}
    m = PIT.membership(per, lists)
    assert m["AAAUSDT"].tolist() == [True] * 8 + [False] * 4           # 2019 uses 2020's list
    assert m["BBBUSDT"].tolist() == [False] * 8 + [True] * 4
    PIT.breadth_members(per, m)
    assert per["BTCUSDT"]["breadth"].tolist() == [1.0] * 8 + [0.5] * 4  # BBB (down) counts only in 2021
    assert per["BBBUSDT"]["breadth"].tolist() == [1.0] * 8 + [0.5] * 4  # a non-member reads the members'


def _fake_union():
    y = np.repeat([2021, 2022], 50)
    rng = np.random.default_rng(0)
    per = {s: {"X": rng.normal(0, 1, (len(y), 3)), "year": y, "ns": np.arange(len(y), dtype=np.int64),
               "close": np.ones(len(y)), "breadth": np.ones(len(y))} for s in ("BTCUSDT", "AAAUSDT", "BBBUSDT")}
    member = {"BTCUSDT": np.ones(len(y), bool), "AAAUSDT": y == 2021, "BBBUSDT": y == 2022}
    return {"per": per, "band": {}, "risk": {}, "member": member}


def test_union_world_gates_trains_and_books_members_only(monkeypatch):
    monkeypatch.setattr(PIT, "load_union", lambda cap: _fake_union())
    w = S.World(universe="union")
    assert w.valid["AAAUSDT"].sum() == 50 and not w.valid["AAAUSDT"][50:].any()
    assert w.per["AAAUSDT"]["X"].shape == (100, 0) and w.x["AAAUSDT"].shape == (100, 3)
    got = []
    monkeypatch.setattr(w.C, "book_year", lambda per, *a, **k: got.append(sorted(per)) or {})
    w.book({}, 2022, 96)
    w.book({}, 2021, 96)
    assert got == [["BBBUSDT", "BTCUSDT"], ["AAAUSDT", "BTCUSDT"]]


def test_default_world_books_every_coin(monkeypatch):
    w = S.World.__new__(S.World)
    data = _fake_union()
    w.per, w.band, w.risk, w.C = data["per"], {}, {}, S._tools()
    got = []
    monkeypatch.setattr(w.C, "book_year", lambda per, *a, **k: got.append(per) or {})
    w.book({}, 2022, 96)
    assert got[0] is w.per                                            # no member attribute: untouched
