import numpy as np
import yaml
from pathlib import Path

from cri_leveliia import assignment_law, dgp

ROOT = Path(__file__).resolve().parents[1]


def test_fixed_multiset_law_probabilities_and_moments():
    cfg = yaml.safe_load(open(ROOT / "configs/anchor.yaml"))
    rng = np.random.default_rng(123)
    ds = dgp.generate_dataset(rng, cfg)
    law = assignment_law.conditional_assignment_table(ds, cfg)

    assert law["law_type"] == "fixed_multiset_without_replacement"
    assert law["support"].shape == law["prob"].shape
    assert law["support"].shape[0] == ds.n_trials
    assert np.allclose(law["prob"].sum(axis=1), 1.0)
    assert np.all(law["prob"] >= 0.0)

    mu_manual = np.sum(law["prob"] * law["support"], axis=1)
    var_manual = np.sum(law["prob"] * (law["support"] - mu_manual[:, None]) ** 2, axis=1)
    assert np.allclose(law["mu"], mu_manual)
    assert np.allclose(law["var"], var_manual)
    assert np.all(law["var"] >= -1e-15)


def test_observed_assignment_has_positive_conditional_probability_until_draw():
    cfg = yaml.safe_load(open(ROOT / "configs/anchor.yaml"))
    rng = np.random.default_rng(456)
    ds = dgp.generate_dataset(rng, cfg)
    law = assignment_law.conditional_assignment_table(ds, cfg)
    for i, tau in enumerate(ds.tau_assigned):
        hit = np.isclose(law["support"][i], tau, rtol=0.0, atol=1e-12)
        assert hit.sum() == 1
        assert law["prob"][i, hit][0] > 0.0


def test_final_within_participant_draw_is_deterministic_and_not_estimable():
    cfg = yaml.safe_load(open(ROOT / "configs/anchor.yaml"))
    rng = np.random.default_rng(789)
    ds = dgp.generate_dataset(rng, cfg)
    law = assignment_law.conditional_assignment_table(ds, cfg)
    for pid in np.unique(ds.participant):
        rows = np.flatnonzero(ds.participant == pid)
        last = rows[np.argmax(ds.trial_index[rows])]
        assert np.isclose(law["var"][last], 0.0)
        assert not law["valid"][last]
