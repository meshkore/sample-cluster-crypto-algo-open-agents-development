"""A103: the champion is fed 96 bars and can only see 15 of them.

Measured by gradient probe on the shipping net, not by reading the config: push a
window through OracleNet and ask which input timesteps the output depends on. 15 of
the 96 bars have a non-zero gradient. The other 81 are read from disk, standardised,
copied to the GPU and multiplied by nothing - their influence on the prediction is
exactly zero.

    window 96 bars                  24h at 15m
    channels [192, 192, 192]        dilations 1, 2, 4
    receptive field 1 + 2*(1+2+4) = 15 bars       3h45m

The teacher, meanwhile, is a 3% zigzag: its hold-runs last DAYS. So the student is
being asked to predict a multi-day swing state from under four hours of context, and
the extra twenty hours we carefully prepared for it are decoration.

Nothing needs to be written to fix it. ModelConfig.resolved_dilations derives the
dilations from the LENGTH of `channels` - `2**i for i in range(len(channels))` - so
six blocks give dilations 1,2,4,8,16,32 and a receptive field of 127 bars, which
finally covers the window with room to spare. The cost is one more doubling of
depth: ~2x the parameters of a model that is already only 256k.

This is the treatment arm. Everything else is copied from the champion's model card
verbatim - same 14 symbols, same seed, same 50 epochs, same 3% label threshold, same
96-bar window - so the ONLY difference between this net and the shipping one is how
far back it is allowed to look.

Run from the repo root with PYTHONPATH=trading-system.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from system006_oracle_net_15m.train import train

# Copied from research/system06/_w192/model_card.json, not re-derived.
CHAMPION = dict(
    symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ACEUSDT",
             "ZECUSDT", "TRXUSDT", "SUIUSDT", "WLDUSDT", "DOGEUSDT", "NEARUSDT",
             "LINKUSDT", "ADAUSDT"],
    interval="15m",
    threshold=0.03,
    window=96,
    epochs=50,
    seed=91002,
    dropout=0.1,
)
CONTROL_CHANNELS = (192, 192, 192)          # receptive field 15 bars
TREATMENT_CHANNELS = (192,) * 6             # receptive field 127 bars


def receptive_field(channels, kernel: int = 3) -> int:
    dil = [2 ** i for i in range(len(channels))]
    return 1 + (kernel - 1) * sum(dil)


def main() -> int:
    out = Path("research/system06/_w192d6")
    rf_c, rf_t = receptive_field(CONTROL_CHANNELS), receptive_field(TREATMENT_CHANNELS)
    print(f"control   channels {list(CONTROL_CHANNELS)}  receptive field {rf_c:>3} bars "
          f"({rf_c * 15 / 60:.2f}h)  <- the shipping champion")
    print(f"treatment channels {list(TREATMENT_CHANNELS)}  receptive field {rf_t:>3} bars "
          f"({rf_t * 15 / 60:.2f}h)  <- covers the {CHAMPION['window']}-bar window")
    print(f"out -> {out}", flush=True)

    started = datetime.now(timezone.utc)
    result = train(out_dir=str(out), channels=TREATMENT_CHANNELS, **CHAMPION)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    note = {
        "id": "A103", "at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 1),
        "control": {"channels": list(CONTROL_CHANNELS), "receptive_field_bars": rf_c},
        "treatment": {"channels": list(TREATMENT_CHANNELS), "receptive_field_bars": rf_t},
        "window": CHAMPION["window"],
        "shared": {k: v for k, v in CHAMPION.items() if k != "symbols"},
        "result": {k: v for k, v in (result or {}).items()
                   if not isinstance(v, (list, dict)) or k in ("val_metrics",)},
        "status": "trained; NOT adopted - a paired backtest and the held-out method "
                  "decide, and the sealed year is a separate deliberate reading",
    }
    dest = Path("research/system06/rnd") / f"a103_deep_field_{started:%Y-%m-%d}.json"
    dest.write_text(json.dumps(note, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {dest}  ({elapsed / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
