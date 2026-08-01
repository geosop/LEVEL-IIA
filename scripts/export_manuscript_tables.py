#!/usr/bin/env python3
"""Export manuscript-facing LaTeX tables without regenerating evidence files.

This command is the safe manuscript-export path for a frozen run. It applies the
rendering-only repair, then copies canonical table artefacts into
manuscript/tables/. It does not invoke run_all.py, make_tables.py, any Monte
Carlo generator, or any summary-CSV writer.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

from repair_manuscript_table_rendering import repair_run_tables

LEGACY_TABLES = {
    "operating_characteristics.tex",
    "adequacy_operating_characteristic.tex",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_tables(
    repo_root: Path,
    run_hash: str,
    experiment_id: str | None,
) -> list[str]:
    root = repo_root.resolve()
    run_tables = root / "outputs" / run_hash / "tables"
    manuscript_tables = root / "manuscript" / "tables"
    if not run_tables.is_dir():
        raise FileNotFoundError(run_tables)
    manuscript_tables.mkdir(parents=True, exist_ok=True)

    repair_run_tables(
        repo_root=root,
        run_hash=run_hash,
        experiment_id=experiment_id,
        copy_manuscript=True,
    )

    for name in LEGACY_TABLES:
        legacy = manuscript_tables / name
        if legacy.exists():
            legacy.unlink()

    copied: list[str] = []
    for source in sorted(run_tables.glob("*.tex"), key=lambda p: p.name):
        if source.name in LEGACY_TABLES:
            continue
        destination = manuscript_tables / source.name
        shutil.copy2(source, destination)
        if sha256(source) != sha256(destination):
            raise RuntimeError(f"exported table differs from canonical source: {source.name}")
        copied.append(source.name)

    unexpected_legacy = [
        name for name in LEGACY_TABLES if (manuscript_tables / name).exists()
    ]
    if unexpected_legacy:
        raise RuntimeError(f"legacy manuscript tables remain: {unexpected_legacy}")
    return copied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--run-hash", required=True)
    parser.add_argument("--experiment-id", default=None)
    args = parser.parse_args()
    copied = export_tables(args.repo, args.run_hash, args.experiment_id)
    print(f"[manuscript-export] run={args.run_hash}")
    for name in copied:
        print(f"[manuscript-export] {name}")
    print("[manuscript-export] no raw or summary artefacts regenerated")


if __name__ == "__main__":
    main()
