import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from make_false_adequacy_rates import derive_false_adequacy_rows


def test_false_adequacy_rates_are_derived_from_null_counts(tmp_path):
    oc = tmp_path / "operating_characteristics.csv"
    rows = [
        {
            "scenario": "injected_residual",
            "generator": "endpoint_injected",
            "M": "1200",
            "null_n": "75",
            "beta_inj": "-60.0",
            "run_hash": "abc123",
        },
        {
            "scenario": "opposite_direction",
            "generator": "endpoint_injected_positive",
            "M": "1200",
            "null_n": "60",
            "beta_inj": "60.0",
            "run_hash": "abc123",
        },
    ]

    with oc.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    derived = derive_false_adequacy_rows(oc)
    by_scenario = {row["scenario"]: row for row in derived}

    assert by_scenario["injected_residual"]["false_adequacy_n"] == "75"
    assert by_scenario["injected_residual"]["false_adequacy_rate"] == "0.062500"
    assert by_scenario["opposite_direction"]["false_adequacy_n"] == "60"
    assert by_scenario["opposite_direction"]["false_adequacy_rate"] == "0.050000"
