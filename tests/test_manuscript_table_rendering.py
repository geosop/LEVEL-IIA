from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_HASH = "0cd4cac11153c546"
EXPERIMENT_ID = "route_match_1be69ec6cd081a58"
RUN_DIR = ROOT / "outputs" / RUN_HASH
OUTPUT_TABLES = RUN_DIR / "tables"
MANUSCRIPT_TABLES = ROOT / "manuscript" / "tables"
WORKED_NAMES = [
    "worked_decision_example_values.tex",
    "worked_decision_example_bins.tex",
    "worked_decision_example_slopes.tex",
    "worked_decision_example_decision.tex",
    "worked_decision_example.tex",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rendering_repairs_are_present_and_copies_match() -> None:
    names = [
        "operating_characteristics_design.tex",
        "operating_characteristics_outcomes.tex",
        "route_matched_null_comparison.tex",
        "v12_result_macros.tex",
        *WORKED_NAMES,
    ]
    for name in names:
        output = OUTPUT_TABLES / name
        manuscript = MANUSCRIPT_TABLES / name
        assert output.exists(), name
        assert manuscript.exists(), name
        assert output.read_bytes() == manuscript.read_bytes(), name

    design = (OUTPUT_TABLES / "operating_characteristics_design.tex").read_text(
        encoding="utf-8"
    )
    assert r"\resizebox{\linewidth}{!}{%" in design
    assert r"\begin{tabular}{@{}llrrrrrr@{}}" in design

    outcomes = (OUTPUT_TABLES / "operating_characteristics_outcomes.tex").read_text(
        encoding="utf-8"
    )
    assert "A. Diagnostic and qualification rates" in outcomes
    assert "B. Mutually exclusive decision outcomes" in outcomes
    assert outcomes.count(r"\resizebox{\linewidth}{!}{%") == 2
    assert r"\begin{tabular}{lrrrrrrrrllllll}" not in outcomes

    route = (OUTPUT_TABLES / "route_matched_null_comparison.tex").read_text(
        encoding="utf-8"
    )
    assert r"\resizebox{\linewidth}{!}{%" in route
    assert r"\begin{tabular}{@{}llrrrrr@{}}" in route
    assert r"\begin{tabular}{@{}lrrp{0.42\textwidth}@{}}" in route
    assert r"\begin{tabular}{lrrrrrrr}" not in route

    macros = (OUTPUT_TABLES / "v12_result_macros.tex").read_text(
        encoding="utf-8"
    )
    assert r"\providecommand{\LevelIIAAnchorSelectionLimitedRate}{0.008}" in macros
    assert (
        r"\providecommand{\LevelIIAAnchorSelectionLimitedCountRate}{9/1200=0.008}"
        in macros
    )


def test_worked_example_is_data_only_and_split() -> None:
    values = (OUTPUT_TABLES / "worked_decision_example_values.tex").read_text(
        encoding="utf-8"
    )
    required_macros = {
        "LevelIIAWorkedRepSupported": "657",
        "LevelIIAWorkedSeedSupported": "102",
        "LevelIIAWorkedRepClean": "438",
        "LevelIIAWorkedSeedClean": "101",
        "LevelIIAWorkedP": "24",
        "LevelIIAWorkedSigmaTau": "0.00708",
        "LevelIIAWorkedSigmaBlind": "1.10",
        "LevelIIAWorkedNbarRet": "95.4",
        "LevelIIAWorkedBetaMin": "31.8",
        "LevelIIAWorkedSlopeMean": "-60.1",
        "LevelIIAWorkedSlopeSE": "3.7",
    }
    for macro, value in required_macros.items():
        assert rf"\providecommand{{\{macro}}}{{{value}}}" in values

    forbidden = [
        r"\paragraph{",
        "This floor is a resolvability threshold",
        "The assignment-calibrated randomisation test asks",
        "The clean-null draw uses",
        "The executable classifier therefore returns",
    ]
    for name in WORKED_NAMES:
        text = (OUTPUT_TABLES / name).read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, (name, phrase)

    bins = (OUTPUT_TABLES / "worked_decision_example_bins.tex").read_text(
        encoding="utf-8"
    )
    slopes = (OUTPUT_TABLES / "worked_decision_example_slopes.tex").read_text(
        encoding="utf-8"
    )
    decision = (OUTPUT_TABLES / "worked_decision_example_decision.tex").read_text(
        encoding="utf-8"
    )
    aggregate = (OUTPUT_TABLES / "worked_decision_example.tex").read_text(
        encoding="utf-8"
    )

    assert bins.count(r"\begin{table}[H]") == 1
    assert r"\label{tab:si-worked-bins}" in bins
    assert slopes.count(r"\begin{table}[H]") == 1
    assert r"\label{tab:si-worked-slopes}" in slopes
    assert decision.count(r"\begin{table}[H]") == 1
    assert r"\label{tab:si-worked-decision}" in decision
    assert r">{\raggedright\arraybackslash}X" in decision
    assert r"forward\_\allowbreak only\_\allowbreak adequate" in decision
    assert "p{3.9cm}p{3.0cm}p{3.0cm}p{3.0cm}" not in decision
    assert aggregate.count(r"\begin{table}[H]") == 3


def test_route_checksum_chain_matches_all_three_copies() -> None:
    pointer_path = RUN_DIR / "metadata" / "route_matched_null_comparison.json"
    aux_dir = RUN_DIR / "auxiliary" / EXPERIMENT_ID
    aux_metadata_path = aux_dir / "metadata.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    auxiliary = json.loads(aux_metadata_path.read_text(encoding="utf-8"))

    canonical = RUN_DIR / pointer["table"]["path"]
    aux_table = aux_dir / "tables" / "route_matched_null_comparison.tex"
    manuscript = MANUSCRIPT_TABLES / "route_matched_null_comparison.tex"
    expected = _sha256(canonical)

    assert pointer["parent_run_hash"] == RUN_HASH
    assert auxiliary["parent_run_hash"] == RUN_HASH
    assert pointer["experiment_id"] == EXPERIMENT_ID
    assert auxiliary["experiment_id"] == EXPERIMENT_ID
    assert _sha256(aux_table) == expected
    assert _sha256(manuscript) == expected
    assert pointer["table"]["sha256"] == expected
    assert auxiliary["table"]["sha256"] == expected
    for metadata in (pointer, auxiliary):
        repair = metadata["table"]["rendering_repair"]
        assert repair["script"] == "scripts/repair_manuscript_table_rendering.py"
        assert repair["raw_summary_contrasts_unchanged"] is True


def test_parent_checksum_manifest_matches_repaired_files() -> None:
    manifest = RUN_DIR / "metadata" / "certified-output-checksums.csv"
    with manifest.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = {row["Path"]: row for row in csv.DictReader(fh)}

    names = [
        "operating_characteristics_design.tex",
        "operating_characteristics_outcomes.tex",
        "v12_result_macros.tex",
        *WORKED_NAMES,
    ]
    targets = [OUTPUT_TABLES / name for name in names]
    targets.append(RUN_DIR / "metadata" / "manuscript_table_rendering.json")
    for path in targets:
        relative = path.relative_to(ROOT).as_posix()
        assert relative in rows
        assert int(rows[relative]["Length"]) == path.stat().st_size
        assert rows[relative]["SHA256"] == _sha256(path)


def test_rendering_metadata_preserves_parent_identifiers() -> None:
    metadata_path = RUN_DIR / "metadata" / "manuscript_table_rendering.json"
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert data["parent_run_hash"] == RUN_HASH
    assert data["route_experiment_id"] == EXPERIMENT_ID
    assert data["raw_and_summary_evidence_unchanged"] is True
    assert data["protected_evidence_file_count"] > 0
    assert len(data["protected_evidence_tree_sha256"]) == 64

    split = data["worked_example_split"]
    assert split["script"] == "scripts/split_worked_example_rendering.py"
    assert split["raw_summary_and_representative_evidence_unchanged"] is True
    assert len(split["script_sha256"]) == 64

    hashes = data["table_sha256"]
    for name in WORKED_NAMES:
        assert hashes[name] == _sha256(OUTPUT_TABLES / name)
