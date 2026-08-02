#!/usr/bin/env python3
"""Split the frozen worked-example artefact into data-only manuscript inputs.

This presentation-layer utility does not regenerate Monte Carlo rows, summary
statistics, representative indices, or classifier outputs. It extracts locked
scalars and the three table environments from the existing frozen worked-example
LaTeX artefact, removes interpretive prose from generated outputs, synchronizes
canonical and manuscript copies, and updates presentation checksum provenance.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from repair_manuscript_table_rendering import (
    atomic_write_text,
    git_commit,
    protected_evidence_paths,
    sha256,
    stable_tree_digest,
    update_checksum_manifest,
)

WORKED_NAMES = [
    "worked_decision_example_values.tex",
    "worked_decision_example_bins.tex",
    "worked_decision_example_slopes.tex",
    "worked_decision_example_decision.tex",
    "worked_decision_example.tex",
]

FORBIDDEN_PROSE = [
    r"\paragraph{",
    "This floor is a resolvability threshold",
    "The assignment-calibrated randomisation test asks",
    "The clean-null draw uses",
    "The executable classifier therefore returns",
]


def _capture(text: str, pattern: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        raise ValueError(f"worked-example scalar not found: {label}")
    return match.group(1)


def _extract_table(text: str, label: str) -> str:
    blocks = re.findall(
        r"\\begin\{table\}\[[^\]]+\].*?\\end\{table\}",
        text,
        flags=re.DOTALL,
    )
    needle = rf"\label{{{label}}}"
    matches = [block for block in blocks if needle in block]
    if len(matches) != 1:
        raise ValueError(
            f"expected one worked-example table for {label}, found {len(matches)}"
        )
    return matches[0].replace(r"\begin{table}[t]", r"\begin{table}[H]", 1) + "\n"


def _repair_decision_table(table: str) -> str:
    old_spec = (
        "\\footnotesize\n"
        "\\setlength{\\tabcolsep}{3.5pt}\n"
        "\\begin{tabularx}{\\textwidth}{@{}p{3.9cm}p{3.0cm}p{3.0cm}p{3.0cm}@{}}"
    )
    new_spec = (
        "\\footnotesize\n"
        "\\setlength{\\tabcolsep}{3pt}\n"
        "\\begin{tabularx}{\\textwidth}{@{}\n"
        "    >{\\raggedright\\arraybackslash}p{4.0cm}\n"
        "    >{\\raggedright\\arraybackslash}X\n"
        "    >{\\raggedright\\arraybackslash}p{3.0cm}\n"
        "    >{\\raggedright\\arraybackslash}p{3.0cm}\n"
        "@{}}"
    )
    if old_spec in table:
        table = table.replace(old_spec, new_spec, 1)
    elif new_spec not in table:
        raise ValueError("unrecognized worked-example decision-table layout")

    old_row = (
        "Decision & executable classifier & \\texttt{supported} & "
        "\\texttt{forward\\_only\\_adequate} \\\\"
    )
    new_row = (
        "Decision & executable classifier & \\texttt{supported} &\n"
        "\\texttt{forward\\_\\allowbreak only\\_\\allowbreak adequate} \\\\"
    )
    if old_row in table:
        table = table.replace(old_row, new_row, 1)
    elif new_row not in table:
        raise ValueError("unrecognized worked-example classifier row")
    return table


def _render_values(text: str, run_hash: str) -> str:
    if f"Frozen run hash: {run_hash}." not in text:
        raise ValueError("worked-example run-hash provenance mismatch")

    supported = re.search(
        re.escape("supported injected-residual draw is replicate \\(")
        + r"(\d+)"
        + re.escape("\\) with base seed \\(")
        + r"(\d+)"
        + re.escape("\\)"),
        text,
    )
    clean = re.search(
        re.escape("clean-null draw is replicate \\(")
        + r"(\d+)"
        + re.escape("\\) with base seed \\(")
        + r"(\d+)"
        + re.escape("\\)"),
        text,
    )
    if supported is None or clean is None:
        raise ValueError("worked-example representative indices could not be parsed")

    values = {
        "LevelIIAWorkedRepSupported": supported.group(1),
        "LevelIIAWorkedSeedSupported": supported.group(2),
        "LevelIIAWorkedRepClean": clean.group(1),
        "LevelIIAWorkedSeedClean": clean.group(2),
        "LevelIIAWorkedP": _capture(
            text,
            re.escape("Both examples use \\(P=") + r"(\d+)" + re.escape("\\) participants"),
            "participant count",
        ),
        "LevelIIAWorkedSigmaTau": _capture(
            text,
            re.escape(r"\sigma_\tau=") + r"([0-9.]+)" + re.escape(r"\,\mathrm{s}"),
            "sigma tau",
        ),
        "LevelIIAWorkedSigmaBlind": _capture(
            text,
            re.escape(r"\sigma^{\mathrm{blind}}_{\mathrm{resid}}=")
            + r"([0-9.]+)",
            "blind residual scale",
        ),
        "LevelIIAWorkedNbarRet": _capture(
            text,
            re.escape(r"\bar n_{\mathrm{ret}}=") + r"([0-9.]+)",
            "retained-trial yield",
        ),
        "LevelIIAWorkedBetaMin": _capture(
            text,
            re.escape(r"\sqrt{\bar n_{\mathrm{ret}}}}=")
            + r"([0-9.]+)"
            + re.escape(r"\,\mu\mathrm{V\,s^{-1}}"),
            "resolution floor",
        ),
        "LevelIIAWorkedSlopeMean": _capture(
            text,
            re.escape(r"Their mean is \(\widehat\beta_\tau=") + r"([-0-9.]+)",
            "slope mean",
        ),
        "LevelIIAWorkedSlopeSE": _capture(
            text,
            re.escape("participant-level standard error \\(") + r"([0-9.]+)",
            "slope standard error",
        ),
    }

    lines = [
        "% Rendering-derived locked worked-example scalars; do not edit.",
        f"% Frozen run hash: {run_hash}.",
    ]
    for macro, value in values.items():
        lines.append(f"\\providecommand{{\\{macro}}}{{{value}}}")
    return "\n".join(lines) + "\n"


def _update_rendering_metadata(
    repo_root: Path,
    run_dir: Path,
    paths: list[Path],
) -> None:
    metadata_path = run_dir / "metadata" / "manuscript_table_rendering.json"
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    script_path = Path(__file__).resolve()
    existing = data.get("worked_example_split", {})
    data["worked_example_split"] = {
        "schema_version": 1,
        "reason": "separate frozen data artefacts from manuscript-owned interpretation",
        "script": "scripts/split_worked_example_rendering.py",
        "script_sha256": sha256(script_path),
        "first_applied_git_commit": existing.get("first_applied_git_commit")
        or git_commit(repo_root),
        "raw_summary_and_representative_evidence_unchanged": True,
    }
    table_hashes = data.setdefault("table_sha256", {})
    for path in paths:
        table_hashes[path.name] = sha256(path)
    atomic_write_text(metadata_path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def split_worked_example(
    repo_root: Path,
    run_hash: str,
    copy_manuscript: bool = True,
) -> dict[str, str]:
    root = repo_root.resolve()
    run_dir = root / "outputs" / run_hash
    output_tables = run_dir / "tables"
    manuscript_tables = root / "manuscript" / "tables"
    aggregate_path = output_tables / "worked_decision_example.tex"
    if not aggregate_path.is_file():
        raise FileNotFoundError(aggregate_path)

    protected = protected_evidence_paths(run_dir)
    evidence_before, evidence_count = stable_tree_digest(root, protected)

    aggregate_text = aggregate_path.read_text(encoding="utf-8")
    values_path = output_tables / "worked_decision_example_values.tex"
    if r"\paragraph{Design and locked constants.}" in aggregate_text:
        values_text = _render_values(aggregate_text, run_hash)
    else:
        if not values_path.is_file():
            raise ValueError(
                "worked-example aggregate is already data-only but values file is missing"
            )
        values_text = values_path.read_text(encoding="utf-8")

    bins_text = _extract_table(aggregate_text, "tab:si-worked-bins")
    slopes_text = _extract_table(aggregate_text, "tab:si-worked-slopes")
    decision_text = _repair_decision_table(
        _extract_table(aggregate_text, "tab:si-worked-decision")
    )

    outputs = {
        "worked_decision_example_values.tex": values_text,
        "worked_decision_example_bins.tex": bins_text,
        "worked_decision_example_slopes.tex": slopes_text,
        "worked_decision_example_decision.tex": decision_text,
    }
    for name, text in outputs.items():
        if any(phrase in text for phrase in FORBIDDEN_PROSE):
            raise ValueError(f"interpretive prose remains in generated file: {name}")
        atomic_write_text(output_tables / name, text)

    aggregate = (
        "% Data-only compatibility aggregate produced by "
        "scripts/split_worked_example_rendering.py; do not edit.\n"
        f"% Frozen run hash: {run_hash}.\n"
        + bins_text
        + "\n"
        + slopes_text
        + "\n"
        + decision_text
    )
    if any(phrase in aggregate for phrase in FORBIDDEN_PROSE):
        raise ValueError("interpretive prose remains in worked-example aggregate")
    atomic_write_text(aggregate_path, aggregate)

    affected = [output_tables / name for name in WORKED_NAMES]
    if copy_manuscript:
        manuscript_tables.mkdir(parents=True, exist_ok=True)
        for source in affected:
            atomic_write_text(
                manuscript_tables / source.name,
                source.read_text(encoding="utf-8"),
            )

    evidence_after, evidence_count_after = stable_tree_digest(root, protected)
    if evidence_count_after != evidence_count or evidence_after != evidence_before:
        raise RuntimeError("protected raw/summary evidence changed during worked split")

    _update_rendering_metadata(root, run_dir, affected)
    metadata_path = run_dir / "metadata" / "manuscript_table_rendering.json"
    update_checksum_manifest(
        run_dir / "metadata" / "certified-output-checksums.csv",
        root,
        [*affected, metadata_path],
    )

    hashes = {path.name: sha256(path) for path in affected}
    if copy_manuscript:
        for source in affected:
            destination = manuscript_tables / source.name
            if sha256(source) != sha256(destination):
                raise RuntimeError(f"manuscript copy differs: {source.name}")
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--run-hash", required=True)
    parser.add_argument("--no-copy", action="store_true")
    args = parser.parse_args()
    hashes = split_worked_example(
        repo_root=args.repo,
        run_hash=args.run_hash,
        copy_manuscript=not args.no_copy,
    )
    print(f"[worked-split] run={args.run_hash}")
    for name, digest in sorted(hashes.items()):
        print(f"[worked-split] {name} sha256={digest}")
    print("[worked-split] interpretive prose remains manuscript-owned")
    print("[worked-split] no raw or summary artefacts regenerated")


if __name__ == "__main__":
    main()
