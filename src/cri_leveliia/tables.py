"""Table writers for the realised operating characteristics.

All numbers written here originate from the benchmark output; nothing is typed by
hand. The LaTeX writers emit booktabs tables that the manuscript and SI include.
"""

from __future__ import annotations

import pandas as pd


# ordered columns for the realised operating-characteristics table (SI S9)
OC_COLUMNS = [
    ("scenario", "Scenario"),
    ("generator", "Generator"),
    ("M", "$M$"),
    ("P", "$P$"),
    ("trials_per_bin", "trials/bin"),
    ("delay_support_ms", "support (ms)"),
    ("sigma_resid", "$\\sigma_{\\mathrm{resid}}$"),
    ("beta_min_med", "$\\beta_{\\min}$"),
    ("beta_inj", "$\\beta^{\\mathrm{inj}}$"),
    ("mean_beta_hat", "mean $\\widehat{\\beta}_\\tau$"),
    ("sd_beta_hat", "SD $\\widehat{\\beta}_\\tau$"),
    ("median_ucb", "med.\\ UCB"),
    ("rand_pass_rate", "rand.\\ pass"),
    ("materiality_pass_rate", "resol.\\ pass"),
    ("retention_fire_rate", "reten.\\ fire"),
    ("leak_fire_rate", "leak fire"),
    ("gate_pass_rate", "gate pass"),
    ("collider_fire_rate", "collider fire"),
    ("support_rate", "support"),
    ("selection_limited_rate", "sel.-lim."),
    ("diagnostic_failure_rate", "diag.\\ fail"),
    ("null_rate", "null"),
    ("opposite_direction_rate", "opp.\\ dir."),
]


def _fmt(v):
    if isinstance(v, float):
        if v == 0:
            return "0"
        if abs(v) < 1 and abs(v) >= 1e-4:
            return f"{v:.3f}"
        if abs(v) >= 1:
            return f"{v:.1f}"
        return f"{v:.2e}"
    return str(v)


def operating_characteristics_csv(summaries, path):
    df = pd.DataFrame(summaries)
    df.to_csv(path, index=False)
    return df


def operating_characteristics_latex(summaries, path, caption, label, columns=None):
    columns = columns or OC_COLUMNS
    keys = [k for k, _ in columns]
    heads = [h for _, h in columns]
    lines = []
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{" + caption + "}")
    lines.append("\\label{" + label + "}")
    lines.append("\\scriptsize")
    lines.append("\\setlength{\\tabcolsep}{3pt}")
    lines.append("\\begin{tabular}{l" + "r" * (len(keys) - 1) + "}")
    lines.append("\\toprule")
    lines.append(" & ".join(heads) + " \\\\")
    lines.append("\\midrule")
    for s in summaries:
        row = []
        for k in keys:
            v = s.get(k, "")
            row.append(_fmt(v) if not isinstance(v, str) else v.replace("_", "\\_"))
        lines.append(" & ".join(row) + " \\\\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return "\n".join(lines)


def collider_subtable_latex(summary, sweep_df, path, caption, label):
    """Dedicated collider scope-test subtable."""
    lines = []
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{" + caption + "}")
    lines.append("\\label{" + label + "}")
    lines.append("\\footnotesize")
    lines.append("\\begin{tabular}{lrrrrrr}")
    lines.append("\\toprule")
    lines.append("$\\gamma$ & med.\\ $\\widehat{\\beta}_\\tau$ & marg.\\ imbal. & "
                 "reten.\\ fire & resol.\\ pass & interaction fire & sel.-lim. \\\\")
    lines.append("\\midrule")
    for _, r in sweep_df.iterrows():
        lines.append(" & ".join([
            _fmt(r["collider_gamma"]),
            _fmt(r["median_beta_hat"]),
            _fmt(r["retention_imbalance_med"]),
            _fmt(r["retention_fire_rate"]),
            _fmt(r["materiality_pass_rate"]),
            _fmt(r["interaction_fire_rate"]),
            _fmt(r["selection_limited_rate"]),
        ]) + " \\\\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return "\n".join(lines)
