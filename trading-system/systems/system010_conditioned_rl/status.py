"""The live status of system 10: what the machine and every job are doing, every 10 seconds.

The operator, 2026-10-10: *"I want to look at the screen and be sure it is updating in real
time ... what are we doing right now - training, evaluating, backtesting, forward testing
2026 - and that the machine is working at its maximum."*

Writes research/system10/rnd/live_status.json (atomic). The public page's pusher carries it
inside `state` every 8 seconds, so the screen is never older than ~20 seconds. Reads only
files, nvidia-smi and the OS counters; decides nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

OUT = Path(__file__).resolve().parents[3] / "research" / "system10"
RND = OUT / "rnd"
LIVE = RND / "live_status.json"
EVERY_S = 10
KEEP = 180                 # samples of history (30 minutes at 10 s)
SLOW_EVERY_S = 60          # the ledger-derived figures
WORKERS = ("w1", "w2", "w3", "w4")
STALE_S = {"w": 45 * 60, "evaluator": 2 * 3600}
FIXED_AT = "2026-10-10T00:00:00+00:00"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        if x.strip():
            try:
                out.append(json.loads(x))
            except ValueError:
                pass
    return out


def last_line(path: Path) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 4096))
            lines = [x for x in fh.read().decode("utf-8", "replace").splitlines() if x.strip()]
        return lines[-1] if lines else ""
    except OSError:
        return ""


def gpu() -> dict:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout.strip()
        name, util, used, total, temp, power = [x.strip() for x in out.split(",")]
        num = lambda v: float(v) if v.replace(".", "", 1).isdigit() else None  # noqa: E731
        return {"name": name, "util_pct": num(util), "mem_used_mb": num(used), "mem_total_mb": num(total),
                "temp_c": num(temp), "power_w": num(power)}
    except Exception:  # noqa: BLE001
        return {}


class Rates:
    """Bytes per second for the network and the disks, from successive counters."""

    def __init__(self):
        self.t, self.net, self.disk = time.time(), psutil.net_io_counters(), psutil.disk_io_counters()

    def read(self) -> dict:
        t, net, disk = time.time(), psutil.net_io_counters(), psutil.disk_io_counters()
        dt = max(t - self.t, 1e-3)
        out = {"net_down_kbps": round((net.bytes_recv - self.net.bytes_recv) / dt / 1024, 1),
               "net_up_kbps": round((net.bytes_sent - self.net.bytes_sent) / dt / 1024, 1),
               "disk_read_mbps": round((disk.read_bytes - self.disk.read_bytes) / dt / 2**20, 2),
               "disk_write_mbps": round((disk.write_bytes - self.disk.write_bytes) / dt / 2**20, 2)}
        self.t, self.net, self.disk = t, net, disk
        return out


def jobs() -> list[dict]:
    """One row per job: what it is doing now, from its log and the claims ledger."""
    out = []
    claims = {}
    for r in rows(RND / "search_claims.jsonl")[-400:]:
        claims[r.get("worker")] = r
    t = time.time()
    for w in WORKERS:
        log = OUT / f"s10_{w}.log"
        age = t - log.stat().st_mtime if log.is_file() else None
        line = last_line(log)
        c = claims.get(w)
        if age is None or age > STALE_S["w"]:
            state, doing, since = "down", "not running", None
        elif "loading bars" in line or "oracle up-swings" in line:
            state, doing, since = "loading", "loading 8 years of 15-minute bars", None
        elif c and t - c["t"] < 3600:
            state = "running"
            doing = "testing " + (c.get("label") or f"config {c.get('id')}")
            since = datetime.fromtimestamp(c["t"], timezone.utc).isoformat(timespec="seconds")
        else:
            state, doing, since = "running", "choosing the next configuration", None
        out.append({"job": w, "role": "condition search", "device": "GPU" if w in ("w1", "w2") else "CPU",
                    "state": state,
                    "doing": doing, "since": since})
    log = OUT / "s10_evaluator.log"
    line = last_line(log)
    age = t - log.stat().st_mtime if log.is_file() else None
    if age is None or age > STALE_S["evaluator"]:
        state, doing = "down", "not running"
    elif "loading bars" in line or "oracle up-swings" in line:
        state, doing = "loading", "loading bars through today"
    else:
        state, doing = "running", "forward test of the live release on 2026, every hour"
    out.append({"job": "evaluator", "role": "2026 forward test", "device": "GPU", "state": state,
                "doing": doing, "since": None, "last": line[line.find("evaluator:") + 11:][:160] if "evaluator:" in line else None})
    log = OUT / "s10_forecaster.log"
    line = last_line(log)
    age = t - log.stat().st_mtime if log.is_file() else None
    if age is None or age > 2 * 3600:
        state, doing = "down", "not running"
    elif "loading" in line or "oracle up-swings" in line:
        state, doing = "loading", "loading 8 years of bars"
    else:
        state, doing = "running", "training the signal forecaster (walk-forward folds 2021-2026)"
    out.append({"job": "forecaster", "role": "signal model training", "device": "GPU", "state": state,
                "doing": doing, "since": None,
                "last": line[line.find("forecaster:") + 12:][:160] if "forecaster:" in line else None})
    stamp = RND / "last_review.txt"
    out.append({"job": "review", "role": "8-hour review + health every 15 min", "device": "CPU",
                "state": "running" if stamp.is_file() else "down",
                "doing": "next full review in "
                         f"{max(0, 8 * 3600 - (t - stamp.stat().st_mtime)) / 3600:.1f} h" if stamp.is_file() else "never ran",
                "since": None})
    return out


def slow() -> dict:
    """Best backtest (unseen 2022-2025) and 2026 forward, progress counters."""
    from . import search as S
    done = S.ledger()
    champ = S.champion(done)
    rel = S.releases()
    live = rel[-1] if rel else None
    tl = rows(RND / "training_timeline.jsonl")
    # Readings before FIXED_AT booked releases without their money management (commit
    # 94ec71e): release 27 read +54% there against +27% in its real form. Never shown.
    fwd = [r for r in tl if isinstance(r.get("forward_2026"), dict) and r["forward_2026"].get("return") is not None
           and r["at"] >= FIXED_AT]
    cut = time.time() - 86400
    ts = lambda r: datetime.fromisoformat(r["at"]).timestamp()  # noqa: E731
    recent = [r for r in done if ts(r) >= cut]

    def years(r):
        return {str(y): {k: v.get(k) for k in ("return", "max_dd", "win_rate", "trades")}
                for y, v in r["years"].items()}

    best_bt = None
    src = champ or (live and next((r for r in done if r["id"] == live["id"]), None))
    if src:
        best_bt = {"label": S.cfg_label(src["cfg"]), "worst_year": src["worst_year"], "cagr": src["cagr"],
                   "max_dd": src["max_dd"], "years": years(src),
                   "win_rate": S.pooled({int(k): v for k, v in src["years"].items()})["win_rate"],
                   "is_champion": bool(champ)}
    most = max((r for r in done if r["eligible"] and S.operates(r)), key=lambda r: r["cagr"], default=None)
    return {
        "best_backtest": best_bt,
        "max_profit_backtest": ({"label": S.cfg_label(most["cfg"]), "worst_year": most["worst_year"],
                                 "cagr": most["cagr"], "max_dd": most["max_dd"]} if most else None),
        "forward_2026": ({**fwd[-1]["forward_2026"], "at": fwd[-1]["at"],
                          "release": live["n"] if live else None} if fwd else None),
        "forward_2026_best": (max((r["forward_2026"] | {"at": r["at"]} for r in fwd), key=lambda f: f["return"])
                              if fwd else None),
        "forward_series": [{"at": r["at"], "return": r["forward_2026"]["return"],
                            "max_dd": r["forward_2026"]["max_dd"], "win_rate": r["forward_2026"].get("win_rate")}
                           for r in fwd[-336:]],
        "progress": {"trials_total": len(done), "trials_24h": len(recent),
                     "qualifying_24h": sum(r["eligible"] for r in recent),
                     "qualifying_total": sum(r["eligible"] for r in done),
                     "releases": len(rel), "live_release": live["n"] if live else None,
                     "live_release_label": live["label"] if live else None},
    }


def headline(js: list[dict]) -> str:
    w = [j for j in js if j["job"].startswith("w")]
    run = sum(j["state"] == "running" for j in w)
    load = sum(j["state"] == "loading" for j in w)
    ev = next(j for j in js if j["job"] == "evaluator")
    parts = []
    fc = next((j for j in js if j["job"] == "forecaster"), None)
    if fc and fc["state"] == "running":
        parts.append("Training the signal forecaster on the GPU")
    if run:
        parts.append(f"searching trading conditions on {run} worker{'s' * (run > 1)}")
    if load:
        parts.append(f"{load} worker{'s' * (load > 1)} loading data")
    if ev["state"] == "running":
        parts.append("forward-testing the live release on 2026 every hour")
    elif ev["state"] == "loading":
        parts.append("evaluator reloading data")
    if not parts:
        return "Stopped"
    return " · ".join(parts)


def main() -> int:
    rates = Rates()
    psutil.cpu_percent(percpu=True)
    hist = {k: [] for k in ("t", "cpu", "gpu", "ram", "net_down", "net_up", "gpu_mem")}
    if LIVE.is_file():
        try:
            hist = json.loads(LIVE.read_text(encoding="utf-8")).get("history", hist)
        except (OSError, ValueError):
            pass
    slow_cache, slow_at = {}, 0.0
    while not (OUT / "STOP_S10").exists():
        time.sleep(EVERY_S)
        cores = psutil.cpu_percent(percpu=True)
        vm = psutil.virtual_memory()
        g = gpu()
        r = rates.read()
        machine = {"cpu_pct": round(sum(cores) / len(cores), 1), "cpu_cores": cores,
                   "ram_used_gb": round(vm.used / 2**30, 1), "ram_total_gb": round(vm.total / 2**30, 1),
                   "ram_pct": vm.percent, "gpu": g, **r}
        for k, v in (("t", int(time.time())), ("cpu", machine["cpu_pct"]), ("gpu", g.get("util_pct")),
                     ("ram", vm.percent), ("net_down", r["net_down_kbps"]), ("net_up", r["net_up_kbps"]),
                     ("gpu_mem", round(100 * g["mem_used_mb"] / g["mem_total_mb"], 1)
                      if g.get("mem_total_mb") else None)):
            hist.setdefault(k, []).append(v)
            del hist[k][:-KEEP]
        if time.time() - slow_at >= SLOW_EVERY_S:
            try:
                slow_cache = slow()
            except Exception as exc:  # noqa: BLE001
                slow_cache = {**slow_cache, "error": f"{type(exc).__name__}: {exc}"[:200]}
            slow_at = time.time()
        js = jobs()
        doc = {"at": now_iso(), "every_s": EVERY_S, "headline": headline(js), "machine": machine,
               "history": hist, "jobs": js, "rl": {"state": "on hold",
                                                   "why": "the position manager lost to the rule out of sample; "
                                                          "strength sizing replaced it"},
               **slow_cache}
        tmp = LIVE.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, default=str), encoding="utf-8")
        os.replace(tmp, LIVE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
