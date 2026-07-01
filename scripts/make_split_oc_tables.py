#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union


DEFAULT_FROZEN_RUN_HASH = "9d2658d6d147de10"

NumberLike = Union[str, int, float, Decimal]
ColumnSpec = Tuple[str, str, str]


GENERATOR_LABELS = {
    "forward_only": "Forward-only null",
    "endpoint_injected": "Negative endpoint-level residual",
    "forward_only_with_leak": "Forward-only null with temporal leak",
    "forward_only_monotone_selection": "Forward-only null with monotone selection",
    "forward_only_collider_selection": "Forward-only null with endpoint-by-delay collider",
    "adversarial_forward_only": "Adversarial forward-only null",
    "endpoint_injected_positive": "Positive endpoint-level residual",
}


OUTCOME_COUNT_KEYS = {
    "support_rate": "support_n",
    "selection_limited_rate": "selection_limited_n",
    "diagnostic_failure_rate": "diagnostic_failure_n",
    "null_rate": "null_n",
    "opposite_direction_rate": "opposite_direction_n",
    "inconclusive_rate": "inconclusive_n",
}


DESIGN_COLUMNS: List[ColumnSpec] = [
    ("scenario", "Scenario", "text"),
    ("generator", "Generator", "generator"),
    ("trials_per_bin", "$n$/bin", "int"),
    ("beta_min_med", "$\\beta_{\\min}$", "num"),
    ("beta_inj", "$\\beta^{\\mathrm{inj}}$", "num"),
    ("mean_beta_hat", "Mean $\\widehat{\\beta}_\\tau$", "num"),
    ("median_ucb", "Med. UCB", "num"),
]


OUTCOME_COLUMNS: List[ColumnSpec] = [
    ("scenario", "Scenario", "text"),
    ("rand_pass_rate", "rand. pass", "rate"),
    ("materiality_pass_rate", "resol. pass", "rate"),
    ("retention_fire_rate", "reten. fire", "rate"),
    ("leak_fire_rate", "leak fire", "rate"),
    ("gate_pass_rate", "gate pass", "rate"),
    ("collider_fire_rate", "collider fire", "rate"),
    ("support_rate", "support", "count_rate"),
    ("selection_limited_rate", "sel.-lim.", "count_rate"),
    ("diagnostic_failure_rate", "diag. fail", "count_rate"),
    ("null_rate", "null", "count_rate"),
    ("opposite_direction_rate", "opp. dir.", "count_rate"),
]


def latex_escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("#", "\\#")
    )


def as_decimal(value: NumberLike) -> Decimal:
    try:
        dec = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Cannot parse numeric value: {value!r}") from exc

    if not dec.is_finite():
        raise ValueError(f"Numeric value is not finite: {value!r}")

    return dec


def round_half_up_str(value: NumberLike, places: int) -> str:
    dec = as_decimal(value)
    quant = Decimal("1").scaleb(-places)
    rounded = dec.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{rounded:.{places}f}"


def fmt_num(value: str) -> str:
    x = as_decimal(value)

    if x == 0:
        return "0"

    ax = abs(x)
    if Decimal("0.0001") <= ax < Decimal("1"):
        return round_half_up_str(x, 3)

    if ax >= Decimal("1"):
        return round_half_up_str(x, 1)

    return f"{float(x):.2e}"


def fmt_rate(value: str) -> str:
    return round_half_up_str(value, 3)


def fmt_int(value: str) -> str:
    return str(int(as_decimal(value)))


def fmt_caption_number(value: str) -> str:
    """Format a scalar caption number; leave non-scalar strings escaped."""
    try:
        x = as_decimal(value)
    except ValueError:
        return latex_escape(str(value))

    if x == x.to_integral_value():
        return str(int(x))

    return str(x.normalize())


