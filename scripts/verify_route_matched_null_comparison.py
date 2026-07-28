#!/usr/bin/env python3
"""Verify a completed route-matched null comparison."""

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
from make_route_matched_null_comparison import (  # noqa: E402
    CELL_ORDER,
    OUTCOME_MAP,
    _build_cell_configs,
    _clean_dataset_family_digest,
    _contrast_rows,
    _load_yaml,
    _resolved_manifest,
    _source_paths,
    _validate_raw,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _locate_metadata(run_dir: Path, experiment_id: str | None) -> Path:
    if experiment_id:
        return run_dir / "auxiliary" / experiment_id / "metadata.json"
    return run_dir / "metadata" / "route_matched_null_comparison.json"


def verify(run_dir: Path, run_hash: str, experiment_id: str | None) -> None:
    metadata_path = _locate_metadata(run_dir, experiment_id)
    if not metadata_path.exists():
        raise FileNotFoundError(f"route-matched metadata is missing: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    actual_id = str(metadata["experiment_id"])
    if experiment_id is not None and actual_id != experiment_id:
        raise ValueError("requested experiment ID does not match metadata")
    if metadata["parent_run_hash"] != run_hash:
        raise ValueError("parent run hash mismatch")

    parent_path = run_dir / "metadata" / "run_metadata.json"
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    if parent["run_hash"] != run_hash:
        raise ValueError("parent metadata run hash mismatch")
    if parent["source_fingerprint"] != MD.source_fingerprint():
        raise ValueError("current core-source fingerprint differs from parent")
    if parent["dependency_lock_sha256"] != MD.dependency_lock_sha256():
        raise ValueError("current dependency lock differs from parent")

    manifest_path = ROOT / metadata["manifest_path"]
    resolved = _resolved_manifest(metadata["resolved_manifest"], None)
    configs = _build_cell_configs(resolved)
    expected_id = MD.compute_experiment_id(
        "route_match",
        {
            "parent_run_hash": run_hash,
            "kind": resolved["kind"],
            "resolved_manifest": resolved,
            "resolved_cell_configs": configs,
            "seed_family": "route_match_v1",
            "M": int(resolved["M"]),
        },
        _source_paths(manifest_path, resolved),
    )
    if actual_id != expected_id:
        raise ValueError(f"experiment ID {actual_id} does not recompute as {expected_id}")

    experiment_dir = run_dir / "auxiliary" / actual_id
    m = int(resolved["M"])
    raw = {}
    for cell_id in CELL_ORDER:
        path = experiment_dir / "raw" / f"{cell_id}.csv"
        raw[cell_id] = _validate_raw(path, m, cell_id)
        if metadata["raw_checksums"].get(path.name) != _sha256(path):
            raise ValueError(f"raw checksum mismatch: {path}")

    expected_family = _clean_dataset_family_digest(configs, m)
    if metadata["clean_dataset_family_sha256"] != expected_family:
        raise ValueError("clean dataset-family digest mismatch")

    canonical_summary = run_dir / metadata["summary"]["path"]
    auxiliary_summary = experiment_dir / "summary" / "route_matched_null_comparison.csv"
    canonical_contrasts = run_dir / metadata["contrasts"]["path"]
    auxiliary_contrasts = experiment_dir / "summary" / "route_matched_null_contrasts.csv"
    canonical_table = run_dir / metadata["table"]["path"]
    auxiliary_table = experiment_dir / "tables" / "route_matched_null_comparison.tex"

    for canonical, auxiliary, expected in (
        (canonical_summary, auxiliary_summary, metadata["summary"]["sha256"]),
        (canonical_contrasts, auxiliary_contrasts, metadata["contrasts"]["sha256"]),
        (canonical_table, auxiliary_table, metadata["table"]["sha256"]),
    ):
        if _sha256(canonical) != _sha256(auxiliary):
            raise ValueError(f"canonical and auxiliary files differ: {canonical}")
        if _sha256(canonical) != expected:
            raise ValueError(f"metadata checksum mismatch: {canonical}")

    summary = pd.read_csv(canonical_summary)
    if summary["cell_id"].tolist() != CELL_ORDER:
        raise ValueError("summary cell order differs from declaration")
    for row in summary.itertuples(index=False):
        total = sum(int(getattr(row, f"{label}_n")) for label in OUTCOME_MAP.values())
        if total != m:
            raise ValueError(f"{row.cell_id}: outcome counts sum to {total}, expected {m}")
        if not np.isclose(row.adequate_rate, row.adequate_n / m, atol=1e-12):
            raise ValueError(f"{row.cell_id}: adequacy count/rate mismatch")

    observed_contrasts = pd.read_csv(canonical_contrasts)
    expected_contrasts = pd.DataFrame(_contrast_rows(raw, resolved))
    if observed_contrasts["contrast_id"].tolist() != expected_contrasts["contrast_id"].tolist():
        raise ValueError("contrast set mismatch")
    numeric = ["estimate", "ci95_low", "ci95_high", "p_value"]
    if not np.allclose(
        observed_contrasts[numeric].to_numpy(float),
        expected_contrasts[numeric].to_numpy(float),
        atol=5e-13,
        equal_nan=True,
    ):
        raise ValueError("contrast values do not reproduce")

    print(
        f"[verify-route-match] PASS run={run_hash} "
        f"experiment_id={actual_id} cells=3 M={m}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-hash", required=True)
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = parser.parse_args()
    verify(Path(args.outdir).resolve() / args.run_hash, args.run_hash, args.experiment_id)


if __name__ == "__main__":
    main()
