#!/usr/bin/env python3
"""Verify a completed v1.2 adequacy certification family."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cri_leveliia import metadata as MD  # noqa: E402
from make_adequacy_operating_characteristic import (  # noqa: E402
    OUTCOME_COLUMNS,
    _source_paths,
    _simultaneous_cp_upper,
    _validate_raw,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _locate_metadata(run_dir: Path, adequacy_id: str | None) -> Path:
    if adequacy_id:
        return run_dir / "auxiliary" / adequacy_id / "metadata.json"
    pointer = run_dir / "metadata" / "adequacy_certification.json"
    if not pointer.exists():
        raise FileNotFoundError(f"adequacy metadata is missing: {pointer}")
    return pointer


def verify(run_dir: Path, run_hash: str, adequacy_id: str | None = None) -> None:
    metadata_path = _locate_metadata(run_dir, adequacy_id)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    actual_id = str(metadata["adequacy_id"])
    if adequacy_id is not None and actual_id != adequacy_id:
        raise ValueError("requested adequacy_id does not match metadata")
    if metadata["parent_run_hash"] != run_hash:
        raise ValueError("adequacy metadata parent run hash mismatch")

    resolved = metadata["resolved_manifest"]
    m = int(resolved["M"])
    family_size = int(resolved["family_size"])
    alpha_family = float(resolved["alpha_family"])
    manifest_path = ROOT / metadata["manifest_path"]
    expected_id = MD.compute_experiment_id(
        "adequacy",
        {
            "parent_run_hash": run_hash,
            "kind": "adequacy_certification",
            "resolved_manifest": resolved,
            "seed_family": "adequacy_v1.2",
            "M": m,
        },
        _source_paths(manifest_path, resolved),
    )
    if actual_id != expected_id:
        raise ValueError(
            f"adequacy_id={actual_id} does not recompute as {expected_id}"
        )
    adequacy_dir = run_dir / "auxiliary" / actual_id
    csv_path = (
        adequacy_dir
        / "summary"
        / "adequacy_operating_characteristic.csv"
    )
    canonical_csv = run_dir / "summary" / "adequacy_operating_characteristic.csv"
    if _sha256(csv_path) != _sha256(canonical_csv):
        raise ValueError("canonical and auxiliary adequacy summaries differ")
    if _sha256(canonical_csv) != metadata["summary_sha256"]:
        raise ValueError("adequacy summary checksum mismatch")

    df = pd.read_csv(csv_path)
    if len(df) != family_size:
        raise ValueError(
            f"adequacy CSV has {len(df)} rows, expected {family_size}"
        )
    expected_cells = {
        (route, direction, float(delta))
        for route in resolved["routes"]
        for direction in resolved["directions"]
        for delta in resolved["deltas"]
    }
    observed_cells = {
        (str(row.route), str(row.direction), float(row.delta))
        for row in df.itertuples(index=False)
    }
    if observed_cells != expected_cells:
        raise ValueError("adequacy cell set differs from the resolved manifest")

    for row in df.itertuples(index=False):
        counts = sum(int(getattr(row, column)) for column in OUTCOME_COLUMNS)
        if counts != m:
            raise ValueError(
                f"{row.route}/{row.direction}/{row.delta}: "
                f"outcomes sum to {counts}, expected {m}"
            )
        expected_rate = int(row.false_adequacy_n) / m
        if not np.isclose(row.false_adequacy_rate, expected_rate, atol=1e-12):
            raise ValueError("false-adequacy count/rate mismatch")
        expected_upper = _simultaneous_cp_upper(
            int(row.false_adequacy_n),
            m,
            alpha_family,
            family_size,
        )
        if not np.isclose(
            row.simultaneous_cp_upper,
            expected_upper,
            atol=5e-13,
        ):
            raise ValueError("simultaneous Clopper-Pearson upper bound mismatch")

        raw_path = run_dir / str(row.source_raw_csv)
        _validate_raw(raw_path, m)
        if _sha256(raw_path) != str(row.source_raw_sha256):
            raise ValueError(f"raw checksum mismatch: {raw_path}")
        if metadata["raw_checksums"].get(raw_path.name) != _sha256(raw_path):
            raise ValueError(f"metadata raw checksum mismatch: {raw_path}")

    for route in resolved["routes"]:
        for direction in resolved["directions"]:
            group = df[
                (df["route"] == route)
                & (df["direction"] == direction)
            ].sort_values("delta")
            uppers = group["simultaneous_cp_upper"].to_numpy(float)
            expected_envelope = np.maximum.accumulate(uppers[::-1])[::-1]
            if not np.allclose(
                group["envelope_simultaneous_cp_upper"],
                expected_envelope,
                atol=5e-13,
            ):
                raise ValueError(
                    f"envelope mismatch for {route}/{direction}"
                )
            expected_pass = (
                (group["false_adequacy_rate"] <= group["p_fa_max"])
                & (expected_envelope <= group["p_fa_max"])
            )
            if not np.array_equal(
                group["envelope_pass"].astype(bool).to_numpy(),
                expected_pass.to_numpy(),
            ):
                raise ValueError(
                    f"certification verdict mismatch for {route}/{direction}"
                )

    for route, item in metadata["tables"].items():
        path = run_dir / item["path"]
        if _sha256(path) != item["sha256"]:
            raise ValueError(f"table checksum mismatch for route {route}")

    print(
        f"[verify-adequacy] PASS run={run_hash} "
        f"adequacy_id={actual_id} cells={family_size} M={m}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-hash", required=True)
    parser.add_argument("--adequacy-id", default=None)
    parser.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = parser.parse_args()
    run_dir = Path(args.outdir).resolve() / args.run_hash
    verify(run_dir, args.run_hash, args.adequacy_id)


if __name__ == "__main__":
    main()
