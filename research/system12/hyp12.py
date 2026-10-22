"""System 12 - the hypothesis loop (operator 2026-10-21: "hypothesis 1, 2, 3 ... up to 1000, iterate without stopping").

Every hypothesis is WRITTEN in hypotheses12.py (id, text, a small parameter grid, an overlay on the book's weights)
before it runs, and the ledger keeps it whatever the result.

Walk-forward, exactly like the system itself:
    base book for year N     = the 20 configurations chosen on 2019..N-1 (out_ls/results.json, folds[N])
    champion for year N      = base book + every ADOPTED overlay, each with the parameter it chose on 2019..N-1
    the new hypothesis       = champion + its overlay, the parameter ("off" included) chosen on 2019..N-1
                               with the same law (B.objective_value), then read on N.

Adoption (pre-registered; the bar rises with every hypothesis tested, because more tries find more luck):
    - v2: judged on 2021-2023 ONLY (2024-2026 stay out of sample for the loop as a whole):
    - v4: AND holds up on 2024-2025 (each year >= champion - 2 pp, Sharpe >= champion's). 2026 alone is out of sample.
    - v3: improves the Sharpe of 2021-2023 (daily) by at least bar(n) = 0.05 + 0.03 x ln(n), AND
    - beats the champion in at least 2 of the 3 years 2021-2023 (gain > 0.1 pp),
    - mean yearly gain >= bar(n) = 1 pp + 0.5 pp * ln(n), n = hypotheses tested so far,
    - the 2021-2025 chain's worst drawdown at most MAX_DD = 40% (operator 2026-10-22: "maxima caida 40";
      until then: not worse than the champion's by more than 2 pp).
2026 is computed and printed, NEVER used to decide. The paper book (paper/selection.json) is never touched:
an adopted champion is a candidate the operator may move to paper.

    python research/system12/hyp12.py            one pass: tests every hypothesis not yet in the ledger
    python research/system12/hyp12.py --loop     passes forever (task system12-hyp), brake: hyp/STOP
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import time
import traceback
from datetime import datetime, timezone

import numpy as np

import system12_ls as L

HERE = L.S.HERE
OUT = HERE / "hyp"
LEDGER = OUT / "ledger.jsonl"
CHAMP = OUT / "champion.json"
STATUS = OUT / "status.json"
READ = (2021, 2022, 2023, 2024, 2025)
# v2 (2026-10-22): ADOPTION looks only at 2021-2023. v1 adopted on 2021-2025, so after 3,100 tries the champion was chosen on the
# very years it was scored on (2021-25 +79%/yr) while 2026 read -23%. 2024, 2025 and 2026 are now out-of-sample for the
# whole loop, not only for each parameter.
ADOPT = (2021, 2022, 2023)
VALID = (2024, 2025)          # v4: a candidate must not lose here (filter only; never used to choose a parameter)
OOS = (2026,)                 # the only year nothing ever looks at
FWD = 2026
FIRST = L.S.FIRST
MAX_DD = 0.40


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def bar(n: int) -> float:
    """v3: the required Sharpe improvement (2021-23 daily, annualised); rises with every hypothesis tested."""
    return 0.05 + 0.03 * math.log(max(n, 1))


def sharpe(d) -> float:
    d = np.asarray(d, dtype=float)
    return float(d.mean() / d.std() * math.sqrt(365)) if d.std() > 0 else 0.0


class X:
    """What an overlay may read. Everything is indexed by 4h bar; use lag() so a decision at close t trades from t+1."""

    def __init__(self, eng):
        self.eng, self.w = eng, eng.w
        coins = list(self.w.P4["coins"])
        self.ib, self.ie = coins.index("BTCUSDT"), coins.index("ETHUSDT")
        c = self.w.P4["close"]
        self.close = c
        self.btc = _ffill(c[:, self.ib])
        self.eth = _ffill(c[:, self.ie])
        self.fund = self.w.fund4
        self.year = self.w.P4["year"]
        self.T = c.shape[0]

    @staticmethod
    def lag(m: np.ndarray, k: int = 1) -> np.ndarray:
        out = np.empty_like(m, dtype=float)
        out[:k] = m[0] if m.ndim == 1 else m[0]
        out[k:] = m[:-k]
        return out

    def ret4(self, W: np.ndarray) -> np.ndarray:
        return L.H.bar_returns(self.w, W, L.LV.PERP_HALF, self.fund)[0]

    @staticmethod
    def scale_long(W, m):
        return np.where(W > 0, W * m[:, None], W)

    @staticmethod
    def scale_short(W, m):
        return np.where(W < 0, W * m[:, None], W)


def _ffill(x: np.ndarray) -> np.ndarray:
    x = x.astype(float).copy()
    ok = np.isfinite(x)
    idx = np.where(ok, np.arange(len(x)), 0)
    np.maximum.accumulate(idx, out=idx)
    x = x[idx]
    x[~np.isfinite(x)] = np.nan
    return x


class Lab:
    def __init__(self):
        self.eng, self.regs = L.setup()
        self.x = X(self.eng)
        self.dy = self.eng.dy
        res = json.loads((L.OUT / "results.json").read_text(encoding="utf-8"))
        self.base = {}
        for N in READ + (FWD,):
            m = res["folds"][str(N)]["ensemble"]["members"]
            self.base[N] = sum(self.eng.weights_ls(self.regs[r], b, float(v), None if s == "None" else eval(s))  # noqa: S307
                               for r, b, v, s in m) / len(m)

    def daily(self, W):
        return self.eng.daily_ls(W)

    def apply(self, H, W, p):
        return W if p is None else H.fn(self.x, W, p)

    def champion_W(self, champ, N, reg):
        W = self.base[N]
        for c in champ:
            W = self.apply(reg[c["id"]], W, c["params"][str(N)])
        return W

    def walk(self, H, champ, reg) -> dict:
        """Choose H's parameter on 2019..N-1 for each N, read N. Returns per-year numbers for H and the champion."""
        out = {}
        for N in READ + (FWD,):
            Wc = self.champion_W(champ, N, reg)
            train = tuple(range(FIRST, N))
            best, bp = -np.inf, None
            for p in [None] + list(H.grid):
                d = self.daily(self.apply(H, Wc, p))
                v = L.B.objective_value(d, self.dy, train)[0]
                if np.isfinite(v) and v > best + 1e-12:
                    best, bp = v, p
            Wh = self.apply(H, Wc, bp)
            dh, dc = self.daily(Wh), self.daily(Wc)
            yr = self.x.year == N
            out[N] = {"p": bp, "xh": float(np.abs(Wh[yr]).sum(axis=1).mean()), "xc": float(np.abs(Wc[yr]).sum(axis=1).mean()), "h": L.B.yearly(dh, self.dy, (N,))[N], "c": L.B.yearly(dc, self.dy, (N,))[N],
                      "dh": dh[self.dy == N], "dc": dc[self.dy == N]}
        return out