def fmt_delay_support(value: str) -> str:
    """Format assigned-delay support for captions.

    The benchmark CSV may store support as '0-20'. The SI caption should display
    this as '[0,20]' inside math mode. This function also tolerates '[0,20]',
    '0,20', and scalar legacy encodings such as '20'.
    """
    raw = str(value).strip()
    compact = raw.replace(" ", "")

    if compact.startswith("[") and compact.endswith("]"):
        return compact

    if "-" in compact:
        left, right = compact.split("-", 1)
        return f"[{fmt_caption_number(left)},{fmt_caption_number(right)}]"

    if "," in compact:
        left, right = compact.split(",", 1)
        return f"[{fmt_caption_number(left)},{fmt_caption_number(right)}]"

    return f"[0,{fmt_caption_number(compact)}]"


def fmt_count_rate(row: Dict[str, str], rate_key: str) -> str:
    count_key = OUTCOME_COUNT_KEYS[rate_key]

    if count_key not in row:
        raise KeyError(f"Missing count column {count_key!r} for {rate_key!r}")

    if "M" not in row:
        raise KeyError("Missing required column 'M' for count/rate formatting")

    m = int(as_decimal(row["M"]))
    if m <= 0:
        raise ValueError(f"M must be positive for count/rate formatting; got {m}")

    raw_count = row[count_key]
    if raw_count == "":
        rate = as_decimal(row[rate_key])
        count = int((rate * Decimal(m)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        count = int(as_decimal(raw_count))

    display_rate = (Decimal(count) / Decimal(m)).quantize(
        Decimal("0.001"),
        rounding=ROUND_HALF_UP,
    )
    return f"{count}/{m} ({display_rate})"


def fmt_cell(row: Dict[str, str], key: str, kind: str) -> str:
    if key not in row:
        raise KeyError(f"Missing required column {key!r}")

    if kind == "text":
        return latex_escape(row[key])

    if kind == "generator":
        return latex_escape(GENERATOR_LABELS.get(row[key], row[key]))

    if kind == "int":
        return fmt_int(row[key])

    if kind == "num":
        return fmt_num(row[key])

    if kind == "rate":
        return fmt_rate(row[key])

    if kind == "count_rate":
        return fmt_count_rate(row, key)

    raise ValueError(f"Unknown column kind: {kind}")


def read_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        raise RuntimeError(f"No rows found in {csv_path}")

    return rows


def required_columns(columns: List[ColumnSpec]) -> Set[str]:
    required = {key for key, _, _ in columns}
    required.add("M")

    for key, _, kind in columns:
        if kind == "count_rate":
            required.add(OUTCOME_COUNT_KEYS[key])

    return required


def validate_rows(rows: List[Dict[str, str]], columns: List[ColumnSpec]) -> None:
    required = required_columns(columns)

    for metadata_key in ["P", "delay_support_ms", "sigma_resid"]:
        required.add(metadata_key)

    for idx, row in enumerate(rows, start=1):
        missing = sorted(k for k in required if k not in row)
        if missing:
            raise KeyError(f"Row {idx} is missing required columns: {missing}")


def common_value(rows: List[Dict[str, str]], key: str) -> str:
    values = []
    for row in rows:
        if key not in row:
            raise KeyError(f"Missing required metadata column {key!r}")
        values.append(row[key])

    unique = sorted(set(values))
    if len(unique) != 1:
        raise ValueError(f"Expected one common value for {key!r}, found {unique}")

    return unique[0]


def provenance_header(run_hash: str) -> List[str]:
    return [
        (
            "% Machine-generated by scripts/run_all.py / "
            f"scripts/make_split_oc_tables.py; run_hash={run_hash}; "
            "do not edit by hand."
        ),
        f"% Source: outputs/{run_hash}/summary/operating_characteristics.csv",
    ]


def write_table(
    rows: List[Dict[str, str]],
    out_path: Path,
    run_hash: str,
    columns: List[ColumnSpec],
    caption: str,
    label: str,
    tabular_spec: str,
    fontsize: str = "\\scriptsize",
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.extend(provenance_header(run_hash))
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{" + caption + "}")
    lines.append("\\label{" + label + "}")
    lines.append(fontsize)
    lines.append("\\setlength{\\tabcolsep}{3pt}")
    lines.append("\\begin{tabular}{" + tabular_spec + "}")
    lines.append("\\toprule")
    lines.append(" & ".join(head for _, head, _ in columns) + " \\\\")
    lines.append("\\midrule")

    for row in rows:
        cells = [fmt_cell(row, key, kind) for key, _, kind in columns]
        lines.append(" & ".join(cells) + " \\\\")

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_split_tables(
    csv_path: Path,
    outdir: Path,
    run_hash: Optional[str] = None,
) -> None:
    rows = read_rows(csv_path)
    actual_hash = run_hash or rows[0].get("run_hash") or DEFAULT_FROZEN_RUN_HASH

    validate_rows(rows, DESIGN_COLUMNS)
    validate_rows(rows, OUTCOME_COLUMNS)

    outdir.mkdir(parents=True, exist_ok=True)

    m = fmt_caption_number(common_value(rows, "M"))
    p = fmt_caption_number(common_value(rows, "P"))
    support_text = fmt_delay_support(common_value(rows, "delay_support_ms"))
    sigma_resid = fmt_caption_number(common_value(rows, "sigma_resid"))

    design_caption = (
        "Benchmark design and slope-resolution summaries for the locked Level II-A "
        "pipeline on simulated data. Rates and decision outcomes are reported separately "
        f"in Table~\\ref{{tab:si-oc-outcomes}}. Run hash \\texttt{{{actual_hash}}}; "
        f"$M={m}$ datasets per scenario; $P={p}$ participants; assigned-delay support "
        f"${support_text}$ ms; "
        f"$\\sigma_{{\\mathrm{{resid}}}}={sigma_resid}\\,\\mu$V is the nominal "
        "generator residual-noise scale; the displayed $\\beta_{\\min}$ is "
        "recomputed for each scenario from the label-blind realised residual "
        "scale and retained-trial yield through the locked materiality formula, "
        "so its variation across rows is expected; not human EEG."
    )

    outcome_caption = (
        "Diagnostic rates and mutually exclusive decision outcomes for the locked Level II-A "
        "pipeline on simulated data. Design constants and slope summaries are reported in "
        f"Table~\\ref{{tab:si-oc-design}}. Run hash \\texttt{{{actual_hash}}}; all outcome "
        f"cells are exact counts over $M={m}$ Monte Carlo datasets with rates in parentheses; "
        "not human EEG."
    )

    write_table(
        rows=rows,
        out_path=outdir / "operating_characteristics_design.tex",
        run_hash=actual_hash,
        columns=DESIGN_COLUMNS,
        caption=design_caption,
        label="tab:si-oc-design",
        tabular_spec="llrrrrr",
        fontsize="\\footnotesize",
    )

    write_table(
        rows=rows,
        out_path=outdir / "operating_characteristics_outcomes.tex",
        run_hash=actual_hash,
        columns=OUTCOME_COLUMNS,
        caption=outcome_caption,
        label="tab:si-oc-outcomes",
        tabular_spec="lrrrrrrlllll",
        fontsize="\\scriptsize",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-hash", required=True)
    ap.add_argument("--outdir", default="outputs")
    args = ap.parse_args()

    run_dir = Path(args.outdir) / args.run_hash
    csv_path = run_dir / "summary" / "operating_characteristics.csv"
    table_dir = run_dir / "tables"

    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    write_split_tables(csv_path=csv_path, outdir=table_dir, run_hash=args.run_hash)
    print(f"[split-oc] wrote {table_dir / 'operating_characteristics_design.tex'}")
    print(f"[split-oc] wrote {table_dir / 'operating_characteristics_outcomes.tex'}")


if __name__ == "__main__":
    main()