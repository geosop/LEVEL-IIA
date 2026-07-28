#!/usr/bin/env python3
"""Certify the validity-matched null-generator/inference-route comparison.

The auxiliary experiment is parented to a frozen seven-scenario benchmark run.
It does not alter or regenerate any parent-run raw file. Three valid cells are
run:

1. clean generator, assignment-isolation route;
2. the identical clean datasets, sequential e-value route;
3. adversarial carryover generator, sequential e-value route.

The fourth nominal factorial cell is prohibited because the full adversarial
carryover generator does not satisfy frozen-endpoint-array invariance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cri_leveliia import benchmarks as B  # noqa: E402
from cri_leveliia import dgp  # noqa: E402
from cri_leveliia import metadata as MD  # noqa: E402
from make_false_adequacy_rates import _wilson_interval  # noqa: E402

DEFAULT_MANIFEST = ROOT / "configs" / "route_matched_null_comparison.yaml"
CELL_ORDER = [
    "clean_assignment_isolation",
    "clean_sequential_evalue",
    "adversarial_sequential_evalue",
]
OUTCOME_MAP = {
    "supported": "support",
    "forward_only_adequate": "adequate",
    "opposite_direction": "opposite",
    "selection_limited": "selection_limited",
    "diagnostic_failure": "diagnostic_failure",
    "inconclusive": "inconclusive",
}


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _atomic_write_dataframe(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False, lineterminator="\n")
    tmp.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolved_manifest(manifest: dict, m_override: int | None = None) -> dict:
    resolved = json.loads(json.dumps(manifest))
    if int(resolved.get("schema_version", 0)) != 1:
        raise ValueError("route-matched manifest schema_version must equal 1")
    if resolved.get("kind") != "route_matched_null_comparison":
        raise ValueError("manifest kind must be route_matched_null_comparison")
    if m_override is not None:
        resolved["M"] = int(m_override)
    if int(resolved["M"]) <= 0:
        raise ValueError("M must be positive")
    if not (0.0 < float(resolved["confidence_level"]) < 1.0):
        raise ValueError("confidence_level must lie in (0, 1)")

    cells = resolved.get("cells", [])
    observed = [str(cell.get("id")) for cell in cells]
    if observed != CELL_ORDER:
        raise ValueError(f"cells must be ordered exactly as {CELL_ORDER}")
    expected = {
        "clean_assignment_isolation": ("clean", "assignment_isolation"),
        "clean_sequential_evalue": ("clean", "sequential_evalue"),
        "adversarial_sequential_evalue": ("adversarial", "sequential_evalue"),
    }
    for cell in cells:
        pair = (cell.get("generator_family"), cell.get("inference_route"))
        if pair != expected[cell["id"]]:
            raise ValueError(f"invalid cell declaration: {cell}")
    if any(
        cell.get("generator_family") == "adversarial"
        and cell.get("inference_route") == "assignment_isolation"
        for cell in cells
    ):
        raise ValueError("the adversarial assignment-isolation cell is prohibited")

    contrast_ids = [item["id"] for item in resolved["predeclared_contrasts"]]
    if contrast_ids != [
        "clean_sequential_minus_clean_assignment",
        "adversarial_sequential_minus_clean_sequential",
    ]:
        raise ValueError("unexpected predeclared contrast set")
    if int(resolved["paired_bootstrap"]["replicates"]) < 1000:
        raise ValueError("paired bootstrap must use at least 1000 replicates")
    return resolved


def _source_paths(manifest_path: Path, resolved: dict) -> list[Path]:
    names = {
        resolved["clean_base_config"],
        resolved["adversarial_base_config"],
        resolved["sequential_settings_source"],
    }
    paths = [
        *MD.SOURCE_PATHS,
        Path(__file__).resolve(),
        manifest_path.resolve(),
        *[(ROOT / "configs" / name).resolve() for name in names],
    ]
    return sorted(set(paths), key=lambda p: p.as_posix())


def _parent_metadata(run_dir: Path, run_hash: str) -> dict:
    path = run_dir / "metadata" / "run_metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"parent run metadata is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("run_hash") != run_hash:
        raise ValueError("parent metadata run_hash does not match its directory")
    current_source = MD.source_fingerprint()
    if data.get("source_fingerprint") != current_source:
        raise ValueError(
            "current executable-source fingerprint differs from the parent run: "
            f"parent={data.get('source_fingerprint')} current={current_source}"
        )
    current_lock = MD.dependency_lock_sha256()
    if data.get("dependency_lock_sha256") != current_lock:
        raise ValueError(
            "current dependency lock differs from the parent run: "
            f"parent={data.get('dependency_lock_sha256')} current={current_lock}"
        )
    return data


def _build_cell_configs(resolved: dict) -> dict[str, dict]:
    clean_base = _load_yaml(ROOT / "configs" / resolved["clean_base_config"])
    adversarial = _load_yaml(
        ROOT / "configs" / resolved["adversarial_base_config"]
    )
    sequential_source = _load_yaml(
        ROOT / "configs" / resolved["sequential_settings_source"]
    )

    clean_base.update(resolved.get("clean_overrides", {}))
    clean_base["base_seed"] = int(resolved["clean_base_seed"])
    clean_base["sequential_evalue"] = json.loads(
        json.dumps(sequential_source["sequential_evalue"])
    )

    clean_ai = json.loads(json.dumps(clean_base))
    clean_ai.update(
        {
            "name": "route_match_clean_assignment_isolation",
            "generator": "route_match_clean_forward_only",
            "inference_route": "assignment_isolation",
        }
    )
    clean_seq = json.loads(json.dumps(clean_base))
    clean_seq.update(
        {
            "name": "route_match_clean_sequential_evalue",
            "generator": "route_match_clean_forward_only",
            "inference_route": "sequential_evalue",
        }
    )

    adversarial["base_seed"] = int(resolved["adversarial_base_seed"])
    adversarial.update(
        {
            "name": "route_match_adversarial_sequential_evalue",
            "generator": "route_match_adversarial_forward_only",
            "inference_route": "sequential_evalue",
        }
    )

    ignored = {"name", "generator", "inference_route"}
    ai_generator = {k: v for k, v in clean_ai.items() if k not in ignored}
    seq_generator = {k: v for k, v in clean_seq.items() if k not in ignored}
    if ai_generator != seq_generator:
        raise ValueError("the two clean cells differ in generator fields")
    if clean_ai.get("retention_timing") != "pre_assignment":
        raise ValueError("clean route comparison requires pre-assignment retention")
    if clean_seq.get("retention_timing") != "pre_assignment":
        raise ValueError("clean sequential cell requires pre-assignment retention")
    if adversarial.get("retention_timing") != "pre_assignment":
        raise ValueError("adversarial sequential cell requires pre-assignment retention")
    if float(adversarial.get("coef_carryover", 0.0)) == 0.0:
        raise ValueError("the full adversarial generator must retain carryover")

    return {
        "clean_assignment_isolation": clean_ai,
        "clean_sequential_evalue": clean_seq,
        "adversarial_sequential_evalue": adversarial,
    }


def _dataset_digest(ds: dgp.Dataset) -> str:
    digest = hashlib.sha256()
    arrays = [
        ds.participant,
        ds.e,
        ds.prev_e,
        ds.hazard,
        ds.tau_prev,
        ds.tau_assigned,
        ds.tau_delivered,
        ds.A_pre,
        ds.H_pre,
        ds.S,
        ds.bin_index,
        ds.trial_index,
        ds.grid_s,
        ds.leak_probe,
    ]
    for array in arrays:
        arr = np.ascontiguousarray(array)
        digest.update(str(arr.dtype).encode("ascii"))
        digest.update(np.asarray(arr.shape, dtype=np.int64).tobytes())
        digest.update(arr.tobytes())
    digest.update(json.dumps(ds.meta, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def _clean_dataset_family_digest(configs: dict[str, dict], m: int) -> str:
    left = configs["clean_assignment_isolation"]
    right = configs["clean_sequential_evalue"]
    family = hashlib.sha256()
    for replicate in range(m):
        seed = B._replicate_seed(left["base_seed"], replicate)
        ds_left = dgp.generate_dataset(np.random.default_rng(seed), left)
        ds_right = dgp.generate_dataset(np.random.default_rng(seed), right)
        left_digest = _dataset_digest(ds_left)
        right_digest = _dataset_digest(ds_right)
        if left_digest != right_digest:
            raise ValueError(
                f"clean datasets differ between routes at replicate {replicate}"
            )
        family.update(replicate.to_bytes(8, "little", signed=False))
        family.update(bytes.fromhex(left_digest))
    return family.hexdigest()


def _validate_raw(path: Path, m: int, cell_id: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {
        "replicate",
        "inference_route",
        "route_valid",
        "decision",
        "component_disagreement",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    if len(df) != m:
        raise ValueError(f"{path}: found {len(df)} rows, expected {m}")
    replicate = df["replicate"].astype(int)
    if set(replicate) != set(range(m)) or replicate.nunique() != m:
        raise ValueError(f"{path}: replicate identifiers must be 0 through {m - 1}")
    if not set(df["decision"]).issubset(set(B.DECISIONS)):
        raise ValueError(f"{path}: unknown decision value")
    expected_route = (
        "assignment_isolation"
        if cell_id == "clean_assignment_isolation"
        else "sequential_evalue"
    )
    if set(df["inference_route"]) != {expected_route}:
        raise ValueError(f"{path}: route does not match {cell_id}")
    if not df["route_valid"].astype(bool).all():
        reasons = sorted(set(df.loc[~df["route_valid"].astype(bool), "route_reason"]))
        raise ValueError(f"{path}: invalid route rows: {reasons}")
    return df.sort_values("replicate").reset_index(drop=True)


def _cell_summary(cell_id: str, df: pd.DataFrame, cfg: dict, m: int) -> dict:
    summary = B.summarise(df, cfg, cfg["name"], cfg["generator"])
    adequate_n = int(summary["null_n"])
    low, high = _wilson_interval(adequate_n, m)
    row = {
        "cell_id": cell_id,
        "generator_family": "adversarial" if cell_id.startswith("adversarial") else "clean",
        "inference_route": cfg["inference_route"],
        "M": m,
        "adequate_n": adequate_n,
        "adequate_rate": adequate_n / m,
        "adequate_wilson95_low": low,
        "adequate_wilson95_high": high,
        "component_disagreement_n": int(df["component_disagreement"].astype(bool).sum()),
        "component_disagreement_rate": float(df["component_disagreement"].astype(bool).mean()),
        "base_seed": int(cfg["base_seed"]),
    }
    for decision, label in OUTCOME_MAP.items():
        n = int((df["decision"] == decision).sum())
        row[f"{label}_n"] = n
        row[f"{label}_rate"] = n / m
    if sum(row[f"{label}_n"] for label in OUTCOME_MAP.values()) != m:
        raise ValueError(f"{cell_id}: mutually exclusive outcomes do not sum to M")
    return row


def _paired_bootstrap_interval(
    differences: np.ndarray,
    confidence_level: float,
    replicates: int,
    seed: int,
) -> tuple[float, float]:
    differences = np.asarray(differences, dtype=float)
    rng = np.random.default_rng(seed)
    n = differences.size
    estimates = np.empty(replicates, dtype=float)
    chunk = 1000
    written = 0
    while written < replicates:
        take = min(chunk, replicates - written)
        indices = rng.integers(0, n, size=(take, n))
        estimates[written : written + take] = differences[indices].mean(axis=1)
        written += take
    alpha = 1.0 - confidence_level
    return (
        float(np.quantile(estimates, alpha / 2.0)),
        float(np.quantile(estimates, 1.0 - alpha / 2.0)),
    )


def _newcombe_difference_interval(
    k1: int,
    n1: int,
    k0: int,
    n0: int,
) -> tuple[float, float]:
    p1 = k1 / n1
    p0 = k0 / n0
    l1, u1 = _wilson_interval(k1, n1)
    l0, u0 = _wilson_interval(k0, n0)
    diff = p1 - p0
    lower = diff - np.sqrt((p1 - l1) ** 2 + (u0 - p0) ** 2)
    upper = diff + np.sqrt((u1 - p1) ** 2 + (p0 - l0) ** 2)
    return float(max(-1.0, lower)), float(min(1.0, upper))


def _contrast_rows(
    raw: dict[str, pd.DataFrame],
    resolved: dict,
) -> list[dict]:
    confidence = float(resolved["confidence_level"])
    boot = resolved["paired_bootstrap"]

    ai = (raw["clean_assignment_isolation"]["decision"] == "forward_only_adequate").to_numpy(int)
    clean_seq = (raw["clean_sequential_evalue"]["decision"] == "forward_only_adequate").to_numpy(int)
    adv_seq = (raw["adversarial_sequential_evalue"]["decision"] == "forward_only_adequate").to_numpy(int)

    paired_diff = clean_seq - ai
    paired_low, paired_high = _paired_bootstrap_interval(
        paired_diff,
        confidence,
        int(boot["replicates"]),
        int(boot["seed"]),
    )
    ai_only = int(np.sum((ai == 1) & (clean_seq == 0)))
    seq_only = int(np.sum((ai == 0) & (clean_seq == 1)))
    discordant = ai_only + seq_only
    mcnemar_p = (
        1.0
        if discordant == 0
        else float(stats.binomtest(seq_only, discordant, 0.5).pvalue)
    )

    clean_n = int(clean_seq.sum())
    adv_n = int(adv_seq.sum())
    independent_low, independent_high = _newcombe_difference_interval(
        adv_n,
        adv_seq.size,
        clean_n,
        clean_seq.size,
    )
    table = np.array(
        [
            [adv_n, adv_seq.size - adv_n],
            [clean_n, clean_seq.size - clean_n],
        ]
    )
    fisher_p = float(stats.fisher_exact(table, alternative="two-sided").pvalue)

    return [
        {
            "contrast_id": "clean_sequential_minus_clean_assignment",
            "comparison": "paired_identical_clean_datasets",
            "estimate": float(paired_diff.mean()),
            "ci95_low": paired_low,
            "ci95_high": paired_high,
            "test": "exact_mcnemar_binomial",
            "p_value": mcnemar_p,
            "discordant_assignment_only": ai_only,
            "discordant_sequential_only": seq_only,
            "M_left": int(clean_seq.size),
            "M_right": int(ai.size),
        },
        {
            "contrast_id": "adversarial_sequential_minus_clean_sequential",
            "comparison": "independent_generators_common_sequential_route",
            "estimate": float(adv_seq.mean() - clean_seq.mean()),
            "ci95_low": independent_low,
            "ci95_high": independent_high,
            "test": "two_sided_fisher_exact",
            "p_value": fisher_p,
            "discordant_assignment_only": np.nan,
            "discordant_sequential_only": np.nan,
            "M_left": int(adv_seq.size),
            "M_right": int(clean_seq.size),
        },
    ]


def _format_count(n: int, m: int) -> str:
    return f"{n}/{m} ({n / m:.3f})"


def _render_table(
    summary: pd.DataFrame,
    contrasts: pd.DataFrame,
    run_hash: str,
    experiment_id: str,
) -> str:
    labels = {
        "clean_assignment_isolation": "Clean & assignment isolation",
        "clean_sequential_evalue": "Clean & sequential e-value",
        "adversarial_sequential_evalue": "Adversarial & sequential e-value",
    }
    row_end = r" \\"
    lines = [
        "% Machine-generated by scripts/make_route_matched_null_comparison.py; do not edit.",
        f"% parent run={run_hash}; experiment_id={experiment_id}",
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Validity-matched null-generator and inference-route comparison. The two clean rows use identical generated datasets replicate by replicate. The full adversarial carryover generator is evaluated only under the sequential e-value route because assignment isolation requires endpoint-array invariance. Intervals beside adequacy rates are descriptive Wilson intervals.}",
        "\\label{tab:si-route-matched-null-comparison}",
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{3pt}",
        "\\begin{tabular}{lrrrrrrr}",
        "\\toprule",
        "Cell & Adequate & Support & Opposite & Inconclusive & Selection-limited & Diagnostic failure & Component disagreement" + row_end,
        "\\midrule",
    ]
    for cell_id in CELL_ORDER:
        row = summary.loc[summary["cell_id"] == cell_id].iloc[0]
        lines.append(
            " & ".join(
                [
                    labels[cell_id],
                    _format_count(int(row.adequate_n), int(row.M)),
                    _format_count(int(row.support_n), int(row.M)),
                    _format_count(int(row.opposite_n), int(row.M)),
                    _format_count(int(row.inconclusive_n), int(row.M)),
                    _format_count(int(row.selection_limited_n), int(row.M)),
                    _format_count(int(row.diagnostic_failure_n), int(row.M)),
                    _format_count(int(row.component_disagreement_n), int(row.M)),
                ]
            )
            + row_end
        )
    lines.extend(
        [
            "\\midrule",
            r"Contrast & Estimate & 95\% interval & \multicolumn{5}{l}{Interpretation}" + row_end,
        ]
    )
    route = contrasts.loc[
        contrasts["contrast_id"] == "clean_sequential_minus_clean_assignment"
    ].iloc[0]
    generator = contrasts.loc[
        contrasts["contrast_id"] == "adversarial_sequential_minus_clean_sequential"
    ].iloc[0]
    lines.append(
        "Clean sequential $-$ clean assignment"
        f" & {route.estimate:+.3f} & [{route.ci95_low:+.3f}, {route.ci95_high:+.3f}]"
        r" & \multicolumn{5}{l}{Paired route contrast on identical clean datasets}"
        + row_end
    )
    lines.append(
        "Adversarial sequential $-$ clean sequential"
        f" & {generator.estimate:+.3f} & [{generator.ci95_low:+.3f}, {generator.ci95_high:+.3f}]"
        r" & \multicolumn{5}{l}{Generator contrast under the common sequential route}"
        + row_end
    )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}"])
    return "\n".join(lines) + "\n"
def run_experiment(
    run_hash: str,
    out_root: Path,
    manifest_path: Path,
    m_override: int | None,
    resume: bool,
    copy_table: bool,
) -> str:
    manifest = _load_yaml(manifest_path)
    resolved = _resolved_manifest(manifest, m_override)
    if resolved["parent_run_hash"] != run_hash:
        raise ValueError("manifest parent_run_hash does not match --run-hash")
    m = int(resolved["M"])

    run_dir = out_root / run_hash
    if not run_dir.exists():
        raise FileNotFoundError(f"parent run directory does not exist: {run_dir}")
    parent = _parent_metadata(run_dir, run_hash)
    configs = _build_cell_configs(resolved)

    payload = {
        "parent_run_hash": run_hash,
        "kind": resolved["kind"],
        "resolved_manifest": resolved,
        "resolved_cell_configs": configs,
        "seed_family": "route_match_v1",
        "M": m,
    }
    experiment_id = MD.compute_experiment_id(
        "route_match",
        payload,
        _source_paths(manifest_path, resolved),
    )
    experiment_dir = run_dir / "auxiliary" / experiment_id
    completed = experiment_dir / "metadata.json"
    start_marker_path = experiment_dir / "start.json"
    if completed.exists():
        raise FileExistsError(f"completed experiment already exists: {experiment_dir}")
    if experiment_dir.exists() and not resume:
        raise FileExistsError(
            f"incomplete experiment exists: {experiment_dir}; use --resume"
        )
    if resume and not experiment_dir.exists():
        raise FileNotFoundError(f"cannot resume absent experiment: {experiment_dir}")

    if resume:
        if not start_marker_path.exists():
            raise FileNotFoundError(
                f"resume marker is missing from incomplete experiment: {start_marker_path}"
            )
        start_marker = json.loads(start_marker_path.read_text(encoding="utf-8"))
        if start_marker.get("experiment_id") != experiment_id:
            raise ValueError("resume marker experiment ID mismatch")
        if start_marker.get("generating_git_commit") != MD.git_commit():
            raise ValueError("repository commit changed since the experiment started")
        if start_marker.get("parent_source_fingerprint") != MD.source_fingerprint():
            raise ValueError("core source changed since the experiment started")
        if start_marker.get("experiment_source_fingerprint") != MD.source_fingerprint(
            _source_paths(manifest_path, resolved)
        ):
            raise ValueError("auxiliary experiment source changed since start")
    else:
        if MD.git_dirty():
            raise RuntimeError(
                "repository is dirty at experiment start; commit the implementation "
                "before running the certification experiment"
            )
        experiment_dir.mkdir(parents=True, exist_ok=False)
        start_marker = {
            "experiment_id": experiment_id,
            "parent_run_hash": run_hash,
            "generating_git_commit": MD.git_commit(),
            "parent_source_fingerprint": MD.source_fingerprint(),
            "experiment_source_fingerprint": MD.source_fingerprint(
                _source_paths(manifest_path, resolved)
            ),
            "dependency_lock_sha256": MD.dependency_lock_sha256(),
            "manifest_sha256": _sha256(manifest_path),
            "git_dirty_at_initial_start": False,
        }
        _atomic_write_text(
            start_marker_path,
            json.dumps(start_marker, indent=2, sort_keys=True) + "\n",
        )

    pointer = run_dir / "metadata" / "route_matched_null_comparison.json"
    if pointer.exists():
        raise FileExistsError(
            f"canonical route-matched pointer already exists: {pointer}"
        )

    (experiment_dir / "raw").mkdir(parents=True, exist_ok=True)
    clean_dataset_family_sha256 = _clean_dataset_family_digest(configs, m)

    raw: dict[str, pd.DataFrame] = {}
    raw_checksums: dict[str, str] = {}
    for cell_id in CELL_ORDER:
        cfg = configs[cell_id]
        raw_path = experiment_dir / "raw" / f"{cell_id}.csv"
        if raw_path.exists():
            if not resume:
                raise FileExistsError(f"raw cell already exists: {raw_path}")
            df = _validate_raw(raw_path, m, cell_id)
            print(f"[route-match] resume {cell_id}", flush=True)
        else:
            print(f"[route-match] cell={cell_id} M={m}", flush=True)
            df = B.run_scenario(cfg, M=m, base_seed=cfg["base_seed"])
            _atomic_write_dataframe(raw_path, df)
            df = _validate_raw(raw_path, m, cell_id)
        raw[cell_id] = df
        raw_checksums[raw_path.name] = _sha256(raw_path)

    summary = pd.DataFrame(
        [_cell_summary(cell_id, raw[cell_id], configs[cell_id], m) for cell_id in CELL_ORDER]
    )
    contrasts = pd.DataFrame(_contrast_rows(raw, resolved))

    auxiliary_summary = experiment_dir / "summary" / "route_matched_null_comparison.csv"
    auxiliary_contrasts = experiment_dir / "summary" / "route_matched_null_contrasts.csv"
    canonical_summary = run_dir / "summary" / "route_matched_null_comparison.csv"
    canonical_contrasts = run_dir / "summary" / "route_matched_null_contrasts.csv"
    for path, frame in (
        (auxiliary_summary, summary),
        (auxiliary_contrasts, contrasts),
        (canonical_summary, summary),
        (canonical_contrasts, contrasts),
    ):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
        _atomic_write_dataframe(path, frame)

    table_text = _render_table(summary, contrasts, run_hash, experiment_id)
    auxiliary_table = experiment_dir / "tables" / "route_matched_null_comparison.tex"
    canonical_table = run_dir / "tables" / "route_matched_null_comparison.tex"
    for path in (auxiliary_table, canonical_table):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing table: {path}")
        _atomic_write_text(path, table_text)

    metadata = {
        "experiment_id": experiment_id,
        "kind": resolved["kind"],
        "parent_run_hash": run_hash,
        "parent_git_commit": parent["git_commit"],
        "parent_source_fingerprint": parent["source_fingerprint"],
        "parent_dependency_lock_sha256": parent["dependency_lock_sha256"],
        "generating_git_commit": start_marker["generating_git_commit"],
        "git_dirty_at_initial_start": start_marker["git_dirty_at_initial_start"],
        "manifest_path": manifest_path.relative_to(ROOT).as_posix(),
        "manifest_sha256": _sha256(manifest_path),
        "resolved_manifest": resolved,
        "resolved_cell_configs": configs,
        "experiment_source_fingerprint": MD.source_fingerprint(
            _source_paths(manifest_path, resolved)
        ),
        "clean_dataset_family_sha256": clean_dataset_family_sha256,
        "raw_checksums": raw_checksums,
        "summary": {
            "path": canonical_summary.relative_to(run_dir).as_posix(),
            "sha256": _sha256(canonical_summary),
        },
        "contrasts": {
            "path": canonical_contrasts.relative_to(run_dir).as_posix(),
            "sha256": _sha256(canonical_contrasts),
        },
        "table": {
            "path": canonical_table.relative_to(run_dir).as_posix(),
            "sha256": _sha256(canonical_table),
        },
    }
    _atomic_write_text(
        experiment_dir / "metadata.json",
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(
        pointer,
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    )

    if copy_table:
        destination = ROOT / "manuscript" / "tables" / canonical_table.name
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite manuscript table: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical_table, destination)

    print(f"[route-match] complete: {experiment_id}")
    return experiment_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-hash", required=True)
    parser.add_argument("--outdir", default=str(ROOT / "outputs"))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--M", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-copy", action="store_true")
    args = parser.parse_args()
    run_experiment(
        run_hash=args.run_hash,
        out_root=Path(args.outdir).resolve(),
        manifest_path=Path(args.manifest).resolve(),
        m_override=args.M,
        resume=args.resume,
        copy_table=not args.no_copy,
    )


if __name__ == "__main__":
    main()
