import numpy as np
import yaml
from pathlib import Path

from cri_leveliia import benchmarks

ROOT = Path(__file__).resolve().parents[1]


def test_carryover_config_uses_sequential_route():
    cfg = yaml.safe_load(open(ROOT / "configs/adversarial_null.yaml"))
    assert cfg["coef_carryover"] != 0
    assert cfg["inference_route"] == "sequential_evalue"


def test_sequential_route_output_schema_and_no_randomisation_fallback():
    cfg = yaml.safe_load(open(ROOT / "configs/adversarial_null.yaml"))
    cfg["R"] = 99
    cfg["B"] = 99
    df = benchmarks.run_scenario(cfg, M=3, base_seed=cfg["base_seed"])
    required = {
        "inference_route", "calibration", "route_valid", "route_reason",
        "p_infer_less", "p_infer_greater", "p_seq_less", "p_seq_greater",
        "log_e_seq_less", "log_e_seq_greater", "p_rand_less", "p_rand_greater",
        "sigma_tau_design", "sigma_tau_eff",
    }
    assert required.issubset(df.columns)
    assert set(df["inference_route"]) == {"sequential_evalue"}
    assert set(df["calibration"]) == {"martingale_evalue"}
    assert df["route_valid"].all()
    assert df["p_rand_less"].isna().all()
    assert df["p_rand_greater"].isna().all()
    assert np.all((df["p_seq_less"] >= 0.0) & (df["p_seq_less"] <= 1.0))


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
