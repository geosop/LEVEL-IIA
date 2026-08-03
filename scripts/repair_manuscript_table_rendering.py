#!/usr/bin/env python3
"""Apply deterministic, rendering-only repairs to manuscript-facing tables.

The script never regenerates Monte Carlo rows or summary statistics. It reads
frozen CSV/table artefacts, rewrites only LaTeX presentation artefacts, keeps
canonical/manuscript/auxiliary copies synchronized, updates the existing parent
checksum manifest for the affected parent-run files, and updates the route-table
checksum in the route-matched metadata chain.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

import pandas as pd

ROUTE_CELL_ORDER = [
    "clean_assignment_isolation",
    "clean_sequential_evalue",
    "adversarial_sequential_evalue",
]
ROUTE_LABELS = {
    "clean_assignment_isolation": ("Clean", "assignment isolation"),
    "clean_sequential_evalue": ("Clean", "sequential e-value"),
    "adversarial_sequential_evalue": ("Adversarial", "sequential e-value"),
}
SCENARIO_ORDER = [
    "clean_null",
    "injected_residual",
    "leakage",
    "selection_standard",
    "collider_selection",
    "adversarial_null",
    "opposite_direction",
]
PARENT_TABLE_NAMES = [
    "operating_characteristics_design.tex",
    "operating_characteristics_outcomes.tex",
    "v12_result_macros.tex",
    "worked_decision_example.tex",
]
ALL_REPAIRED_TABLE_NAMES = [
    *PARENT_TABLE_NAMES,
    "route_matched_null_comparison.tex",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "no-git"


def stable_tree_digest(root: Path, paths: Iterable[Path]) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted({p.resolve() for p in paths}, key=lambda p: p.as_posix()):
        if not path.is_file():
            continue
        try:
            label = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            label = path.name
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256(path)))
        digest.update(b"\0")
        count += 1
    return digest.hexdigest(), count


def protected_evidence_paths(run_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for dirname in ("raw", "summary"):
        base = run_dir / dirname
        if base.exists():
            paths.extend(path for path in base.rglob("*") if path.is_file())
    auxiliary = run_dir / "auxiliary"
    if auxiliary.exists():
        for directory in auxiliary.rglob("*"):
            if directory.is_dir() and directory.name in {"raw", "summary"}:
                paths.extend(path for path in directory.rglob("*") if path.is_file())
    return paths


def repair_design_table(text: str, run_hash: str) -> str:
    if f"run_hash={run_hash}" not in text:
        raise ValueError("design table run-hash provenance mismatch")
    old_open = (
        "\\setlength{\\tabcolsep}{3pt}\n"
        "\\begin{tabular}{llrrrrrr}"
    )
    new_open = (
        "\\setlength{\\tabcolsep}{3pt}\n"
        "\\resizebox{\\linewidth}{!}{%\n"
        "\\begin{tabular}{@{}llrrrrrr@{}}"
    )
    old_close = "\\bottomrule\n\\end{tabular}\n\\end{table}"
    new_close = "\\bottomrule\n\\end{tabular}%\n}\n\\end{table}"

    if old_open in text:
        text = text.replace(old_open, new_open, 1)
    elif new_open not in text:
        raise ValueError("unrecognized design-table opening")

    if old_close in text:
        text = text.replace(old_close, new_close, 1)
    elif new_close not in text:
        raise ValueError("unrecognized design-table closing")
    return text


def fmt_rate(value: object) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{Decimal(str(value)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP):.3f}"


def fmt_count_rate(n: int, m: int) -> str:
    rate = (Decimal(n) / Decimal(m)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    return f"{n}/{m} ({rate:.3f})"


def latex_escape(text: object) -> str:
    return str(text).replace("_", "\\_")


def render_outcomes_table(oc: pd.DataFrame, run_hash: str) -> str:
    if oc["scenario"].tolist() != SCENARIO_ORDER:
        raise ValueError("unexpected operating-characteristic scenario order")
    m_values = set(oc["M"].astype(int))
    if m_values != {1200}:
        raise ValueError(f"unexpected M values for locked table: {sorted(m_values)}")
    m = 1200
    lines = [
        "% Rendering repaired by scripts/repair_manuscript_table_rendering.py; do not edit.",
        f"% Source: outputs/{run_hash}/summary/operating_characteristics.csv",
        "\\begin{table}[t]",
        "\\centering",
        (
            "\\caption{Diagnostic rates and mutually exclusive decision outcomes "
            "for the locked Level II-A pipeline on simulated data. Design constants "
            "and slope summaries are reported in Table~\\ref{tab:si-oc-design}. "
            f"Run hash \\texttt{{{run_hash}}}; $M={m}$ Monte Carlo datasets per "
            "scenario. Panel~A reports diagnostic and qualification rates. Panel~B "
            "reports exact counts with rates in parentheses for the six mutually "
            "exclusive outcomes. The negative tail is the sole confirmatory "
            "level-$\\alpha$ hypothesis; the positive tail is a prespecified "
            "diagnostic. Component disagreement is routed to the inconclusive "
            "class. $^{a}$The scalar selection gate is evaluated only for a resolved "
            "material departure; the displayed rate is conditional on applicability. "
            "Not human EEG.}"
        ),
        "\\label{tab:si-oc-outcomes}",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{3.5pt}",
        "\\textbf{A. Diagnostic and qualification rates}\\par\\smallskip",
        "\\resizebox{\\linewidth}{!}{%",
        "\\begin{tabular}{@{}lrrrrrrrr@{}}",
        "\\toprule",
        (
            "Scenario & rand. pass & resol. pass & comp. dis. & reten. fire & "
            "leak fire & gate pass$^{a}$ & collider fire & est. block \\\\"
        ),
        "\\midrule",
    ]
    for row in oc.itertuples(index=False):
        lines.append(
            " & ".join(
                [
                    latex_escape(row.scenario),
                    fmt_rate(row.rand_pass_rate),
                    fmt_rate(row.materiality_pass_rate),
                    fmt_rate(row.component_disagreement_rate),
                    fmt_rate(row.retention_fire_rate),
                    fmt_rate(row.leak_fire_rate),
                    fmt_rate(row.gate_pass_given_applicable_rate),
                    fmt_rate(row.collider_fire_rate),
                    fmt_rate(row.estimability_conclusion_change_rate),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}%",
            "}",
            "",
            "\\medskip",
            "\\textbf{B. Mutually exclusive decision outcomes}\\par\\smallskip",
            "\\resizebox{\\linewidth}{!}{%",
            "\\begin{tabular}{@{}lrrrrrr@{}}",
            "\\toprule",
            (
                "Scenario & support & sel.-lim. & diag. fail & null & opp. diag. "
                "& inconcl. \\\\"
            ),
            "\\midrule",
        ]
    )
    count_columns = [
        "support_n",
        "selection_limited_n",
        "diagnostic_failure_n",
        "null_n",
        "opposite_direction_n",
        "inconclusive_n",
    ]
    for _, row in oc.iterrows():
        values = [latex_escape(row["scenario"])]
        values.extend(fmt_count_rate(int(row[col]), int(row["M"])) for col in count_columns)
        lines.append(" & ".join(values) + r" \\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}%", "}", "\\end{table}"])
    return "\n".join(lines) + "\n"


def render_route_table(
    summary: pd.DataFrame,
    contrasts: pd.DataFrame,
    run_hash: str,
    experiment_id: str,
) -> str:
    if summary["cell_id"].tolist() != ROUTE_CELL_ORDER:
        raise ValueError("unexpected route-matched cell order")
    if (summary["support_n"].astype(int) != 0).any():
        raise ValueError("route table assumes zero support in all null cells")
    if (summary["opposite_n"].astype(int) != 0).any():
        raise ValueError("route table assumes zero opposite outcomes in all cells")
    expected_contrasts = [
        "clean_sequential_minus_clean_assignment",
        "adversarial_sequential_minus_clean_sequential",
    ]
    if contrasts["contrast_id"].tolist() != expected_contrasts:
        raise ValueError("unexpected route-matched contrast order")

    lines = [
        "% Rendering repaired by scripts/repair_manuscript_table_rendering.py; do not edit.",
        f"% parent run={run_hash}; experiment_id={experiment_id}",
        "\\begin{table}[t]",
        "\\centering",
        (
            "\\caption{Validity-matched null-generator and inference-route "
            "comparison. The two clean rows use identical generated datasets "
            "replicate by replicate. The full adversarial carryover generator is "
            "evaluated only under the sequential e-value route because assignment "
            "isolation requires endpoint-array invariance. Outcome cells report "
            "counts and rates from \\(M=1200\\) datasets; support and "
            "opposite-direction counts were zero in all three cells. Contrast "
            "intervals use the locked paired or independent procedure appropriate "
            "to each comparison.}"
        ),
        "\\label{tab:si-route-matched-null-comparison}",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{2.5pt}",
        "\\resizebox{\\linewidth}{!}{%",
        "\\begin{tabular}{@{}llrrrrr@{}}",
        "\\toprule",
        (
            "Generator & Route & Adequate & Inconclusive & Selection-limited & "
            "Diagnostic failure & Component disagreement \\\\"
        ),
        "\\midrule",
    ]
    for cell_id in ROUTE_CELL_ORDER:
        row = summary.loc[summary["cell_id"] == cell_id].iloc[0]
        generator, route = ROUTE_LABELS[cell_id]
        m = int(row["M"])
        lines.append(
            " & ".join(
                [
                    generator,
                    route,
                    fmt_count_rate(int(row["adequate_n"]), m),
                    fmt_count_rate(int(row["inconclusive_n"]), m),
                    fmt_count_rate(int(row["selection_limited_n"]), m),
                    fmt_count_rate(int(row["diagnostic_failure_n"]), m),
                    fmt_count_rate(int(row["component_disagreement_n"]), m),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}%",
            "}",
            "",
            "\\medskip",
            "\\begin{tabular}{@{}lrrp{0.42\\textwidth}@{}}",
            "\\toprule",
            r"Contrast & Estimate & 95\% interval & Interpretation \\",
            "\\midrule",
        ]
    )
    route = contrasts.iloc[0]
    generator = contrasts.iloc[1]
    lines.append(
        "Clean sequential $-$ clean assignment"
        f" & {route['estimate']:+.3f}"
        f" & [{route['ci95_low']:+.3f}, {route['ci95_high']:+.3f}]"
        r" & Paired route contrast on identical clean datasets \\"
    )
    lines.append(
        "Adversarial sequential $-$ clean sequential"
        f" & {generator['estimate']:+.3f}"
        f" & [{generator['ci95_low']:+.3f}, {generator['ci95_high']:+.3f}]"
        r" & Generator contrast under the common sequential route \\"
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}"])
    return "\n".join(lines) + "\n"


def repair_worked_table(text: str, run_hash: str) -> str:
    if f"Frozen run hash: {run_hash}." not in text:
        raise ValueError("worked-example run-hash provenance mismatch")
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
    if old_spec in text:
        text = text.replace(old_spec, new_spec, 1)
    elif new_spec not in text:
        raise ValueError("unrecognized worked-example table specification")

    old_row = (
        "Decision & executable classifier & \\texttt{supported} & "
        "\\texttt{forward\\_only\\_adequate} \\\\"
    )
    new_row = (
        "Decision & executable classifier & \\texttt{supported} &\n"
        "\\texttt{forward\\_\\allowbreak only\\_\\allowbreak adequate} \\\\"
    )
    if old_row in text:
        text = text.replace(old_row, new_row, 1)
    elif new_row not in text:
        raise ValueError("unrecognized worked-example decision row")
    return text


def repair_result_macros(text: str, oc: pd.DataFrame, run_hash: str) -> str:
    if f"{{{run_hash}}}" not in text:
        raise ValueError("result-macro run-hash mismatch")
    row = oc.loc[oc["scenario"] == "clean_null"].iloc[0]
    n = int(row["selection_limited_n"])
    m = int(row["M"])
    rate = (Decimal(n) / Decimal(m)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    replacements = {
        "LevelIIAAnchorSelectionLimitedRate": f"{rate:.3f}",
        "LevelIIAAnchorSelectionLimitedCountRate": f"{n}/{m}={rate:.3f}",
    }
    for macro, value in replacements.items():
        pattern = re.compile(
            rf"(\\providecommand\{{\\{re.escape(macro)}\}}\{{)[^}}]*(\}})"
        )
        text, count = pattern.subn(rf"\g<1>{value}\g<2>", text, count=1)
        if count != 1:
            raise ValueError(f"could not normalize macro {macro}")
    return text


def update_checksum_manifest(
    manifest_path: Path,
    root: Path,
    affected_paths: list[Path],
) -> None:
    if not manifest_path.exists():
        return
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    expected_fields = ["Path", "Length", "SHA256"]
    if not rows or list(rows[0].keys()) != expected_fields:
        raise ValueError("unexpected certified-output checksum manifest schema")

    by_path = {row["Path"]: row for row in rows}
    for path in affected_paths:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        row = by_path.get(relative)
        if row is None:
            row = {"Path": relative, "Length": "", "SHA256": ""}
            rows.append(row)
            by_path[relative] = row
        row["Length"] = str(path.stat().st_size)
        row["SHA256"] = sha256(path)

    rows.sort(key=lambda item: item["Path"])
    _write_checksum_manifest_rows(
        manifest_path,
        fieldnames=expected_fields,
        rows=rows,
    )


def _write_checksum_manifest_rows(
    manifest_path: Path,
    *,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> None:
    """Write the checksum manifest with deterministic LF endings."""
    tmp = manifest_path.with_name(
        manifest_path.name + ".tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fieldnames,
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(manifest_path)


def update_route_metadata(
    root: Path,
    pointer_path: Path,
    aux_metadata_path: Path,
    table_hash: str,
    script_hash: str,
) -> None:
    existing_first_commit: str | None = None
    for path in (pointer_path, aux_metadata_path):
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data.get("table", {}).get("rendering_repair", {})
        if record.get("first_applied_git_commit"):
            existing_first_commit = str(record["first_applied_git_commit"])
            break
    first_commit = existing_first_commit or git_commit(root)
    record = {
        "schema_version": 1,
        "reason": "correct LaTeX column structure and submission layout only",
        "script": "scripts/repair_manuscript_table_rendering.py",
        "script_sha256": script_hash,
        "first_applied_git_commit": first_commit,
        "raw_summary_contrasts_unchanged": True,
    }
    for path in (pointer_path, aux_metadata_path):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["table"]["sha256"] = table_hash
        data["table"]["rendering_repair"] = record
        atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _load_previous_rendering_provenance(
    metadata_path: Path,
    *,
    run_hash: str,
    experiment_id: str,
) -> tuple[str | None, dict[str, object] | None]:
    """Load immutable provenance owned by earlier rendering operations."""
    if not metadata_path.exists():
        return None, None

    previous = json.loads(
        metadata_path.read_text(encoding="utf-8")
    )

    compatible_previous = (
        previous.get("schema_version") == 1
        and previous.get("kind")
        == "manuscript_table_rendering_repair"
        and previous.get("parent_run_hash") == run_hash
        and previous.get("route_experiment_id")
        == experiment_id
    )

    if not compatible_previous:
        return None, None

    existing_first_commit = previous.get(
        "first_applied_git_commit"
    )

    first_commit = (
        existing_first_commit
        if isinstance(existing_first_commit, str)
        and existing_first_commit
        else None
    )

    existing_split = previous.get(
        "worked_example_split"
    )

    worked_example_split = (
        dict(existing_split)
        if isinstance(existing_split, dict)
        else None
    )

    return first_commit, worked_example_split


def repair_run_tables(
    repo_root: Path,
    run_hash: str,
    experiment_id: str | None = None,
    copy_manuscript: bool = True,
) -> dict[str, str]:
    root = repo_root.resolve()
    run_dir = root / "outputs" / run_hash
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    run_metadata_path = run_dir / "metadata" / "run_metadata.json"
    run_metadata = json.loads(run_metadata_path.read_text(encoding="utf-8"))
    if run_metadata.get("run_hash") != run_hash:
        raise ValueError("parent run metadata mismatch")

    protected = protected_evidence_paths(run_dir)
    evidence_before, evidence_count = stable_tree_digest(root, protected)

    oc_path = run_dir / "summary" / "operating_characteristics.csv"
    oc = pd.read_csv(oc_path)
    if oc["scenario"].tolist() != SCENARIO_ORDER:
        raise ValueError("unexpected canonical scenario order")

    output_tables = run_dir / "tables"
    manuscript_tables = root / "manuscript" / "tables"
    manuscript_tables.mkdir(parents=True, exist_ok=True)

    design_path = output_tables / "operating_characteristics_design.tex"
    outcomes_path = output_tables / "operating_characteristics_outcomes.tex"
    macros_path = output_tables / "v12_result_macros.tex"
    worked_path = output_tables / "worked_decision_example.tex"

    atomic_write_text(
        design_path,
        repair_design_table(design_path.read_text(encoding="utf-8"), run_hash),
    )
    atomic_write_text(outcomes_path, render_outcomes_table(oc, run_hash))
    atomic_write_text(
        macros_path,
        repair_result_macros(macros_path.read_text(encoding="utf-8"), oc, run_hash),
    )
    atomic_write_text(
        worked_path,
        repair_worked_table(worked_path.read_text(encoding="utf-8"), run_hash),
    )

    pointer_path = run_dir / "metadata" / "route_matched_null_comparison.json"
    if pointer_path.exists():
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        actual_experiment_id = str(pointer["experiment_id"])
        if experiment_id is not None and actual_experiment_id != experiment_id:
            raise ValueError("route experiment ID mismatch")
        experiment_id = actual_experiment_id
        if pointer.get("parent_run_hash") != run_hash:
            raise ValueError("route pointer parent-run mismatch")
        aux_dir = run_dir / "auxiliary" / experiment_id
        aux_metadata_path = aux_dir / "metadata.json"
        auxiliary = json.loads(aux_metadata_path.read_text(encoding="utf-8"))
        if auxiliary.get("experiment_id") != experiment_id:
            raise ValueError("auxiliary route metadata mismatch")
        summary_path = run_dir / pointer["summary"]["path"]
        contrasts_path = run_dir / pointer["contrasts"]["path"]
        route_text = render_route_table(
            pd.read_csv(summary_path),
            pd.read_csv(contrasts_path),
            run_hash,
            experiment_id,
        )
        route_output = run_dir / pointer["table"]["path"]
        route_aux = aux_dir / "tables" / "route_matched_null_comparison.tex"
        for path in (route_output, route_aux):
            atomic_write_text(path, route_text)
        if copy_manuscript:
            atomic_write_text(
                manuscript_tables / "route_matched_null_comparison.tex", route_text
            )
        route_hash = sha256(route_output)
        if sha256(route_aux) != route_hash:
            raise RuntimeError("canonical and auxiliary route tables differ")
        script_hash = sha256(Path(__file__).resolve())
        update_route_metadata(
            root,
            pointer_path,
            aux_metadata_path,
            route_hash,
            script_hash,
        )
    elif experiment_id is not None:
        raise FileNotFoundError(pointer_path)

    if copy_manuscript:
        for name in PARENT_TABLE_NAMES:
            source = output_tables / name
            atomic_write_text(
                manuscript_tables / name,
                source.read_text(encoding="utf-8"),
            )

    evidence_after, evidence_count_after = stable_tree_digest(root, protected)
    if evidence_count_after != evidence_count or evidence_after != evidence_before:
        raise RuntimeError("protected raw/summary evidence changed during repair")

    table_hashes = {
        name: sha256(output_tables / name)
        for name in ALL_REPAIRED_TABLE_NAMES
        if (output_tables / name).exists()
    }
    metadata_path = run_dir / "metadata" / "manuscript_table_rendering.json"
    (
        previous_first_commit,
        previous_worked_example_split,
    ) = _load_previous_rendering_provenance(
        metadata_path,
        run_hash=run_hash,
        experiment_id=experiment_id,
    )
    rendering_metadata = {
        "schema_version": 1,
        "kind": "manuscript_table_rendering_repair",
        "parent_run_hash": run_hash,
        "route_experiment_id": experiment_id,
        "script": "scripts/repair_manuscript_table_rendering.py",
        "script_sha256": sha256(Path(__file__).resolve()),
        "first_applied_git_commit": previous_first_commit or git_commit(root),
        "protected_evidence_file_count": evidence_count,
        "protected_evidence_tree_sha256": evidence_before,
        "raw_and_summary_evidence_unchanged": True,
        "table_sha256": table_hashes,
    }

    if previous_worked_example_split is not None:
        rendering_metadata["worked_example_split"] = (
            previous_worked_example_split
        )

    atomic_write_text(
        metadata_path,
        json.dumps(rendering_metadata, indent=2, sort_keys=True) + "\n",
    )

    manifest_path = run_dir / "metadata" / "certified-output-checksums.csv"
    manifest_targets = [output_tables / name for name in PARENT_TABLE_NAMES]
    manifest_targets.append(metadata_path)
    update_checksum_manifest(manifest_path, root, manifest_targets)

    if copy_manuscript:
        for name in ALL_REPAIRED_TABLE_NAMES:
            source = output_tables / name
            destination = manuscript_tables / name
            if source.exists() and sha256(source) != sha256(destination):
                raise RuntimeError(f"manuscript copy differs: {name}")

    return table_hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--run-hash", required=True)
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--no-copy", action="store_true")
    args = parser.parse_args()
    hashes = repair_run_tables(
        repo_root=args.repo,
        run_hash=args.run_hash,
        experiment_id=args.experiment_id,
        copy_manuscript=not args.no_copy,
    )
    print(f"[rendering-repair] run={args.run_hash}")
    for name, digest in sorted(hashes.items()):
        print(f"[rendering-repair] {name} sha256={digest}")
    print("[rendering-repair] protected raw and summary evidence unchanged")


if __name__ == "__main__":
    main()
