# -*- coding: utf-8 -*-
"""Benchmark orchestration: full locked pipeline and decision rule.

A single dataset is carried through comparator fitting, residual freezing,
route-specific calibration, bootstrap bounds, audits, the scalar selection gate,
endpoint-by-delay collider diagnostics, participant-level estimability
qualification, and the non-compensatory final classifier.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import (
    assignment_law,
    audits,
    collider,
    comparator,
    dgp,
    estimability,
    inference,
    selection,
)


DECISIONS = [
    "supported",
    "forward_only_adequate",
    "opposite_direction",
    "selection_limited",
    "diagnostic_failure",
    "inconclusive",
]
ROUTES = {"assignment_isolation", "sequential_evalue"}


def directional_components(out, cfg):
    """Return the locked inferential and magnitude components.

    The negative tail is the confirmatory directional hypothesis. The positive
    tail is a prespecified opposite-direction diagnostic. Component disagreement
    in either direction is routed to the inconclusive class.
    """
    alpha = float(cfg.get("alpha", 0.05))
    bmin = float(out.get("beta_min", np.nan))
    p_less = float(out.get("p_infer_less", out.get("p_rand_less", 1.0)))
    p_greater = float(out.get("p_infer_greater", out.get("p_rand_greater", 1.0)))
    ucb = float(out.get("ucb", np.nan))
    lcb = float(out.get("lcb", np.nan))

    infer_neg = bool(np.isfinite(p_less) and p_less <= alpha)
    infer_pos = bool(np.isfinite(p_greater) and p_greater <= alpha)
    magnitude_neg = bool(np.isfinite(ucb) and np.isfinite(bmin) and ucb < -bmin)
    magnitude_pos = bool(np.isfinite(lcb) and np.isfinite(bmin) and lcb > bmin)
    resolved_neg = infer_neg and magnitude_neg
    resolved_pos = infer_pos and magnitude_pos
    component_disagreement = (infer_neg != magnitude_neg) or (infer_pos != magnitude_pos)

    return {
        "infer_neg_pass": infer_neg,
        "infer_pos_pass": infer_pos,
        "magnitude_neg_pass": magnitude_neg,
        "magnitude_pos_pass": magnitude_pos,
        "resolved_neg": resolved_neg,
        "resolved_pos": resolved_pos,
        "resolved_any": resolved_neg or resolved_pos,
        "component_disagreement": component_disagreement,
    }


def _default_estimability_for_decision(out):
    """Backward-compatible all-clear object for unit-level decision inputs."""
    return out.get(
        "estimability",
        {
            "information_sufficient": True,
            "summary_difference_fired": False,
            "support_passed": True,
            "opposite_passed": True,
            "adequacy_passed": True,
        },
    )


def decide(out, cfg):
    """Apply the non-compensatory decision rule.

    Route failure or insufficient participant information produces an
    inconclusive outcome. Hard operational audits take precedence over selection
    qualifications. The scalar selection gate is applicable only to an already
    resolved material departure. Participant-estimability sensitivity is applied
    to support, opposite-direction, and affirmative-null candidates.
    """
    N_min = int(cfg.get("N_min", 10))

    if out.get("route_valid", True) is False:
        return "inconclusive"

    est = _default_estimability_for_decision(out)
    a = out["audits"]
    if (
        a["leakage"]["fired"]
        or a["delivery"]["fired"]
        or a["balance"]["fired"]
        or a["swap"]["fired"]
    ):
        return "diagnostic_failure"

    comp = directional_components(out, cfg)

    if a["retention"]["fired"] or out["collider"]["fired"]:
        return "selection_limited"

    if est.get("summary_difference_fired", False):
        return "selection_limited"

    if int(out.get("N", 0)) < N_min:
        return "inconclusive"

    if est.get("information_sufficient", True) is False:
        return "inconclusive"

    if comp["resolved_any"] and not out["selection_gate"]["passed"]:
        return "selection_limited"

    if comp["component_disagreement"]:
        return "inconclusive"

    if comp["resolved_neg"]:
        return "supported" if est.get("support_passed", True) else "selection_limited"

    if comp["resolved_pos"]:
        return (
            "opposite_direction"
            if est.get("opposite_passed", True)
            else "selection_limited"
        )

    if not est.get("adequacy_passed", True):
        return "selection_limited"

    return "forward_only_adequate"


def _blank_calibration_fields(route, p_less=1.0, p_greater=1.0):
    return {
        "inference_route": route,
        "route_valid": True,
        "route_reason": "ok",
        "calibration": (
            "plus_one_randomisation"
            if route == "assignment_isolation"
            else "martingale_evalue"
        ),
        "p_infer_less": p_less,
        "p_infer_greater": p_greater,
        "p_rand_less": np.nan,
        "p_rand_greater": np.nan,
        "p_seq_less": np.nan,
        "p_seq_greater": np.nan,
        "log_e_seq_less": np.nan,
        "log_e_seq_greater": np.nan,
        "n_evalue_terms": 0,
        "n_evalue_participants": 0,
        "evalue_fold_term_counts": "[]",
        "evalue_fold_participant_counts": "[]",
        "sigma_tau_design": np.nan,
        "sigma_tau_eff": np.nan,
    }


def _invalid_route_fields(route, reason):
    out = _blank_calibration_fields(route, 1.0, 1.0)
    out["route_valid"] = False
    out["route_reason"] = reason
    return out


def _within_participant_sd(values, participant, mask=None):
    values = np.asarray(values, dtype=float)
    participant = np.asarray(participant)
    use = np.isfinite(values) if mask is None else (np.asarray(mask, dtype=bool) & np.isfinite(values))
    centred = []
    for pid in np.unique(participant[use]):
        m = use & (participant == pid)
        x = values[m]
        if x.size:
            centred.append(x - np.mean(x))
    if not centred:
        return np.nan
    x = np.concatenate(centred)
    return float(np.std(x, ddof=1)) if x.size > 1 else np.nan


def _blank_estimability(ds, cfg, reason):
    pids = np.unique(ds.participant)
    return {
        "N_eligible": int(pids.size),
        "N_estimable": 0,
        "N_nonestimable": int(pids.size),
        "nonestimable_fraction": 1.0,
        "nonestimable_ids": [int(x) for x in pids],
        "nonestimable_reasons": {reason: int(pids.size)},
        "median_leverage_fraction": 0.0,
        "min_leverage_fraction_estimable": np.nan,
        "summary_smds": {},
        "summary_max_smd": np.nan,
        "summary_difference_fired": False,
        "nonestimable_abs_bound_sum": np.nan,
        "information_sufficient": False,
        "support_passed": False,
        "opposite_passed": False,
        "adequacy_passed": False,
        "records": [],
    }


# --------------------------------------------------------------------------- #
# Full pipeline on one dataset
# --------------------------------------------------------------------------- #
def pipeline_once(ds, cfg, rng):
    tols = cfg.get("tolerances", {})
    kappa = float(cfg.get("kappa", 2.0))
    route = cfg.get("inference_route", "assignment_isolation")
    if route not in ROUTES:
        raise ValueError(f"unknown inference_route {route!r}; expected one of {sorted(ROUTES)}")

    grid_s = np.asarray(ds.grid_s, dtype=float)
    grid_mean = float(ds.meta["grid_mean"])
    sigma_tau_design = float(np.std(grid_s))
    support_s = float(grid_s.max() - grid_s.min())

    resid, idx_ret, comparator_info = comparator.cross_fitted_residual(
        ds,
        n_folds=cfg.get("n_folds", 5),
        lam=cfg.get("ridge_lambda", 1.0),
        rng=rng,
        fold_seed=cfg.get("crossfit_fold_seed", 0),
    )
    part_ret = ds.participant[idx_ret]
    tau_ret = ds.tau_assigned[idx_ret]

    global_sigma_blind = _within_participant_sd(resid, part_ret)
    route_fields = None
    assessment = None
    analysis_mask_ret = np.zeros(idx_ret.size, dtype=bool)
    slopes = np.asarray([], dtype=float)
    keep = np.asarray([], dtype=int)
    beta = np.nan
    sigma_tau_eff = np.nan
    tau_design_ret = np.full(idx_ret.size, np.nan, dtype=float)

    try:
        if route == "assignment_isolation":
            tau_c = inference.center_within_participant(tau_ret, part_ret)
            tau_design_ret = tau_c
            tau_all_c = inference.center_within_participant(ds.tau_assigned, ds.participant)
            usable_ret = np.isfinite(resid) & np.isfinite(tau_c)
            assessment, keep = estimability.assess_participants(
                participant_all=ds.participant,
                endpoint_all=ds.A_pre,
                retained_all=ds.S == 1,
                participant_retained=part_ret,
                tau_retained=tau_ret,
                residual_retained=resid,
                usable_retained=usable_ret,
                denominator_terms_retained=tau_c ** 2,
                denominator_terms_all=tau_all_c ** 2,
                absolute_design_terms_all=np.abs(tau_all_c),
                support_s=support_s,
                global_label_blind_scale=global_sigma_blind,
                cfg=cfg,
            )
            analysis_mask_ret = usable_ret & np.isin(part_ret, keep)
            slopes, _, keep_check, beta = inference.participant_slopes(
                resid[analysis_mask_ret],
                part_ret[analysis_mask_ret],
                tau_c[analysis_mask_ret],
            )
            keep = keep_check
            if np.any(analysis_mask_ret):
                sigma_tau_eff = float(np.sqrt(np.mean(tau_c[analysis_mask_ret] ** 2)))

        else:
            declared_timing = cfg.get("retention_timing", "post_assignment")
            generated_timing = ds.meta.get(
                "retention_timing",
                "post_assignment",
            )
            if (
                declared_timing != "pre_assignment"
                or generated_timing != "pre_assignment"
            ):
                raise ValueError(
                    "sequential e-values require retention_timing=pre_assignment"
                )
            if not np.array_equal(
                np.asarray(ds.H_pre, dtype=bool),
                np.asarray(ds.S, dtype=bool),
            ):
                raise ValueError(
                    "sequential analysis inclusion differs from the "
                    "pre-assignment eligibility vector"
                )

            law = assignment_law.conditional_assignment_table(ds, cfg)
            support_ret = law["support"][idx_ret]
            prob_ret = law["prob"][idx_ret]
            mu_ret = law["mu"][idx_ret]
            var_ret = law["var"][idx_ret]
            valid_ret = law["valid"][idx_ret]
            tau_design_ret = tau_ret - mu_ret
            usable_ret = (
                valid_ret
                & np.isfinite(resid)
                & np.isfinite(mu_ret)
                & np.isfinite(var_ret)
                & (var_ret > 0)
            )
            assessment, keep = estimability.assess_participants(
                participant_all=ds.participant,
                endpoint_all=ds.A_pre,
                retained_all=ds.S == 1,
                participant_retained=part_ret,
                tau_retained=tau_ret,
                residual_retained=resid,
                usable_retained=usable_ret,
                denominator_terms_retained=np.where(usable_ret, var_ret, 0.0),
                denominator_terms_all=np.where(
                    law["valid"] & np.isfinite(law["var"]) & (law["var"] > 0),
                    law["var"],
                    0.0,
                ),
                absolute_design_terms_all=np.where(
                    law["valid"] & np.isfinite(law["mu"]),
                    np.abs(ds.tau_assigned - law["mu"]),
                    0.0,
                ),
                support_s=support_s,
                global_label_blind_scale=global_sigma_blind,
                cfg=cfg,
            )
            analysis_mask_ret = usable_ret & np.isin(part_ret, keep)
            slopes, _, keep_check, beta = inference.participant_sequential_slopes(
                resid[analysis_mask_ret],
                part_ret[analysis_mask_ret],
                tau_ret[analysis_mask_ret] - mu_ret[analysis_mask_ret],
                var_ret[analysis_mask_ret],
            )
            keep = keep_check
            if np.any(analysis_mask_ret):
                sigma_tau_eff = float(np.sqrt(np.mean(var_ret[analysis_mask_ret])))

            seq_cfg = cfg.get("sequential_evalue", {}) or {}
            evalue_mask_ret = usable_ret
            fold_ret = np.asarray(
                comparator_info["fold_retained"],
                dtype=int,
            )
            seq_less = inference.sequential_evalue_pvalue(
                resid=resid[evalue_mask_ret],
                tau_obs=tau_ret[evalue_mask_ret],
                support=support_ret[evalue_mask_ret],
                prob=prob_ret[evalue_mask_ret],
                mu=mu_ret[evalue_mask_ret],
                participant=part_ret[evalue_mask_ret],
                fold=fold_ret[evalue_mask_ret],
                fold_weights=seq_cfg.get("fold_weights", "equal"),
                lambda_grid=seq_cfg.get("lambda_grid", [1, 2, 5, 10, 20, 50, 100, 200]),
                weights=seq_cfg.get("weights", "equal"),
                alternative="less",
            )
            seq_greater = inference.sequential_evalue_pvalue(
                resid=resid[evalue_mask_ret],
                tau_obs=tau_ret[evalue_mask_ret],
                support=support_ret[evalue_mask_ret],
                prob=prob_ret[evalue_mask_ret],
                mu=mu_ret[evalue_mask_ret],
                participant=part_ret[evalue_mask_ret],
                fold=fold_ret[evalue_mask_ret],
                fold_weights=seq_cfg.get("fold_weights", "equal"),
                lambda_grid=seq_cfg.get("lambda_grid", [1, 2, 5, 10, 20, 50, 100, 200]),
                weights=seq_cfg.get("weights", "equal"),
                alternative="greater",
            )
            route_fields = _blank_calibration_fields(
                route, seq_less["p_seq"], seq_greater["p_seq"]
            )
            route_fields.update({
                "p_seq_less": seq_less["p_seq"],
                "p_seq_greater": seq_greater["p_seq"],
                "log_e_seq_less": seq_less["log_e_mix"],
                "log_e_seq_greater": seq_greater["log_e_mix"],
                "n_evalue_terms": seq_less["n_terms"],
                "n_evalue_participants": seq_less["n_participants"],
                "evalue_fold_term_counts": json.dumps(
                    seq_less["n_terms_by_fold"].tolist()
                ),
                "evalue_fold_participant_counts": json.dumps(
                    seq_less["n_participants_by_fold"].tolist()
                ),
                "route_valid": bool(
                    seq_less["valid"] and seq_greater["valid"] and np.isfinite(beta)
                ),
                "route_reason": (
                    seq_less["reason"]
                    if seq_less["reason"] != "ok"
                    else seq_greater["reason"]
                ),
            })
    except Exception as exc:  # route failure is reported, never converted to support
        slopes = np.asarray([], dtype=float)
        keep = np.asarray([], dtype=int)
        beta = np.nan
        sigma_tau_eff = np.nan
        assessment = _blank_estimability(ds, cfg, f"route_error_{type(exc).__name__}")
        route_fields = _invalid_route_fields(route, f"{type(exc).__name__}: {exc}")

    if assessment is None:
        assessment = _blank_estimability(ds, cfg, "estimability_not_computed")

    N = int(keep.size)
    nbar_ret = float(np.sum(analysis_mask_ret) / N) if N > 0 else 0.0
    nb = int(ds.bin_index.max()) + 1
    n_per_bin = idx_ret.size / nb

    sigma_blind = _within_participant_sd(resid, part_ret, analysis_mask_ret)
    if not np.isfinite(sigma_blind) or sigma_blind <= 0:
        sigma_blind = global_sigma_blind

    sigma_tau_for_floor = (
        sigma_tau_eff
        if np.isfinite(sigma_tau_eff) and sigma_tau_eff > 0
        else sigma_tau_design
    )
    bmin = (
        inference.beta_min(sigma_blind, sigma_tau_for_floor, nbar_ret, kappa=kappa)
        if np.isfinite(sigma_blind) and nbar_ret > 0
        else np.inf
    )

    aud = audits.run_audit_battery(ds, tols)
    col = collider.run_collider_diagnostics(ds, cfg)
    if route_fields is None:
        route_fields = _blank_calibration_fields(route)

    if N >= 2 and np.isfinite(beta):
        if route == "assignment_isolation":
            tau_c = inference.center_within_participant(tau_ret, part_ret)
            p_less, beta_perm = inference.randomisation_pvalue(
                resid[analysis_mask_ret],
                part_ret[analysis_mask_ret],
                tau_c[analysis_mask_ret],
                beta,
                R=cfg.get("R", 1499),
                rng=rng,
                alternative="less",
            )
            # Use the same permutation distribution for the diagnostic positive tail.
            p_greater = float(
                (1.0 + np.sum(beta_perm >= beta)) / (beta_perm.size + 1.0)
            )
            route_fields = _blank_calibration_fields(route, p_less, p_greater)
            route_fields.update({"p_rand_less": p_less, "p_rand_greater": p_greater})

        bb = inference.bootstrap_bounds(slopes, B=cfg.get("B", 1499), rng=rng)
        gate = selection.selection_gate(
            beta,
            support_s,
            sigma_blind,
            aud["retention"]["imbalance"],
            n_per_bin,
            p_high=cfg.get("base_retention", 0.8),
        )
        assessment = estimability.add_sensitivity_bounds(
            assessment,
            beta=beta,
            ucb=bb["ucb"],
            lcb=bb["lcb"],
            beta_min=bmin,
        )
        out = {
            "beta": beta,
            "se": bb["se"],
            "ucb": bb["ucb"],
            "lcb": bb["lcb"],
            "ucb_bca": bb["ucb_bca"],
            "ucb_t": bb["ucb_t"],
            "q_lo": bb["q_lo"],
            "beta_min": bmin,
            "N": N,
            "nbar_ret": nbar_ret,
            "sigma_blind": sigma_blind,
            "audits": aud,
            "selection_gate": gate,
            "collider": col,
            "estimability": assessment,
        }
    else:
        assessment = estimability.add_sensitivity_bounds(
            assessment,
            beta=beta,
            ucb=np.nan,
            lcb=np.nan,
            beta_min=bmin,
        )
        out = {
            "beta": beta,
            "se": np.nan,
            "ucb": np.nan,
            "lcb": np.nan,
            "ucb_bca": np.nan,
            "ucb_t": np.nan,
            "q_lo": np.nan,
            "beta_min": bmin,
            "N": N,
            "nbar_ret": nbar_ret,
            "sigma_blind": sigma_blind,
            "audits": aud,
            "selection_gate": {
                "passed": True,
                "required": 0.0,
                "audited": 0.0,
                "lcb_required": 0.0,
                "ucb_audited": 0.0,
            },
            "collider": col,
            "estimability": assessment,
        }

    out.update(route_fields)
    out["sigma_tau_design"] = sigma_tau_design
    out["sigma_tau_eff"] = sigma_tau_eff
    comp = directional_components(out, cfg)
    out["decision_components"] = comp
    out["selection_gate"]["applicable"] = bool(comp["resolved_any"])
    out["estimability"]["conclusion_changing"] = bool(
        out["estimability"].get("summary_difference_fired", False)
        or (comp["resolved_neg"] and not out["estimability"].get("support_passed", True))
        or (comp["resolved_pos"] and not out["estimability"].get("opposite_passed", True))
        or (
            not comp["resolved_any"]
            and not comp["component_disagreement"]
            and not out["estimability"].get("adequacy_passed", True)
        )
    )
    out["decision"] = decide(out, cfg)
    out["_analysis_details"] = {
        "residual_retained": resid,
        "retained_indices": idx_ret,
        "analysis_mask_retained": analysis_mask_ret,
        "participant_retained": part_ret,
        "tau_design_retained": tau_design_ret,
        "participant_slopes": slopes,
        "estimable_participants": keep,
    }
    return out


def _replicate_seed(base_seed, i):
    return int(base_seed) * 1_000_000 + int(i)


def run_one(cfg, base_seed, i):
    """Generate and analyse a single replicate (deterministic in seed and index)."""
    rng = np.random.default_rng(_replicate_seed(base_seed, i))
    ds = dgp.generate_dataset(rng, cfg)
    return pipeline_once(ds, cfg, rng)


# --------------------------------------------------------------------------- #
# Scenario runner
# --------------------------------------------------------------------------- #
def run_scenario(cfg, M, base_seed):
    rows = []
    for i in range(M):
        out = run_one(cfg, base_seed, i)
        a = out["audits"]
        est = out["estimability"]
        comp = out["decision_components"]
        reasons = est.get("nonestimable_reasons", {})
        rows.append({
            "replicate": i,
            "inference_route": out["inference_route"],
            "calibration": out["calibration"],
            "route_valid": out["route_valid"],
            "route_reason": out["route_reason"],
            "beta_hat": out["beta"],
            "se": out["se"],
            "ucb": out["ucb"],
            "lcb": out["lcb"],
            "beta_min": out["beta_min"],
            "p_infer_less": out["p_infer_less"],
            "p_infer_greater": out["p_infer_greater"],
            "p_rand_less": out["p_rand_less"],
            "p_rand_greater": out["p_rand_greater"],
            "p_seq_less": out["p_seq_less"],
            "p_seq_greater": out["p_seq_greater"],
            "log_e_seq_less": out["log_e_seq_less"],
            "log_e_seq_greater": out["log_e_seq_greater"],
            "n_evalue_terms": out["n_evalue_terms"],
            "n_evalue_participants": out["n_evalue_participants"],
            "evalue_fold_term_counts": out["evalue_fold_term_counts"],
            "evalue_fold_participant_counts": out[
                "evalue_fold_participant_counts"
            ],
            "infer_neg_pass": comp["infer_neg_pass"],
            "infer_pos_pass": comp["infer_pos_pass"],
            "magnitude_neg_pass": comp["magnitude_neg_pass"],
            "magnitude_pos_pass": comp["magnitude_pos_pass"],
            "component_disagreement": comp["component_disagreement"],
            "sigma_tau_design": out["sigma_tau_design"],
            "sigma_tau_eff": out["sigma_tau_eff"],
            "N": out["N"],
            "N_eligible": est["N_eligible"],
            "N_estimable": est["N_estimable"],
            "N_nonestimable": est["N_nonestimable"],
            "nonestimable_fraction": est["nonestimable_fraction"],
            "nonestimable_reasons": json.dumps(reasons, sort_keys=True),
            "median_leverage_fraction": est["median_leverage_fraction"],
            "min_leverage_fraction_estimable": est["min_leverage_fraction_estimable"],
            "estimability_summary_max_smd": est["summary_max_smd"],
            "estimability_summary_fired": est["summary_difference_fired"],
            "estimability_information_sufficient": est["information_sufficient"],
            "estimability_support_passed": est.get("support_passed", False),
            "estimability_opposite_passed": est.get("opposite_passed", False),
            "estimability_adequacy_passed": est.get("adequacy_passed", False),
            "estimability_conclusion_changing": est.get("conclusion_changing", False),
            "nonestimable_abs_bound_sum": est["nonestimable_abs_bound_sum"],
            "support_ucb_upper": est.get("support_ucb_upper", np.nan),
            "eligible_lcb_lower": est.get("eligible_lcb_lower", np.nan),
            "eligible_ucb_upper": est.get("eligible_ucb_upper", np.nan),
            "nbar_ret": out["nbar_ret"],
            "sigma_blind": out["sigma_blind"],
            "leak_excursion": a["leakage"]["excursion"],
            "leak_fired": a["leakage"]["fired"],
            "delivery_p99_ms": a["delivery"]["p99_ms"],
            "delivery_fired": a["delivery"]["fired"],
            "retention_imbalance": a["retention"]["imbalance"],
            "retention_fired": a["retention"]["fired"],
            "balance_fired": a["balance"]["fired"],
            "gate_required": out["selection_gate"]["required"],
            "gate_audited": out["selection_gate"]["audited"],
            "gate_passed": out["selection_gate"]["passed"],
            "gate_applicable": out["selection_gate"].get("applicable", False),
            "collider_inter_z": out["collider"]["interaction"]["z"],
            "collider_inter_p": out["collider"]["interaction"]["p"],
            "collider_inter_valid": out["collider"]["interaction"]["valid"],
            "collider_inter_fired": out["collider"]["interaction"]["fired"],
            "collider_smd": out["collider"]["smd"]["max_smd"],
            "collider_smd_min_p": out["collider"]["smd"]["min_p"],
            "collider_smd_valid": out["collider"]["smd"]["valid"],
            "collider_smd_fired": out["collider"]["smd"]["fired"],
            "collider_rank_z": out["collider"]["rank"]["z"],
            "collider_invalid": out["collider"]["invalid"],
            "collider_fired": out["collider"]["fired"],
            "decision": out["decision"],
        })
    return pd.DataFrame(rows)


def summarise(df, cfg, scenario_name, generator_name):
    M = len(df)
    alpha = cfg.get("alpha", 0.05)
    material_neg = (df["p_infer_less"] <= alpha) & (df["ucb"] < -df["beta_min"])
    calib_pass = df["p_infer_less"] <= alpha
    gate_app = df["gate_applicable"].astype(bool)
    gate_conditional = float(df.loc[gate_app, "gate_passed"].mean()) if gate_app.any() else np.nan
    reasons_have_leverage = df["nonestimable_reasons"].str.contains(
        "insufficient_leverage|zero_leverage", regex=True
    )

    summary = {
        "scenario": scenario_name,
        "generator": generator_name,
        "M": M,
        "P": cfg.get("n_participants", 24),
        "trials_per_bin": cfg.get("trials_per_bin", 12),
        "delay_support_ms": f"{cfg.get('delay_grid_ms')[0]}-{cfg.get('delay_grid_ms')[-1]}",
        "n_bins": len(cfg.get("delay_grid_ms")),
        "sigma_resid": cfg.get("sigma_resid", 1.0),
        "inference_route": cfg.get("inference_route", "assignment_isolation"),
        "calibration": str(df["calibration"].iloc[0]) if M else "",
        "route_invalid_rate": float((~df["route_valid"].astype(bool)).mean()) if M else np.nan,
        "beta_min_med": float(df["beta_min"].median()),
        "beta_inj": cfg.get("beta_inj", 0.0),
        "mean_beta_hat": float(df["beta_hat"].mean()),
        "sd_beta_hat": float(df["beta_hat"].std(ddof=1)),
        "median_ucb": float(df["ucb"].median()),
        "median_lcb": float(df["lcb"].median()),
        "calib_pass_rate": float(calib_pass.mean()),
        "rand_pass_rate": float(calib_pass.mean()),
        "positive_diagnostic_pass_rate": float((df["p_infer_greater"] <= alpha).mean()),
        "materiality_pass_rate": float(material_neg.mean()),
        "component_disagreement_rate": float(df["component_disagreement"].mean()),
        "leak_fire_rate": float(df["leak_fired"].mean()),
        "delivery_fire_rate": float(df["delivery_fired"].mean()),
        "retention_imbalance_med": float(df["retention_imbalance"].median()),
        "retention_fire_rate": float(df["retention_fired"].mean()),
        "gate_applicable_rate": float(gate_app.mean()),
        "gate_pass_rate": float(df["gate_passed"].mean()),
        "gate_pass_given_applicable_rate": gate_conditional,
        "collider_inter_fire_rate": float(
            df["collider_inter_fired"].astype(bool).mean()
        ),
        "collider_inter_invalid_rate": float(
            (~df["collider_inter_valid"].astype(bool)).mean()
        ),
        "collider_smd_fire_rate": float(
            df["collider_smd_fired"].astype(bool).mean()
        ),
        "collider_invalid_rate": float(
            df["collider_invalid"].astype(bool).mean()
        ),
        "collider_fire_rate": float(df["collider_fired"].mean()),
        "N_estimable_med": float(df["N_estimable"].median()),
        "nonestimable_fraction_med": float(df["nonestimable_fraction"].median()),
        "leverage_failure_rate": float(reasons_have_leverage.mean()),
        "estimability_summary_fire_rate": float(df["estimability_summary_fired"].mean()),
        "estimability_conclusion_change_rate": float(
            df["estimability_conclusion_changing"].mean()
        ),
        "support_n": int((df["decision"] == "supported").sum()),
        "support_rate": float((df["decision"] == "supported").mean()),
        "null_n": int((df["decision"] == "forward_only_adequate").sum()),
        "null_rate": float((df["decision"] == "forward_only_adequate").mean()),
        "selection_limited_n": int((df["decision"] == "selection_limited").sum()),
        "selection_limited_rate": float((df["decision"] == "selection_limited").mean()),
        "diagnostic_failure_n": int((df["decision"] == "diagnostic_failure").sum()),
        "diagnostic_failure_rate": float((df["decision"] == "diagnostic_failure").mean()),
        "opposite_direction_n": int((df["decision"] == "opposite_direction").sum()),
        "opposite_direction_rate": float((df["decision"] == "opposite_direction").mean()),
        "inconclusive_n": int((df["decision"] == "inconclusive").sum()),
        "inconclusive_rate": float((df["decision"] == "inconclusive").mean()),
        "base_seed": cfg.get("base_seed"),
    }
    return summary


# --------------------------------------------------------------------------- #
# Collider calibration sweep
# --------------------------------------------------------------------------- #
def collider_sweep(base_cfg, gammas, M, base_seed):
    """Sweep collider strength and report the diagnostic/classifier behaviour."""
    out_rows = []
    for g in gammas:
        cfg = dict(base_cfg)
        cfg["collider_gamma"] = g
        df = run_scenario(cfg, M, base_seed)
        material_neg = (df["p_infer_less"] <= cfg.get("alpha", 0.05)) & (
            df["ucb"] < -df["beta_min"]
        )
        app = df["gate_applicable"].astype(bool)
        gate_conditional = float(df.loc[app, "gate_passed"].mean()) if app.any() else np.nan
        out_rows.append({
            "collider_gamma": g,
            "median_beta_hat": float(df["beta_hat"].median()),
            "retention_imbalance_med": float(df["retention_imbalance"].median()),
            "retention_fire_rate": float(df["retention_fired"].mean()),
            "materiality_pass_rate": float(material_neg.mean()),
            "interaction_fire_rate": float(
                df["collider_inter_fired"].astype(bool).mean()
            ),
            "gate_pass_rate": gate_conditional,
            "support_rate": float((df["decision"] == "supported").mean()),
            "selection_limited_rate": float(
                (df["decision"] == "selection_limited").mean()
            ),
        })
    return pd.DataFrame(out_rows)
