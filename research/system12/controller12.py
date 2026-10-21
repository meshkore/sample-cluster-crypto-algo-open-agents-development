"""System 12 controller (Windows task "system12-lab", every 5 min): keeps WORKERS lab workers alive (relaunched at
below-normal priority if their pid is gone, unless lab/STOP exists), then merges their results into the
walk-forward scoreboard (lab12.merge) and refreshes the page document.

    python research/system12/controller12.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psutil

import lab12

WORKERS = 10
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def alive(wid: int) -> bool:
    f = lab12.LAB / f"w{wid}.json"
    try:
        pid = json.loads(f.read_text(encoding="utf-8"))["pid"]
        p = psutil.Process(pid)
        return p.is_running() and "lab12.py" in " ".join(p.cmdline())
    except Exception:  # noqa: BLE001
        return False


def launch(wid: int) -> None:
    lab12.LAB.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    log = open(lab12.LAB / f"w{wid}.log", "a", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-u", str(HERE / "lab12.py"), "--worker", str(wid)], cwd=str(ROOT), env=env,
                         stdout=log, stderr=subprocess.STDOUT, creationflags=0x4000 | 0x00000008)   # below normal, detached
    (lab12.LAB / f"w{wid}.json").write_text(json.dumps({"worker": wid, "pid": p.pid, "done": 0, "at": lab12.now(), "starting": True}))


def main() -> int:
    if not lab12.STOP.exists():
        for wid in range(1, WORKERS + 1):
            if not alive(wid):
                launch(wid)
    lab12.merge()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
