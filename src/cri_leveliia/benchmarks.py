# -*- coding: utf-8 -*-
"""
Created on Sun Jun 28 09:56:35 2026

@author: ADMIN

Benchmark orchestration: full locked pipeline, decision rule, scenario runner.

A single dataset is carried through comparator fitting, residual freezing,
randomisation test, bootstrap bound, audits, the scalar selection gate, and the
endpoint-by-delay collider diagnostics, then classified by the non-compensatory
decision rule. ``run_scenario`` repeats this over M datasets and aggregates the
realised operating characteristics. Per-replicate seeds make every dataset, and
hence the representative figure draw, exactly reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import dgp, comparator, inference, audits, selection, collider


# --------------------------------------------------------------------------- #
# Decision rule
# --------------------------------------------------------------------------- #
DECISIONS = ["supported", "forward_only_adequate", "opposite_direction",
             "selection_limited", "diagnostic_failure", "inconclusive"]

def decide(out, cfg):
    """Non-compensatory decision rule.

    Each analysed dataset is assigned exactly one outcome. Hard implementation
    or audit failures are classified before slope interpretation. Selection and
    collider diagnostics that make the analysed sample non-ignorable are applied
    before the forward-only adequate null label can be assigned. A dataset is
    therefore labelled forward_only_adequate only when audits and support-blocking
    diagnostics pass and no material resolved departure is supported.
    """
    alpha = cfg.get("alpha", 0.05)
    bmin = out["beta_min"]
    N_min = cfg.get("N_min", 10)

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

    material_neg = (
        (out["p_rand_less"] <= alpha)
        and (out["ucb"] < -bmin)
    )
    material_pos = (
        (out["p_rand_greater"] <= alpha)
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


# --------------------------------------------------------------------------- #
# Full pipeline on one dataset
# --------------------------------------------------------------------------- #
def pipeline_once(ds, cfg, rng):
    tols = cfg.get("tolerances", {})
    kappa = cfg.get("kappa", 2.0)
    grid_s = ds.grid_s
    grid_mean = ds.meta["grid_mean"]
    sigma_tau = float(np.std(grid_s))
    support_s = float(grid_s.max() - grid_s.min())

    resid, idx_ret, info = comparator.cross_fitted_residual(
        ds, n_folds=cfg.get("n_folds", 5), lam=cfg.get("ridge_lambda", 1.0), rng=rng)

    part_ret = ds.participant[idx_ret]
    tau_ret = ds.tau_assigned[idx_ret]
    tau_c = tau_ret - grid_mean

    # blind residual scale used for the resolution floor: the within-participant
    # residual SD. The participant-slope estimand uses centred delay and is
    # invariant to per-participant offsets, so this is the dispersion the slope
    # actually sees. It is label-blind (no delay information enters).
    resid_within = resid.copy()
    for pid in np.unique(part_ret):
        m = part_ret == pid
        resid_within[m] = resid_within[m] - np.nanmean(resid_within[m])
    sigma_blind = float(np.nanstd(resid_within, ddof=1))

    slopes, denoms, keep, beta = inference.participant_slopes(resid, part_ret, tau_c)
    N = int(keep.size)
    nbar_ret = idx_ret.size / max(N, 1)
    nb = int(ds.bin_index.max()) + 1
    n_per_bin = idx_ret.size / nb  # total retained trials per bin

    bmin = inference.beta_min(sigma_blind, sigma_tau, nbar_ret, kappa=kappa)

    if N < 2 or not np.isfinite(beta):
        return {"beta": beta, "se": np.nan, "ucb": np.nan, "lcb": np.nan,
                "p_rand_less": 1.0, "p_rand_greater": 1.0, "beta_min": bmin,
                "N": N, "nbar_ret": nbar_ret, "sigma_blind": sigma_blind,
                "audits": audits.run_audit_battery(ds, tols),
                "selection_gate": {"passed": True, "required": 0.0, "audited": 0.0,
                                   "lcb_required": 0.0, "ucb_audited": 0.0},
                "collider": collider.run_collider_diagnostics(ds, cfg),
                "decision": "inconclusive"}

    p_less, _ = inference.randomisation_pvalue(
        resid, part_ret, tau_c, beta, R=cfg.get("R", 1499), rng=rng, alternative="less")
    p_greater, _ = inference.randomisation_pvalue(
        resid, part_ret, tau_c, beta, R=cfg.get("R", 1499), rng=rng, alternative="greater")
    bb = inference.bootstrap_bounds(slopes, B=cfg.get("B", 1499), rng=rng)

    aud = audits.run_audit_battery(ds, tols)
    gate = selection.selection_gate(
        beta, support_s, sigma_blind, aud["retention"]["imbalance"],
        n_per_bin, p_high=cfg.get("base_retention", 0.8))
    col = collider.run_collider_diagnostics(ds, cfg)

    out = {"beta": beta, "se": bb["se"], "ucb": bb["ucb"], "lcb": bb["lcb"],
           "ucb_bca": bb["ucb_bca"], "ucb_t": bb["ucb_t"],
           "q_lo": bb["q_lo"],
           "p_rand_less": p_less, "p_rand_greater": p_greater,
           "beta_min": bmin, "N": N, "nbar_ret": nbar_ret,
           "sigma_blind": sigma_blind,
           "audits": aud, "selection_gate": gate, "collider": col}
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
            "beta_hat": out["beta"],
            "se": out["se"],
            "ucb": out["ucb"],
            "lcb": out["lcb"],
            "beta_min": out["beta_min"],
            "p_rand_less": out["p_rand_less"],
            "p_rand_greater": out["p_rand_greater"],
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
    material_neg = (df["p_rand_less"] <= cfg.get("alpha", 0.05)) & (df["ucb"] < -df["beta_min"])
    summary = {
        "scenario": scenario_name,
        "generator": generator_name,
        "M": M,
        "P": cfg.get("n_participants", 24),
        "trials_per_bin": cfg.get("trials_per_bin", 12),
        "delay_support_ms": f"{cfg.get('delay_grid_ms')[0]}-{cfg.get('delay_grid_ms')[-1]}",
        "n_bins": len(cfg.get("delay_grid_ms")),
        "sigma_resid": cfg.get("sigma_resid", 1.0),
        "beta_min_med": float(df["beta_min"].median()),
        "beta_inj": cfg.get("beta_inj", 0.0),
        "mean_beta_hat": float(df["beta_hat"].mean()),
        "sd_beta_hat": float(df["beta_hat"].std(ddof=1)),
        "median_ucb": float(df["ucb"].median()),
        "median_lcb": float(df["lcb"].median()),
        "rand_pass_rate": float((df["p_rand_less"] <= cfg.get("alpha", 0.05)).mean()),
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
        material_neg = (df["p_rand_less"] <= cfg.get("alpha", 0.05)) & (df["ucb"] < -df["beta_min"])
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