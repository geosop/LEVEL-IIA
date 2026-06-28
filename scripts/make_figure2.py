#!/usr/bin/env python3
"""Regenerate Figure 2 from a frozen benchmark run.

Usage: python scripts/make_figure2.py --run-hash <RUN_HASH>

The panels (forward-only null, injected residual, leakage) are rebuilt from the
representative replicate recorded in representative_index.json, using the
deterministic per-replicate seed, so the figure is an exact function of the run.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cri_leveliia import figures as F  # noqa: E402

PANELS = [
    ("anchor", "(a) forward-only null"),
    ("injected_residual", "(b) injected endpoint residual"),
    ("leakage", "(c) leakage artefact (audit fires)"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-hash", required=True)
    ap.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = ap.parse_args()

    run_dir = Path(args.outdir) / args.run_hash
    with open(run_dir / "summary" / "representative_index.json") as fh:
        rep = json.load(fh)
    summ = pd.read_csv(run_dir / "summary" / "operating_characteristics.csv")
    summaries_by_scenario = {row["scenario"]: row.to_dict() for _, row in summ.iterrows()}
    # map scenario file name -> scenario summary name
    name_map = {"anchor": "clean_null", "injected_residual": "injected_residual",
                "leakage": "leakage"}

    panels = []
    for fname, label in PANELS:
        cfg = yaml.safe_load(open(ROOT / "configs" / f"{fname}.yaml"))
        seed = rep[fname]["base_seed"]
        replicate = rep[fname]["replicate"]
        panels.append((name_map[fname], cfg, seed, replicate, label))

    out_pdf = run_dir / "figures" / "figure2_validation.pdf"
    F.make_figure(panels, summaries_by_scenario, out_pdf, args.run_hash)
    # also copy into the manuscript figures folder
    man = ROOT / "manuscript" / "figures"
    man.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(out_pdf, man / "CRI_synthetic_validation.pdf")
    shutil.copy(str(out_pdf).replace(".pdf", ".png"),
                man / "CRI_synthetic_validation.png")
    print(f"[make_figure2] wrote {out_pdf} and manuscript/figures/CRI_synthetic_validation.pdf")


if __name__ == "__main__":
    main()
