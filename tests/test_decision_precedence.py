# -*- coding: utf-8 -*-
"""
Created on Sun Jun 28 10:00:00 2026

@author: ADMIN
"""
from cri_leveliia.benchmarks import decide


def _base_out():
    return {
        "beta_min": 45.0,
        "N": 24,
        "p_rand_less": 1.0,
        "p_rand_greater": 1.0,
        "ucb": 0.0,
        "lcb": 0.0,
        "audits": {
            "leakage": {"fired": False},
            "delivery": {"fired": False},
            "balance": {"fired": False},
            "swap": {"fired": False},
            "retention": {"fired": False},
        },
        "selection_gate": {"passed": True},
        "collider": {"fired": False},
    }


def test_retention_fire_blocks_forward_only_null_without_resolved_slope():
    out = _base_out()
    out["audits"]["retention"]["fired"] = True
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "selection_limited"


def test_collider_fire_blocks_forward_only_null_without_resolved_slope():
    out = _base_out()
    out["collider"]["fired"] = True
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "selection_limited"


def test_hard_diagnostic_failure_precedes_selection_limited():
    out = _base_out()
    out["audits"]["leakage"]["fired"] = True
    out["audits"]["retention"]["fired"] = True
    out["collider"]["fired"] = True
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "diagnostic_failure"


def test_selection_gate_failure_blocks_resolved_negative_support():
    out = _base_out()
    out["p_rand_less"] = 0.001
    out["ucb"] = -50.0
    out["selection_gate"]["passed"] = False
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "selection_limited"


def test_selection_gate_failure_does_not_block_clean_unresolved_null():
    out = _base_out()
    out["selection_gate"]["passed"] = False
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "forward_only_adequate"


def test_resolved_positive_slope_is_opposite_direction():
    out = _base_out()
    out["p_rand_greater"] = 0.001
    out["lcb"] = 50.0
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "opposite_direction"