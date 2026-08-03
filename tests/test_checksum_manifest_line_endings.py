from __future__ import annotations

import csv
import sys
from pathlib import Path


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "scripts"
)

sys.path.insert(
    0,
    str(SCRIPTS_DIR),
)

from repair_manuscript_table_rendering import (  # noqa: E402
    _write_checksum_manifest_rows,
)


def test_checksum_manifest_writer_uses_lf_only(
    tmp_path: Path,
) -> None:
    manifest_path = (
        tmp_path
        / "certified-output-checksums.csv"
    )

    rows = [
        {
            "Path": "outputs/example.txt",
            "Bytes": "3",
            "SHA256": "abc123",
        }
    ]

    _write_checksum_manifest_rows(
        manifest_path,
        fieldnames=[
            "Path",
            "Bytes",
            "SHA256",
        ],
        rows=rows,
    )

    payload = manifest_path.read_bytes()

    assert b"\r\n" not in payload

    assert payload == (
        b'"Path","Bytes","SHA256"\n'
        b'"outputs/example.txt","3","abc123"\n'
    )

    with manifest_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        parsed_rows = list(
            csv.DictReader(handle)
        )

    assert parsed_rows == rows
