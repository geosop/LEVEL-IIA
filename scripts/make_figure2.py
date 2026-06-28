#!/usr/bin/env python3
"""Regenerate Figure 2 from a frozen benchmark run.

Usage:
    python scripts/make_figure2.py --run-hash <RUN_HASH>

The panels are rebuilt from the representative replicate recorded in
representative_index.json. Each displayed dataset is regenerated from its
deterministic per-replicate seed, so the figure remains an exact function of the
locked public run.

This script changes only the visual architecture of Figure 2. It does not rerun
the benchmark, change the classifier, alter the operating-characteristics table,
or edit any summary CSV files.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cri_leveliia import comparator, dgp  # noqa: E402
from cri_leveliia.benchmarks import _replicate_seed, pipeline_once  # noqa: E402


BLUE = "#2c6fbb"
GREEN = "#2e8b57"
RED = "#c0392b"
GREY = "#9aa0a6"


PANELS = [
    {
        "fname": "anchor",
        "scenario": "clean_null",
        "title": "(a)  Forward-only null",
        "banner": "Forward-only adequate",
        "chips": r"slope --      $\rightarrow$  null",
        "note": "residual carries no\nassigned-delay slope",
        "color": BLUE,
        "rate_kind": "null",
    },
    {
        "fname": "injected_residual",
        "scenario": "injected_residual",
        "title": "(b)  Injected endpoint residual",
        "banner": "Supported residual",
        "chips": r"slope $\checkmark$ · UCB $\checkmark$ · audits $\checkmark$   $\rightarrow$  SUPPORT",
        "note": "injected endpoint residual\nrecovered on residual scale",
        "color": GREEN,
        "rate_kind": "support",
    },
    {
        "fname": "leakage",
        "scenario": "leakage",
        "title": "(c)  Leakage artefact",
        "banner": "Blocked by audit - not support",
        "chips": r"slope $\checkmark$ · UCB $\checkmark$ · audit $\times$   $\rightarrow$  NOT SUPPORT",
        "note": "apparent slope from a\npost-endpoint temporal leak",
        "color": RED,
        "rate_kind": "leakage",
    },
]


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _as_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _as_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(round(float(value)))
    except Exception:
        return default


def _count(summary: dict, count_key: str, rate_key: str) -> int:
    """Return an exact count if available; otherwise reconstruct from M and rate."""
    if count_key in summary:
        return _as_int(summary[count_key])
    M = _as_int(summary.get("M", 0))
    rate = _as_float(summary.get(rate_key, 0.0))
    return int(round(M * rate))


def _count_rate(summary: dict, count_key: str, rate_key: str) -> str:
    M = _as_int(summary.get("M", 0))
    n = _count(summary, count_key, rate_key)
    rate = _as_float(summary.get(rate_key, n / M if M else 0.0))
    return f"{n}/{M} ({rate:.3f})"


def _panel_objects(cfg: dict, base_seed: int, replicate: int) -> dict:
    """Rebuild the representative dataset and display objects from the locked seed."""
    seed = _replicate_seed(base_seed, replicate)

    rng = np.random.default_rng(seed)
    ds = dgp.generate_dataset(rng, cfg)
    out = pipeline_once(ds, cfg, rng)

    resid, idx_ret, _info = comparator.cross_fitted_residual(
        ds,
        n_folds=cfg.get("n_folds", 5),
        lam=cfg.get("ridge_lambda", 1.0),
        rng=np.random.default_rng(seed),
    )

    part = ds.participant[idx_ret]
    binidx = ds.bin_index[idx_ret]
    grid_ms = ds.grid_s * 1000.0
    nb = int(ds.bin_index.max()) + 1

    pids = np.sort(np.unique(part))
    participant_bin_means = np.full((len(pids), nb), np.nan)

    for i, pid in enumerate(pids):
        for b in range(nb):
            m = (part == pid) & (binidx == b)
            if np.any(m):
                participant_bin_means[i, b] = float(np.nanmean(resid[m]))

    grand = np.array(
        [float(np.nanmean(resid[binidx == b])) for b in range(nb)],
        dtype=float,
    )

    se = np.array(
        [
            float(np.nanstd(resid[binidx == b], ddof=1) / np.sqrt(max(np.sum(binidx == b), 1)))
            for b in range(nb)
        ],
        dtype=float,
    )

    return {
        "grid_ms": grid_ms,
        "participant_bin_means": participant_bin_means,
        "grand": grand,
        "se": se,
        "out": out,
        "dataset": ds,
        "seed": seed,
    }


def _decision_box_text(obj: dict, summary: dict) -> str:
    out = obj["out"]
    beta = _as_float(out.get("beta", np.nan))
    ucb = _as_float(out.get("ucb", np.nan))
    beta_min = _as_float(summary.get("beta_min_med", out.get("beta_min", np.nan)))

    clears = np.isfinite(ucb) and np.isfinite(beta_min) and (ucb < -beta_min)
    cmp = r"$<-\beta_{\min}$  $\checkmark$" if clears else r"$\geq-\beta_{\min}$  $\times$"

    return (
        rf"$\widehat{{\beta}}_\tau = {beta:.1f}$" + "\n"
        + rf"$\mathrm{{UCB}}_{{0.95}} = {ucb:+.1f}$  {cmp}" + "\n"
        + rf"$\beta_{{\min}} = {beta_min:.1f}$   (all $\mu$V s$^{{-1}}$)"
    )


def _rate_text(panel: dict, summary: dict) -> str:
    kind = panel["rate_kind"]

    if kind == "null":
        return (
            "false-support rate\n"
            + _count_rate(summary, "support_n", "support_rate")
            + "\nnull "
            + _count_rate(summary, "null_n", "null_rate")
        )

    if kind == "support":
        return (
            "support\n"
            + _count_rate(summary, "support_n", "support_rate")
            + "\nnull "
            + _count_rate(summary, "null_n", "null_rate")
        )

    if kind == "leakage":
        return (
            "diagnostic failure\n"
            + _count_rate(summary, "diagnostic_failure_n", "diagnostic_failure_rate")
            + "\nsupport "
            + _count_rate(summary, "support_n", "support_rate")
        )

    return "support\n" + _count_rate(summary, "support_n", "support_rate")


def _choose_ylim(objects: list[dict]) -> tuple[float, float]:
    vals = []
    for obj in objects:
        pbm = obj["participant_bin_means"]
        vals.extend(np.ravel(pbm[np.isfinite(pbm)]).tolist())
        vals.extend(np.ravel(obj["grand"][np.isfinite(obj["grand"])]).tolist())
        vals.extend(np.ravel((obj["grand"] + obj["se"])[np.isfinite(obj["grand"] + obj["se"])]).tolist())
        vals.extend(np.ravel((obj["grand"] - obj["se"])[np.isfinite(obj["grand"] - obj["se"])]).tolist())

    if not vals:
        return (-1.25, 1.25)

    lim = max(1.25, float(np.nanmax(np.abs(vals))) * 1.12)
    lim = min(max(lim, 1.25), 2.25)
    return (-lim, lim)


def _draw_panel(ax, panel: dict, obj: dict, summary: dict, ylim: tuple[float, float]) -> None:
    color = panel["color"]
    grid_ms = obj["grid_ms"]
    pbm = obj["participant_bin_means"]
    grand = obj["grand"]
    se = obj["se"]
    beta = _as_float(obj["out"].get("beta", np.nan))

    jitter_rng = np.random.default_rng(12345)

    for j, x in enumerate(grid_ms):
        y = pbm[:, j]
        y = y[np.isfinite(y)]
        if y.size == 0:
            continue

        x_jitter = jitter_rng.normal(0.0, 0.28, size=y.size)
        ax.scatter(
            np.full(y.size, x) + x_jitter,
            y,
            s=11,
            color=color,
            alpha=0.38,
            linewidths=0,
            zorder=1,
        )

    xs = np.linspace(float(np.min(grid_ms)) - 1.0, float(np.max(grid_ms)) + 1.0, 100)
    xc = (xs - float(np.mean(grid_ms))) / 1000.0
    ax.plot(xs, beta * xc, color=color, lw=2.3, zorder=3)

    ax.errorbar(
        grid_ms,
        grand,
        yerr=se,
        fmt="o",
        ms=7,
        color=color,
        ecolor=color,
        elinewidth=1.4,
        capsize=3,
        mfc="white",
        mec=color,
        mew=1.8,
        zorder=4,
    )

    ax.axhline(0.0, color=GREY, lw=0.9, ls=(0, (4, 4)), zorder=0)

    ax.set_xlim(float(np.min(grid_ms)) - 1.6, float(np.max(grid_ms)) + 1.6)
    ax.set_ylim(*ylim)
    ax.set_xticks(grid_ms)
    ax.set_xlabel(r"assigned delay  $\tau_L$  (ms)")

    ax.text(
        0.035,
        0.965,
        panel["note"],
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=9.0,
        color="#444444",
        style="italic",
    )

    ax.text(
        0.035,
        0.205,
        _decision_box_text(obj, summary),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=8.7,
        color="#222222",
        bbox=dict(boxstyle="round,pad=0.35", fc="#f7f7f9", ec="#d9d9de", lw=0.8),
    )

    ax.text(
        0.965,
        0.035,
        _rate_text(panel, summary),
        transform=ax.transAxes,
        va="bottom",
        ha="right",
        fontsize=8.7,
        color=color,
        fontweight="bold",
    )


def _draw_panel_headers(fig, panels: list[dict], axes) -> None:
    for panel, ax in zip(panels, axes):
        bb = ax.get_position()
        xc = bb.x0 + bb.width / 2.0

        fig.text(
            xc,
            bb.y1 + 0.205,
            panel["title"],
            ha="center",
            va="center",
            fontsize=12.5,
            fontweight="bold",
            color="#1a1a1a",
        )

        fig.text(
            xc,
            bb.y1 + 0.120,
            panel["banner"],
            ha="center",
            va="center",
            fontsize=10.5,
            fontweight="bold",
            color="white",
            bbox=dict(boxstyle="round,pad=0.45", fc=panel["color"], ec="none"),
        )

        fig.text(
            xc,
            bb.y1 + 0.045,
            panel["chips"],
            ha="center",
            va="center",
            fontsize=8.7,
            color="#333333",
        )


def _draw_leakage_inset(ax, leakage_obj: dict) -> None:
    """Draw the locked-run temporal-leakage audit inset in panel (c)."""
    aud = leakage_obj["out"].get("audits", {}).get("leakage", {})
    excursion = aud.get("excursion", None)
    r_crit = aud.get("r_crit", None)
    fired = bool(aud.get("fired", False))

    if excursion is None or r_crit is None:
        return

    excursion_pct = 100.0 * float(excursion)
    crit_pct = 100.0 * float(r_crit)

    ins = ax.inset_axes([0.32, 0.70, 0.55, 0.12])
    ins.barh([0], [excursion_pct], color=RED, alpha=0.85, height=0.7)
    ins.axvline(crit_pct, color="#222222", lw=1.4)

    ins.text(
        crit_pct - 7.0,
        1.05,
        f"crit {crit_pct:.1f}%",
        fontsize=7.0,
        color="#222222",
        va="bottom",
        ha="center",
    )

    fire_text = "fires" if fired else "passes"
    fire_mark = r"$\times$" if fired else r"$\checkmark$"

    ins.text(
        excursion_pct,
        0,
        f" {excursion_pct:.1f}%  {fire_mark} {fire_text}",
        fontsize=7.4,
        color=RED if fired else "#333333",
        va="center",
        ha="left",
        fontweight="bold",
    )

    xmax = max(9.5, excursion_pct * 1.25, crit_pct * 1.45)
    ins.set_xlim(0, xmax)
    ins.set_ylim(-0.6, 1.5)
    ins.set_yticks([])
    ins.tick_params(labelsize=6.3, length=2)
    ins.set_xlabel("leakage audit excursion (%)", fontsize=6.8, labelpad=1.5)
    ins.set_title("temporal-leakage audit", fontsize=7.2, color="#222222", pad=2)

    for side in ["top", "right", "left"]:
        ins.spines[side].set_visible(False)


def make_figure(
    panels: list[dict],
    summaries_by_scenario: dict[str, dict],
    representative_index: dict,
    run_hash: str,
    out_pdf: Path,
) -> Path:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10.5,
            "axes.linewidth": 0.9,
            "axes.edgecolor": "#333333",
            "xtick.color": "#333333",
            "ytick.color": "#333333",
        }
    )

    panel_objects = []

    for panel in panels:
        fname = panel["fname"]
        cfg = _load_yaml(ROOT / "configs" / f"{fname}.yaml")
        base_seed = representative_index[fname]["base_seed"]
        replicate = representative_index[fname]["replicate"]
        obj = _panel_objects(cfg, base_seed, replicate)
        panel_objects.append(obj)

    ylim = _choose_ylim(panel_objects)

    fig, axes = plt.subplots(1, len(panels), figsize=(13.4, 5.15), sharey=True)
    fig.subplots_adjust(left=0.065, right=0.985, top=0.685, bottom=0.135, wspace=0.10)

    for ax, panel, obj in zip(axes, panels, panel_objects):
        scenario = panel["scenario"]
        summary = summaries_by_scenario[scenario]
        _draw_panel(ax, panel, obj, summary, ylim)

    axes[0].set_ylabel(r"residual endpoint  $A_{\mathrm{pre}}^{\mathrm{resid}}$  ($\mu$V)")

    _draw_panel_headers(fig, panels, axes)
    _draw_leakage_inset(axes[2], panel_objects[2])

    fig.suptitle(
        "Synthetic validation of the Level II-A decision pipeline "
        "(simulated data; not human EEG)",
        fontsize=12.5,
        fontweight="bold",
        y=0.978,
        color="#111111",
    )

    fig.text(
        0.985,
        0.012,
        f"locked run {run_hash}",
        ha="right",
        va="bottom",
        fontsize=6.8,
        color="#666666",
    )

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_pdf, bbox_inches="tight")
    fig.savefig(str(out_pdf).replace(".pdf", ".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)

    return out_pdf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-hash", required=True)
    ap.add_argument("--outdir", default=str(ROOT / "outputs"))
    args = ap.parse_args()

    run_dir = Path(args.outdir) / args.run_hash
    if not run_dir.exists():
        raise FileNotFoundError(f"run directory not found: {run_dir}")

    representative_index = _load_json(run_dir / "summary" / "representative_index.json")

    summary_path = run_dir / "summary" / "operating_characteristics.csv"
    summ = pd.read_csv(summary_path)
    summaries_by_scenario = {row["scenario"]: row.to_dict() for _, row in summ.iterrows()}

    missing = [p["scenario"] for p in PANELS if p["scenario"] not in summaries_by_scenario]
    if missing:
        raise KeyError(f"missing scenarios in {summary_path}: {missing}")

    out_pdf = run_dir / "figures" / "figure2_validation.pdf"
    make_figure(PANELS, summaries_by_scenario, representative_index, args.run_hash, out_pdf)

    man = ROOT / "manuscript" / "figures"
    man.mkdir(parents=True, exist_ok=True)

    out_png = Path(str(out_pdf).replace(".pdf", ".png"))
    shutil.copy(out_pdf, man / "CRI_synthetic_validation.pdf")
    shutil.copy(out_png, man / "CRI_synthetic_validation.png")

    print(f"[make_figure2] wrote {out_pdf}")
    print("[make_figure2] copied manuscript/figures/CRI_synthetic_validation.pdf")
    print("[make_figure2] copied manuscript/figures/CRI_synthetic_validation.png")


if __name__ == "__main__":
    main()