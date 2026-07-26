import numpy as np
import yaml
from pathlib import Path

from cri_leveliia import benchmarks, comparator, dgp

ROOT = Path(__file__).resolve().parents[1]


def test_carryover_config_uses_sequential_route():
    cfg = yaml.safe_load(open(ROOT / "configs/adversarial_null.yaml"))
    assert cfg["coef_carryover"] != 0
    assert cfg["inference_route"] == "sequential_evalue"
    assert cfg["retention_timing"] == "pre_assignment"


def test_sequential_route_output_schema_and_no_randomisation_fallback():
    cfg = yaml.safe_load(open(ROOT / "configs/adversarial_null.yaml"))
    cfg["R"] = 99
    cfg["B"] = 99
    df = benchmarks.run_scenario(cfg, M=3, base_seed=cfg["base_seed"])
    required = {
        "inference_route", "calibration", "route_valid", "route_reason",
        "p_infer_less", "p_infer_greater", "p_seq_less", "p_seq_greater",
        "log_e_seq_less", "log_e_seq_greater", "p_rand_less", "p_rand_greater",
        "sigma_tau_design", "sigma_tau_eff", "n_evalue_terms",
        "n_evalue_participants", "evalue_fold_term_counts",
    }
    assert required.issubset(df.columns)
    assert set(df["inference_route"]) == {"sequential_evalue"}
    assert set(df["calibration"]) == {"martingale_evalue"}
    assert df["route_valid"].all()
    assert df["p_rand_less"].isna().all()
    assert df["p_rand_greater"].isna().all()
    assert np.all((df["p_seq_less"] >= 0.0) & (df["p_seq_less"] <= 1.0))
    assert (df["n_evalue_participants"] == cfg["n_participants"]).all()
    assert (df["n_evalue_terms"] > 0).all()


def test_assignment_isolation_output_schema():
    cfg = yaml.safe_load(open(ROOT / "configs/anchor.yaml"))
    cfg["R"] = 99
    cfg["B"] = 99
    df = benchmarks.run_scenario(cfg, M=3, base_seed=cfg["base_seed"])
    assert set(df["inference_route"]) == {"assignment_isolation"}
    assert set(df["calibration"]) == {"plus_one_randomisation"}
    assert df["route_valid"].all()
    assert df["p_seq_less"].isna().all()
    assert df["p_rand_less"].notna().all()


def test_sequential_evalue_has_low_smoke_support_under_adversarial_null():
    cfg = yaml.safe_load(open(ROOT / "configs/adversarial_null.yaml"))
    cfg["R"] = 99
    cfg["B"] = 99
    df = benchmarks.run_scenario(cfg, M=10, base_seed=cfg["base_seed"])
    assert (df["decision"] == "supported").mean() <= 0.20


def test_participant_folds_ignore_assignments_and_retention():
    cfg = yaml.safe_load(open(ROOT / "configs/adversarial_null.yaml"))
    rng = np.random.default_rng(123)
    ds = dgp.generate_dataset(rng, cfg)
    first = comparator.participant_fold_assignment(
        ds.participant,
        n_folds=cfg["n_folds"],
        fold_seed=cfg["crossfit_fold_seed"],
    )
    ds.tau_assigned = ds.tau_assigned[::-1].copy()
    ds.S = 1 - ds.S
    second = comparator.participant_fold_assignment(
        ds.participant,
        n_folds=cfg["n_folds"],
        fold_seed=cfg["crossfit_fold_seed"],
    )
    assert np.array_equal(first, second)


def test_sequential_route_rejects_post_assignment_inclusion():
    cfg = yaml.safe_load(open(ROOT / "configs/adversarial_null.yaml"))
    cfg["retention_timing"] = "post_assignment"
    cfg["R"] = 19
    cfg["B"] = 19
    out = benchmarks.run_one(cfg, cfg["base_seed"], 0)
    assert not out["route_valid"]
    assert out["decision"] == "inconclusive"
    assert "pre_assignment" in out["route_reason"]
