# System 003 — the supervised-ML generation (2026-08-12)

**There is no strategy package here, and that is the record, not an omission.**

Generation three was the first time the laboratory tried to *learn* a rule instead of
being told one: triple-barrier labels, purged time-series splits, a feature table built
strictly from columns the backtester had already served. It worked well enough that its
machinery outlived it — every later generation trains on it.

So the code lives at `trading-system/quantlab_ml/` as a **shared library**, not as a
system, because three systems import it:

- `systems/system002_intraday_momentum_5m/momentum.py`
- `systems/system005_meta_label_filter/strategy.py`
- `systems/system006_oracle_net_15m/{channels,meta}.py`

Promoting it to a numbered system folder would let one system's edit silently change
another system's measured result. Keeping it shared and keeping this note is the honest
way to hold the number open.

See `trading-system/systems/README.md` for where 003 sits in the sequence.
