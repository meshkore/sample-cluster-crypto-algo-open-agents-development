"""The 8-hourly review: where are we, and the corrections that need no one's permission.

The operator, 2026-10-08: *"you should run an evaluation about every eight hours, on a
schedule, and make the corrections automatically without asking me anything."*

The watchdog launches this when `rnd/last_review.txt` is older than eight hours. It reads
only files (the trial ledger, the releases, the logs) and imports no model code, so it
costs seconds. It decides nothing from 2026: the forward readings are reported, never
used to choose.

Automatic corrections, each logged as an event:
  health   a system 10 process whose log has not moved for too long is hung - it is
           stopped, and the watchdog relaunches it within five minutes
  rl       if the policy is stuck (the last four RL releases trade 2025 identically and
           the training reward has not risen over the window), the next rung of a ladder
           is applied through `rl_control.json`, read live by the trainer:
             1  more exploration (entropy 0.03)
             2  more exploration and a faster step (entropy 0.05, lr 3e-4)
             3  fresh weights (the checkpoint is set aside) and the defaults back
           when the reward rises again the ladder resets
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "research" / "system10"
RND = OUT / "rnd"
STAMP = RND / "last_review.txt"
REVIEWS = RND / "reviews.jsonl"
EVENTS = RND / "events.jsonl"
CONTROL = OUT / "rl_control.json"
CKPT = OUT / "_auto_rl_checkpoint.pt"
WINDOW_H = 8
STALE_MIN = {"w1": 120, "w2": 120, "rl": 45, "evaluator": 180}
PATTERN = {"w1": "*system010_conditioned_rl.search*--worker w1*",
           "w2": "*system010_conditioned_rl.search*--worker w2*",
           "rl": "*system010_conditioned_rl.rl *",
           "evaluator": "*system010_conditioned_rl.evaluator*"}
LADDER = [{}, {"ent_coef": 0.03}, {"ent_coef": 0.05, "lr": 3e-4}, "reset"]
DD_CAP = 0.25


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def event(kind: str, text: str) -> None:
    with EVENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now(), "kind": kind, "text": text}) + "\n")


def age_min(path: Path) -> float | None:
    return (time.time() - path.stat().st_mtime) / 60 if path.is_file() else None


def stop_process(tag: str) -> bool:
    ps = (f"$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          f"Where-Object {{ $_.CommandLine -like '{PATTERN[tag]}' }}; "
          f"$p | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}; @($p).Count")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return out not in ("", "0")
    except Exception:  # noqa: BLE001
        return False


def health() -> list[str]:
    acts = []
    for tag, limit in STALE_MIN.items():
        a = age_min(OUT / f"s10_{tag}.log")
        if a is not None and a > limit and stop_process(tag):
            acts.append(f"{tag} log silent {a:.0f} min - stopped, the watchdog relaunches it")
    return acts


def rl_rewards() -> list[tuple[float, float]]:
    """(training hours, mean reward) from the trainer's progress lines, current and last log."""
    out = []
    for name in ("s10_rl.log.1", "s10_rl.log"):
        p = OUT / name
        if p.is_file():
            for m in re.finditer(r"update \d+ \(([\d.]+) h\) reward ([+-][\d.]+)", p.read_text(encoding="utf-8")):
                out.append((float(m.group(1)), float(m.group(2))))
    return sorted(set(out))


