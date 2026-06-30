#!/usr/bin/env python3
"""Rebuild manuscript-facing LaTeX tables from a frozen run.

This script generates the split S5/S6 operating-characteristics tables from the
frozen CSV, copies the split manuscript-facing tables into both:
  - manuscript/tables/
  - CRI_Perspective/Tables/

It deliberately does not copy the legacy wide operating_characteristics.tex into
the manuscript-facing table directories.
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


def copy_required(src_dir: Path, dst_dir: Path, names: list[str]) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = src_dir / name
        if not src.exists():
            raise FileNotFoundError(src)
        shutil.copy(src, dst_dir / name)
        print(f"[make_tables] {name} -> {dst_dir.relative_to(ROOT)}/")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-hash", required=True)
    ap.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = ap.parse_args()

    run_dir = Path(args.outdir) / args.run_hash
    run_tables = run_dir / "tables"
    run_summary = run_dir / "summary"

    csv_path = run_summary / "operating_characteristics.csv"
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    # Rebuild split S5/S6 tables from the frozen CSV.
    write_split_tables(csv_path=csv_path, outdir=run_tables, run_hash=args.run_hash)

    split_names = [
        "operating_characteristics_design.tex",
        "operating_characteristics_outcomes.tex",
    ]

    # Manuscript-facing package copies.
    copy_required(run_tables, ROOT / "manuscript" / "tables", split_names)
    copy_required(run_tables, ROOT / "CRI_Perspective" / "Tables", split_names)

    # Preserve non-operating-characteristics generated tables, such as collider_sweep.
    for tex in run_tables.glob("*.tex"):
        if tex.name == "operating_characteristics.tex":
            print("[make_tables] skipped legacy wide table: operating_characteristics.tex")
            continue
        if tex.name in split_names:
            continue
        shutil.copy(tex, ROOT / "manuscript" / "tables" / tex.name)
        shutil.copy(tex, ROOT / "CRI_Perspective" / "Tables" / tex.name)
        print(f"[make_tables] {tex.name} -> manuscript/tables/ and CRI_Perspective/Tables/")

    print("[make_tables] done.")


if __name__ == "__main__":
    main()
