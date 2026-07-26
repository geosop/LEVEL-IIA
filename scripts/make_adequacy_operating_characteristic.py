#!/usr/bin/env python3
"""Run and render the route-specific v1.2 adequacy certification family."""

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
from cri_leveliia import metadata as MD  # noqa: E402
from make_false_adequacy_rates import _wilson_interval  # noqa: E402


DEFAULT_MANIFEST = ROOT / "configs" / "adequacy_certification.yaml"
OUTCOME_COLUMNS = [
    "support_n",
    "false_adequacy_n",
    "opposite_direction_n",
    "inconclusive_n",
    "selection_limited_n",
    "diagnostic_failure_n",
]


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _latest_run_hash(out_root: Path) -> str:
    path = out_root / "LATEST_RUN.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"No run hash supplied and {path} does not exist"
        )
    return path.read_text(encoding="utf-8").strip()


def _delta_tag(delta: float) -> str:
    return f"{float(delta):g}".replace(".", "p").replace("-", "m")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_dataframe(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_raw(path: Path, m: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "replicate" not in df.columns:
        raise ValueError(f"{path}: missing replicate column")
    if len(df) != m:
        raise ValueError(f"{path}: found {len(df)} rows, expected {m}")
    replicate = df["replicate"].astype(int)
    if replicate.nunique() != m:
        raise ValueError(f"{path}: replicate identifiers are not unique")
    if set(replicate) != set(range(m)):
        raise ValueError(f"{path}: replicate identifiers must be 0 through {m - 1}")
    if "decision" not in df.columns:
        raise ValueError(f"{path}: missing decision column")
    if not set(df["decision"]).issubset(set(B.DECISIONS)):
        raise ValueError(f"{path}: contains an unknown decision")
    return df


def _simultaneous_cp_upper(k: int, n: int, alpha_family: float, family_size: int) -> float:
    """One-sided Clopper-Pearson upper bound with Bonferroni family control."""
    if not (0 <= k <= n and n > 0):
        raise ValueError("expected 0 <= k <= n and n > 0")
    if not (0.0 < alpha_family < 1.0):
        raise ValueError("alpha_family must lie in (0, 1)")
    if family_size <= 0:
        raise ValueError("family_size must be positive")
    if k == n:
        return 1.0
    alpha_cell = alpha_family / family_size
    return float(stats.beta.ppf(1.0 - alpha_cell, k + 1, n - k))


def _resolved_manifest(manifest: dict, m_override: int | None) -> dict:
    resolved = json.loads(json.dumps(manifest))
    if int(resolved.get("schema_version", 0)) != 1:
        raise ValueError("adequacy manifest schema_version must equal 1")
    if m_override is not None:
        resolved["M"] = int(m_override)
    m = int(resolved["M"])
    if m <= 0:
        raise ValueError("M must be positive")

    deltas = [float(x) for x in resolved["deltas"]]
    if not deltas or any(x <= 0 for x in deltas):
        raise ValueError("deltas must be a nonempty positive grid")
    if deltas != sorted(set(deltas)):
        raise ValueError("deltas must be strictly increasing and unique")
    resolved["deltas"] = deltas

    directions = list(resolved["directions"])
    if directions != ["negative", "positive"]:
        raise ValueError("directions must be [negative, positive]")
    routes = resolved["routes"]
    if list(routes) != ["assignment_isolation", "sequential_evalue"]:
        raise ValueError(
            "routes must be ordered [assignment_isolation, sequential_evalue]"
        )
    resolved["family_size"] = len(deltas) * len(directions) * len(routes)
    if resolved.get("bound") != "one_sided_bonferroni_clopper_pearson":
        raise ValueError("unsupported simultaneous-bound convention")
    return resolved


def _source_paths(manifest_path: Path, resolved: dict) -> list[Path]:
    paths = [
        *MD.SOURCE_PATHS,
        Path(__file__).resolve(),
        manifest_path.resolve(),
    ]
    for route in resolved["routes"].values():
        for key in ("negative_config", "positive_config"):
            paths.append((ROOT / "configs" / route[key]).resolve())
    return sorted(set(paths), key=lambda p: p.as_posix())


def _parent_metadata(run_dir: Path, run_hash: str) -> dict:
    path = run_dir / "metadata" / "run_metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"parent run metadata is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("run_hash") != run_hash:
        raise ValueError("parent metadata run_hash does not match its directory")
    if data.get("source_fingerprint") != MD.source_fingerprint():
        raise ValueError(
            "current executable-source fingerprint differs from the parent run"
        )
    if data.get("dependency_lock_sha256") != MD.dependency_lock_sha256():
        raise ValueError(
            "current dependency lock differs from the parent run"
        )
    return data


def _cell_config(
    resolved: dict,
    route: str,
    direction: str,
    delta: float,
) -> dict:
    route_cfg = resolved["routes"][route]
    config_name = route_cfg[f"{direction}_config"]
    cfg = _load_yaml(ROOT / "configs" / config_name)
    if cfg.get("inference_route") != route:
        raise ValueError(
            f"{config_name}: expected inference_route={route}, "
            f"found {cfg.get('inference_route')}"
        )
    sign = -1.0 if direction == "negative" else 1.0
    cfg["name"] = (
        f"adequacy_{route}_{direction}_delta_{_delta_tag(delta)}"
    )
    cfg["generator"] = (
        f"{route}_{direction}_endpoint_injected_sweep"
    )
    cfg["beta_inj"] = sign * float(delta)
    return cfg


def _cell_raw_name(route: str, direction: str, delta: float) -> str:
    return (
        f"adequacy_{route}_{direction}_delta_{_delta_tag(delta)}.csv"
    )


def _summarise_cell(
    df: pd.DataFrame,
    cfg: dict,
    route: str,
    direction: str,
    delta: float,
    m: int,
    run_hash: str,
    adequacy_id: str,
    raw_relative: str,
    raw_sha256: str,
    alpha_family: float,
    family_size: int,
    p_fa_max: float,
) -> dict:
    summary = B.summarise(df, cfg, cfg["name"], cfg["generator"])
    fa_n = int(summary["null_n"])
    point_low, point_high = _wilson_interval(fa_n, m)
    simultaneous_upper = _simultaneous_cp_upper(
        fa_n,
        m,
        alpha_family,
        family_size,
    )
    beta_min = float(summary["beta_min_med"])
    row = {
        "adequacy_id": adequacy_id,
        "run_hash": run_hash,
        "route": route,
        "direction": direction,
        "beta_inj": float(summary["beta_inj"]),
        "delta": float(delta),
        "beta_min_med": beta_min,
        "delta_over_beta_min": float(delta / beta_min),
        "M": int(m),
        "false_adequacy_n": fa_n,
        "false_adequacy_rate": float(fa_n / m),
        "pointwise_wilson95_low": float(point_low),
        "pointwise_wilson95_high": float(point_high),
        "simultaneous_cp_upper": simultaneous_upper,
        "envelope_simultaneous_cp_upper": np.nan,
        "p_fa_max": float(p_fa_max),
        "envelope_pass": False,
        "certified_delta_direction": np.nan,
        "lower_grid_censored": False,
        "support_n": int(summary["support_n"]),
        "support_rate": float(summary["support_rate"]),
        "opposite_direction_n": int(summary["opposite_direction_n"]),
        "opposite_direction_rate": float(
            summary["opposite_direction_rate"]
        ),
        "inconclusive_n": int(summary["inconclusive_n"]),
        "inconclusive_rate": float(summary["inconclusive_rate"]),
        "selection_limited_n": int(summary["selection_limited_n"]),
        "selection_limited_rate": float(summary["selection_limited_rate"]),
        "diagnostic_failure_n": int(summary["diagnostic_failure_n"]),
        "diagnostic_failure_rate": float(
            summary["diagnostic_failure_rate"]
        ),
        "base_seed": int(cfg["base_seed"]),
        "source_raw_csv": raw_relative,
        "source_raw_sha256": raw_sha256,
    }
    if sum(int(row[col]) for col in OUTCOME_COLUMNS) != m:
        raise ValueError(
            f"{cfg['name']}: six mutually exclusive outcomes do not sum to M"
        )
    return row


def _apply_envelopes(rows: list[dict]) -> None:
    for route in sorted({row["route"] for row in rows}):
        for direction in ("negative", "positive"):
            group = sorted(
                [
                    row
                    for row in rows
                    if row["route"] == route
                    and row["direction"] == direction
                ],
                key=lambda row: row["delta"],
            )
            if not group:
                raise ValueError(f"missing adequacy group {route}/{direction}")

            certified = None
            for i, row in enumerate(group):
                envelope = max(
                    item["simultaneous_cp_upper"]
                    for item in group[i:]
                )
                row["envelope_simultaneous_cp_upper"] = float(envelope)
                row["envelope_pass"] = bool(
                    row["false_adequacy_rate"] <= row["p_fa_max"]
                    and envelope <= row["p_fa_max"]
                )
                if row["envelope_pass"] and certified is None:
                    certified = float(row["delta"])

            for row in group:
                row["certified_delta_direction"] = (
                    np.nan if certified is None else certified
                )
                row["lower_grid_censored"] = bool(
                    certified is not None
                    and certified == float(group[0]["delta"])
                )


def _format_rate(n: int, m: int) -> str:
    return f"{n}/{m} ({n / m:.3f})"


def _render_route_table(
    rows: list[dict],
    route: str,
    run_hash: str,
    adequacy_id: str,
) -> str:
    route_rows = [
        row for row in rows if row["route"] == route
    ]
    title = (
        "assignment-isolation"
        if route == "assignment_isolation"
        else "sequential e-value"
    )
    lines = [
        "% Machine-generated by scripts/make_adequacy_operating_characteristic.py; do not edit.",
        f"% parent run={run_hash}; adequacy_id={adequacy_id}; route={route}",
        "\\begin{table}[t]",
        "\\centering",
        (
            "\\caption{Route-specific adequacy operating characteristic for the "
            f"{title} route. Point intervals are descriptive Wilson intervals; "
            "certification uses the displayed one-sided, Bonferroni-adjusted "
            "Clopper--Pearson familywise upper-bound envelope.}"
        ),
        f"\\label{{tab:si-adequacy-{route.replace('_', '-')}}}",
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{3pt}",
        "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        (
            "Direction & $\\delta$ & False adequacy & Wilson 95\\% & "
            "simultaneous UCB & envelope UCB & verdict \\\\"
        ),
        "\\midrule",
    ]
    for row in route_rows:
        interval = (
            f"[{row['pointwise_wilson95_low']:.4f},"
            f"{row['pointwise_wilson95_high']:.4f}]"
        )
        verdict = "pass" if row["envelope_pass"] else "fail"
        lines.append(
            " & ".join(
                [
                    row["direction"],
                    f"{row['delta']:.1f}",
                    _format_rate(row["false_adequacy_n"], row["M"]),
                    interval,
                    f"{row['simultaneous_cp_upper']:.4f}",
                    f"{row['envelope_simultaneous_cp_upper']:.4f}",
                    verdict,
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}"])
    return "\n".join(lines) + "\n"


def _write_outputs(
    rows: list[dict],
    run_dir: Path,
    adequacy_dir: Path,
    run_hash: str,
    adequacy_id: str,
    resolved: dict,
    parent_metadata: dict,
    manifest_path: Path,
    copy_tables: bool,
) -> None:
    rows = sorted(
        rows,
        key=lambda row: (
            list(resolved["routes"]).index(row["route"]),
            resolved["directions"].index(row["direction"]),
            row["delta"],
        ),
    )
    summary_df = pd.DataFrame(rows)
    auxiliary_csv = adequacy_dir / "summary" / "adequacy_operating_characteristic.csv"
    canonical_csv = run_dir / "summary" / "adequacy_operating_characteristic.csv"
    _atomic_write_dataframe(auxiliary_csv, summary_df)
    _atomic_write_dataframe(canonical_csv, summary_df)

    table_paths = {}
    for route in resolved["routes"]:
        text = _render_route_table(
            rows,
            route,
            run_hash,
            adequacy_id,
        )
        name = f"adequacy_operating_characteristic_{route}.tex"
        auxiliary_table = adequacy_dir / "tables" / name
        canonical_table = run_dir / "tables" / name
        _atomic_write_text(auxiliary_table, text)
        _atomic_write_text(canonical_table, text)
        table_paths[route] = canonical_table

    raw_checksums = {
        path.name: _sha256(path)
        for path in sorted((adequacy_dir / "raw").glob("*.csv"))
    }
    metadata = {
        "adequacy_id": adequacy_id,
        "parent_run_hash": run_hash,
        "parent_git_commit": parent_metadata["git_commit"],
        "parent_source_fingerprint": parent_metadata["source_fingerprint"],
        "dependency_lock_sha256": MD.dependency_lock_sha256(),
        "manifest_path": manifest_path.relative_to(ROOT).as_posix(),
        "manifest_sha256": _sha256(manifest_path),
        "resolved_manifest": resolved,
        "raw_checksums": raw_checksums,
        "summary_sha256": _sha256(canonical_csv),
        "tables": {
            route: {
                "path": path.relative_to(run_dir).as_posix(),
                "sha256": _sha256(path),
            }
            for route, path in table_paths.items()
        },
    }
    metadata_path = adequacy_dir / "metadata.json"
    _atomic_write_text(
        metadata_path,
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(
        run_dir / "metadata" / "adequacy_certification.json",
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
    )

    if copy_tables:
        destination = ROOT / "manuscript" / "tables"
        destination.mkdir(parents=True, exist_ok=True)
        for path in table_paths.values():
            shutil.copy2(path, destination / path.name)


def run_certification(
    run_hash: str,
    out_root: Path,
    manifest_path: Path,
    m_override: int | None,
    resume: bool,
    copy_tables: bool,
) -> str:
    manifest = _load_yaml(manifest_path)
    resolved = _resolved_manifest(manifest, m_override)
    m = int(resolved["M"])
    run_dir = out_root / run_hash
    if not run_dir.exists():
        raise FileNotFoundError(f"parent run directory does not exist: {run_dir}")
    parent_metadata = _parent_metadata(run_dir, run_hash)

    payload = {
        "parent_run_hash": run_hash,
        "kind": "adequacy_certification",
        "resolved_manifest": resolved,
        "seed_family": "adequacy_v1.2",
        "M": m,
    }
    adequacy_id = MD.compute_experiment_id(
        "adequacy",
        payload,
        _source_paths(manifest_path, resolved),
    )
    adequacy_dir = run_dir / "auxiliary" / adequacy_id
    completed = adequacy_dir / "metadata.json"
    if completed.exists():
        raise FileExistsError(
            f"completed adequacy experiment already exists: {adequacy_dir}"
        )
    if adequacy_dir.exists() and not resume:
        raise FileExistsError(
            f"incomplete adequacy experiment exists: {adequacy_dir}; use --resume"
        )
    if resume and not adequacy_dir.exists():
        raise FileNotFoundError(
            f"cannot resume absent adequacy experiment: {adequacy_dir}"
        )
    (adequacy_dir / "raw").mkdir(parents=True, exist_ok=True)

    family_size = int(resolved["family_size"])
    alpha_family = float(resolved["alpha_family"])
    p_fa_max = float(resolved["p_fa_max"])
    rows = []

    for route in resolved["routes"]:
        for direction in resolved["directions"]:
            for delta in resolved["deltas"]:
                cfg = _cell_config(resolved, route, direction, delta)
                raw_name = _cell_raw_name(route, direction, delta)
                raw_path = adequacy_dir / "raw" / raw_name
                if raw_path.exists():
                    if not resume:
                        raise FileExistsError(
                            f"raw adequacy cell already exists: {raw_path}"
                        )
                    df = _validate_raw(raw_path, m)
                    print(f"[adequacy] resume {raw_name}", flush=True)
                else:
                    print(
                        f"[adequacy] route={route} direction={direction} "
                        f"delta={delta:g} M={m}",
                        flush=True,
                    )
                    df = B.run_scenario(
                        cfg,
                        M=m,
                        base_seed=cfg["base_seed"],
                    )
                    _atomic_write_dataframe(raw_path, df)
                    df = _validate_raw(raw_path, m)

                raw_relative = raw_path.relative_to(run_dir).as_posix()
                rows.append(
                    _summarise_cell(
                        df=df,
                        cfg=cfg,
                        route=route,
                        direction=direction,
                        delta=delta,
                        m=m,
                        run_hash=run_hash,
                        adequacy_id=adequacy_id,
                        raw_relative=raw_relative,
                        raw_sha256=_sha256(raw_path),
                        alpha_family=alpha_family,
                        family_size=family_size,
                        p_fa_max=p_fa_max,
                    )
                )

    if len(rows) != family_size:
        raise RuntimeError(
            f"generated {len(rows)} adequacy cells, expected {family_size}"
        )
    _apply_envelopes(rows)
    _write_outputs(
        rows=rows,
        run_dir=run_dir,
        adequacy_dir=adequacy_dir,
        run_hash=run_hash,
        adequacy_id=adequacy_id,
        resolved=resolved,
        parent_metadata=parent_metadata,
        manifest_path=manifest_path,
        copy_tables=copy_tables,
    )
    print(f"[adequacy] complete: {adequacy_id}")
    return adequacy_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-hash", default=None)
    parser.add_argument("--outdir", default=str(ROOT / "outputs"))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--M", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-copy", action="store_true")
    args = parser.parse_args()

    out_root = Path(args.outdir).resolve()
    run_hash = args.run_hash or _latest_run_hash(out_root)
    run_certification(
        run_hash=run_hash,
        out_root=out_root,
        manifest_path=Path(args.manifest).resolve(),
        m_override=args.M,
        resume=args.resume,
        copy_tables=not args.no_copy,
    )


if __name__ == "__main__":
    main()