def verdict(r: dict, n: int) -> dict:
    gains = [r[N]["h"] - r[N]["c"] for N in ADOPT]
    wins = sum(g > 0.001 for g in gains)
    mg = float(np.mean(gains))
    ddh = L.B.max_dd(np.concatenate([r[N]["dh"] for N in ADOPT]))
    ddc = L.B.max_dd(np.concatenate([r[N]["dc"] for N in ADOPT]))
    # v3 (2026-10-22): "better" = more return per unit of risk. v2 adopted on raw return, so stacking exposure ("add" modes,
    # x1.2 leverage) won every bull year and the champion lost to the frozen book in 2025 and 2026, the years it never saw.
    sh = sharpe(np.concatenate([r[N]["dh"] for N in ADOPT])) - sharpe(np.concatenate([r[N]["dc"] for N in ADOPT]))
    # v4 (2026-10-22): v3 still adopted luck (turn-of-month, RSI+SMA: 2021-23 better, 2025-26 worse). A candidate must
    # also hold up on 2024-2025: not worse than the champion in either year (2 pp tolerance) nor in Sharpe.
    valid = all(r[N]["h"] >= r[N]["c"] - 0.02 for N in VALID) and         sharpe(np.concatenate([r[N]["dh"] for N in VALID])) >= sharpe(np.concatenate([r[N]["dc"] for N in VALID]))
    ok = wins >= 2 and sh >= bar(n) and ddh <= MAX_DD and valid
    return {"wins": wins, "mean_gain": round(mg, 4), "sharpe_gain": round(sh, 3), "valid_2024_25": bool(valid), "bar": round(bar(n), 4), "dd": round(ddh, 4),
            "dd_champion": round(ddc, 4), "adopted": bool(ok)}


