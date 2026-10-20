"""Plan v2 loop controller (Windows task "plan-v2-controller", every 5 minutes).

Operator, 2026-10-20: "the machine must always be training and working; check every hour that
everything is at the top; daily and even hourly progress." This module guarantees it:

every run (5 min)
  machine    CPU, RAM, GPU utilisation / memory / temperature
  workers    each lab worker (w1-w4 CPU, g1-g2 GPU): alive? its current hypothesis (claims), minutes
             since its log last moved. A worker silent for STALE_MIN is killed; a dead one is relaunched
             (lab_watchdog.ps1) at once, not at the watchdog's next 15-min tick
  tasks      the lab watchdog and the forward task must exist; the forward task must have run in 5 h
  status     lab/control_status.json - everything the Live view shows: machine, workers, current system
             (rules, honest nested results per year, paper book), progress series, leaderboard, alerts
every hour (first run past the hour)
  progress   one row in lab/progress.jsonl: experiments in the hour, mean CPU / GPU over the hour's
             samples, workers alive, actions taken, best pooled spec. A day's rows are the daily report
  checks     ALERT when: < 4 experiments in the hour, a worker restarted twice in the hour, mean GPU < 20%
             while a GPU worker is alive, the paper book older than 5 h, the forward task failing

    python research/plan_v2/controller.py
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil

HERE = Path(__file__).resolve().parent
LAB = HERE / "lab"
STATUS = LAB / "control_status.json"
PROGRESS = LAB / "progress.jsonl"
SAMPLES = LAB / "machine_samples.jsonl"
WORKERS = ("w1", "w2", "w3", "w4", "g1", "g2")
STALE_MIN = 45
PAPER_SPEC = "cap14-spot_long-xs-base-mlp"


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for x in p.read_text(encoding="utf-8").splitlines():
        if x.strip():
            try:
                out.append(json.loads(x))
            except ValueError:
                pass
    return out


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def machine() -> dict:
    vm = psutil.virtual_memory()
    out = {"cpu_pct": psutil.cpu_percent(interval=2.0), "cores": psutil.cpu_percent(interval=None, percpu=True),
           "ram_used_gb": round((vm.total - vm.available) / 2**30, 1), "ram_total_gb": round(vm.total / 2**30, 1)}
    try:
        q = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=20).stdout.strip()
        n, u, mu, mt, tc, pw = [x.strip() for x in q.split(",")]
        out["gpu"] = {"name": n, "util_pct": float(u), "mem_used_mb": float(mu), "mem_total_mb": float(mt),
                      "temp_c": float(tc), "power_w": float(pw) if pw not in ("[N/A]", "") else None}
    except Exception:  # noqa: BLE001
        out["gpu"] = None
    return out


def workers(ledger: list[dict]) -> list[dict]:
    claims = read_jsonl(LAB / "claims.jsonl")
    done = {(r["id"], tuple(sorted(r["seed_sets"]))) for r in ledger}
    out = []
    for w in WORKERS:
        pid_f = LAB / f"run_{w}.pid"
        pid = int(pid_f.read_text().strip()) if pid_f.exists() else None
        alive = bool(pid and psutil.pid_exists(pid))
        log = LAB / f"lab_{w}.log"
        quiet = (time.time() - log.stat().st_mtime) / 60 if log.exists() else None
        mine = [c for c in claims if c.get("worker") == w]
        cur = next((c for c in reversed(mine) if (c["id"], tuple(c["seeds"])) not in done), None)
        last = next((r for r in reversed(ledger) if r.get("worker") == w), None)
        out.append({"worker": w, "device": "GPU" if w.startswith("g") else "CPU", "pid": pid, "alive": alive,
                    "log_quiet_min": round(quiet, 1) if quiet is not None else None,
                    "doing": f"{cur['id']} · seeds {'+'.join(cur['seeds'])}" if cur else ("loading data" if alive else "—"),
                    "since": iso(datetime.fromtimestamp(cur["t"], timezone.utc)) if cur else None,
                    "last_result": {"id": last["id"], "sharpe": last["result"]["sharpe"], "at": last["at"]} if last else None,
                    "done": sum(1 for r in ledger if r.get("worker") == w)})
    return out


def heal(ws: list[dict]) -> list[str]:
    acts = []
    for w in ws:
        if w["alive"] and w["log_quiet_min"] is not None and w["log_quiet_min"] > STALE_MIN:
            try:
                psutil.Process(w["pid"]).kill()
                acts.append(f"{w['worker']} silent {w['log_quiet_min']:.0f} min - killed")
                w["alive"] = False
            except Exception:  # noqa: BLE001
                pass
    if not (LAB / "STOP").exists() and any(not w["alive"] for w in ws):
        # detached, no pipes: the workers it starts would inherit captured pipes and the controller would
        # wait on them forever (first version hung 15 min on 2026-10-20)
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAB / "lab_watchdog.ps1")],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200, close_fds=True)
        acts.append("relaunched: " + ", ".join(w["worker"] for w in ws if not w["alive"]))
    return acts


def task_info(name: str) -> dict:
    try:
        q = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"$i = Get-ScheduledTask '{name}' | Get-ScheduledTaskInfo; "
                            "'{0}|{1}' -f $i.LastRunTime.ToUniversalTime().ToString('o'), $i.LastTaskResult"],
                           capture_output=True, text=True, timeout=30).stdout.strip()
        t, r = q.split("|")
        return {"exists": True, "last_run": t[:19] + "Z", "last_result": int(r)}
    except Exception:  # noqa: BLE001
        return {"exists": False}


def current_system(ledger: list[dict], pool: list[dict]) -> dict:
    """The paper candidate: its rules in words, honest nested results per year (median over seed pairs,
    worse seed set of each pair), the DD-scaled version, and its frozen selection."""
    rows = [r for r in ledger if r["id"] == PAPER_SPEC]
    years = {}
    for N in ("2022", "2023", "2024", "2025"):
        v = [r["per_seed"][r["worse_seed_set"]]["picks"].get(N, {}).get("return") for r in rows]
        v = [x for x in v if x is not None]
        dd = [r["per_seed"][r["worse_seed_set"]]["picks"].get(N, {}).get("max_dd") for r in rows]
        dd = [x for x in dd if x is not None]
        years[N] = {"return_median": round(float(np.median(v)), 4) if v else 0.0,
                    "return_p10": round(float(np.percentile(v, 10)), 4) if v else 0.0,
                    "return_p90": round(float(np.percentile(v, 90)), 4) if v else 0.0,
                    "max_dd_median": round(float(np.median(dd)), 4) if dd else 0.0,
                    "cash_share": round(float(np.mean([r["per_seed"][r["worse_seed_set"]]["picks"].get(N, {}).get("eligible", 0) == 0
                                                       for r in rows])), 3) if rows else None}
    pr = next((p for p in pool if p["id"] == PAPER_SPEC), None)
    sel = load(HERE / "paper_v2" / "selection.json") or {}
    return {"id": PAPER_SPEC, "pooled": pr, "years": years, "replications": len(rows),
            "rules": ["Universe: the 14 most-traded Binance USDT coins as of 31 Dec of the year before (delisted coins included)",
                      "Model: a small neural net (MLP, 2 x 128) ranks the coins by expected return relative to the others",
                      "Inputs: 28 price / volume / BTC / breadth features on 4-hour and daily bars",
                      "Book: hold the top 3-5 coins for 1-7 days while BTC is above its 100-day average; cash otherwise",
                      "Risk: 1% daily risk per coin, book volatility <= 2%/day, correlated coins capped, exposure scaled to an 18% drawdown budget",
                      "Execution: decide at a bar's close, buy or sell at the next one, 0.225% per side + market impact"],
            "selection": {"configs": [c["cfg"] for c in sel.get("configs", [])], "scale": sel.get("scale")}}


def series(ledger: list[dict]) -> dict:
    """Hourly, over DISTINCT hypotheses (each spec's first seed pair; replications would inflate it):
    cumulative hypotheses tested, share with nested Sharpe > 0 (success rate), best so far."""
    first = {}
    for r in ledger:
        first.setdefault(r["id"], r)
    if not first:
        return {"t": [], "n": [], "rate": [], "best": []}
    t = sorted((r["at"], r["result"]["sharpe"]) for r in first.values())
    by_h: dict = {}
    n = pos = 0
    best = -9.0
    for at, sh in t:
        n += 1
        pos += sh > 0
        best = max(best, sh)
        by_h[at[:13]] = (n, pos / n, best)
    hs = sorted(by_h)
    return {"t": [h + ":00Z" for h in hs], "n": [by_h[h][0] for h in hs],
            "rate": [round(by_h[h][1], 4) for h in hs], "best": [round(by_h[h][2], 3) for h in hs]}


def main() -> int:
    import sys
    sys.path.insert(0, str(HERE))
    import lab_v2 as LV
    t = now()
    ledger = LV.ledger()
    m = machine()
    with SAMPLES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": iso(t), "cpu": m["cpu_pct"], "gpu": (m.get("gpu") or {}).get("util_pct")}) + "\n")
    ws = workers(ledger)
    acts = heal(ws)
    if acts:
        ws = workers(ledger)
    pool = LV.pooled(ledger)
    tasks = {k: task_info(k) for k in ("plan-v2-lab", "plan-v2-forward-ic", "plan-v2-controller")}
    paper = load(HERE / "paper_v2" / "state.json")
    alerts = []
    prog = read_jsonl(PROGRESS)
    last_h = prog[-1]["hour"] if prog else None
    hour = t.strftime("%Y-%m-%dT%H:00Z")
    if hour != last_h:
        h0 = t.timestamp() - 3600
        n_h = sum(1 for r in ledger if datetime.fromisoformat(r["at"]).timestamp() >= h0)
        smp = [s for s in read_jsonl(SAMPLES) if datetime.fromisoformat(s["at"]).timestamp() >= h0]
        cpu = float(np.mean([s["cpu"] for s in smp])) if smp else m["cpu_pct"]
        gpus = [s["gpu"] for s in smp if s.get("gpu") is not None]
        gpu = float(np.mean(gpus)) if gpus else None
        restarts = sum(1 for p in prog[-1:] for a in p.get("actions", []) if "relaunched" in a)
        if n_h < 4:
            alerts.append(f"only {n_h} experiments in the last hour")
        if gpu is not None and gpu < 20 and any(w["alive"] and w["device"] == "GPU" for w in ws):
            alerts.append(f"GPU averaged {gpu:.0f}% with a GPU worker alive")
        if restarts >= 2:
            alerts.append("workers relaunched repeatedly")
        if paper and (t.timestamp() - datetime.fromisoformat(paper["at"]).timestamp()) > 5 * 3600:
            alerts.append("paper book older than 5 h")
        fr = tasks.get("plan-v2-forward-ic", {})
        if fr.get("exists") and fr.get("last_result") not in (0, 267009, 267011, None):
            alerts.append(f"forward task last result {fr.get('last_result')}")
        row = {"hour": hour, "at": iso(t), "experiments_hour": n_h, "experiments_total": len(ledger),
               "cpu_mean": round(cpu, 1), "gpu_mean": round(gpu, 1) if gpu is not None else None,
               "workers_alive": sum(w["alive"] for w in ws), "actions": acts, "alerts": alerts,
               "best_pooled": {k: pool[0][k] for k in ("id", "sharpe_mean", "reps")} if pool else None,
               "paper_equity": paper.get("equity") if paper else None}
        with PROGRESS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        prog.append(row)
        keep = [s for s in read_jsonl(SAMPLES) if datetime.fromisoformat(s["at"]).timestamp() >= t.timestamp() - 2 * 3600]
        SAMPLES.write_text("".join(json.dumps(s) + "\n" for s in keep), encoding="utf-8")
    day0 = t.timestamp() - 86400
    status = {
        "at": iso(t), "machine": m, "workers": ws, "actions_now": acts, "tasks": tasks,
        "alerts": (prog[-1].get("alerts", []) if prog else []),
        "progress": {"experiments_total": len(ledger),
                     "experiments_24h": sum(1 for r in ledger if datetime.fromisoformat(r["at"]).timestamp() >= day0),
                     "experiments_1h": sum(1 for r in ledger if datetime.fromisoformat(r["at"]).timestamp() >= t.timestamp() - 3600),
                     "specs_tested": len({r["id"] for r in ledger}), "specs_total": len(LV.SPECS),
                     "success_rate": round(float(np.mean([p["sharpe_mean"] > 0 for p in pool])), 4) if pool else None,
                     "success_rate_note": "share of distinct hypotheses whose mean nested Sharpe over all seed pairs is > 0",
                     "paper_candidates": [p["id"] for p in pool if p["paper"]],
                     "hourly": prog[-48:]},
        "series": series(ledger),
        "leaderboard": [{k: p[k] for k in ("id", "reps", "sharpe_mean", "sharpe_p10", "share_pos", "p_median",
                                           "ann_median", "dd_median", "scaled_ann", "paper")} for p in pool[:10]],
        "latest": [{"id": r["id"], "seeds": "+".join(sorted(r["seed_sets"])), "worker": r.get("worker"), "at": r["at"],
                    "sharpe": r["result"]["sharpe"], "ann": r["result"]["ann_return"], "dd": r["result"]["max_dd"]}
                   for r in ledger[-10:]][::-1],
        "current_system": current_system(ledger, pool),
        "paper": paper,
    }
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, default=str), encoding="utf-8")
    tmp.replace(STATUS)
    print(f"[{iso(t)}] cpu {m['cpu_pct']:.0f}% gpu {(m.get('gpu') or {}).get('util_pct')}% workers "
          f"{sum(w['alive'] for w in ws)}/{len(ws)} actions {acts} alerts {status['alerts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
