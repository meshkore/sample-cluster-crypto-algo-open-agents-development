"""List the decision modules and their levers: `python -m quantlab_system06.modules`.

A quick, dependency-free introspection of the ensemble's parts — proof that each module
stands on its own and a map of which lever turns each on.
"""

from __future__ import annotations

from . import meta, microstructure, momentum, money, oracle_nn, regime, risk, volatility

MODULES = [
    (oracle_nn.OracleNN, "always on", "the TCN's per-bar conviction (the primary)"),
    (meta.Meta, "meta_margin", "refuse entries the secondary model expects to lose"),
    (risk.Stops, "stop_loss / trail_stop", "hard + trailing stop exits"),
    (regime.Regime, "breadth_gate / regime_deploy / regime_persist", "breadth risk-off + deployment"),
    (volatility.Volatility, "vol_scale / vol_floor", "vol-target position sizing"),
    (momentum.Momentum, "mom_gate", "cross-sectional relative-strength gate"),
    (money.Money, "money_kelly / money_pyramid", "fractional-Kelly + anti-martingale"),
    (microstructure.Microstructure, "micro_gate", "contrarian veto from derivatives crowd"),
]


def main() -> int:
    print("system 06 decision modules (combined by orchestrator.EnsembleBrain):\n")
    for cls, lever, blurb in MODULES:
        inst = cls()
        print(f"  {inst.name:<15} weight={inst.weight:<3g} lever: {lever}")
        print(f"  {'':<15} {blurb}")
    print("\nEvery module self-disables when its lever is off; see README.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
