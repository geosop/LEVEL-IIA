from pathlib import Path
import sys

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from make_adequacy_operating_characteristic import (  # noqa: E402
    _apply_envelopes,
    _resolved_manifest,
    _simultaneous_cp_upper,
)


def test_v12_adequacy_manifest_declares_complete_40_cell_family():
    manifest = yaml.safe_load(
        (ROOT / "configs" / "adequacy_certification.yaml").read_text(
            encoding="utf-8"
        )
    )
    resolved = _resolved_manifest(manifest, None)
    assert resolved["M"] == 1200
    assert resolved["deltas"] == [
        5.0,
        10.0,
        15.0,
        20.0,
        30.0,
        40.0,
        50.0,
        60.0,
        75.0,
        90.0,
    ]
    assert list(resolved["routes"]) == [
        "assignment_isolation",
        "sequential_evalue",
    ]
    assert resolved["family_size"] == 40


def test_simultaneous_cp_bound_uses_entire_declared_family():
    upper = _simultaneous_cp_upper(
        k=0,
        n=1200,
        alpha_family=0.05,
        family_size=40,
    )
    expected = 1.0 - (0.05 / 40.0) ** (1.0 / 1200.0)
    assert np.isclose(upper, expected, rtol=0.0, atol=1e-14)
    assert 0.0055 < upper < 0.0057


def test_envelope_is_applied_separately_by_route_and_direction():
    rows = []
    for route in ("assignment_isolation", "sequential_evalue"):
        for direction in ("negative", "positive"):
            for delta, upper in [(5.0, 0.08), (10.0, 0.04), (20.0, 0.03)]:
                rows.append(
                    {
                        "route": route,
                        "direction": direction,
                        "delta": delta,
                        "simultaneous_cp_upper": upper,
                        "false_adequacy_rate": upper / 2.0,
                        "p_fa_max": 0.05,
                    }
                )
    _apply_envelopes(rows)
    for row in rows:
        assert row["certified_delta_direction"] == 10.0
        assert not row["lower_grid_censored"]
        assert row["envelope_pass"] == (row["delta"] >= 10.0)
