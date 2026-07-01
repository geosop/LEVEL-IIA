#!/usr/bin/env python3
"""Run the full Level II-A benchmark suite and write a frozen output directory.

Usage
-----
python scripts/run_all.py --smoke
python scripts/run_all.py --all
python scripts/run_all.py --config configs/anchor.yaml

Outputs are written to outputs/<run_hash>/ with raw per-replicate CSVs, scenario
summary CSV/LaTeX, the collider sweep, the representative-draw index, and run
metadata. Re-running writes a NEW run directory unless --overwrite is given.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cri_leveliia import benchmarks as B          # noqa: E402
from cri_leveliia import tables as T              # noqa: E402
from cri_leveliia import metadata as MD           # noqa: E402
from cri_leveliia.figures import representative_index  # noqa: E402

SCENARIOS = [
    "anchor", "injected_residual", "leakage", "selection",
    "collider_selection", "adversarial_null", "opposite_direction",
]


def load_cfg(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="fast low-M run")
    ap.add_argument("--all", action="store_true", help="full manuscript run")
    ap.add_argument("--config", default=None, help="run a single config file")
    ap.add_argument("--M", type=int, default=None, help="override Monte Carlo M")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="skip scenarios already saved in the run directory")
    ap.add_argument("--no-sweep", action="store_true")
    ap.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = ap.parse_args()

    if args.smoke:
        M = args.M or 50
        seed_family = "smoke"
    else:
        M = args.M or 1200
        seed_family = "full"

    if args.config:
        names = [Path(args.config).stem]
    else:
        names = SCENARIOS

    cfgs = {n: load_cfg(ROOT / "configs" / f"{n}.yaml") for n in names}
    config_bundle = {n: cfgs[n] for n in names}
    run_hash = MD.compute_run_hash(config_bundle, f"{seed_family}:M={M}")
    run_dir = Path(args.outdir) / run_hash
    if run_dir.exists() and not args.overwrite:
        print(f"[run_all] run directory exists: {run_dir} (use --overwrite)")
    for sub in ("raw", "summary", "tables", "figures", "metadata"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    summaries = []
    rep_index = {}
    for n in names:
        cfg = cfgs[n]
        raw_path = run_dir / "raw" / f"{n}.csv"
        ssum_path = run_dir / "summary" / f"{n}_summary.json"
        srep_path = run_dir / "summary" / f"{n}_rep.json"
        if args.resume and raw_path.exists() and ssum_path.exists() and srep_path.exists():
            with open(ssum_path) as fh:
                s = json.load(fh)
            with open(srep_path) as fh:
                rep_index[n] = json.load(fh)
            summaries.append(s)
            print(f"[run_all] {n}: resumed from disk (support={s['support_rate']:.3f})")
            continue
        print(f"[run_all] {n}: M={M} ...", flush=True)
        df = B.run_scenario(cfg, M=M, base_seed=cfg["base_seed"])
        df.to_csv(raw_path, index=False)
        s = B.summarise(df, cfg, cfg["name"], cfg["generator"])
        s["run_hash"] = run_hash
        summaries.append(s)
        rep, modal = representative_index(df)
        rep_index[n] = {"replicate": rep, "modal_decision": modal,
                        "base_seed": cfg["base_seed"]}
        with open(ssum_path, "w") as fh:
            json.dump(s, fh, indent=2)
        with open(srep_path, "w") as fh:
            json.dump(rep_index[n], fh, indent=2)
        print(f"          support={s['support_rate']:.3f} null={s['null_rate']:.3f} "
              f"selLim={s['selection_limited_rate']:.3f} diagF={s['diagnostic_failure_rate']:.3f} "
              f"oppDir={s['opposite_direction_rate']:.3f}")

    all_done = all((run_dir / "raw" / f"{n}.csv").exists() for n in SCENARIOS) \
        and set(names) == set(SCENARIOS)

    # collider sweep (Task 4A)
    if all_done and "collider_selection" in cfgs and not args.no_sweep:
        ccfg = cfgs["collider_selection"]
        gammas = [-0.5, -0.9, -1.4, -2.0, -2.6, -3.2]
        sweep = B.collider_sweep(ccfg, gammas, M=min(max(M // 3, 50), 200),
                                 base_seed=ccfg["base_seed"])
        sweep.to_csv(run_dir / "summary" / "collider_sweep.csv", index=False)
        T.collider_subtable_latex(
            None, sweep, run_dir / "tables" / "collider_sweep.tex",
            caption=("Collider-selection scope sweep (simulated data). The "
                     "manufactured retained-sample slope grows with collider "
                     "strength while the marginal retention imbalance stays small; "
                     "the endpoint-by-delay interaction diagnostic fires throughout."),
            label="tab:si-collider-sweep")

    T.operating_characteristics_csv(summaries, run_dir / "summary" / "operating_characteristics.csv")
    # Manuscript-facing operating-characteristics tables are generated from
    # summary/operating_characteristics.csv by scripts/make_tables.py. The
    # legacy single wide LaTeX table is intentionally no longer emitted, because
    # it duplicated the split SI tables and previously allowed display-rounding
    # drift across archived artifacts.

    with open(run_dir / "summary" / "representative_index.json", "w") as fh:
        json.dump(rep_index, fh, indent=2)

    if all_done:
        meta = MD.make_metadata(config_bundle, f"{seed_family}:M={M}", run_hash,
                                script_path=str(Path(__file__).relative_to(ROOT)))
        meta["M"] = M
        with open(run_dir / "metadata" / "run_metadata.json", "w") as fh:
            json.dump(meta, fh, indent=2)
        with open(Path(args.outdir) / "LATEST_RUN.txt", "w") as fh:
            fh.write(run_hash + "\n")
        print(f"[run_all] ALL DONE. run_hash={run_hash}\n[run_all] outputs in {run_dir}")
    else:
        remaining = [n for n in SCENARIOS if not (run_dir / 'raw' / f'{n}.csv').exists()]
        print(f"[run_all] partial. run_hash={run_hash} remaining={remaining}")
    return run_hash


if __name__ == "__main__":
    main()
