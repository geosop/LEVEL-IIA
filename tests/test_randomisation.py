"""The plus-one randomisation test holds its nominal size under the null and
rejects an injected slope."""
import numpy as np, yaml
from pathlib import Path
from cri_leveliia import dgp, comparator, inference
from cri_leveliia.benchmarks import _replicate_seed

ROOT = Path(__file__).resolve().parents[1]

def _pval(cfg, seed, i, R=999):
    rng = np.random.default_rng(_replicate_seed(seed, i))
    ds = dgp.generate_dataset(rng, cfg)
    resid, idx, _ = comparator.cross_fitted_residual(ds, rng=rng)
    part = ds.participant[idx]; tc = ds.tau_assigned[idx] - ds.meta["grid_mean"]
    sl, _, _, beta = inference.participant_slopes(resid, part, tc)
    p, _ = inference.randomisation_pvalue(resid, part, tc, beta, R=R, rng=rng)
    return p

def test_size_under_null():
    cfg = yaml.safe_load(open(ROOT / "configs/anchor.yaml"))
    ps = [_pval(cfg, 101, i) for i in range(60)]
    # nominal 5% one-sided test: rejection fraction should be near 0.05, well under 0.20
    rej = np.mean(np.array(ps) <= 0.05)
    assert rej <= 0.20

def test_power_under_injection():
    cfg = yaml.safe_load(open(ROOT / "configs/injected_residual.yaml"))
    ps = [_pval(cfg, 102, i) for i in range(20)]
    assert np.mean(np.array(ps) <= 0.05) >= 0.8

def test_plus_one_floor():
    p = _pval(yaml.safe_load(open(ROOT / "configs/anchor.yaml")), 101, 0, R=199)
    assert p >= 1.0 / (199 + 1) - 1e-9