def rl_review() -> tuple[dict, list[str]]:
    tl = list({r["release"]: r for r in rows(RND / "rl_timeline.jsonl")}.values())  # one per release
    rw = rl_rewards()
    acts: list[str] = []
    info = {"releases": len(tl)}
    if tl:
        last = tl[-1]
        info.update({"train_hours": last["train_hours"], "in_sample_2025": last["in_sample_2025"],
                     "forward_2026": last["forward_2026"]})
    if rw:
        h_end = rw[-1][0]
        recent = [r for h, r in rw if h >= h_end - 2]
        before = [r for h, r in rw if h_end - WINDOW_H - 2 <= h < h_end - WINDOW_H]
        info["reward_now"] = round(sum(recent) / len(recent), 4)
        info["reward_8h_ago"] = round(sum(before) / len(before), 4) if before else None
    sig = [(r["in_sample_2025"]["return"], r["in_sample_2025"]["trades"]) for r in tl[-4:]]
    frozen = len(sig) == 4 and len(set(sig)) == 1
    rising = (info.get("reward_8h_ago") is not None
              and info["reward_now"] > info["reward_8h_ago"] + 0.002)
    ctl = json.loads(CONTROL.read_text(encoding="utf-8")) if CONTROL.is_file() else {}
    rung = int(ctl.get("rung", 0))
    info.update({"frozen": frozen, "rising": rising, "rung": rung})
    if frozen and not rising:
        rung += 1
        step = LADDER[min(rung, len(LADDER) - 1)]
        if step == "reset":
            if CKPT.is_file():
                CKPT.rename(CKPT.with_name(f"_auto_rl_checkpoint_stuck_{int(time.time())}.pt"))
            CONTROL.write_text(json.dumps({"rung": 0, "note": "fresh weights after the ladder"}), encoding="utf-8")
            stop_process("rl")
            acts.append("RL stuck through every rung - weights set aside, training restarts fresh")
        else:
            CONTROL.write_text(json.dumps({**step, "rung": rung}), encoding="utf-8")
            acts.append(f"RL stuck (last 4 releases identical, reward flat) - rung {rung}: {step}")
    elif rising and rung:
        keep = LADDER[rung] if isinstance(LADDER[rung], dict) else {}
        CONTROL.write_text(json.dumps({**keep, "rung": 0}), encoding="utf-8")
        acts.append("RL reward rising again - ladder reset (current settings kept)")
    return info, acts


def search_review() -> dict:
    done = rows(RND / "search_trials.jsonl")
    cut = time.time() - WINDOW_H * 3600
    ts = lambda r: datetime.fromisoformat(r["at"]).timestamp()  # noqa: E731
    recent = [r for r in done if ts(r) >= cut]
    ok = [r for r in done if r["eligible"] and r["max_dd"] <= DD_CAP and r["cfg"].get("size_down", 1) > 0]
    optimal = max(ok, key=lambda r: (r["score"], r["worst_q"])) if ok else None
    most = max(ok, key=lambda r: r["cagr"]) if ok else None
    pick = lambda r: r and {"cfg": r["cfg"], "worst_year": r["worst_year"], "cagr": r["cagr"],  # noqa: E731
                            "max_dd": r["max_dd"]}
    rel = sorted((OUT / "releases").glob("release_*.json"))
    fwd = rows(RND / "training_timeline.jsonl")
    return {"trials": len(done), "trials_window": len(recent),
            "eligible_window": sum(r["eligible"] and r["max_dd"] <= DD_CAP for r in recent),
            "best_dd_window": min((r["max_dd"] for r in recent if all(v["trades"] for v in r["years"].values())),
                                  default=None),
            "optimal": pick(optimal), "max_profit": pick(most),
            "latest_release": rel[-1].stem if rel else None,
            "release_forward_2026": (fwd[-1].get("forward_2026") if fwd else None)}


def main() -> int:
    force = "--force" in sys.argv
    if not force and STAMP.is_file() and age_min(STAMP) < WINDOW_H * 60:
        return 0
    STAMP.write_text(now(), encoding="utf-8")
    acts = health()
    rl, rl_acts = rl_review()
    acts += rl_acts
    se = search_review()
    row = {"at": now(), "search": se, "rl": rl, "actions": acts}
    with REVIEWS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    opt = se["optimal"]
    head = (f"optimal under {DD_CAP:.0%} DD: worst year {opt['worst_year']:+.1%}, CAGR {opt['cagr']:+.1%}, "
            f"DD {opt['max_dd']:.0%}" if opt else f"no trial yet under {DD_CAP:.0%} DD every year")
    event("review", f"8-hour review: {se['trials_window']} trials, {head}; RL {rl.get('train_hours')} h, "
                    f"reward {rl.get('reward_now')}" + (f"; actions: {'; '.join(acts)}" if acts else ""))
    print(json.dumps(row, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
