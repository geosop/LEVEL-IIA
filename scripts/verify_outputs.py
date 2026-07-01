#!/usr/bin/env python3
"""Verify benchmark output invariants and operating-characteristic thresholds.

Usage:
    python scripts/verify_outputs.py --run-hash 9d2658d6d147de10
    python scripts/verify_outputs.py --smoke
    python scripts/verify_outputs.py --run-hash 9d2658d6d147de10 --strict-manuscript

The verifier has two layers.

1. Exact internal invariants:
   - required scenarios are present;
   - mutually exclusive outcome counts sum to M;
   - outcome rates equal outcome counts divided by M;
   - outcome rates sum to one;
   - diagnostic rates are in [0, 1];
   - row-level run_hash values match the output directory.

2. Operating-characteristic qualification checks:
   - false-support control under null scenarios;
   - recovery under injected residual;
   - leakage, selection and collider failures are blocked;
   - opposite-direction injections are not counted as directional support.

The script exits non-zero on failure so it can gate local release checks or CI.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
import sys

ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_FOR_IMPORT / "src"))
from cri_leveliia.formatting import rate_display  # noqa: E402

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_SCENARIOS = [
    "clean_null",
    "injected_residual",
    "leakage",
    "selection_standard",
    "collider_selection",
    "adversarial_null",
    "opposite_direction",
]


OUTCOME_COUNT_RATE_PAIRS = [
    ("support_n", "support_rate"),
    ("null_n", "null_rate"),
    ("selection_limited_n", "selection_limited_rate"),
    ("diagnostic_failure_n", "diagnostic_failure_rate"),
    ("opposite_direction_n", "opposite_direction_rate"),
    ("inconclusive_n", "inconclusive_rate"),
]


DIAGNOSTIC_RATE_COLS = [
    "rand_pass_rate",
    "materiality_pass_rate",
    "leak_fire_rate",
    "delivery_fire_rate",
    "retention_fire_rate",
    "gate_pass_rate",
    "collider_inter_fire_rate",
    "collider_fire_rate",
]


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


MANUSCRIPT_LOCKED_COUNTS = {
    "clean_null": {
        "M": 1200,
        "support_n": 0,
        "selection_limited_n": 9,
        "diagnostic_failure_n": 1,
        "null_n": 1190,
        "opposite_direction_n": 0,
        "inconclusive_n": 0,
    },
    "injected_residual": {
        "M": 1200,
        "support_n": 1113,
        "selection_limited_n": 10,
        "diagnostic_failure_n": 2,
        "null_n": 75,
        "opposite_direction_n": 0,
        "inconclusive_n": 0,
    },
    "leakage": {
        "M": 1200,
        "support_n": 0,
        "selection_limited_n": 0,
        "diagnostic_failure_n": 1200,
        "null_n": 0,
        "opposite_direction_n": 0,
        "inconclusive_n": 0,
    },
    "selection_standard": {
        "M": 1200,
        "support_n": 0,
        "selection_limited_n": 1197,
        "diagnostic_failure_n": 3,
        "null_n": 0,
        "opposite_direction_n": 0,
        "inconclusive_n": 0,
    },
    "collider_selection": {
        "M": 1200,
        "support_n": 0,
        "selection_limited_n": 1197,
        "diagnostic_failure_n": 3,
        "null_n": 0,
        "opposite_direction_n": 0,
        "inconclusive_n": 0,
    },
    "adversarial_null": {
        "M": 1200,
        "support_n": 0,
        "selection_limited_n": 6,
        "diagnostic_failure_n": 0,
        "null_n": 1194,
        "opposite_direction_n": 0,
        "inconclusive_n": 0,
    },
    "opposite_direction": {
        "M": 1200,
        "support_n": 0,
        "selection_limited_n": 11,
        "diagnostic_failure_n": 3,
        "null_n": 60,
        "opposite_direction_n": 1126,
        "inconclusive_n": 0,
    },
}


def _latest(outdir: str | Path) -> str | None:
    p = Path(outdir) / "LATEST_RUN.txt"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


def _cmp(v: float, op: str, t: float) -> bool:
    if op == "<=":
        return v <= t
    if op == ">=":
        return v >= t
    raise ValueError(f"unsupported operator: {op}")


def _is_int_like(value: object) -> bool:
    try:
        return float(value).is_integer()
    except (TypeError, ValueError):
        return False


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)
    print(f"[FAIL] {msg}")


def _ok(msg: str) -> None:
    print(f"[ok  ] {msg}")


def _check_required_columns(df: pd.DataFrame, errors: list[str]) -> None:
    required = {"scenario", "M"}
    required.update(col for pair in OUTCOME_COUNT_RATE_PAIRS for col in pair)
    required.update(DIAGNOSTIC_RATE_COLS)

    missing = sorted(required.difference(df.columns))
    if missing:
        _fail(errors, f"missing required columns: {', '.join(missing)}")
    else:
        _ok("all required invariant-check columns are present")


def _check_required_scenarios(df: pd.DataFrame, smoke: bool, errors: list[str]) -> None:
    present = set(df["scenario"].astype(str))
    missing = [s for s in REQUIRED_SCENARIOS if s not in present]

    if missing and not smoke:
        _fail(errors, f"missing required scenarios: {', '.join(missing)}")
    elif missing and smoke:
        print(f"[warn] smoke run missing scenarios: {', '.join(missing)}")
    else:
        _ok("all required benchmark scenarios are present")


def _check_run_hash_column(df: pd.DataFrame, run_hash: str, errors: list[str]) -> None:
    if "run_hash" not in df.columns:
        print("[warn] run_hash column absent; cannot check row-level run hash")
        return

    bad = df[df["run_hash"].astype(str) != str(run_hash)]
    if bad.empty:
        _ok("all row-level run_hash values match the verified run directory")
    else:
        scenarios = ", ".join(bad["scenario"].astype(str).tolist())
        _fail(errors, f"run_hash mismatch in scenarios: {scenarios}")


def _check_internal_invariants(df: pd.DataFrame, errors: list[str]) -> None:
    tol = 1.0e-10

    for _, row in df.iterrows():
        scen = str(row["scenario"])

        if not _is_int_like(row["M"]):
            _fail(errors, f"{scen}: M is not an integer-like value: {row['M']}")
            continue

        m = int(row["M"])
        if m <= 0:
            _fail(errors, f"{scen}: M must be positive, got {m}")
            continue

        outcome_count_sum = 0
        outcome_rate_sum = 0.0

        for count_col, rate_col in OUTCOME_COUNT_RATE_PAIRS:
            if not _is_int_like(row[count_col]):
                _fail(errors, f"{scen}: {count_col} is not integer-like: {row[count_col]}")
                continue

            count = int(row[count_col])
            rate = float(row[rate_col])
            outcome_count_sum += count
            outcome_rate_sum += rate

            if count < 0:
                _fail(errors, f"{scen}: {count_col} is negative: {count}")
            if count > m:
                _fail(errors, f"{scen}: {count_col}={count} exceeds M={m}")
            if not (0.0 <= rate <= 1.0):
                _fail(errors, f"{scen}: {rate_col}={rate:.12g} outside [0, 1]")

            expected_rate = count / m
            if abs(rate - expected_rate) > tol:
                _fail(
                    errors,
                    (
                        f"{scen}: {rate_col}={rate:.12g} does not equal "
                        f"{count_col}/M={expected_rate:.12g}"
                    ),
                )

        if outcome_count_sum != m:
            _fail(
                errors,
                (
                    f"{scen}: mutually exclusive outcome counts sum to "
                    f"{outcome_count_sum}, expected M={m}"
                ),
            )

        if abs(outcome_rate_sum - 1.0) > tol:
            _fail(
                errors,
                (
                    f"{scen}: mutually exclusive outcome rates sum to "
                    f"{outcome_rate_sum:.12g}, expected 1.0"
                ),
            )

        for rate_col in DIAGNOSTIC_RATE_COLS:
            rate = float(row[rate_col])
            if not math.isfinite(rate):
                _fail(errors, f"{scen}: {rate_col} is not finite: {rate}")
            elif not (0.0 <= rate <= 1.0):
                _fail(errors, f"{scen}: {rate_col}={rate:.12g} outside [0, 1]")

    if not errors:
        _ok("all internal count/rate and mutual-exclusivity invariants pass")


def _check_operating_thresholds(df_indexed: pd.DataFrame, smoke: bool, errors: list[str]) -> None:
    tol = 0.07 if smoke else 0.0

    for scen, col, op, thr, desc in CHECKS:
        if scen not in df_indexed.index:
            if smoke:
                print(f"[warn] threshold check skipped for absent smoke scenario: {scen}")
                continue
            _fail(errors, f"threshold check scenario absent: {scen}")
            continue

        if col not in df_indexed.columns:
            _fail(errors, f"threshold check column absent: {col}")
            continue

        v = float(df_indexed.loc[scen, col])
        t = thr + tol if op == "<=" else thr - tol
        passed = _cmp(v, op, t)

        if passed:
            print(f"[ok  ] {desc:38s} {scen}.{col}={rate_display(v)} {op} {rate_display(t)}")
        else:
            _fail(errors, f"{desc}: {scen}.{col}={rate_display(v)} not {op} {rate_display(t)}")


def _check_locked_manuscript_counts(df_indexed: pd.DataFrame, run_hash: str, errors: list[str]) -> None:
    expected_hash = "9d2658d6d147de10"
    if run_hash != expected_hash:
        _fail(
            errors,
            (
                "--strict-manuscript was requested, but run hash is "
                f"{run_hash}; expected {expected_hash}"
            ),
        )
        return

    for scen, expected in MANUSCRIPT_LOCKED_COUNTS.items():
        if scen not in df_indexed.index:
            _fail(errors, f"strict manuscript check missing scenario: {scen}")
            continue

        row = df_indexed.loc[scen]
        for col, expected_value in expected.items():
            observed = int(row[col])
            if observed != expected_value:
                _fail(
                    errors,
                    (
                        f"strict manuscript mismatch: {scen}.{col}="
                        f"{observed}, expected {expected_value}"
                    ),
                )

    if not errors:
        _ok("strict manuscript counts match run 9d2658d6d147de10")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run-hash", default=None)
    ap.add_argument("--outdir", default=str(ROOT / "outputs"))
    ap.add_argument(
        "--strict-manuscript",
        action="store_true",
        help="also require exact outcome counts for manuscript run 9d2658d6d147de10",
    )
    args = ap.parse_args()

    run_hash = args.run_hash or _latest(args.outdir)
    if run_hash is None:
        print("[verify] no run hash given and no LATEST_RUN.txt found")
        sys.exit(2)

    csv = Path(args.outdir) / run_hash / "summary" / "operating_characteristics.csv"
    if not csv.exists():
        print(f"[verify] missing {csv}")
        sys.exit(2)

    df = pd.read_csv(csv)
    errors: list[str] = []

    print(f"[verify] checking {csv}")

    _check_required_columns(df, errors)
    if errors:
        print(f"[verify] run {run_hash}: FAIL")
        sys.exit(1)

    _check_required_scenarios(df, args.smoke, errors)
    _check_run_hash_column(df, run_hash, errors)
    _check_internal_invariants(df, errors)

    df_indexed = df.set_index("scenario", drop=False)
    _check_operating_thresholds(df_indexed, args.smoke, errors)

    if args.strict_manuscript:
        _check_locked_manuscript_counts(df_indexed, run_hash, errors)

    print(f"[verify] run {run_hash}: {'PASS' if not errors else 'FAIL'}")
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
