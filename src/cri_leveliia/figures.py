"""Regeneration of the validation figure from frozen benchmark output.

The displayed dataset for each panel is selected by a predeclared rule: within a
scenario, the replicate whose participant-mean slope is closest to the scenario
median among replicates carrying the modal final decision. The figure is rebuilt
by regenerating that replicate from its deterministic seed, so the panel is an
exact function of the recorded output, not a hand-picked illustration.
"""

from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import dgp, comparator, inference
from .benchmarks import _replicate_seed, pipeline_once


def representative_index(df):
    """Predeclared representative-selection rule."""
    modal = df["decision"].mode().iloc[0]
    sub = df[df["decision"] == modal]
    if len(sub) == 0:
        sub = df
    med = sub["beta_hat"].median()
    j = (sub["beta_hat"] - med).abs().idxmin()
    return int(df.loc[j, "replicate"]), modal


def _panel_objects(cfg, base_seed, replicate):
    rng = np.random.default_rng(_replicate_seed(base_seed, replicate))
    ds = dgp.generate_dataset(rng, cfg)
    out = pipeline_once(ds, cfg, rng)
    # recompute residual and participant bin means for display
    resid, idx_ret, info = comparator.cross_fitted_residual(
        ds, n_folds=cfg.get("n_folds", 5), lam=cfg.get("ridge_lambda", 1.0),
        rng=np.random.default_rng(_replicate_seed(base_seed, replicate)))
    part = ds.participant[idx_ret]
    grid = ds.grid_s * 1000.0  # ms
    binidx = ds.bin_index[idx_ret]
    nb = int(ds.bin_index.max()) + 1
    # participant-level bin means
    pbm = {}
    for pid in np.unique(part):
        means = []
        for b in range(nb):
            m = (part == pid) & (binidx == b)
            means.append(resid[m].mean() if m.sum() else np.nan)
        pbm[pid] = np.array(means)
    grand = np.array([resid[binidx == b].mean() for b in range(nb)])
    se = np.array([resid[binidx == b].std(ddof=1) / np.sqrt(max((binidx == b).sum(), 1))
                   for b in range(nb)])
    centred = ds.grid_s - ds.meta["grid_mean"]
    fit = out["beta"] * centred
    return {"grid_ms": grid, "pbm": pbm, "grand": grand, "se": se,
            "fit": fit, "centred": centred, "out": out}


def make_figure(panels, summaries_by_scenario, out_path, run_hash):
    """panels: list of (scenario_name, cfg, base_seed, replicate, label)."""
    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(4.6 * n, 4.0), squeeze=False)
    axes = axes[0]
    for ax, (name, cfg, seed, rep, label) in zip(axes, panels):
        obj = _panel_objects(cfg, seed, rep)
        g = obj["grid_ms"]
        for pid, means in obj["pbm"].items():
            ax.plot(g, means, color="0.75", lw=0.6, alpha=0.5, zorder=1)
        ax.errorbar(g, obj["grand"], yerr=obj["se"], fmt="o", color="C0",
                    ms=5, capsize=2, zorder=3)
        gc = (g - g.mean())
        ax.plot(g, obj["out"]["beta"] * (gc / 1000.0), color="C3", lw=1.8, zorder=2)
        s = summaries_by_scenario[name]
        bmin = s["beta_min_med"]
        ax.set_title(label, fontsize=10)
        ax.set_xlabel("assigned delay (ms)")
        ax.set_ylabel("residual endpoint (\u00b5V)")
        txt = (f"$\\widehat{{\\beta}}_\\tau$={obj['out']['beta']:.1f}\n"
               f"UCB={obj['out']['ucb']:.1f}\n"
               f"$\\beta_{{\\min}}$={bmin:.1f}\n"
               f"support={s['support_rate']*100:.1f}%")
        ax.text(0.04, 0.04, txt, transform=ax.transAxes, fontsize=8,
                va="bottom", ha="left",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.7", alpha=0.9))
    fig.suptitle(f"Synthetic validation (simulated data, not human EEG) "
                 f"\u00b7 run {run_hash}", fontsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, bbox_inches="tight")
    fig.savefig(str(out_path).replace(".pdf", ".png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
