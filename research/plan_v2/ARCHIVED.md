# ARCHIVED 2026-10-21 - System 11 (plan v2)

Stopped on the operator's decision: "stop at System 11, everything on System 12". Do not extend this folder.

- **What it was.** A point-in-time top-14 coin-ranking model (MLP), long-only spot, walk-forward. Per year: 2020 +59%, 2021 +96%, 2022 -12%, 2023 +38%, 2024 +19%, 2025 +7.8%, 2026 +1.7%.
- **Why it stopped.** Every attempt to improve it failed walk-forward:
  - `bayes11*/`, `rocket11/`, `exits11/`, `ema_exit_test.py`, `classics11/`;
  - bigger size, `lab/` grid C.

  "Equal-weight basket while BTC > MA100" matched it at equal risk, so the net adds almost nothing. See `research/system12/README.md`.
- **Still running, as a yardstick only.** The Windows task `plan-v2-forward-ic` (4 h) runs `forward_ic.py` and the System 11 paper book `paper_v2.py`.
- **Disabled.** The tasks `plan-v2-lab`, `plan-v2-controller` and `plan-v2-history`, and Rocket 11 (`rocket11/STOP`).
- **Still imported by System 12, so do NOT move or delete:**
  - `history_v2.py` (point-in-time data, costs, funding);
  - `classics11.py` (`Ctx`), `bayes11.py` (yearly / drawdown / objective helpers);
  - `rocket11.py` + `rocket11/cache/base.npz`;
  - `lab_v2.py`, `phase3_select.py`.
