from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / "scripts"
)

sys.path.insert(0, str(SCRIPTS_DIR))

from repair_manuscript_table_rendering import (  # noqa: E402
    _load_previous_rendering_provenance,
)


RUN_HASH = "0cd4cac11153c546"
EXPERIMENT_ID = "route_match_1be69ec6cd081a58"
FIRST_SPLIT_COMMIT = (
    "661cfdb96e46432a50dede927dd7ca764595ce81"
)


def _compatible_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "manuscript_table_rendering_repair",
        "parent_run_hash": RUN_HASH,
        "route_experiment_id": EXPERIMENT_ID,
        "first_applied_git_commit": (
            "7ebd0d6ce1a20bc2517df3136075239a027ac403"
        ),
        "worked_example_split": {
            "schema_version": 1,
            "reason": (
                "separate frozen data artefacts "
                "from manuscript-owned interpretation"
            ),
            "script": (
                "scripts/split_worked_example_rendering.py"
            ),
            "script_sha256": "split-script-sha256",
            "first_applied_git_commit": (
                FIRST_SPLIT_COMMIT
            ),
            (
                "raw_summary_and_representative_"
                "evidence_unchanged"
            ): True,
        },
    }


def test_preserves_compatible_worked_example_split(
    tmp_path: Path,
) -> None:
    metadata_path = (
        tmp_path / "manuscript_table_rendering.json"
    )

    payload = _compatible_payload()

    metadata_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    first_commit, split_record = (
        _load_previous_rendering_provenance(
            metadata_path,
            run_hash=RUN_HASH,
            experiment_id=EXPERIMENT_ID,
        )
    )

    assert first_commit == (
        "7ebd0d6ce1a20bc2517df3136075239a027ac403"
    )
    assert split_record is not None
    assert split_record["first_applied_git_commit"] == (
        FIRST_SPLIT_COMMIT
    )


def test_rejects_incompatible_prior_metadata(
    tmp_path: Path,
) -> None:
    metadata_path = (
        tmp_path / "manuscript_table_rendering.json"
    )

    payload = _compatible_payload()
    payload["parent_run_hash"] = "different-run"

    metadata_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    first_commit, split_record = (
        _load_previous_rendering_provenance(
            metadata_path,
            run_hash=RUN_HASH,
            experiment_id=EXPERIMENT_ID,
        )
    )

    assert first_commit is None
    assert split_record is None
