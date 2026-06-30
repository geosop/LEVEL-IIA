#!/usr/bin/env python3
"""Rebuild manuscript-facing LaTeX tables from a frozen run.

This script keeps the complete frozen run under outputs/<run_hash>/, but the
manuscript-facing SI uses the split operating-characteristics tables:
  - operating_characteristics_design.tex
  - operating_characteristics_outcomes.tex

The legacy wide operating_characteristics.tex is not copied into manuscript/tables.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from make_split_oc_tables import write_split_tables


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-hash", required=True)
    ap.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = ap.parse_args()

    run_dir = Path(args.outdir) / args.run_hash
    run_tables = run_dir / "tables"
    run_summary = run_dir / "summary"

    if not run_dir.exists():
        raise FileNotFoundError(run_dir)

    # Generate the split SI tables from the frozen CSV.
    csv_path = run_summary / "operating_characteristics.csv"
    if csv_path.exists():
        write_split_tables(csv_path=csv_path, outdir=run_tables, run_hash=args.run_hash)
    else:
        raise FileNotFoundError(csv_path)

    man = ROOT / "manuscript" / "tables"
    man.mkdir(parents=True, exist_ok=True)

    # Do not copy the legacy 22-column table into the manuscript-facing table directory.
    skip_for_manuscript = {"operating_characteristics.tex"}

    for tex in run_tables.glob("*.tex"):
        if tex.name in skip_for_manuscript:
            print(f"[make_tables] skipped manuscript-facing copy of legacy wide table: {tex.name}")
            continue
        shutil.copy(tex, man / tex.name)
        print(f"[make_tables] {tex.name} -> manuscript/tables/")

    print("[make_tables] done.")


if __name__ == "__main__":
    main()
