#!/usr/bin/env python3
"""Rebuild LaTeX tables from a frozen run and copy them into manuscript/tables.

Usage: python scripts/make_tables.py --run-hash <RUN_HASH>
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-hash", required=True)
    ap.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = ap.parse_args()
    run_dir = Path(args.outdir) / args.run_hash
    man = ROOT / "manuscript" / "tables"
    man.mkdir(parents=True, exist_ok=True)
    for tex in (run_dir / "tables").glob("*.tex"):
        shutil.copy(tex, man / tex.name)
        print(f"[make_tables] {tex.name} -> manuscript/tables/")
    print("[make_tables] done.")


if __name__ == "__main__":
    main()
