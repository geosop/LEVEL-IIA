"""The scalar selection gate passes a genuine signal and fails detectable
marginal-imbalance selection, but cannot see a balanced collider."""
import numpy as np, yaml
from pathlib import Path
from cri_leveliia import dgp, audits, selection
from cri_leveliia.benchmarks import _replicate_seed, run_one

ROOT = Path(__file__).resolve().parents[1]

def test_gate_passes_clean_signal():
    cfg = yaml.safe_load(open(ROOT / "configs/injected_residual.yaml"))
    out = run_one(cfg, 102, 5)
    assert out["selection_gate"]["passed"]

def test_collider_balanced_marginal_retention():
    # the pure collider keeps marginal retention approximately balanced
    cfg = yaml.safe_load(open(ROOT / "configs/collider_selection.yaml"))
    rng = np.random.default_rng(_replicate_seed(105, 0))
    ds = dgp.generate_dataset(rng, cfg)
    a = audits.retention_audit(ds)
    assert a["imbalance"] < 0.08 and not a["fired"]
