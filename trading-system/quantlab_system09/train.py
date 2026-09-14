"""PHASE 2 - train the model: `python -m quantlab_system09.train`.

The operator's phase 2 is "train the model on how the players behaved". `features.py` explains
why that cannot mean fitting a policy to the reconstruction's own flows - it would be fitting
my priors to themselves. It means this instead:

    the cohort state is the INPUT, the market's forward return is the TARGET, and the whole
    experiment is whether the first helps predict the second beyond what price already says.

TWO MODELS, IDENTICAL IN EVERY OTHER RESPECT

  MARKET          returns, drawdown, volatility, funding. The baseline.
  MARKET+LEDGER   the same, plus who holds the float, who has dry powder, and how far each
                  segment sits from its cost basis.

Same architecture, same seed, same optimiser, same epochs, same folds. The only difference is
the input width. That is what makes the comparison a measurement rather than a demonstration:
if the ledger half adds nothing, the two curves land on top of each other and we say so.

WALK-FORWARD, AND THE SEALED WINDOW IS NOT IN IT

Folds train on everything before a year and validate on that year: 2021 through 2025. Nothing
is selected on 2026 - it is not loaded here at all. The final model is refitted on the whole
research era with the settings fixed in advance, and saved for phase 3 to use once.

The metric is the rank correlation between prediction and realised forward return
(the information coefficient), plus directional accuracy. Rank correlation because the sizes
of crypto returns are heavy-tailed enough that a squared error is mostly a report on which
week had the biggest move.
"""

from __future__ import annotations

import json
import sys
import time

import numpy as np
import torch
import torch.nn as nn

from quantlab_catalog.paths import indicator_dir

from . import features as F
from . import pipeline

SEED = 20260914
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
FOLDS = ("2021", "2022", "2023", "2024", "2025")
RESEARCH_END_EXCLUSIVE = "2026-01-01"

EPOCHS = 120
PATIENCE = 15
BATCH = 512
HIDDEN = (128, 64)
DROPOUT = 0.25
LR = 1e-3
WEIGHT_DECAY = 1e-4

OUT = indicator_dir("system09")


def _mlp(n_in: int) -> nn.Module:
    layers: list[nn.Module] = []
    prev = n_in
    for h in HIDDEN:
        layers += [nn.Linear(prev, h), nn.GELU(), nn.Dropout(DROPOUT)]
        prev = h
    layers.append(nn.Linear(prev, 1))
    return nn.Sequential(*layers)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 8:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(np.float64)
    rb = np.argsort(np.argsort(b)).astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


