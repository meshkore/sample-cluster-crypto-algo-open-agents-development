"""The walk-forward exam, as ONE instrument instead of a copy per question.

    python research/system06/tools/walkforward.py --id A111 \
        --arms "{\"reach15\": {}, \"reach7\": {\"dilations\": [1,1,1]}}" \
        --train-until 2024 --exam 2025 --seeds 91002

Why this file exists. Since A103 lost the sealed year by 43 points, the mandated
instrument for any NET-level change has been: train on years <= X, judge on year X+1
alone, and spend no sealed reading until a candidate has won one. That rule has been
obeyed -- and re-implemented every time. `a109_walkforward.py`, `a110b_recency_exam2.py`,
`a112_wf_second_exam.py`, `a113_wf_third_exam.py` and `a96b_reference_exam2.py` are five
copies of the same forty lines with the arms and the years edited in place. Five copies
is five chances for one of them to drift, and a drifted exam is worse than no exam
because its verdict still reads like the others'.

So the arms are DATA. Everything else -- the champion's band and risk verbatim, the
overlays rebuilt per arm, the single exam year, the refusal to touch 2026 -- is fixed
here and is the same for every question anyone asks of it.

One honesty note, inherited from A109 and worth keeping in front of the reader: the meta
and money overlays are fitted on research bars that INCLUDE the exam year. The net never
sees it; the overlays' own procedure walks expanding blocks, so their verdicts in the
exam year are causal. The band and the risk config are the champion's, chosen long before
any arm here runs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("research/system06")


def main(argv: list[str] | None = None) -> int:
    from system006_oracle_net_15m import autoloop, infer, launch, moneymodel, train, universe
    from system006_oracle_net_15m import meta as metalabel
    from system006_oracle_net_15m.dataset import Dataset
    from quantlab_catalog.paths import DATA_ROOT

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--id", required=True, help="agenda id, e.g. A111")
    parser.add_argument("--arms", required=True,
                        help="JSON mapping label -> train() kwargs; first arm is the control")
    parser.add_argument("--train-until", type=int, required=True)
    parser.add_argument("--exam", type=int, required=True,
                        help="the single year to judge on; must be train_until + 1")
    parser.add_argument("--seeds", default="91002",
                        help="comma list; one net per arm per seed")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)

    if args.exam != args.train_until + 1:
        raise SystemExit(
            f"exam year {args.exam} is not {args.train_until}+1. The exam is the FIRST "
            "year the net has never seen; any later year is a different question, and a "
            "wider gap quietly becomes a test of staleness instead of skill.")
    if args.exam >= 2026:
        raise SystemExit("2026 is the sealed window and is never an exam year")

    arms: dict[str, dict] = json.loads(args.arms)
    if not arms:
        raise SystemExit("no arms")
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    control = next(iter(arms))

    best = json.loads((ROOT / "best.json").read_text(encoding="utf-8"))
    cfg, band, risk = dict(best["config"]), dict(best["band"]), dict(best["risk"])
    enter, exit_, hold = float(band["enter"]), float(band["exit_"]), int(band["min_hold"])
    data = str(DATA_ROOT)

    symbols = universe.load()
    if not isinstance(symbols, list) or len(symbols) < 5:
        raise SystemExit(f"degenerate universe: {symbols!r} -- run from the repository root")
    dataset = Dataset(data_root=data, symbols=symbols, interval="15m")
    rbars = dataset.research()
    rstamps = sorted({b.timestamp for series in rbars.values() for b in series})

    print(f"{args.id}: train_until={args.train_until}, exam={args.exam}, "
          f"{len(arms)} arms x {len(seeds)} seed(s), control = {control!r}", flush=True)

    results: dict[str, dict] = {}
    for name, extra in arms.items():
        per_seed = {}
        for seed in seeds:
            scratch = ROOT / f"_wf_{args.id}_{name}_{seed}".replace(" ", "")
            scratch.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            print(f"\n=== {name} seed {seed}: {extra or 'champion recipe verbatim'} ===",
                  flush=True)
            call = dict(data_root=data, symbols=symbols, threshold=cfg["threshold"],
                        window=cfg["window"], epochs=cfg["epochs"], lr=cfg["lr"],
                        dropout=cfg["dropout"], out_dir=str(scratch), seed=seed,
                        uniqueness_weighting=float(cfg.get("uniqueness_weighting", 0.0)),
                        embargo=int(cfg.get("embargo", 0)),
                        enter=enter, exit_=exit_, min_hold=hold,
                        train_until=args.train_until)
            if cfg.get("channels"):
                call["channels"] = tuple(int(c) for c in cfg["channels"])
            call.update(extra)
            if not (scratch / "oracle_net.pt").exists():
                train.train(**call)
                print(f"  trained in {(time.time() - t0) / 60:.1f} min", flush=True)

            sig = str(scratch / "signals.npz")
            if not Path(sig).exists():
                infer.export(data_root=data, symbols=symbols, model_dir=str(scratch),
                             out_path=sig,
                             trend_span=int(cfg.get("trend_span", autoloop.TREND_SPAN)))
            if not (scratch / "meta.npz").exists():
                cand = metalabel.gather_candidates(dataset, sig, symbols, enter=enter)
                verdicts, _doc = metalabel.build_verdicts(cand)
                metalabel.write_meta(verdicts, str(scratch / "meta.npz"))
            brain = {"enter": enter, "exit_": exit_, "min_hold": hold,
                     "meta_signals": str(scratch / "meta.npz"), **risk}
            if float(risk.get("money_model") or 0) > 0:
                if not (scratch / "moneymodel.npz").exists():
                    overlay = moneymodel.build_sizing(
                        sig, data, enter=enter, exit_=exit_, min_hold=hold,
                        stop_loss=float(risk.get("stop_loss") or 0.0),
                        trail_stop=float(risk.get("trail_stop") or 0.0), research=rbars)
                    moneymodel.write_sizing(overlay, str(scratch / "moneymodel.npz"))
                brain["size_signals"] = str(scratch / "moneymodel.npz")

            py = launch.per_year(rbars, rstamps, [args.exam], sig, brain_kwargs=brain)
            r = (py.get(args.exam) or py.get(str(args.exam))) or {}
            per_seed[seed] = {"return": r.get("return_pct"),
                              "max_drawdown": r.get("max_drawdown"),
                              "trades": r.get("trades"),
                              "minutes": round((time.time() - t0) / 60, 1)}
            print(f"  {name} seed {seed}  {args.exam}: {r.get('return_pct') or 0:+.2%}  "
                  f"maxDD {r.get('max_drawdown') or 0:.1%}  trades {r.get('trades')}",
                  flush=True)

        got = [v["return"] for v in per_seed.values() if v["return"] is not None]
        dd = [v["max_drawdown"] for v in per_seed.values() if v["max_drawdown"] is not None]
        results[name] = {
            "train_kwargs": extra,
            "per_seed": per_seed,
            "median_return": statistics.median(got) if got else None,
            "median_drawdown": statistics.median(dd) if dd else None,
        }

    base = results[control]["median_return"]
    print(f"\n=== {args.id} WALK-FORWARD VERDICT: {args.exam}, unseen by every net ===")
    for name, r in results.items():
        if r["median_return"] is None:
            print(f"  {name:22s} no result")
            continue
        delta = ("  (control)" if name == control
                 else f"  delta {r['median_return'] - base:+.4f}" if base is not None else "")
        print(f"  {name:22s} {r['median_return']:+.2%}  "
              f"DD {r['median_drawdown']:.1%}{delta}")
    print("\n2026 was not read. A sealed reading is earned by winning exams, not by this one.")

    out = ROOT / "rnd" / f"walkforward_{args.id}_{args.exam}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "id": args.id, "at": datetime.now(timezone.utc).isoformat(),
        "train_until": args.train_until, "exam_year": args.exam,
        "seeds": seeds, "control": control, "arms": results,
        "band_and_risk": "champion verbatim; only the training recipe differs between arms",
        "note": args.note,
    }, indent=1, default=str), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
