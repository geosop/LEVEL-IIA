#!/usr/bin/env python3
"""Derive false-adequacy rates from operating-characteristics outputs.

A false-adequacy classification occurs when a material endpoint-level departure
is present in the generator but the final mutually exclusive decision is
forward-only adequate. The quantity is derived from null_n/M in the frozen
operating_characteristics.csv file; it is never hand-entered.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Optional


DEFAULT_FROZEN_RUN_HASH = "9d2658d6d147de10"
Z_95 = 1.959963984540054


TARGET_SCENARIOS = {
    "injected_residual": {
        "material_departure": "negative endpoint-level residual",
        "direction": "negative",
    },
    "opposite_direction": {
        "material_departure": "positive endpoint-level residual",
        "direction": "positive",
    },
}


OUTPUT_COLUMNS = [
    "scenario",
    "generator",
    "material_departure",
    "direction",
    "beta_inj",
    "false_adequacy_n",
    "M",
    "false_adequacy_rate",
    "wilson95_low",
    "wilson95_high",
    "run_hash",
    "source_csv",
]


def _fmt_rate(value: float) -> str:
    return f"{value:.6f}"


def _wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    if n <= 0:
        raise ValueError(f"M must be positive, got {n}")

    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    half = z * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))

    low = max(0.0, (centre - half) / denom)
    high = min(1.0, (centre + half) / denom)
    return low, high


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def derive_false_adequacy_rows(csv_path: Path) -> list[dict[str, str]]:
    rows = _read_rows(csv_path)
    by_scenario = {row["scenario"]: row for row in rows}
    derived: list[dict[str, str]] = []

    for scenario, meta in TARGET_SCENARIOS.items():
        if scenario not in by_scenario:
            continue

        source = by_scenario[scenario]
        n = int(float(source["M"]))
        k = int(float(source["null_n"]))
        low, high = _wilson_interval(k, n)
        rate = k / n
        run_hash = source.get("run_hash", "") or DEFAULT_FROZEN_RUN_HASH
        source_label = (
            f"outputs/{run_hash}/summary/operating_characteristics.csv"
            if run_hash
            else str(csv_path).replace("\\", "/")
        )

        derived.append(
            {
                "scenario": scenario,
                "generator": source.get("generator", ""),
                "material_departure": meta["material_departure"],
                "direction": meta["direction"],
                "beta_inj": source.get("beta_inj", ""),
                "false_adequacy_n": str(k),
                "M": str(n),
                "false_adequacy_rate": _fmt_rate(rate),
                "wilson95_low": _fmt_rate(low),
                "wilson95_high": _fmt_rate(high),
                "run_hash": run_hash,
                "source_csv": source_label,
            }
        )

    return derived


def write_false_adequacy_rates(
    csv_path: Path,
    outdir: Path,
    run_hash: Optional[str] = None,
) -> Path:
    csv_path = Path(csv_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = derive_false_adequacy_rows(csv_path)

    if run_hash:
        for row in rows:
            row["run_hash"] = str(run_hash)
            row["source_csv"] = (
                f"outputs/{run_hash}/summary/operating_characteristics.csv"
            )

    out_path = outdir / "false_adequacy_rates.csv"
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-hash", required=True)
    ap.add_argument("--outdir", default="outputs")
    args = ap.parse_args()

    run_dir = Path(args.outdir) / args.run_hash
    csv_path = run_dir / "summary" / "operating_characteristics.csv"

    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    out_path = write_false_adequacy_rates(
        csv_path=csv_path,
        outdir=run_dir / "summary",
        run_hash=args.run_hash,
    )

    print(f"[false-adequacy] wrote {out_path}")


if __name__ == "__main__":
    main()
