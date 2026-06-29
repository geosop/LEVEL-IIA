# -*- coding: utf-8 -*-
"""
Created on Mon Jun 29 08:35:37 2026

@author: ADMIN
"""
from cri_leveliia.benchmarks import decide


def _clean_audits():
    return {
        "leakage": {"fired": False},
        "delivery": {"fired": False},
        "balance": {"fired": False},
        "swap": {"fired": False},
        "retention": {"fired": False},
    }


def test_resolved_material_slope_with_failed_selection_gate_is_selection_limited():
    cfg = {"alpha": 0.05, "N_min": 10}

    out = {
        "N": 24,
        "beta_min": 40.0,
        "p_rand_less": 0.001,
        "p_rand_greater": 1.0,
        "ucb": -50.0,
        "lcb": -70.0,
        "audits": _clean_audits(),
        "collider": {"fired": False},
        "selection_gate": {"passed": False},
    }

    assert decide(out, cfg) == "selection_limited"