"""Scope test: a pure endpoint-by-delay collider manufactures a retained-sample
slope with balanced marginal retention; the scalar gate misses it and the
interaction diagnostic catches it, so it is never supported."""
import yaml
from pathlib import Path
from cri_leveliia.benchmarks import run_one

ROOT = Path(__file__).resolve().parents[1]

def test_collider_is_selection_limited_not_supported():
    cfg = yaml.safe_load(open(ROOT / "configs/collider_selection.yaml"))
    decisions = [run_one(cfg, 105, i)["decision"] for i in range(30)]
    assert "supported" not in decisions
    assert decisions.count("selection_limited") >= 24  # >=80%

def test_scalar_gate_misses_collider_but_diagnostic_catches():
    cfg = yaml.safe_load(open(ROOT / "configs/collider_selection.yaml"))
    gate_pass, inter_fire = 0, 0
    for i in range(20):
        out = run_one(cfg, 105, i)
        gate_pass += out["selection_gate"]["passed"]
        inter_fire += out["collider"]["interaction"]["fired"]
    assert gate_pass >= 18      # scalar gate passes (misses) almost always
    assert inter_fire >= 18     # interaction diagnostic fires (catches) almost always

def test_full_sample_obeys_boundary():
    # before selection, A_pre is uncorrelated with the assigned delay
    import numpy as np
    from cri_leveliia import dgp
    from cri_leveliia.benchmarks import _replicate_seed
    cfg = yaml.safe_load(open(ROOT / "configs/collider_selection.yaml"))
    rng = np.random.default_rng(_replicate_seed(105, 1))
    ds = dgp.generate_dataset(rng, cfg)
    d = ds.tau_assigned - ds.meta["grid_mean"]
    assert abs(np.corrcoef(ds.A_pre, d)[0, 1]) < 0.05
