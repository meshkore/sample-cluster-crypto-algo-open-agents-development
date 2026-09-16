# System 09 v2, stage 1 — frozen 2026-09-14

The record of the concentrated-book path, closed deliberately rather than abandoned. Everything
below is reproducible from this commit; the next stage starts from a different idea and this
page exists so that the comparison is possible later.

## The best result this path produced

**90-day hold · 3 names per side · long/short · stop −5%**

| | Research years (2021–2025) | Sealed 2026 |
|---|---|---|
| Return | mean **+113%**, worst year **+25.4%** | **+5.38%** |
| Positive every year | **yes** — the first configuration ever to manage it | — |
| Max drawdown | — | −13.5% |
| Operations | — | 12 |
| Winners | — | **1** |
| Buy & hold universe, same window | +357.7% mean | −7.65% |
| Buy & hold BTC | — | −11.19% |

## The criteria that produced it

- **Selection on research years only**, by walk-forward: each year scored by a model fitted on
  everything before it and early-stopped on the year *before* it. No fit ever saw the year it
  was scoring, and no fit ever saw 2026.
- **Grid**: 4 horizons × 3 widths × 2 shapes × 5 stop levels = 120 candidates.
- **Bar**: positive in every research year **and** ahead of holding the universe in every
  research year. Nothing cleared the second half, and it was not relaxed to produce a winner.
- **Costs**: 0.30% round trip, charged on the stop as well.
- **Features**: market + ledger + world, at a 30-day horizon.

## Why it is being frozen rather than continued

The 2026 result is one trade. Eleven positions stopped out at −5.3% and the entire profit is a
single NEAR long at +94.2%. A concentrated book of three names per side cannot produce enough
independent outcomes in nine months for any number it prints to mean something, and no amount
of further tuning changes that arithmetic: the sample size is a property of the design.

The measurements that justify the next design, all taken here:

| Measurement | Value | What it implies |
|---|---|---|
| Rank IC, 30-day horizon, market+ledger+world | **+0.150**, positive in 5/5 folds | the model ORDERS the universe usefully |
| Directional accuracy | ~0.50 | it cannot call a single name's sign |
| Forecast bias over 2026 | +4.77% per week, up on 250/250 days | its LEVEL is meaningless |
| Winner drawdown vs loser drawdown | −1.5% vs −7.5% | the two populations separate, so risk control pays |

A signal that ranks well, calls signs badly and has an unusable level is precisely the signal
an **index** exploits and a **concentrated book** wastes. Ranking maps to weights; sign maps to
nothing. That is the whole argument for stage 2.

## What is frozen

- `policy.py` at this commit, with `STOPS` in the selection grid.
- `research/system09/policy_report.json` — the run above.
- The calibrated reconstruction (V5 CALIBRATED, worst float error 0.00% at three checkpoints).
- The macro layer (`world.py`), whose strict-addition test is the only arm positive in all
  five research folds.
