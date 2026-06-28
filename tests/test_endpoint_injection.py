"""Endpoint-level injection is recovered by the full pipeline and, in the clean
anchor where covariates are independent of the delay, is close to a residual-scale
injection."""
import numpy as np, yaml
from pathlib import Path
from cri_leveliia import dgp, comparator, inference
from cri_leveliia.benchmarks import _replicate_seed

ROOT = Path(__file__).resolve().parents[1]

def _beta(cfg, seed, i):
    rng = np.random.default_rng(_replicate_seed(seed, i))
    ds = dgp.generate_dataset(rng, cfg)
    resid, idx, _ = comparator.cross_fitted_residual(ds, rng=rng)
    part = ds.participant[idx]; tc = ds.tau_assigned[idx] - ds.meta["grid_mean"]
    _, _, _, beta = inference.participant_slopes(resid, part, tc)
    return beta

def test_recovers_injected_slope():
    cfg = yaml.safe_load(open(ROOT / "configs/injected_residual.yaml"))
    betas = [_beta(cfg, 102, i) for i in range(40)]
    # mean recovered slope is close to the injected -60 uV/s
    assert abs(np.mean(betas) - cfg["beta_inj"]) < 6.0

def test_null_has_zero_slope():
    cfg = yaml.safe_load(open(ROOT / "configs/anchor.yaml"))
    betas = [_beta(cfg, 101, i) for i in range(40)]
    assert abs(np.mean(betas)) < 4.0

def test_injection_is_endpoint_level():
    # the dataset carries the injection in A_pre before any comparator fitting
    cfg = yaml.safe_load(open(ROOT / "configs/injected_residual.yaml"))
    rng = np.random.default_rng(_replicate_seed(102, 0))
    ds = dgp.generate_dataset(rng, cfg)
    d = ds.tau_assigned - ds.meta["grid_mean"]
    # A_pre correlates negatively with centred delay at the endpoint level
    assert np.corrcoef(ds.A_pre, d)[0, 1] < -0.1
