# -*- coding: utf-8 -*-
"""Benchmark orchestration: full locked pipeline and decision rule.

A single dataset is carried through comparator fitting, residual freezing,
route-specific calibration, bootstrap bounds, audits, the scalar selection gate,
and endpoint-by-delay collider diagnostics, then classified by the
non-compensatory decision rule.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import dgp, comparator, inference, audits, selection, collider, assignment_law


DECISIONS = ["supported", "forward_only_adequate", "opposite_direction",
             "selection_limited", "diagnostic_failure", "inconclusive"]
ROUTES = {"assignment_isolation", "sequential_evalue"}


def decide(out, cfg):
    """Non-compensatory decision rule.

    The route-neutral keys p_infer_less and p_infer_greater are used for the
    directional calibration. For assignment isolation these are plus-one
    randomisation p-values. For sequential e-values they are p=min(1,1/E).
    """
    alpha = cfg.get("alpha", 0.05)
    bmin = out["beta_min"]
    N_min = cfg.get("N_min", 10)

    if out.get("route_valid", True) is False:
        return "inconclusive"

    if out["N"] < N_min:
        return "inconclusive"

    a = out["audits"]

    if (
        a["leakage"]["fired"]
        or a["delivery"]["fired"]
        or a["balance"]["fired"]
        or a["swap"]["fired"]
    ):
        return "diagnostic_failure"

    p_less = out.get("p_infer_less", out.get("p_rand_less", 1.0))
    p_greater = out.get("p_infer_greater", out.get("p_rand_greater", 1.0))
    material_neg = (
        (p_less <= alpha)
        and (out["ucb"] < -bmin)
    )
    material_pos = (
        (p_greater <= alpha)
        and (out["lcb"] > bmin)
    )

    resolved_any = material_neg or material_pos

    if (
        a["retention"]["fired"]
        or out["collider"]["fired"]
        or (resolved_any and not out["selection_gate"]["passed"])
    ):
        return "selection_limited"

    if material_neg:
        return "supported"

    if material_pos:
        return "opposite_direction"

    return "forward_only_adequate"


def _blank_calibration_fields(route, p_less=1.0, p_greater=1.0):
    out = {
        "inference_route": route,
        "route_valid": True,
        "route_reason": "ok",
        "calibration": "plus_one_randomisation" if route == "assignment_isolation" else "martingale_evalue",
        "p_infer_less": p_less,
        "p_infer_greater": p_greater,
        "p_rand_less": np.nan,
        "p_rand_greater": np.nan,
        "p_seq_less": np.nan,
        "p_seq_greater": np.nan,
        "log_e_seq_less": np.nan,
        "log_e_seq_greater": np.nan,
        "sigma_tau_design": np.nan,
        "sigma_tau_eff": np.nan,
    }
    return out


def _invalid_route_fields(route, reason):
    out = _blank_calibration_fields(route, 1.0, 1.0)
    out["route_valid"] = False
    out["route_reason"] = reason
    return out


# --------------------------------------------------------------------------- #
# Full pipeline on one dataset
# --------------------------------------------------------------------------- #
def pipeline_once(ds, cfg, rng):
    tols = cfg.get("tolerances", {})
    kappa = cfg.get("kappa", 2.0)
    route = cfg.get("inference_route", "assignment_isolation")
    if route not in ROUTES:
        raise ValueError(f"unknown inference_route {route!r}; expected one of {sorted(ROUTES)}")

    grid_s = ds.grid_s
    grid_mean = ds.meta["grid_mean"]
    sigma_tau_design = float(np.std(grid_s))
    support_s = float(grid_s.max() - grid_s.min())

    resid, idx_ret, info = comparator.cross_fitted_residual(
        ds, n_folds=cfg.get("n_folds", 5), lam=cfg.get("ridge_lambda", 1.0), rng=rng)

    part_ret = ds.participant[idx_ret]
    tau_ret = ds.tau_assigned[idx_ret]
    tau_c = tau_ret - grid_mean

    # Label-blind residual scale used for the resolution floor.
    resid_within = resid.copy()
    for pid in np.unique(part_ret):
        m = part_ret == pid
        resid_within[m] = resid_within[m] - np.nanmean(resid_within[m])
    sigma_blind = float(np.nanstd(resid_within, ddof=1))

    route_fields = None
    if route == "assignment_isolation":
        slopes, denoms, keep, beta = inference.participant_slopes(resid, part_ret, tau_c)
        sigma_tau_eff = sigma_tau_design
    else:
        try:
            law = assignment_law.conditional_assignment_table(ds, cfg)
            support_ret = law["support"][idx_ret]
            prob_ret = law["prob"][idx_ret]
            mu_ret = law["mu"][idx_ret]
            var_ret = law["var"][idx_ret]
            valid_ret = law["valid"][idx_ret]
            # Deterministic final draws have zero conditional variance and do not
            # contribute to the sequential-score slope or e-value.
            est = valid_ret & np.isfinite(resid) & np.isfinite(mu_ret) & np.isfinite(var_ret) & (var_ret > 0)
            slopes, denoms, keep, beta = inference.participant_sequential_slopes(
                resid[est], part_ret[est], tau_ret[est] - mu_ret[est], var_ret[est])
            sigma_tau_eff = float(np.sqrt(np.nanmean(var_ret[est]))) if np.any(est) else np.nan
            seq_cfg = cfg.get("sequential_evalue", {}) or {}
            seq_less = inference.sequential_evalue_pvalue(
                resid=resid[est], tau_obs=tau_ret[est], support=support_ret[est], prob=prob_ret[est],
                mu=mu_ret[est], participant=part_ret[est],
                lambda_grid=seq_cfg.get("lambda_grid", [1, 2, 5, 10, 20, 50, 100, 200]),
                weights=seq_cfg.get("weights", "equal"), alternative="less")
            seq_greater = inference.sequential_evalue_pvalue(
                resid=resid[est], tau_obs=tau_ret[est], support=support_ret[est], prob=prob_ret[est],
                mu=mu_ret[est], participant=part_ret[est],
                lambda_grid=seq_cfg.get("lambda_grid", [1, 2, 5, 10, 20, 50, 100, 200]),
                weights=seq_cfg.get("weights", "equal"), alternative="greater")
            route_fields = _blank_calibration_fields(route, seq_less["p_seq"], seq_greater["p_seq"])
            route_fields.update({
                "p_seq_less": seq_less["p_seq"],
                "p_seq_greater": seq_greater["p_seq"],
                "log_e_seq_less": seq_less["log_e_mix"],
                "log_e_seq_greater": seq_greater["log_e_mix"],
                "route_valid": bool(seq_less["valid"] and seq_greater["valid"] and np.isfinite(beta)),
                "route_reason": seq_less["reason"] if seq_less["reason"] != "ok" else seq_greater["reason"],
            })
        except Exception as exc:  # route failure is reported, not silently converted to support
            slopes = np.asarray([])
            denoms = np.asarray([])
            keep = np.asarray([])
            beta = np.nan
            sigma_tau_eff = np.nan
            route_fields = _invalid_route_fields(route, f"{type(exc).__name__}: {exc}")

    N = int(keep.size)
    nbar_ret = idx_ret.size / max(N, 1)
    nb = int(ds.bin_index.max()) + 1
    n_per_bin = idx_ret.size / nb

    sigma_tau_for_floor = sigma_tau_eff if route == "sequential_evalue" and np.isfinite(sigma_tau_eff) and sigma_tau_eff > 0 else sigma_tau_design
    bmin = inference.beta_min(sigma_blind, sigma_tau_for_floor, nbar_ret, kappa=kappa)

    aud = audits.run_audit_battery(ds, tols)
    col = collider.run_collider_diagnostics(ds, cfg)

    if route_fields is None:
        route_fields = _blank_calibration_fields(route)

    if N < 2 or not np.isfinite(beta):
        out = {"beta": beta, "se": np.nan, "ucb": np.nan, "lcb": np.nan,
               "ucb_bca": np.nan, "ucb_t": np.nan, "q_lo": np.nan,
               "beta_min": bmin, "N": N, "nbar_ret": nbar_ret,
               "sigma_blind": sigma_blind, "audits": aud,
               "selection_gate": {"passed": True, "required": 0.0, "audited": 0.0,
                                  "lcb_required": 0.0, "ucb_audited": 0.0},
               "collider": col}
        out.update(route_fields)
        out["sigma_tau_design"] = sigma_tau_design
        out["sigma_tau_eff"] = sigma_tau_eff
        out["decision"] = decide(out, cfg)
        return out

    if route == "assignment_isolation":
        p_less, _ = inference.randomisation_pvalue(
            resid, part_ret, tau_c, beta, R=cfg.get("R", 1499), rng=rng, alternative="less")
        p_greater, _ = inference.randomisation_pvalue(
            resid, part_ret, tau_c, beta, R=cfg.get("R", 1499), rng=rng, alternative="greater")
        route_fields = _blank_calibration_fields(route, p_less, p_greater)
        route_fields.update({"p_rand_less": p_less, "p_rand_greater": p_greater})

    bb = inference.bootstrap_bounds(slopes, B=cfg.get("B", 1499), rng=rng)

    gate = selection.selection_gate(
        beta, support_s, sigma_blind, aud["retention"]["imbalance"],
        n_per_bin, p_high=cfg.get("base_retention", 0.8))

    out = {"beta": beta, "se": bb["se"], "ucb": bb["ucb"], "lcb": bb["lcb"],
           "ucb_bca": bb["ucb_bca"], "ucb_t": bb["ucb_t"],
           "q_lo": bb["q_lo"],
           "beta_min": bmin, "N": N, "nbar_ret": nbar_ret,
           "sigma_blind": sigma_blind,
           "audits": aud, "selection_gate": gate, "collider": col}
    out.update(route_fields)
    out["sigma_tau_design"] = sigma_tau_design
    out["sigma_tau_eff"] = sigma_tau_eff
    out["decision"] = decide(out, cfg)
    return out


def _replicate_seed(base_seed, i):
    return int(base_seed) * 1_000_000 + int(i)


def run_one(cfg, base_seed, i):
    """Generate and analyse a single replicate (deterministic in (base_seed, i))."""
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
            "sigma_tau_design": out["sigma_tau_design"],
            "sigma_tau_eff": out["sigma_tau_eff"],
            "N": out["N"],
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
            "collider_inter_z": out["collider"]["interaction"]["z"],
            "collider_smd": out["collider"]["smd"]["max_smd"],
            "collider_rank_z": out["collider"]["rank"]["z"],
            "collider_fired": out["collider"]["fired"],
            "decision": out["decision"],
        })
    df = pd.DataFrame(rows)
    return df


def summarise(df, cfg, scenario_name, generator_name):
    M = len(df)
    material_neg = (df["p_infer_less"] <= cfg.get("alpha", 0.05)) & (df["ucb"] < -df["beta_min"])
    calib_pass = df["p_infer_less"] <= cfg.get("alpha", 0.05)
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
        "materiality_pass_rate": float(material_neg.mean()),
        "leak_fire_rate": float(df["leak_fired"].mean()),
        "delivery_fire_rate": float(df["delivery_fired"].mean()),
        "retention_imbalance_med": float(df["retention_imbalance"].median()),
        "retention_fire_rate": float(df["retention_fired"].mean()),
        "gate_pass_rate": float(df["gate_passed"].mean()),
        "collider_inter_fire_rate": float((df["collider_inter_z"].abs() > cfg.get("interaction_z", 3.0)).mean()),
        "collider_fire_rate": float(df["collider_fired"].mean()),
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
# Collider calibration sweep (Task 4A)
# --------------------------------------------------------------------------- #
def collider_sweep(base_cfg, gammas, M, base_seed):
    """Sweep collider strength and report induced slope, marginal imbalance,
    interaction-z, gate pass rate, and decision mix."""
    out_rows = []
    for g in gammas:
        cfg = dict(base_cfg)
        cfg["collider_gamma"] = g
        df = run_scenario(cfg, M, base_seed)
        material_neg = (df["p_infer_less"] <= cfg.get("alpha", 0.05)) & (df["ucb"] < -df["beta_min"])
        out_rows.append({
            "collider_gamma": g,
            "median_beta_hat": float(df["beta_hat"].median()),
            "retention_imbalance_med": float(df["retention_imbalance"].median()),
            "retention_fire_rate": float(df["retention_fired"].mean()),
            "materiality_pass_rate": float(material_neg.mean()),
            "interaction_fire_rate": float((df["collider_inter_z"].abs() > cfg.get("interaction_z", 3.0)).mean()),
            "gate_pass_rate": float(df["gate_passed"].mean()),
            "support_rate": float((df["decision"] == "supported").mean()),
            "selection_limited_rate": float((df["decision"] == "selection_limited").mean()),
        })
    return pd.DataFrame(out_rows)