def _fit(x_tr: np.ndarray, y_tr: np.ndarray, x_va: np.ndarray, y_va: np.ndarray,
         seed: int = SEED) -> tuple[nn.Module, dict, float, np.ndarray]:
    """Fit one model, early-stopping on the validation information coefficient.

    Standardisation is fitted on the TRAINING rows only and carried with the model. A scaler
    fitted on everything is a small, silent leak of the validation era's distribution, and
    this laboratory has paid for smaller ones.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    mu, sd = x_tr.mean(0), x_tr.std(0)
    sd[sd < 1e-8] = 1.0
    xt = torch.tensor((x_tr - mu) / sd, device=DEVICE)
    yt = torch.tensor(y_tr, device=DEVICE).unsqueeze(1)
    xv = torch.tensor((x_va - mu) / sd, device=DEVICE)

    model = _mlp(x_tr.shape[1]).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    loss_fn = nn.SmoothL1Loss(beta=0.02)     # heavy tails: a pure MSE fits the outliers

    best_ic, best_state, best_pred, waited = -9.9, None, None, 0
    n = len(xt)
    for _ in range(EPOCHS):
        model.train()
        perm = torch.randperm(n, device=DEVICE)
        for k in range(0, n, BATCH):
            sel = perm[k:k + BATCH]
            opt.zero_grad()
            loss_fn(model(xt[sel]), yt[sel]).backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            pred = model(xv).squeeze(1).cpu().numpy()
        ic = _spearman(pred, y_va)
        if ic > best_ic:
            best_ic, waited = ic, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            best_pred = pred
        else:
            waited += 1
            if waited >= PATIENCE:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, {"mu": mu, "sd": sd}, best_ic, best_pred


def _hit_rate(pred: np.ndarray, y: np.ndarray) -> float:
    m = pred != 0
    return float(((pred[m] > 0) == (y[m] > 0)).mean()) if m.any() else float("nan")


def main() -> int:
    print("SYSTEM 09 - PHASE 2: train the model")
    print(f"  device {DEVICE}"
          + (f" ({torch.cuda.get_device_name(0)})" if DEVICE == "cuda" else "") + "\n")

    ctx, traj = pipeline.reconstruct(end="2026-09-14", sealed=True, quiet=True)
    ds = F.build(traj, ctx.funding())
    research = ds.mask(hi=RESEARCH_END_EXCLUSIVE)
    print(f"  rows {len(ds):,}  research {int(research.sum()):,}  "
          f"market features {ds.market.shape[1]}  ledger features {ds.ledger.shape[1]}")
    print(f"  horizon {F.HORIZON} days   assets {len(set(ds.symbols))}\n")

    variants = {"market": ds.market, "market+ledger": np.hstack([ds.market, ds.ledger])}
    results: dict[str, list[dict]] = {k: [] for k in variants}

    print(f"  {'fold':<8s} {'train':>8s} {'valid':>7s}   "
          + "   ".join(f"{k:>22s}" for k in variants))
    for year in FOLDS:
        tr = ds.mask(hi=f"{year}-01-01")
        va = ds.mask(lo=f"{year}-01-01", hi=f"{int(year)+1}-01-01") & research
        if tr.sum() < 2000 or va.sum() < 200:
            continue
        line = f"  {year:<8s} {int(tr.sum()):8,d} {int(va.sum()):7,d}   "
        for name, x in variants.items():
            t0 = time.time()
            _, _, ic, pred = _fit(x[tr], ds.y[tr], x[va], ds.y[va])
            hit = _hit_rate(pred, ds.y[va])
            results[name].append({"fold": year, "ic": ic, "hit": hit,
                                  "n_train": int(tr.sum()), "n_valid": int(va.sum())})
            line += f"IC {ic:+.4f} hit {hit:.3f} {time.time()-t0:4.0f}s   "
        print(line)

    print()
    summary = {}
    for name, rows in results.items():
        ics = [r["ic"] for r in rows if r["ic"] == r["ic"]]
        hits = [r["hit"] for r in rows if r["hit"] == r["hit"]]
        summary[name] = {"mean_ic": float(np.mean(ics)) if ics else float("nan"),
                         "mean_hit": float(np.mean(hits)) if hits else float("nan"),
                         "folds_positive": sum(1 for v in ics if v > 0), "n_folds": len(ics),
                         "per_fold": rows}
        print(f"  {name:<16s} mean IC {summary[name]['mean_ic']:+.4f}   "
              f"mean hit {summary[name]['mean_hit']:.4f}   "
              f"positive folds {summary[name]['folds_positive']}/{summary[name]['n_folds']}")

    gain = summary["market+ledger"]["mean_ic"] - summary["market"]["mean_ic"]
    wins = sum(1 for a, b in zip(results["market+ledger"], results["market"])
               if a["ic"] > b["ic"])
    print(f"\n  V4 STRICT ADDITION: the ledger features change mean IC by {gain:+.4f} "
          f"and win {wins} of {len(results['market'])} folds")
    verdict = "LEDGER HELPS" if (gain > 0 and wins > len(results["market"]) / 2) \
        else "LEDGER DOES NOT HELP"
    print(f"  verdict: {verdict}")

    # The model phase 3 will use: the winning variant, refitted on the whole research era with
    # the settings fixed above. The last research year is held out purely as the early-stopping
    # signal - it selects the epoch, never the feature set, which was decided by the folds.
    chosen = "market+ledger" if verdict == "LEDGER HELPS" else "market"
    x = variants[chosen]
    fit_tr = ds.mask(hi="2025-01-01")
    fit_va = ds.mask(lo="2025-01-01", hi=RESEARCH_END_EXCLUSIVE)
    model, scaler, ic, _ = _fit(x[fit_tr], ds.y[fit_tr], x[fit_va], ds.y[fit_va])
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"state": model.state_dict(), "mu": scaler["mu"], "sd": scaler["sd"],
                "variant": chosen, "n_in": x.shape[1], "hidden": HIDDEN,
                "dropout": DROPOUT, "horizon": F.HORIZON, "seed": SEED},
               OUT / "phase2_model.pt")
    (OUT / "phase2_report.json").write_text(json.dumps({
        "device": DEVICE, "rows": len(ds), "research_rows": int(research.sum()),
        "horizon": F.HORIZON, "folds": list(FOLDS), "summary": summary,
        "v4_gain_mean_ic": gain, "v4_folds_won": wins, "verdict": verdict,
        "chosen_variant": chosen, "final_holdout_ic_2025": ic,
    }, indent=2), encoding="utf-8")
    print(f"\n  chosen variant '{chosen}', refit on research, 2025 early-stop IC {ic:+.4f}")
    print(f"  saved  {OUT / 'phase2_model.pt'}\n         {OUT / 'phase2_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
