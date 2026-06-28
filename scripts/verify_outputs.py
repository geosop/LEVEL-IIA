#!/usr/bin/env python3
"""Verify that a benchmark run satisfies the pipeline qualification invariants.

Usage:
  python scripts/verify_outputs.py --smoke
  python scripts/verify_outputs.py --run-hash <RUN_HASH>

Checks the four required behaviours plus the collider scope test against
tolerances that hold at any reasonable Monte Carlo size. Exits non-zero on
failure so it can gate a CI pipeline.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _latest(outdir):
    p = Path(outdir) / "LATEST_RUN.txt"
    return p.read_text().strip() if p.exists() else None


CHECKS = [
    # (scenario, column, op, threshold, description)
    ("clean_null", "support_rate", "<=", 0.05, "false-support control (anchor)"),
    ("clean_null", "null_rate", ">=", 0.85, "anchor classified null"),
    ("injected_residual", "support_rate", ">=", 0.70, "recovery power"),
    ("leakage", "diagnostic_failure_rate", ">=", 0.90, "leakage audit blocks"),
    ("leakage", "support_rate", "<=", 0.02, "leakage not supported"),
    ("selection_standard", "retention_fire_rate", ">=", 0.90, "selection audit fires"),
    ("selection_standard", "support_rate", "<=", 0.02, "selection not supported"),
    ("collider_selection", "gate_pass_rate", ">=", 0.90, "scalar gate misses collider"),
    ("collider_selection", "collider_fire_rate", ">=", 0.90, "interaction catches collider"),
    ("collider_selection", "support_rate", "<=", 0.02, "collider never supported"),
    ("collider_selection", "selection_limited_rate", ">=", 0.80, "collider -> selection-limited"),
    ("adversarial_null", "support_rate", "<=", 0.05, "adversarial false-support control"),
    ("opposite_direction", "support_rate", "<=", 0.02, "opposite not supported as direction"),
    ("opposite_direction", "opposite_direction_rate", ">=", 0.70, "opposite classified"),
]


def _cmp(v, op, t):
    return v <= t if op == "<=" else v >= t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run-hash", default=None)
    ap.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = ap.parse_args()

    run_hash = args.run_hash or _latest(args.outdir)
    if run_hash is None:
        print("[verify] no run hash given and no LATEST_RUN.txt found")
        sys.exit(2)
    csv = Path(args.outdir) / run_hash / "summary" / "operating_characteristics.csv"
    if not csv.exists():
        print(f"[verify] missing {csv}")
        sys.exit(2)
    df = pd.read_csv(csv).set_index("scenario")

    ok = True
    tol = 0.07 if args.smoke else 0.0  # loosen thresholds for tiny smoke runs
    for scen, col, op, thr, desc in CHECKS:
        if scen not in df.index:
            print(f"[verify] SKIP {scen} (absent)")
            continue
        v = float(df.loc[scen, col])
        t = thr + tol if op == "<=" else thr - tol
        passed = _cmp(v, op, t)
        ok = ok and passed
        flag = "ok " if passed else "FAIL"
        print(f"[{flag}] {desc:38s} {scen}.{col}={v:.3f} {op} {t:.3f}")
    print(f"[verify] run {run_hash}: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
