# Strategy S00004

## Signal criteria

```json
{
  "entry_logic": "target long after trigger; next-open fill",
  "exit_logic": "exit after close below 10-bar mean",
  "family": "volatility_expansion",
  "features": [
    "lagged_close_return",
    "prior_20_bar_high",
    "rolling_range"
  ],
  "parameters": {
    "_execution_variant": "MM-00002",
    "exit_window": 10,
    "lookback": 20,
    "max_vol": 0.04
  },
  "trigger": "close[t] > max(close[t-20:t]) and range volatility is bounded"
}
```

## Execution

```json
{
  "commission_bps": 10.0,
  "fill": "next_bar_open",
  "side": "LONG_ONLY",
  "slippage_bps": 5.0
}
```

## Money management

```json
{
  "drawdown_safety_buffer": 0.05,
  "initial_capital": 100000.0,
  "long_only": true,
  "maximum_concurrent_assets": 8,
  "maximum_drawdown": 0.25,
  "maximum_position_fraction": 0.05,
  "minimum_confidence": 0.5,
  "minimum_order_notional": 10.0,
  "objective": "maximize_return_subject_to_max_drawdown_lt_25pct",
  "optimizer_generation": 0,
  "optimizer_source": "latin_hypercube_seed",
  "optimizer_variant": "MM-00002",
  "risk_per_trade": 0.0015,
  "stop_loss_pct": 0.025,
  "take_profit_pct": 0.05,
  "volatility_lookback": 20,
  "volatility_target": 0.02
}
```
