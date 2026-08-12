# The trading systems

`CONTRACT.md` at the repository root splits the laboratory into an instrument
that decides nothing and a trading system that decides everything. This folder
is that second half, and as of 2026-08-12 it holds **two independent systems**
rather than one.

| package | what it is | resolution |
|---|---|---|
| `quantlab_trading/` | **System Four** — the operator's four-piece system: a market-wide trend detector, three regime-conditional branches, a router, and the money-management policy. Plus the shared contract every system uses. | daily, and hourly for override families |
| `quantlab_intraday/` | **The intraday system** — short-horizon hypotheses, one timeframe. `prepare` then `launch`. | 5m |

## Why two, and what keeps them apart

A daily system needs a multi-week move to clear a 0.30% round trip, so in a
falling market its honest answer is to hold cash. That is a ceiling rather than
a defect, and QUANT16 is the record of hitting it: the detector called BEAR
eleven days before the sealed window and held it through all of 2026. Raising
the resolution is the other way to attack the same problem — 96× the decisions,
a forward window of ~21,500 bars per asset instead of ~215 — and it is a
different enough claim to deserve its own code rather than another branch in
the router.

The separation is structural, not a convention:

```
quantlab_intraday  ──▶  quantlab_trading (contract only)  ──▶  quantlab_backtester
        └────────────────────────────────────────────────▶  quantlab_backtester
```

- `quantlab_intraday` imports exactly three things from `quantlab_trading`:
  `runner.Decision` (the tick contract), `brains.register` (the registry), and
  `policy.MoneyManagement` (the structural policy the instrument reads). It
  imports no strategy, no branch and no detector.
- **`quantlab_trading` imports nothing from `quantlab_intraday`.** That is what
  makes it impossible for the new system to move a number System Four has
  already recorded.
- Neither may import `quantlab_manager`, or a strategy could not be scored in
  isolation.

All three rules are enforced by `orchestrator-manager/scripts/check_layering.py`,
which fails the build rather than trusting this paragraph.

## Where a contribution lands

Still here, and registering is still the only wiring step. Which package
depends on what you are proposing:

- a rule about the major trend, a regime branch, or daily money management →
  `quantlab_trading/`;
- a mechanism whose horizon is hours and whose bar is minutes →
  `quantlab_intraday/`, and read its `README.md` first: it is a one-page
  operating guide and it states the 0.30%-per-trade hurdle any intraday rule
  has to clear before it is worth writing.

A new system entirely is a third package beside these two, with the same rule:
it may depend on the contract, never on another system's decisions.

## Running them

```bash
pip install -e .                                   # once, subprocesses included

python3 -m unittest discover -s trading-system/tests -t trading-system/tests
python3 orchestrator-manager/scripts/check_layering.py

python3 -m quantlab_intraday.prepare               # once: candles + indicator panels
python3 -m quantlab_intraday.launch --phase both  # blocks + the sealed window
```