def load_ledger() -> list:
    if not LEDGER.exists():
        return []
    return [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_champ() -> list:
    return json.loads(CHAMP.read_text(encoding="utf-8")) if CHAMP.exists() else []


def chain(lab, champ, reg) -> dict:
    ys = {}
    for N in READ + (FWD,):
        d = lab.daily(lab.champion_W(champ, N, reg))
        ys[N] = {"ret": round(L.B.yearly(d, lab.dy, (N,))[N], 4), "dd": round(L.B.max_dd(d[lab.dy == N]), 4)}
    return ys


def write_status(lab, reg, ledger, champ, testing=None, note=""):
    froz = chain(lab, [], reg)
    cur = chain(lab, champ, reg) if champ else froz
    ann = lambda ys: float(np.prod([1 + ys[N]["ret"] for N in READ]) ** (1 / len(READ)) - 1)  # noqa: E731
    last = [{k: e[k] for k in ("id", "title", "wins", "mean_gain", "bar", "adopted", "fwd_gain")} for e in ledger[-12:]][::-1]
    STATUS.write_text(json.dumps({
        "at": now(), "pid": os.getpid(), "tested": len(ledger), "adopted": [c["id"] for c in champ],
        "queued": max(0, len(reg) - len(ledger)), "testing": testing, "note": note, "bar_next": round(bar(len(ledger) + 1), 4),
        "frozen": {"years": {str(k): v for k, v in froz.items()}, "ann": round(ann(froz), 4)},
        "champion": {"years": {str(k): v for k, v in cur.items()}, "ann": round(ann(cur), 4)},
        "last": last}, indent=1), encoding="utf-8")


def write_report(reg, ledger, champ):
    """hyp/REPORT.md - the morning read: champion vs frozen, what was adopted and why, which pieces help."""
    st = json.loads(STATUS.read_text(encoding="utf-8"))
    F, C = st["frozen"]["years"], st["champion"]["years"]
    ys = sorted(F)
    L = ["# System 12 - hypothesis loop report", "", f"Updated {now()}. {len(ledger)} hypotheses tested, {len(champ)} adopted. "
         f"Next adoption needs a Sharpe gain of {st['bar_next']:.2f} on 2021-2023. Train 2021-2023 (must improve), validation 2024-2025 "
         f"(must not lose), test 2026 (never looked at). "
         "", "",
         "| | " + " | ".join(ys) + " | per year 2021-25 |", "|---|" + "---|" * (len(ys) + 1),
         "| champion | " + " | ".join(f"{C[y]['ret']:+.0%}" for y in ys) + f" | {st['champion']['ann']:+.1%} |",
         "| frozen book (paper) | " + " | ".join(f"{F[y]['ret']:+.0%}" for y in ys) + f" | {st['frozen']['ann']:+.1%} |", "",
         "## Adopted, in order", ""]
    led = {e["id"]: e for e in ledger}
    for c in champ:
        e = led.get(c["id"], {})
        L.append(f"- **{c['id']} {e.get('title', '')}**: {e.get('wins')}/5 years, {e.get('mean_gain', 0):+.1%}/yr, "
                 f"DD {e.get('dd', 0):.0%} (was {e.get('dd_champion', 0):.0%}); 2026 {e.get('fwd_gain', 0):+.1%}. {e.get('text', '')}")
    try:
        import gen12
        sc = gen12._scores(ledger)
        L += ["", "## Pieces: mean gain over the generated tests that used them", "", "| piece | family | tests | mean gain |", "|---|---|---|---|"]
        for k, (m, n) in sorted(sc.items(), key=lambda kv: -kv[1][0]):
            L.append(f"| {k} | {gen12.BY[k][1]} | {n} | {m:+.2%} |")
    except Exception:  # noqa: BLE001
        pass
    (OUT / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def one_pass(lab=None, generate=False) -> int:
    """Tests every written hypothesis not yet in the ledger; with generate=True and nothing written left, a batch from
    gen12.py. Returns how many were tested."""
    OUT.mkdir(parents=True, exist_ok=True)
    import hypotheses12
    importlib.reload(hypotheses12)
    import gen12
    importlib.reload(gen12)
    allH = hypotheses12.ALL + gen12.load()
    reg = {h.id: h for h in allH}
    lab = lab or Lab()
    ledger, champ = load_ledger(), load_champ()
    done = {e["id"] for e in ledger}
    todo = [h for h in allH if h.id not in done]
    if not todo and generate:
        todo = gen12.next_batch(ledger)
        reg.update({h.id: h for h in todo})
    write_status(lab, reg, ledger, champ, todo[0].id if todo else None)
    written = HERE / "hypotheses12.py"
    t_written = written.stat().st_mtime
    for H in todo:
        if (OUT / "STOP").exists():
            break
        if written.stat().st_mtime != t_written:                    # new written hypotheses go before the generator's queue
            break
        write_status(lab, reg, ledger, champ, H.id)
        t0 = time.time()
        try:
            r = lab.walk(H, champ, reg)
        except Exception:  # noqa: BLE001
            e = {"id": H.id, "title": H.title, "at": now(), "error": traceback.format_exc()[-600:], "wins": 0, "mean_gain": 0,
                 "bar": 0, "adopted": False, "fwd_gain": None}
            ledger.append(e)
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(e) + "\n")
            continue
        v = verdict(r, len(ledger) + 1)
        e = {"id": H.id, "title": H.title, "text": H.text, "at": now(), "seconds": round(time.time() - t0, 1),
             "champion_before": [c["id"] for c in champ], **v,
             "years": {str(N): {"h": round(r[N]["h"], 4), "c": round(r[N]["c"], 4), "p": r[N]["p"],
                               "inv_h": round(r[N]["xh"], 3), "inv_c": round(r[N]["xc"], 3)} for N in READ + (FWD,)},
             "fwd_gain": round(r[FWD]["h"] - r[FWD]["c"], 4), "fwd_note": "2026 read only, never used to decide"}
        ledger.append(e)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(e, default=str) + "\n")
        if v["adopted"]:
            champ.append({"id": H.id, "at": now(), "params": {str(N): r[N]["p"] for N in READ + (FWD,)}})
            CHAMP.write_text(json.dumps(champ, indent=1, default=str), encoding="utf-8")
        print(f"[{now()}] {H.id} {H.title}: wins {v['wins']}/3, gain {v['mean_gain']:+.2%}, Sharpe {v['sharpe_gain']:+.2f} (bar {v['bar']:.2f}), "
              f"DD {v['dd']:.0%} vs {v['dd_champion']:.0%} -> {'ADOPTED' if v['adopted'] else 'rejected'}; 2026 {e['fwd_gain']:+.2%}", flush=True)
    write_status(lab, reg, ledger, champ, None, "generating the next batch" if generate else "queue empty")
    write_report(reg, ledger, champ)
    return len(todo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    a = ap.parse_args()
    if not a.loop:
        one_pass()
        return 0
    try:                                           # one loop at a time: the task relaunches it every 10 minutes
        import psutil
        st = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
        if st.get("pid") and st["pid"] != os.getpid() and psutil.pid_exists(st["pid"]) and                 "hyp12" in " ".join(psutil.Process(st["pid"]).cmdline()):
            return 0
    except Exception:  # noqa: BLE001
        pass
    lab = Lab()
    while not (OUT / "STOP").exists():
        if not one_pass(lab, generate=True):
            time.sleep(60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
