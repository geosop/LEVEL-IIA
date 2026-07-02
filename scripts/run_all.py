#!/usr/bin/env python3
"""Run the full Level II-A benchmark suite and write a frozen output directory.

Usage
-----
python scripts/run_all.py --smoke
python scripts/run_all.py --all
python scripts/run_all.py --config configs/anchor.yaml

Outputs are written to outputs/<run_hash>/ with raw per-replicate CSVs,
scenario summary JSON/CSV files, split operating-characteristics LaTeX tables,
the collider sweep, the representative-draw index, figures, and run metadata.
Re-running writes to the deterministic run directory unless --overwrite is
given.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cri_leveliia import benchmarks as B  # noqa: E402
from cri_leveliia import metadata as MD  # noqa: E402
from cri_leveliia import tables as T  # noqa: E402
from cri_leveliia.figures import representative_index  # noqa: E402
from make_split_oc_tables import write_split_tables  # noqa: E402


SCENARIOS = [
    "anchor",
    "injected_residual",
    "leakage",
    "selection",
    "collider_selection",
    "adversarial_null",
    "opposite_direction",
]


def load_cfg(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="fast low-M run")
    ap.add_argument("--all", action="store_true", help="full manuscript run")
    ap.add_argument("--config", default=None, help="run a single config file")
    ap.add_argument("--M", type=int, default=None, help="override Monte Carlo M")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument(
        "--resume",
        action="store_true",
        help="skip scenarios already saved in the run directory",
    )
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
            with ssum_path.open("r", encoding="utf-8") as fh:
                s = json.load(fh)
            with srep_path.open("r", encoding="utf-8") as fh:
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
        rep_index[n] = {
            "replicate": rep,
            "modal_decision": modal,
            "base_seed": cfg["base_seed"],
        }

        with ssum_path.open("w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=2)
        with srep_path.open("w", encoding="utf-8") as fh:
            json.dump(rep_index[n], fh, indent=2)

        print(
            f"          support={s['support_rate']:.3f} null={s['null_rate']:.3f} "
            f"selLim={s['selection_limited_rate']:.3f} "
            f"diagF={s['diagnostic_failure_rate']:.3f} "
            f"oppDir={s['opposite_direction_rate']:.3f}"
        )

    all_done = (
        all((run_dir / "raw" / f"{n}.csv").exists() for n in SCENARIOS)
        and set(names) == set(SCENARIOS)
    )

    if all_done and "collider_selection" in cfgs and not args.no_sweep:
        ccfg = cfgs["collider_selection"]
        gammas = [-0.5, -0.9, -1.4, -2.0, -2.6, -3.2]
        sweep = B.collider_sweep(
            ccfg,
            gammas,
            M=min(max(M // 3, 50), 200),
            base_seed=ccfg["base_seed"],
        )
        sweep_csv = run_dir / "summary" / "collider_sweep.csv"
        sweep.to_csv(sweep_csv, index=False)
        T.collider_subtable_latex(
            None,
            sweep,
            run_dir / "tables" / "collider_sweep.tex",
            caption=(
                "Collider-selection scope sweep (simulated data). The "
                "manufactured retained-sample slope grows with collider "
                "strength while the marginal retention imbalance stays small; "
                "the endpoint-by-delay interaction diagnostic fires throughout."
            ),
            label="tab:si-collider-sweep",
        )

    oc_csv = run_dir / "summary" / "operating_characteristics.csv"
    T.operating_characteristics_csv(summaries, oc_csv)
    write_split_tables(
        csv_path=oc_csv,
        outdir=run_dir / "tables",
        run_hash=run_hash,
    )

    with (run_dir / "summary" / "representative_index.json").open(
        "w",
        encoding="utf-8",
    ) as fh:
        json.dump(rep_index, fh, indent=2)

    if all_done:
        meta = MD.make_metadata(
            config_bundle,
            f"{seed_family}:M={M}",
            run_hash,
            script_path=str(Path(__file__).relative_to(ROOT)),
        )
        meta["M"] = M
        with (run_dir / "metadata" / "run_metadata.json").open(
            "w",
            encoding="utf-8",
        ) as fh:
            json.dump(meta, fh, indent=2)
        with (Path(args.outdir) / "LATEST_RUN.txt").open("w", encoding="utf-8") as fh:
            fh.write(run_hash + "\n")
        print(f"[run_all] ALL DONE. run_hash={run_hash}\n[run_all] outputs in {run_dir}")
    else:
        remaining = [
            n for n in SCENARIOS if not (run_dir / "raw" / f"{n}.csv").exists()
        ]
        print(f"[run_all] partial. run_hash={run_hash} remaining={remaining}")

    return run_hash


if __name__ == "__main__":
    main()
