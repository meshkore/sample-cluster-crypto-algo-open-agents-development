"""System 08 — open, deliberately empty.

Opened 2026-09-08 at the operator's instruction: "abrir una nueva estrategia en blanco
sin hacer nada... que lo unico que va a hacer es intentar siempre superar al best result
de la tabla."

THERE IS NO HYPOTHESIS HERE YET, and that is the point. The folder, the loop, the
documentation and the data access are ready; the idea is not, and inventing one to fill
the silence would be the single worst way to start. System 06 spent three weeks proving
that a plausible idea measured badly is more expensive than no idea at all.

WHAT IS ALREADY AVAILABLE, so nothing here is built twice:

    import quantlab_catalog as cat
    symbols = cat.load_universe()      # the frozen tradable list
    bars    = cat.research(symbols)    # every bar strictly before 2026 - cannot leak
    sealed  = cat.forward(symbols)     # 2026, alone, and only when a reading is earned

Fourteen symbols of 15-minute candles back to 2017, perp funding, Fear & Greed, four
on-chain series and eleven FRED macro series. Seven years of downloads this laboratory
has already paid for. `python -m quantlab_catalog.inventory` prints exactly what is
there and, more usefully, what is not.

WHAT THIS SYSTEM MUST BEAT: the best sealed 2026 result on the table, which today is
system 06 at +25.71% with a 22.13% drawdown over 90 trades. One number, one bar, and it
does not move because we would like it to.

WHAT IT MUST NOT REPEAT: read
`trading-system/quantlab_system06/docs/SUMMARY.md` first - specifically sections 4 and 6,
the twenty ideas that were measured and refused and the nine rules that cost real weeks
to learn. That reading is not optional and it is not a formality; three of those refusals
were candidates that looked better than anything this folder will produce in its first
week.
"""

from __future__ import annotations

__all__ = ["SYSTEM_ID", "INCUMBENT_SEALED_2026"]

SYSTEM_ID = "system08"
# The bar. A single number, stated once, so no part of this system can quietly redefine
# what winning means. Source: research/system06/best.json, forward_2026.
INCUMBENT_SEALED_2026 = 0.2571143689499318
