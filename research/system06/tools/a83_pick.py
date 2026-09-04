"""Pick the point that would actually be shipped, on a rule written before it is applied.

THE RULE, and it uses only FIT and drawdown - never the held-out score:

    among trials whose worst calendar-year drawdown is at or below the CHAMPION'S
    (20.8%), take the highest FIT score.

Two reasons it is not simply "the best fit score".

The drawdown clause: the raw best (trial 66) costs 25.9%, and the top-20 median is
21.2%, so points at champion-level risk exist inside the same good region. Buying the
result with five extra points of drawdown when the region does not require it would be
paying for nothing - and under the operator's balance criterion a gain merely
proportional to its extra drawdown is not worth taking anyway.

Not the best HELD-OUT trial: that would leak the holdout into selection just as
thoroughly as optimising on it, and would look perfectly reasonable in a report. The
held-out figure of whatever this rule returns is a readout, not a chooser.

A max-of-N is inflated by selection whatever the N. The region median is quoted beside
the pick for exactly that reason, and it is the number that should be believed.
"""
import importlib.util
import json
import statistics

import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)
spec = importlib.util.spec_from_file_location(
    "n", "research/system06/tools/numerical_optimization.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CHAMPION_DD = 0.208     # the incumbent's worst calendar-year drawdown, from trial 0

s = optuna.load_study(study_name="thresholds-v1",
                      storage="sqlite:///research/system06/rnd/optuna_thresholds.db")
done = [t for t in s.trials if t.state.name == "COMPLETE" and t.value is not None]
base = done[0]
eligible = [t for t in done if (t.user_attrs.get("worst_drawdown") or 9) <= CHAMPION_DD]
pick = max(eligible, key=lambda t: t.value)

print(f"{len(done)} trials, {len(eligible)} at or below the champion's {CHAMPION_DD:.1%} drawdown\n")
for lab, t in (("CHAMPION      ", base), (f"PICK (trial {pick.number:>3})", pick)):
    a = t.user_attrs
    print(f"{lab}  fit {t.value:+.4f}  holdout {a['holdout']:+.4f}  "
          f"worst fit yr {a['fit_min_year']:+.2%}  worst holdout yr {a['holdout_min_year']:+.2%}  "
          f"maxDD {a['worst_drawdown']:.1%}")
    print("                " + "  ".join(f"{y} {v:+.1%}" for y, v in sorted(a["returns"].items())))

print("\nparams (champion -> pick):")
champ = m._champion_point(json.loads(open("research/system06/best.json", encoding="utf-8").read())["risk"],
                          json.loads(open("research/system06/best.json", encoding="utf-8").read())["band"])
for k in sorted(pick.params):
    c, p = champ[k], pick.params[k]
    f = (lambda v: f"{v:.4g}" if isinstance(v, float) else str(v))
    print(f"  {k:<20} {f(c):>10} -> {f(p):>10}")

top = sorted(eligible, key=lambda t: -t.value)[:20]
print(f"\nthe region, not the point - top 20 eligible by fit:")
print(f"  median holdout      {statistics.median(t.user_attrs['holdout'] for t in top):+.4f}"
      f"   (champion {base.user_attrs['holdout']:+.4f})")
print(f"  median worst yr     {statistics.median(t.user_attrs['holdout_min_year'] for t in top):+.2%}"
      f"   (champion {base.user_attrs['holdout_min_year']:+.2%})")
print(f"  median maxDD        {statistics.median(t.user_attrs['worst_drawdown'] for t in top):.1%}"
      f"   (champion {base.user_attrs['worst_drawdown']:.1%})")
print(f"  all years positive  {sum(1 for t in top if min(t.user_attrs['returns'].values()) > 0)}/20"
      f"   (champion: no, 2025 is {base.user_attrs['returns']['2025']:+.1%})")

out = "research/system06/rnd/a83_pick.json"
json.dump({"rule": "highest FIT among trials with worst drawdown <= the champion's 20.8%; "
                   "the held-out score is a readout and never a chooser",
           "trials_seen": len(done), "eligible": len(eligible),
           "champion": {"fit": base.value, **base.user_attrs},
           "pick": {"trial": pick.number, "params": pick.params, "fit": pick.value,
                    **pick.user_attrs},
           "region_median_holdout": statistics.median(t.user_attrs["holdout"] for t in top)},
          open(out, "w", encoding="utf-8"), indent=1, default=str)
print(f"\nwritten -> {out}")
