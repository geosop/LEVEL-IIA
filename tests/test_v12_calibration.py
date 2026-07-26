from itertools import product
from pathlib import Path

import numpy as np
import yaml
from scipy import stats

from cri_leveliia import collider, dgp, inference
from cri_leveliia.benchmarks import _replicate_seed


ROOT = Path(__file__).resolve().parents[1]


def test_sequential_mixture_evalue_clean_null_mean_at_most_one():
    """The complete finite clean-null assignment average is an e-value."""
    residual = np.array(
        [0.30, -0.20, 0.25, -0.15, 0.20, -0.10, 0.15, -0.05, 0.10, -0.02]
    )
    participant = np.repeat(np.arange(5), 2)
    fold = participant.copy()
    support = np.tile(np.array([-1.0, 1.0]), (residual.size, 1))
    probability = np.full_like(support, 0.5)
    mu = np.zeros(residual.size)
    evalues = []

    for assignment in product([-1.0, 1.0], repeat=residual.size):
        out = inference.sequential_evalue_pvalue(
            resid=residual,
            tau_obs=np.asarray(assignment),
            support=support,
            prob=probability,
            mu=mu,
            participant=participant,
            fold=fold,
            fold_weights="equal",
            lambda_grid=[0.10, 0.20],
            weights="equal",
            alternative="less",
        )
        assert out["valid"], out["reason"]
        # The final fold combination must be an arithmetic mixture, not a
        # product of mutually cross-fitted fold e-values.
        assert np.isclose(
            np.exp(out["log_e_mix"]),
            np.mean(np.exp(out["log_e_fold"])),
            rtol=1e-12,
            atol=1e-12,
        )
        evalues.append(np.exp(out["log_e_mix"]))

    sample_mean = float(np.mean(evalues))
    assert sample_mean <= 1.0 + 5e-12
    assert np.isclose(sample_mean, 1.0, rtol=0.0, atol=5e-12)


def test_clustered_interaction_diagnostic_has_declared_null_size():
    """A clustered, nonlinear endpoint-only null does not create interaction."""
    cfg = yaml.safe_load(
        (ROOT / "configs" / "collider_clustered_null.yaml").read_text(
            encoding="utf-8"
        )
    )
    cfg["trials_per_bin"] = 12
    m = 300
    fired = []

    for replicate in range(m):
        rng = np.random.default_rng(
            _replicate_seed(cfg["base_seed"], replicate)
        )
        ds = dgp.generate_dataset(rng, cfg)
        diagnostic = collider.interaction_diagnostic(
            ds,
            z_thresh=cfg["interaction_z"],
        )
        assert diagnostic["valid"], diagnostic["reason"]
        assert diagnostic["covariance"] == "participant_clustered_CR1"
        assert diagnostic["n_clusters"] == cfg["n_participants"]
        fired.append(bool(diagnostic["fired"]))

    observed = float(np.mean(fired))
    declared = float(
        2.0 * stats.norm.sf(float(cfg["interaction_z"]))
    )
    # The tolerance is a predeclared Monte Carlo guardrail, wide enough for a
    # rare event at M=300 but narrow enough to catch gross size inflation.
    assert abs(observed - declared) <= 0.02
