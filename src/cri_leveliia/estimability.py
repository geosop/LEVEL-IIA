"""Participant-level estimability diagnostics and sensitivity bounds.

The confirmatory target is an equal-participant mean slope. Trial-level
retention qualification does not by itself ensure that the participants whose
slopes remain estimable represent the eligible participant set. This module
implements a prospective, label-blind estimability rule and a bounded
sensitivity analysis for non-estimable participants.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

import numpy as np


DEFAULTS = {
    "min_retained_trials": 20,
    "min_delay_levels": 3,
    "min_leverage_fraction": 0.50,
    "slope_bound_scale_multiplier": 3.0,
    "summary_smd_threshold": 0.50,
}


def resolved_config(cfg: dict) -> dict:
    """Return the participant-estimability configuration with defaults."""
    out = dict(DEFAULTS)
    out.update(cfg.get("participant_estimability", {}) or {})
    return out


def _finite_sd(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return np.nan
    return float(np.std(x, ddof=1))


def _standardised_group_difference(values: Iterable[float], is_estimable: np.ndarray) -> float:
    """Absolute mean difference divided by the all-participant SD.

    The denominator is label-blind and remains defined when one group contains
    only one participant. A missing or constant summary contributes zero rather
    than manufacturing a diagnostic failure.
    """
    x = np.asarray(list(values), dtype=float)
    est = np.asarray(is_estimable, dtype=bool)
    finite = np.isfinite(x)
    if not np.any(finite & est) or not np.any(finite & ~est):
        return 0.0
    scale = _finite_sd(x[finite])
    if not np.isfinite(scale) or scale <= 0:
        return 0.0
    return float(abs(np.mean(x[finite & est]) - np.mean(x[finite & ~est])) / scale)


def assess_participants(
    *,
    participant_all: np.ndarray,
    endpoint_all: np.ndarray,
    retained_all: np.ndarray,
    participant_retained: np.ndarray,
    tau_retained: np.ndarray,
    residual_retained: np.ndarray,
    usable_retained: np.ndarray,
    denominator_terms_retained: np.ndarray,
    denominator_terms_all: np.ndarray,
    absolute_design_terms_all: np.ndarray,
    support_s: float,
    global_label_blind_scale: float,
    cfg: dict,
) -> tuple[dict, np.ndarray]:
    """Apply the prospective participant-level estimability rule.

    Parameters are assignment-label blind except for the design quantities needed
    to determine whether a slope is mathematically estimable: retained trial
    count, number of retained assigned-delay levels, and retained denominator
    leverage relative to the participant's planned denominator.

    Returns
    -------
    assessment, estimable_participant_ids
        ``assessment`` is JSON-serialisable apart from the optional per-participant
        records, which contain only Python scalars and lists.
    """
    ecfg = resolved_config(cfg)
    min_trials = int(ecfg["min_retained_trials"])
    min_levels = int(ecfg["min_delay_levels"])
    min_leverage_fraction = float(ecfg["min_leverage_fraction"])
    slope_multiplier = float(ecfg["slope_bound_scale_multiplier"])
    smd_threshold = float(ecfg["summary_smd_threshold"])

    participant_all = np.asarray(participant_all)
    endpoint_all = np.asarray(endpoint_all, dtype=float)
    retained_all = np.asarray(retained_all, dtype=bool)
    participant_retained = np.asarray(participant_retained)
    tau_retained = np.asarray(tau_retained, dtype=float)
    residual_retained = np.asarray(residual_retained, dtype=float)
    usable_retained = np.asarray(usable_retained, dtype=bool)
    denominator_terms_retained = np.asarray(denominator_terms_retained, dtype=float)
    denominator_terms_all = np.asarray(denominator_terms_all, dtype=float)
    absolute_design_terms_all = np.asarray(absolute_design_terms_all, dtype=float)

    if not (
        participant_retained.shape
        == tau_retained.shape
        == residual_retained.shape
        == usable_retained.shape
        == denominator_terms_retained.shape
    ):
        raise ValueError("retained participant, delay, residual, usability, and denominator arrays must align")
    if denominator_terms_all.shape != participant_all.shape:
        raise ValueError("denominator_terms_all must align with participant_all")
    if absolute_design_terms_all.shape != participant_all.shape:
        raise ValueError("absolute_design_terms_all must align with participant_all")

    eligible = np.unique(participant_all)
    records: list[dict] = []
    reasons_counter: Counter[str] = Counter()

    global_scale = float(global_label_blind_scale)
    if not np.isfinite(global_scale) or global_scale <= 0:
        global_scale = _finite_sd(endpoint_all)

    for pid in eligible:
        all_mask = participant_all == pid
        ret_mask = participant_retained == pid
        use_mask = ret_mask & usable_retained & np.isfinite(residual_retained)

        n_assigned = int(np.sum(all_mask))
        n_retained = int(np.sum(ret_mask))
        n_usable = int(np.sum(use_mask))
        n_levels = int(np.unique(tau_retained[use_mask]).size) if n_usable else 0

        observed_denominator = float(np.sum(denominator_terms_retained[use_mask])) if n_usable else 0.0
        planned_denominator = float(np.sum(denominator_terms_all[all_mask]))
        leverage_fraction = (
            observed_denominator / planned_denominator
            if np.isfinite(planned_denominator) and planned_denominator > 0
            else 0.0
        )

        reasons: list[str] = []
        if n_usable < min_trials:
            reasons.append("too_few_usable_trials")
        if n_levels < min_levels:
            reasons.append("too_few_delay_levels")
        if not np.isfinite(observed_denominator) or observed_denominator <= 0:
            reasons.append("zero_leverage")
        elif leverage_fraction < min_leverage_fraction:
            reasons.append("insufficient_leverage")

        estimable = len(reasons) == 0
        reasons_counter.update(reasons)

        endpoint_values = endpoint_all[all_mask]
        endpoint_mean = float(np.nanmean(endpoint_values)) if endpoint_values.size else np.nan
        endpoint_scale = _finite_sd(endpoint_values)
        residual_scale = _finite_sd(residual_retained[ret_mask])
        retention_rate = n_retained / n_assigned if n_assigned else np.nan

        candidate_scales = [global_scale, residual_scale]
        if not np.isfinite(residual_scale):
            candidate_scales.append(endpoint_scale)
        finite_scales = [float(x) for x in candidate_scales if np.isfinite(x) and x > 0]
        bound_scale = max(finite_scales) if finite_scales else np.nan
        planned_abs_design = float(np.sum(absolute_design_terms_all[all_mask]))
        abs_slope_bound = (
            slope_multiplier * bound_scale * planned_abs_design / planned_denominator
            if (
                np.isfinite(bound_scale)
                and bound_scale > 0
                and np.isfinite(planned_abs_design)
                and planned_abs_design > 0
                and np.isfinite(planned_denominator)
                and planned_denominator > 0
            )
            else np.nan
        )

        records.append({
            "participant": int(pid),
            "estimable": bool(estimable),
            "reasons": reasons,
            "n_assigned": n_assigned,
            "n_retained": n_retained,
            "n_usable": n_usable,
            "n_delay_levels": n_levels,
            "observed_denominator": observed_denominator,
            "planned_denominator": planned_denominator,
            "planned_abs_design": planned_abs_design,
            "leverage_fraction": float(leverage_fraction),
            "retention_rate": float(retention_rate),
            "endpoint_mean": endpoint_mean,
            "endpoint_scale": endpoint_scale,
            "residual_scale": residual_scale,
            "bound_scale": bound_scale,
            "abs_slope_bound": abs_slope_bound,
        })

    estimable_flags = np.array([r["estimable"] for r in records], dtype=bool)
    estimable_ids = np.array([r["participant"] for r in records if r["estimable"]])
    nonestimable = [r for r in records if not r["estimable"]]

    summary_smds = {
        "retention_rate": _standardised_group_difference(
            [r["retention_rate"] for r in records], estimable_flags
        ),
        "endpoint_mean": _standardised_group_difference(
            [r["endpoint_mean"] for r in records], estimable_flags
        ),
        "endpoint_scale": _standardised_group_difference(
            [r["endpoint_scale"] for r in records], estimable_flags
        ),
        "residual_scale": _standardised_group_difference(
            [r["residual_scale"] for r in records], estimable_flags
        ),
    }
    max_smd = max(summary_smds.values(), default=0.0)
    bound_values = np.array([r["abs_slope_bound"] for r in nonestimable], dtype=float)
    information_sufficient = bool(bound_values.size == 0 or np.all(np.isfinite(bound_values)))
    bound_sum = float(np.sum(bound_values)) if information_sufficient else np.nan

    leverage_estimable = [r["leverage_fraction"] for r in records if r["estimable"]]
    leverage_all = [r["leverage_fraction"] for r in records]
    n_eligible = len(records)
    n_estimable = int(np.sum(estimable_flags))

    assessment = {
        "N_eligible": int(n_eligible),
        "N_estimable": n_estimable,
        "N_nonestimable": int(n_eligible - n_estimable),
        "nonestimable_fraction": float((n_eligible - n_estimable) / n_eligible) if n_eligible else 1.0,
        "nonestimable_ids": [r["participant"] for r in nonestimable],
        "nonestimable_reasons": dict(sorted(reasons_counter.items())),
        "min_retained_trials": min_trials,
        "min_delay_levels": min_levels,
        "min_leverage_fraction_required": min_leverage_fraction,
        "median_leverage_fraction": float(np.median(leverage_all)) if leverage_all else np.nan,
        "min_leverage_fraction_estimable": float(np.min(leverage_estimable)) if leverage_estimable else np.nan,
        "summary_smds": summary_smds,
        "summary_max_smd": float(max_smd),
        "summary_smd_threshold": smd_threshold,
        "summary_difference_fired": bool(nonestimable and max_smd > smd_threshold),
        "slope_bound_scale_multiplier": slope_multiplier,
        "nonestimable_abs_bound_sum": bound_sum,
        "information_sufficient": information_sufficient,
        "records": records,
    }
    return assessment, estimable_ids


def add_sensitivity_bounds(
    assessment: dict,
    *,
    beta: float,
    ucb: float,
    lcb: float,
    beta_min: float,
) -> dict:
    """Add conclusion-opposing bounds for the eligible participant population.

    The estimable-participant confidence bound is combined with the declared
    absolute slope bounds for non-estimable participants. For example, the
    support-opposing eligible-population UCB is

        (N_est * UCB_est + sum(abs_bound_nonest)) / N_eligible.

    This is conservative and avoids treating non-estimable participants as zero.
    """
    out = dict(assessment)
    n_total = int(out.get("N_eligible", 0))
    n_est = int(out.get("N_estimable", 0))
    bound_sum = float(out.get("nonestimable_abs_bound_sum", np.nan))

    finite_core = all(np.isfinite(x) for x in (beta, ucb, lcb, beta_min))
    sufficient = bool(out.get("information_sufficient", False) and n_total > 0 and n_est > 0 and finite_core)
    out["information_sufficient"] = sufficient

    if not sufficient:
        out.update({
            "support_beta_upper": np.nan,
            "support_ucb_upper": np.nan,
            "opposite_beta_lower": np.nan,
            "opposite_lcb_lower": np.nan,
            "eligible_lcb_lower": np.nan,
            "eligible_ucb_upper": np.nan,
            "support_passed": False,
            "opposite_passed": False,
            "adequacy_passed": False,
        })
        return out

    support_beta_upper = (n_est * beta + bound_sum) / n_total
    support_ucb_upper = (n_est * ucb + bound_sum) / n_total
    opposite_beta_lower = (n_est * beta - bound_sum) / n_total
    opposite_lcb_lower = (n_est * lcb - bound_sum) / n_total
    eligible_lcb_lower = (n_est * lcb - bound_sum) / n_total
    eligible_ucb_upper = (n_est * ucb + bound_sum) / n_total

    out.update({
        "support_beta_upper": float(support_beta_upper),
        "support_ucb_upper": float(support_ucb_upper),
        "opposite_beta_lower": float(opposite_beta_lower),
        "opposite_lcb_lower": float(opposite_lcb_lower),
        "eligible_lcb_lower": float(eligible_lcb_lower),
        "eligible_ucb_upper": float(eligible_ucb_upper),
        "support_passed": bool(support_ucb_upper < -beta_min),
        "opposite_passed": bool(opposite_lcb_lower > beta_min),
        "adequacy_passed": bool(
            eligible_lcb_lower >= -beta_min and eligible_ucb_upper <= beta_min
        ),
    })
    return out
