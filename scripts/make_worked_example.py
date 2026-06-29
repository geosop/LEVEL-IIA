# -*- coding: utf-8 -*-
"""
Created on Mon Jun 29 11:37:22 2026

@author: ADMIN
"""
from pathlib import Path
import json
import math
import sys

import numpy as np
import pandas as pd
import yaml

RUN_HASH = "9d2658d6d147de10"
ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "outputs" / RUN_HASH
OUT = ROOT / "CRI_Perspective" / "Tables" / "worked_decision_example.tex"

sys.path.insert(0, str(ROOT / "src"))

from cri_leveliia import audits, collider, comparator, dgp, inference, selection  # noqa: E402
from cri_leveliia import benchmarks as B  # noqa: E402


def load_cfg(name):
    with open(ROOT / "configs" / f"{name}.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get(row, name, default="---"):
    return row[name] if name in row.index else default


def fmt(x, nd=1):
    try:
        x = float(x)
        if not math.isfinite(x):
            return "---"
        return f"{x:.{nd}f}"
    except Exception:
        return str(x)


def fmtp(x):
    try:
        x = float(x)
        if not math.isfinite(x):
            return "---"
        return f"{x:.1e}" if x < 0.001 else f"{x:.3f}"
    except Exception:
        return str(x)


def tex_escape_text(x):
    return (
        str(x)
        .replace("\\", r"\textbackslash{}")
        .replace("_", r"\_")
        .replace("%", r"\%")
        .replace("&", r"\&")
        .replace("#", r"\#")
    )


def tex_texttt(x):
    return r"\texttt{" + tex_escape_text(x) + "}"


def decision_indicators(decision):
    return {
        "support": int(decision == "supported"),
        "selection_limited": int(decision == "selection_limited"),
        "diagnostic_failure": int(decision == "diagnostic_failure"),
        "opposite_direction": int(decision == "opposite_direction"),
        "null": int(decision == "forward_only_adequate"),
    }


def latex_row(cells):
    return " & ".join(str(c) for c in cells) + r" \\"


def analyse_replicate(cfg_name, scenario_key, rep):
    cfg = load_cfg(cfg_name)
    rng = np.random.default_rng(B._replicate_seed(cfg["base_seed"], rep))
    ds = dgp.generate_dataset(rng, cfg)

    resid, idx_ret, _ = comparator.cross_fitted_residual(
        ds,
        n_folds=cfg.get("n_folds", 5),
        lam=cfg.get("ridge_lambda", 1.0),
        rng=rng,
    )

    part_ret = ds.participant[idx_ret]
    tau_ret = ds.tau_assigned[idx_ret]
    grid_mean = ds.meta.get("grid_mean", float(np.mean(ds.grid_s)))
    tau_c = tau_ret - grid_mean

    resid_within = resid.copy()
    for pid in np.unique(part_ret):
        m = part_ret == pid
        resid_within[m] = resid_within[m] - np.nanmean(resid_within[m])

    sigma_blind = float(np.nanstd(resid_within, ddof=1))
    sigma_tau = float(np.std(ds.grid_s))
    support_s = float(ds.grid_s.max() - ds.grid_s.min())

    slopes, denoms, keep, beta = inference.participant_slopes(resid, part_ret, tau_c)
    n_participants = int(keep.size)
    nbar_ret = idx_ret.size / max(n_participants, 1)
    n_bins = int(ds.bin_index.max()) + 1
    n_per_bin = idx_ret.size / n_bins

    beta_min = inference.beta_min(
        sigma_blind,
        sigma_tau,
        nbar_ret,
        kappa=cfg.get("kappa", 2.0),
    )

    if n_participants >= 2 and np.isfinite(beta):
        p_less, _ = inference.randomisation_pvalue(
            resid, part_ret, tau_c, beta,
            R=cfg.get("R", 1499), rng=rng, alternative="less"
        )
        p_greater, _ = inference.randomisation_pvalue(
            resid, part_ret, tau_c, beta,
            R=cfg.get("R", 1499), rng=rng, alternative="greater"
        )
        bb = inference.bootstrap_bounds(slopes, B=cfg.get("B", 1499), rng=rng)
    else:
        p_less = 1.0
        p_greater = 1.0
        bb = {"se": np.nan, "ucb": np.nan, "lcb": np.nan}

    aud = audits.run_audit_battery(ds, cfg.get("tolerances", {}))
    gate = selection.selection_gate(
        beta,
        support_s,
        sigma_blind,
        aud["retention"]["imbalance"],
        n_per_bin,
        p_high=cfg.get("base_retention", 0.8),
    )
    col = collider.run_collider_diagnostics(ds, cfg)

    out = {
        "beta": beta,
        "se": bb["se"],
        "ucb": bb["ucb"],
        "lcb": bb["lcb"],
        "p_rand_less": p_less,
        "p_rand_greater": p_greater,
        "beta_min": beta_min,
        "N": n_participants,
        "nbar_ret": nbar_ret,
        "sigma_blind": sigma_blind,
        "audits": aud,
        "selection_gate": gate,
        "collider": col,
    }
    out["decision"] = B.decide(out, cfg)

    bin_rows = []
    for i, grid_s in enumerate(ds.grid_s):
        m = ds.bin_index[idx_ret] == i
        vals = resid[m]
        if vals.size:
            mean = float(np.mean(vals))
            se = float(np.std(vals, ddof=1) / np.sqrt(vals.size)) if vals.size > 1 else np.nan
        else:
            mean = np.nan
            se = np.nan
        bin_rows.append({
            "delay_ms": float(grid_s * 1000.0),
            "centered_ms": float((grid_s - grid_mean) * 1000.0),
            "n": int(vals.size),
            "mean": mean,
            "se": se,
        })

    raw = pd.read_csv(RUN_DIR / "raw" / f"{scenario_key}.csv")
    raw_row = raw.loc[raw["replicate"] == rep].iloc[0]

    return {
        "cfg": cfg,
        "replicate": rep,
        "base_seed": cfg["base_seed"],
        "raw": raw_row,
        "computed": out,
        "slopes": slopes,
        "bin_rows": bin_rows,
        "sigma_tau": sigma_tau,
    }


def check_against_raw(label, details):
    raw = details["raw"]
    out = details["computed"]
    checks = [
        ("beta_hat", out["beta"], 0.05),
        ("ucb", out["ucb"], 0.10),
        ("lcb", out["lcb"], 0.10),
        ("beta_min", out["beta_min"], 0.10),
        ("p_rand_less", out["p_rand_less"], 0.002),
        ("p_rand_greater", out["p_rand_greater"], 0.002),
    ]

    warnings = []
    for col, val, tol in checks:
        if col in raw.index:
            diff = abs(float(raw[col]) - float(val))
            if diff > tol:
                warnings.append(f"{label}: {col} raw={raw[col]} recomputed={val} diff={diff}")

    if "decision" in raw.index and str(raw["decision"]) != str(out["decision"]):
        warnings.append(f"{label}: decision raw={raw['decision']} recomputed={out['decision']}")

    return warnings


def slope_table_rows(slopes):
    vals = [fmt(x, 1) for x in slopes]
    rows = []
    for i in range(0, len(vals), 8):
        chunk = vals[i:i + 8]
        while len(chunk) < 8:
            chunk.append("")
        rows.append(latex_row(chunk))
    return rows


def make_latex(inj, nul, warnings):
    inj_raw = inj["raw"]
    nul_raw = nul["raw"]
    inj_out = inj["computed"]
    nul_out = nul["computed"]

    inj_decision = str(get(inj_raw, "decision"))
    nul_decision = str(get(nul_raw, "decision"))
    inj_ind = decision_indicators(inj_decision)
    nul_ind = decision_indicators(nul_decision)

    delays = [int(round(r["delay_ms"])) for r in inj["bin_rows"]]
    centred = [int(round(r["centered_ms"])) for r in inj["bin_rows"]]
    counts = [r["n"] for r in inj["bin_rows"]]
    means = [r["mean"] for r in inj["bin_rows"]]
    ses = [r["se"] for r in inj["bin_rows"]]

    lines = []
    lines.append("% Machine-generated by scripts/make_worked_example.py.")
    lines.append(f"% Frozen run hash: {RUN_HASH}.")
    if warnings:
        lines.append("% Recompute warnings. Headline table values use archived raw rows.")
        for warning in warnings:
            lines.append("% " + warning)
    lines.append("")

    lines.append(r"\paragraph{Design and locked constants.}")
    lines.append(
        f"The worked example is generated from the same frozen benchmark output directory as the "
        f"operating-characteristics table. For run \\texttt{{{RUN_HASH}}}, the representative "
        f"supported injected-residual draw is replicate \\({inj['replicate']}\\) with base seed "
        f"\\({inj['base_seed']}\\), and the representative clean-null draw is replicate "
        f"\\({nul['replicate']}\\) with base seed \\({nul['base_seed']}\\)."
    )
    lines.append(
        f"The representative indices are read from "
        f"\\texttt{{outputs/{RUN_HASH}/summary/representative\\_index.json}}. "
        f"Headline decision objects are read from the frozen raw per-replicate CSV rows, while "
        f"the bin means and participant slopes are recomputed deterministically from the same "
        f"representative replicate and scenario configuration."
    )
    lines.append(
        f"Both examples use \\(P={inj['cfg'].get('n_participants', 24)}\\) participants and the "
        f"assigned-delay grid \\(\\tau_L\\in\\{{{', '.join(str(x) for x in delays)}\\}}\\,"
        f"\\mathrm{{ms}}\\), with \\(\\sigma_\\tau={inj['sigma_tau']:.3g}\\,\\mathrm{{s}}\\) "
        f"on the second scale used by the slope estimator."
    )
    lines.append(
        f"In the supported draw, the label-blind residual scale is "
        f"\\(\\sigma^{{\\mathrm{{blind}}}}_{{\\mathrm{{resid}}}}={inj_out['sigma_blind']:.2f}\\,"
        f"\\mu\\mathrm{{V}}\\), the retained-trial yield is "
        f"\\(\\bar n_{{\\mathrm{{ret}}}}={inj_out['nbar_ret']:.1f}\\), and the registered "
        f"resolution floor is"
    )
    lines.append(r"\[")
    lines.append(
        f"\\beta_{{\\min}}=\\kappa\\,"
        f"\\frac{{\\sigma^{{\\mathrm{{blind}}}}_{{\\mathrm{{resid}}}}}}"
        f"{{\\sigma_\\tau\\sqrt{{\\bar n_{{\\mathrm{{ret}}}}}}}}"
        f"={inj_out['beta_min']:.1f}\\,\\mu\\mathrm{{V\\,s^{{-1}}}} ."
    )
    lines.append(r"\]")
    lines.append(
        r"This floor is a resolvability threshold for the participant-level slope, not a "
        r"biological importance threshold and not a population \(p\)-value."
    )
    lines.append("")

    lines.append(r"\paragraph{Supported injected-residual draw.}")
    lines.append(
        r"The injected-residual generator adds a negative endpoint-level slope before the "
        r"comparator is fitted. The forward-only comparator is label-blind, the cross-fitted "
        r"residuals are frozen, and the same decision rule used in the full benchmark is then "
        r"applied."
    )
    lines.append(
        f"The retained residual bin means in \\Cref{{tab:si-worked-bins}} show the "
        f"delay-ordered residual pattern for this representative draw. The participant "
        f"slopes in \\Cref{{tab:si-worked-slopes}} are the independent units entering the "
        f"equal-participant estimand. Their mean is "
        f"\\(\\widehat\\beta_\\tau={inj_out['beta']:.1f}\\,\\mu\\mathrm{{V\\,s^{{-1}}}}\\), "
        f"with participant-level standard error "
        f"\\({inj_out['se']:.1f}\\,\\mu\\mathrm{{V\\,s^{{-1}}}}\\)."
    )
    lines.append("")

    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Retained residual-endpoint means by assigned-delay bin for the "
        r"representative supported injected-residual draw. Means and standard errors are "
        r"on the frozen residual endpoint scale in \(\mu\mathrm{V}\).}"
    )
    lines.append(r"\label{tab:si-worked-bins}")
    lines.append(r"\footnotesize")
    lines.append(r"\setlength{\tabcolsep}{4pt}")
    lines.append(r"\begin{tabular}{lccccc}")
    lines.append(r"\toprule")
    lines.append(latex_row([r"Assigned delay \(\tau_L\) (ms)"] + [str(x) for x in delays]))
    lines.append(latex_row([r"Centred \(\Delta\tau\) (ms)"] + [str(x) for x in centred]))
    lines.append(r"\midrule")
    lines.append(latex_row(["Retained trials"] + [str(x) for x in counts]))
    lines.append(latex_row([r"Mean \(A^{\mathrm{resid}}_{\mathrm{pre}}\)"] + [fmt(x, 2) for x in means]))
    lines.append(latex_row(["SE"] + [fmt(x, 2) for x in ses]))
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    lines.append("")

    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(
        f"\\caption{{Participant slopes \\(\\widehat\\beta_{{\\tau,p}}\\) for the representative "
        f"supported injected-residual draw. Units are \\(\\mu\\mathrm{{V\\,s^{{-1}}}}\\). "
        f"The equal-participant mean is "
        f"\\(\\widehat\\beta_\\tau={inj_out['beta']:.1f}\\).}}"
    )
    lines.append(r"\label{tab:si-worked-slopes}")
    lines.append(r"\footnotesize")
    lines.append(r"\begin{tabular}{rrrrrrrr}")
    lines.append(r"\toprule")
    lines.extend(slope_table_rows(inj["slopes"]))
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    lines.append("")

    lines.append(
        r"The assignment-calibrated randomisation test asks whether the observed negative "
        r"slope is unusually negative under the assignment mechanism, with the frozen "
        r"residual array held fixed. The participant-bootstrap bound asks whether the "
        r"population participant-level slope is resolved beyond the registered floor. "
        r"In this representative injected-residual draw, the randomisation criterion "
        r"passes, the bootstrap-\(t\) upper bound lies below \(-\beta_{\min}\), the "
        r"analysable participant count meets \(N_{\min}\), the support-blocking audits "
        r"do not fire, the collider diagnostic does not fire, and the selection gate "
        r"passes. The executable classifier therefore returns \texttt{supported}."
    )
    lines.append("")

    lines.append(r"\paragraph{Clean-null draw and contrast.}")
    lines.append(
        r"The clean-null draw uses the same endpoint construction, comparator, "
        r"residual-freezing rule, inference, audits, and classifier, but its generator "
        r"contains no assigned-delay residual. This example is not expected to give an "
        r"exactly zero slope in finite Monte Carlo data. It is expected to fail the "
        r"directional support rule while retaining a valid analysis sample. The final "
        r"side-by-side trace in \Cref{tab:si-worked-decision} shows that the same "
        r"locked pipeline supports the injected-residual draw and returns "
        r"\texttt{forward\_only\_adequate} for the clean-null draw."
    )
    lines.append("")

    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Every decision object available in the frozen per-replicate benchmark "
        r"rows for the representative supported injected-residual draw and the "
        r"representative clean-null draw. Slope, bound and floor units are "
        r"\(\mu\mathrm{V\,s^{-1}}\).}"
    )
    lines.append(r"\label{tab:si-worked-decision}")
    lines.append(r"\footnotesize")
    lines.append(r"\setlength{\tabcolsep}{3.5pt}")
    lines.append(r"\begin{tabularx}{\textwidth}{@{}p{3.9cm}p{3.0cm}p{3.0cm}p{3.0cm}@{}}")
    lines.append(r"\toprule")
    lines.append(latex_row(["Decision object", "Criterion", "Supported draw", "Clean-null draw"]))
    lines.append(r"\midrule")
    lines.append(latex_row(["Scenario", "recorded generator", "injected residual", "clean null"]))
    lines.append(latex_row(["Replicate", "representative index", f"\\({inj['replicate']}\\)", f"\\({nul['replicate']}\\)"]))
    lines.append(latex_row(["Decision", "executable classifier", tex_texttt(inj_decision), tex_texttt(nul_decision)]))
    lines.append(latex_row([r"Estimate \(\widehat\beta_\tau\)", "reported", f"\\({fmt(get(inj_raw, 'beta_hat'))}\\)", f"\\({fmt(get(nul_raw, 'beta_hat'))}\\)"]))
    lines.append(latex_row([r"Bootstrap-\(t\) \(\mathrm{UCB}_{0.95}\)", r"\(<-\beta_{\min}\)", f"\\({fmt(get(inj_raw, 'ucb'))}\\)", f"\\({fmt(get(nul_raw, 'ucb'))}\\)"]))
    lines.append(latex_row([r"Bootstrap-\(t\) \(\mathrm{LCB}_{0.95}\)", "reported", f"\\({fmt(get(inj_raw, 'lcb'))}\\)", f"\\({fmt(get(nul_raw, 'lcb'))}\\)"]))
    lines.append(latex_row([r"Resolution floor \(\beta_{\min}\)", "registered formula", f"\\({fmt(get(inj_raw, 'beta_min'))}\\)", f"\\({fmt(get(nul_raw, 'beta_min'))}\\)"]))
    lines.append(latex_row([r"Randomisation \(p\), negative direction", r"\(\le 0.05\)", f"\\({fmtp(get(inj_raw, 'p_rand_less'))}\\)", f"\\({fmtp(get(nul_raw, 'p_rand_less'))}\\)"]))
    lines.append(latex_row([r"Randomisation \(p\), positive direction", "reported", f"\\({fmtp(get(inj_raw, 'p_rand_greater'))}\\)", f"\\({fmtp(get(nul_raw, 'p_rand_greater'))}\\)"]))
    lines.append(latex_row(["Support indicator", "final outcome class", f"\\({inj_ind['support']}\\)", f"\\({nul_ind['support']}\\)"]))
    lines.append(latex_row(["Selection-limited indicator", "final outcome class", f"\\({inj_ind['selection_limited']}\\)", f"\\({nul_ind['selection_limited']}\\)"]))
    lines.append(latex_row(["Diagnostic-failure indicator", "final outcome class", f"\\({inj_ind['diagnostic_failure']}\\)", f"\\({nul_ind['diagnostic_failure']}\\)"]))
    lines.append(latex_row(["Opposite-direction indicator", "final outcome class", f"\\({inj_ind['opposite_direction']}\\)", f"\\({nul_ind['opposite_direction']}\\)"]))
    lines.append(latex_row(["Null indicator", "final outcome class", f"\\({inj_ind['null']}\\)", f"\\({nul_ind['null']}\\)"]))
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabularx}")
    lines.append(r"\end{table}")
    lines.append("")

    return "\n".join(lines)


