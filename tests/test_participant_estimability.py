import numpy as np

from cri_leveliia import estimability
from cri_leveliia.benchmarks import decide


def _clean_audits():
    return {
        "leakage": {"fired": False},
        "delivery": {"fired": False},
        "balance": {"fired": False},
        "swap": {"fired": False},
        "retention": {"fired": False},
    }


def _base_out():
    return {
        "N": 20,
        "beta_min": 40.0,
        "p_infer_less": 1.0,
        "p_infer_greater": 1.0,
        "ucb": 0.0,
        "lcb": 0.0,
        "audits": _clean_audits(),
        "selection_gate": {"passed": True},
        "collider": {"fired": False},
        "estimability": {
            "information_sufficient": True,
            "summary_difference_fired": False,
            "support_passed": True,
            "opposite_passed": True,
            "adequacy_passed": True,
        },
    }


def test_collapsed_delay_support_is_recorded_as_nonestimable():
    grid = np.array([0.0, 0.005, 0.010, 0.015, 0.020])
    participant_all = np.repeat([0, 1], 25)
    tau_all = np.tile(np.repeat(grid, 5), 2)
    endpoint_all = np.linspace(-1.0, 1.0, participant_all.size)

    retained = np.ones(participant_all.size, dtype=bool)
    retained[(participant_all == 1) & (tau_all != 0.010)] = False
    idx = np.flatnonzero(retained)
    part_ret = participant_all[idx]
    tau_ret = tau_all[idx]
    resid = endpoint_all[idx] - np.mean(endpoint_all[idx])

    tau_ret_c = tau_ret.copy()
    for pid in np.unique(part_ret):
        m = part_ret == pid
        tau_ret_c[m] -= np.mean(tau_ret[m])
    tau_all_c = tau_all.copy()
    for pid in np.unique(participant_all):
        m = participant_all == pid
        tau_all_c[m] -= np.mean(tau_all[m])

    assessment, keep = estimability.assess_participants(
        participant_all=participant_all,
        endpoint_all=endpoint_all,
        retained_all=retained,
        participant_retained=part_ret,
        tau_retained=tau_ret,
        residual_retained=resid,
        usable_retained=np.ones(idx.size, dtype=bool),
        denominator_terms_retained=tau_ret_c ** 2,
        denominator_terms_all=tau_all_c ** 2,
        absolute_design_terms_all=np.abs(tau_all_c),
        support_s=0.020,
        global_label_blind_scale=1.0,
        cfg={
            "participant_estimability": {
                "min_retained_trials": 1,
                "min_delay_levels": 3,
                "min_leverage_fraction": 0.50,
                "slope_bound_scale_multiplier": 3.0,
                "summary_smd_threshold": 10.0,
            }
        },
    )

    assert keep.tolist() == [0]
    assert assessment["N_nonestimable"] == 1
    assert "too_few_delay_levels" in assessment["nonestimable_reasons"]
    assert "zero_leverage" in assessment["nonestimable_reasons"]
    assert np.isfinite(assessment["nonestimable_abs_bound_sum"])


def test_nonestimable_bounds_can_block_affirmative_null():
    assessment = {
        "N_eligible": 24,
        "N_estimable": 12,
        "N_nonestimable": 12,
        "nonestimable_abs_bound_sum": 2400.0,
        "information_sufficient": True,
    }
    bounded = estimability.add_sensitivity_bounds(
        assessment,
        beta=0.0,
        ucb=10.0,
        lcb=-10.0,
        beta_min=40.0,
    )
    assert not bounded["adequacy_passed"]


def test_estimability_bound_blocks_resolved_support():
    out = _base_out()
    out["p_infer_less"] = 0.001
    out["ucb"] = -60.0
    out["lcb"] = -80.0
    out["estimability"]["support_passed"] = False
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "selection_limited"


def test_estimability_bound_blocks_affirmative_null():
    out = _base_out()
    out["estimability"]["adequacy_passed"] = False
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "selection_limited"


def test_unbounded_nonestimable_participants_are_inconclusive():
    out = _base_out()
    out["estimability"]["information_sufficient"] = False
    assert decide(out, {"alpha": 0.05, "N_min": 10}) == "inconclusive"
