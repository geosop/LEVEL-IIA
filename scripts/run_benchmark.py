#!/usr/bin/env python3
"""Run a single benchmark scenario and print its summary.

Usage: python scripts/run_benchmark.py --config configs/anchor.yaml --M 500
This is a thin wrapper around run_all.py for one config (no run directory is
written; use run_all.py to produce the frozen manuscript outputs).
"""

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cri_leveliia import benchmarks as B  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--M", type=int, default=500)
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    df = B.run_scenario(cfg, M=args.M, base_seed=cfg["base_seed"])
    s = B.summarise(df, cfg, cfg["name"], cfg["generator"])
    width = max(len(k) for k in s)
    for k, v in s.items():
        print(f"{k:>{width}} : {v}")


if __name__ == "__main__":
    main()