def main():
    with open(RUN_DIR / "summary" / "representative_index.json", "r", encoding="utf-8") as f:
        reps = json.load(f)

    inj_rep = int(reps["injected_residual"]["replicate"])
    null_rep = int(reps["anchor"]["replicate"])

    inj = analyse_replicate("injected_residual", "injected_residual", inj_rep)
    nul = analyse_replicate("anchor", "anchor", null_rep)

    warnings = []
    warnings.extend(check_against_raw("injected_residual", inj))
    warnings.extend(check_against_raw("anchor", nul))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(make_latex(inj, nul, warnings), encoding="utf-8")

    print(f"Wrote {OUT}")
    print(
        f"Injected residual replicate {inj_rep}: "
        f"decision={get(inj['raw'], 'decision')}, "
        f"beta={fmt(get(inj['raw'], 'beta_hat'))}, "
        f"ucb={fmt(get(inj['raw'], 'ucb'))}, "
        f"beta_min={fmt(get(inj['raw'], 'beta_min'))}"
    )
    print(
        f"Clean-null replicate {null_rep}: "
        f"decision={get(nul['raw'], 'decision')}, "
        f"beta={fmt(get(nul['raw'], 'beta_hat'))}, "
        f"ucb={fmt(get(nul['raw'], 'ucb'))}, "
        f"beta_min={fmt(get(nul['raw'], 'beta_min'))}"
    )

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print("  " + warning)


if __name__ == "__main__":
    main()