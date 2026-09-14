"""PHASE 3 - the sealed 2026 forward test: `python -m quantlab_system09.phase3`.

**This run spends the laboratory's sealed window.** 2026 has never been an optimisation input
for system 09: the reconstruction walks into it without changing behaviour, the model was
fitted and selected entirely on 2017-2025, and this module reads the result once and records
whatever it says. The operator asked for it explicitly and twice.

WHAT IS SIMULATED, AND HOW CLOSE TO REALITY IT TRIES TO BE

  capital      USD 100,000 on 2026-01-01, the laboratory's standing forward constraint
  direction    long only. Shorts are permitted by the constraints now, but a first forward
               reading should test one claim, not two
  sizing       equal weight across at most `MAX_POSITIONS` open trades, never levered
  entry        the model's predicted `HORIZON`-day return, ranked across the assets live
               that day; an asset is bought only if its prediction clears `MIN_SCORE`
  holding      exactly `HORIZON` days, then out. No discretion, so the hit rate means what
               it says
  cost         0.30% round trip - the laboratory's cost invariant, 10bps commission plus
               5bps slippage each way
  capacity     a position is capped at `PARTICIPATION` of the asset's own dollar volume on
               the entry day, which is what stops a backtest buying a token that was not
               there to buy

WHAT IT IS MEASURED AGAINST. Two baselines, both reported whatever they say: buying and
holding Bitcoin over the identical window, and buying and holding the universe equally
weighted. A strategy that does not beat holding the asset is not a strategy.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn as nn

from quantlab_catalog.paths import REPO_ROOT, indicator_dir

from . import features as F
from . import pipeline
from . import segments as SEG

SEALED_FROM = "2026-01-01"
SEALED_TO = "2026-09-14"
CAPITAL = 100_000.0
MAX_POSITIONS = 4
MIN_SCORE = 0.0
ROUND_TRIP = 0.0030
PARTICIPATION = 0.001
OUT = REPO_ROOT / "research" / "system09"


def _load_model(n_market: int, n_ledger: int):
    blob = torch.load(indicator_dir("system09") / "phase2_model.pt", weights_only=False)
    layers: list[nn.Module] = []
    prev = blob["n_in"]
    for h in blob["hidden"]:
        layers += [nn.Linear(prev, h), nn.GELU(), nn.Dropout(blob["dropout"])]
        prev = h
    layers.append(nn.Linear(prev, 1))
    model = nn.Sequential(*layers)
    model.load_state_dict(blob["state"])
    model.eval()
    return model, blob


def _predict(model, blob, ds) -> np.ndarray:
    x = ds.market if blob["variant"] == "market" else np.hstack([ds.market, ds.ledger])
    z = (x - blob["mu"]) / blob["sd"]
    with torch.no_grad():
        return model(torch.tensor(z, dtype=torch.float32)).squeeze(1).numpy()


def _simulate(ds, score: np.ndarray, dollars: dict[tuple[str, str], float]) -> dict:
    """Walk the sealed window day by day, opening and closing trades under the rules above."""
    rows: dict[str, list[int]] = {}
    for i, d in enumerate(ds.days):
        if SEALED_FROM <= d <= SEALED_TO:
            rows.setdefault(d, []).append(i)
    days = sorted(rows)

    cash = CAPITAL
    open_trades: list[dict] = []
    trades: list[dict] = []
    equity: list[dict] = []

    for d in days:
        # Close anything that has served its holding period, before deciding anything new.
        still: list[dict] = []
        for t in open_trades:
            if d >= t["exit_day"]:
                proceeds = t["units"] * t["exit_price"] * (1 - ROUND_TRIP / 2)
                cash += proceeds
                t["pnl"] = proceeds - t["cost"]
                t["ret"] = t["pnl"] / t["cost"] if t["cost"] else 0.0
                t["win"] = t["pnl"] > 0
                trades.append(t)
            else:
                still.append(t)
        open_trades = still

        free = MAX_POSITIONS - len(open_trades)
        if free > 0:
            held = {t["symbol"] for t in open_trades}
            candidates = sorted((i for i in rows[d]
                                 if score[i] > MIN_SCORE and ds.symbols[i] not in held),
                                key=lambda i: -score[i])[:free]
            # Size on CURRENT equity, not on the opening capital: a book that never
            # compounds is not the book anybody would have run.
            equity_now = cash + sum(t["units"] * t["entry_price"] * (1 + _progress(t, d))
                                    for t in open_trades)
            for i in candidates:
                budget = min(cash / max(1, free), equity_now / MAX_POSITIONS)
                cap = dollars.get((ds.symbols[i], d), 0.0) * PARTICIPATION
                budget = min(budget, cap) if cap > 0 else 0.0
                if budget < 50:
                    continue
                px = float(ds.price[i])
                units = budget * (1 - ROUND_TRIP / 2) / px
                cash -= budget
                exit_day = _shift(d, F.HORIZON)
                open_trades.append({
                    "symbol": ds.symbols[i], "entry_day": d, "exit_day": exit_day,
                    "entry_price": px, "exit_price": px * (1 + float(ds.y[i])),
                    "units": units, "cost": budget, "score": float(score[i]),
                })

        mark = sum(t["units"] * t["entry_price"] * (1 + _progress(t, d)) for t in open_trades)
        equity.append({"day": d, "equity": cash + mark, "cash": cash,
                       "open": len(open_trades)})

    for t in open_trades:                       # mark the tail out at its known exit price
        proceeds = t["units"] * t["exit_price"] * (1 - ROUND_TRIP / 2)
        cash += proceeds
        t["pnl"] = proceeds - t["cost"]
        t["ret"] = t["pnl"] / t["cost"] if t["cost"] else 0.0
        t["win"] = t["pnl"] > 0
        t["unclosed"] = True
        trades.append(t)
    if equity:
        equity[-1] = {**equity[-1], "equity": cash}

    curve = [e["equity"] for e in equity] or [CAPITAL]
    peak, dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1.0)
    wins = sum(1 for t in trades if t["win"])
    return {
        "trades": trades, "equity": equity,
        "n_trades": len(trades), "wins": wins, "losses": len(trades) - wins,
        "hit_rate": wins / len(trades) if trades else float("nan"),
        "final_equity": curve[-1], "return_pct": curve[-1] / CAPITAL - 1.0,
        "max_drawdown": dd,
        "avg_win": float(np.mean([t["ret"] for t in trades if t["win"]])) if wins else 0.0,
        "avg_loss": float(np.mean([t["ret"] for t in trades if not t["win"]]))
        if len(trades) - wins else 0.0,
    }


def _progress(trade: dict, day: str) -> float:
    """Linear mark between entry and exit. The reconstruction prices daily, so an open
    position is marked on a straight line rather than pretending to a path it never had."""
    a = _days(trade["entry_day"]), _days(trade["exit_day"]), _days(day)
    span = max(1, a[1] - a[0])
    frac = min(1.0, max(0.0, (a[2] - a[0]) / span))
    return (trade["exit_price"] / trade["entry_price"] - 1.0) * frac


def _days(d: str) -> int:
    return (datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
            - datetime(2026, 1, 1, tzinfo=timezone.utc)).days


def _shift(day: str, n: int) -> str:
    from datetime import timedelta
    return (datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
            + timedelta(days=n)).strftime("%Y-%m-%d")


def _buy_and_hold(traj, symbols: list[str]) -> dict[str, float]:
    """What holding would have done over the identical window, per asset and equal weighted."""
    idx = {d: i for i, d in enumerate(traj.days)}
    lo = min((d for d in traj.days if d >= SEALED_FROM), default=None)
    hi = max((d for d in traj.days if d <= SEALED_TO), default=None)
    if lo is None or hi is None:
        return {}
    out = {}
    for s in symbols:
        a = traj.prices[idx[lo]].get(s)
        b = traj.prices[idx[hi]].get(s)
        if a and b:
            out[s] = b / a - 1.0
    out["_equal_weight"] = float(np.mean([v for k, v in out.items()
                                          if not k.startswith("_")])) if out else 0.0
    return out


def main() -> int:
    print("SYSTEM 09 - PHASE 3: the sealed 2026 forward test")
    print(f"  window [{SEALED_FROM} .. {SEALED_TO}]   capital ${CAPITAL:,.0f}   "
          f"long only, max {MAX_POSITIONS} positions, {ROUND_TRIP:.2%} round trip\n")

    ctx, traj = pipeline.reconstruct(end=SEALED_TO, sealed=True, quiet=True)
    ds = F.build(traj, ctx.funding())
    model, blob = _load_model(ds.market.shape[1], ds.ledger.shape[1])
    print(f"  model variant '{blob['variant']}'  inputs {blob['n_in']}  "
          f"horizon {blob['horizon']}d")

    score = _predict(model, blob, ds)
    sealed = ds.mask(lo=SEALED_FROM)
    ic = _spearman_np(score[sealed], ds.y[sealed])
    hit = float(((score[sealed] > 0) == (ds.y[sealed] > 0)).mean())
    print(f"  sealed rows {int(sealed.sum()):,}   IC {ic:+.4f}   "
          f"directional accuracy {hit:.4f}\n")

    sim = _simulate(ds, score, ctx.day_dollars)
    bh = _buy_and_hold(traj, sorted(set(ds.symbols)))

    print("  RESULT")
    print(f"    operations            {sim['n_trades']}")
    print(f"    successful            {sim['wins']}")
    print(f"    unsuccessful          {sim['losses']}")
    print(f"    success ratio         {sim['hit_rate']:.2%}")
    print(f"    average win / loss    {sim['avg_win']:+.2%} / {sim['avg_loss']:+.2%}")
    print(f"    return                {sim['return_pct']:+.2%}")
    print(f"    max drawdown          {sim['max_drawdown']:.2%}")
    print(f"    final equity          ${sim['final_equity']:,.0f}")
    print("\n  BASELINES over the identical window")
    print(f"    buy and hold BTC      {bh.get('BTCUSDT', float('nan')):+.2%}")
    print(f"    buy and hold universe {bh.get('_equal_weight', float('nan')):+.2%}")

    idx = {d: i for i, d in enumerate(traj.days)}
    market_2026 = [{"day": d, "market_cap": traj.market_cap[idx[d]],
                    "btc": traj.prices[idx[d]].get("BTCUSDT", 0.0),
                    "players": traj.headcount[idx[d]],
                    "segments": {k: {"cash": v["cash"], "assets": v["assets"],
                                     "players": v["players"]}
                                 for k, v in traj.segments[idx[d]].items()}}
                   for d in traj.days if d >= SEALED_FROM]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase3_report.json").write_text(json.dumps({
        "window": [SEALED_FROM, SEALED_TO], "capital": CAPITAL,
        "rules": {"long_only": True, "max_positions": MAX_POSITIONS,
                  "hold_days": F.HORIZON, "round_trip": ROUND_TRIP,
                  "participation_cap": PARTICIPATION, "min_score": MIN_SCORE},
        "model": {"variant": blob["variant"], "inputs": blob["n_in"],
                  "horizon": blob["horizon"]},
        "sealed_ic": ic, "sealed_directional_accuracy": hit,
        "n_trades": sim["n_trades"], "wins": sim["wins"], "losses": sim["losses"],
        "hit_rate": sim["hit_rate"], "return_pct": sim["return_pct"],
        "max_drawdown": sim["max_drawdown"], "final_equity": sim["final_equity"],
        "avg_win": sim["avg_win"], "avg_loss": sim["avg_loss"],
        "baselines": bh, "equity": sim["equity"], "trades": sim["trades"],
        "market_2026": market_2026,
        "segment_labels": SEG.LABELS,
    }, indent=1), encoding="utf-8")
    print(f"\n  written  {OUT / 'phase3_report.json'}")
    return 0


def _spearman_np(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 8:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(np.float64)
    rb = np.argsort(np.argsort(b)).astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


if __name__ == "__main__":
    sys.exit(main())
