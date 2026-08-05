---
title: "The drawdown abort moves to 30%, and stops doubling as the de-leverage ramp"
updated: 2026-08-05
status: stable
---

Context: the operator raised the mandated abort from 25% to 30% and asked
whether a different budget works better. Implementing that literally would
have changed two things at once, because `maximum_drawdown` was doing two
unrelated jobs — the hard abort threshold, and the far end of the ramp that
scales positions down as drawdown deepens. Raising it to allow a deeper
excursion would therefore *also* have enlarged every position at every
drawdown level along the way, and the two effects would have been
inseparable in the result. This is the same coupling QUANT14 removed from
`stop_loss_pct`, found in a second parameter.

Decision: **`drawdown_deleverage_end` is a separate parameter.** It defaults
to `None`, meaning "use `maximum_drawdown`", so every policy already stored in
the database keeps its exact previous behaviour and no historical result
moves. `config/default.json` now sets the abort to 0.30 and pins the ramp end
at 0.25, so the operator's change means what it says: more room before the
run is killed, with sizing untouched.

Measured consequence, five-asset hourly basket, pre-2026:

| arm | abort | ramp end | return | max DD |
|---|---|---|---|---|
| regime_router | 0.25 | 0.25 | +166.37% | 20.66% |
| regime_router | 0.30 | 0.25 | +166.37% | 20.66% |
| regime_router | 0.30 | 0.30 | +169.58% | 20.92% |
| control | 0.25 | 0.25 | +432.42% | 19.05% |
| control | 0.30 | 0.30 | +433.88% | 19.06% |

**Raising the abort alone is bit-identical to not raising it.** Nothing at
this scope was ever hitting the limit, so the abort threshold was inert; the
entire +3.2 point difference comes from the gentler ramp, and on the control
it is +1.5 points on a +432% base. The drawdown budget was not what was
holding results back, and now there is a number saying so instead of an
assumption either way.

This supersedes the corollary in
[[2026-08-04-select-at-the-deployment-scope]] that fixed the abort at 25%. The
rest of that corollary stands unchanged and is the reason this record exists
rather than a quiet edit: **the abort is still a constraint on the search,
never a parameter inside it.** A sweep does not get to choose its own
drawdown budget to make a cell legal — the budget is set here, deliberately,
by the operator, and every sweep runs under whatever it currently is.

Consequence for the published ledger: every result recorded before 2026-08-05
was produced under the 25% abort. Two of them were rejected specifically for
breaching it (QUANT13 stage 4 at 25.34%, QUANT14 stage 5 at 25.47%) and would
be legal under 30%. They are not retroactively promoted — they were selected
on single-asset evidence, which the deployment-scope decision rejects on
separate grounds that this change does not touch.
