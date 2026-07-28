from pathlib import Path
import sys

import numpy as np
import yaml

from cri_leveliia import benchmarks as B
from cri_leveliia import dgp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from make_route_matched_null_comparison import (  # noqa: E402
    CELL_ORDER,
    _build_cell_configs,
    _dataset_digest,
    _resolved_manifest,
)


def _resolved():
    manifest = yaml.safe_load(
        (ROOT / "configs" / "route_matched_null_comparison.yaml").read_text(
            encoding="utf-8"
        )
    )
    return _resolved_manifest(manifest, None)


def test_manifest_declares_exact_validity_matched_three_cell_design():
    resolved = _resolved()
    assert [cell["id"] for cell in resolved["cells"]] == CELL_ORDER
    assert not any(
        cell["generator_family"] == "adversarial"
        and cell["inference_route"] == "assignment_isolation"
        for cell in resolved["cells"]
    )


def test_clean_cells_are_generator_identical_and_dataset_identical():
    configs = _build_cell_configs(_resolved())
    ai = configs["clean_assignment_isolation"]
    seq = configs["clean_sequential_evalue"]
    ignored = {"name", "generator", "inference_route"}
    assert {k: v for k, v in ai.items() if k not in ignored} == {
        k: v for k, v in seq.items() if k not in ignored
    }
    for replicate in range(3):
        seed = B._replicate_seed(ai["base_seed"], replicate)
        left = dgp.generate_dataset(np.random.default_rng(seed), ai)
        right = dgp.generate_dataset(np.random.default_rng(seed), seq)
        assert _dataset_digest(left) == _dataset_digest(right)


def test_both_sequential_cells_are_route_valid_in_smoke_replicates():
    configs = _build_cell_configs(_resolved())
    for cell_id in (
        "clean_sequential_evalue",
        "adversarial_sequential_evalue",
    ):
        cfg = configs[cell_id]
        df = B.run_scenario(cfg, M=2, base_seed=cfg["base_seed"])
        assert df["route_valid"].astype(bool).all()
        assert set(df["inference_route"]) == {"sequential_evalue"}


def test_full_adversarial_generator_retains_carryover():
    cfg = _build_cell_configs(_resolved())["adversarial_sequential_evalue"]
    assert cfg["retention_timing"] == "pre_assignment"
    assert cfg["inference_route"] == "sequential_evalue"
    assert float(cfg["coef_carryover"]) != 0.0
