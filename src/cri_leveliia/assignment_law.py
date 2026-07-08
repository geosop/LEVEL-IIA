"""Conditional assignment laws for Level II-A inference routes.

The sequential e-value route must use the assignment distribution available just
before the current assigned-delay draw. This module reconstructs that law from
locked design information. It does not inspect endpoints, residuals, or
post-assignment diagnostics.
"""

from __future__ import annotations

import numpy as np


def _stable_unique_grid(x: np.ndarray) -> np.ndarray:
    """Return sorted unique support values as floats."""
    return np.asarray(np.unique(np.asarray(x, dtype=float)), dtype=float)


def fixed_multiset_without_replacement(ds):
    """Conditional law for balanced within-participant delay multisets.

    For each participant, the planned support is the participant's observed
    assigned-delay multiset. Before trial j, the conditional probability of each
    support value is its remaining count divided by the remaining total.

    Returns arrays in original dataset row order. The final deterministic draw
    has variance zero and is marked invalid for sequential slope estimation, but
    it is still represented with its degenerate conditional law.
    """
    tau = np.asarray(ds.tau_assigned, dtype=float)
    participant = np.asarray(ds.participant)
    if hasattr(ds, "trial_index"):
        trial_index = np.asarray(ds.trial_index)
    else:
        trial_index = np.zeros_like(participant, dtype=int)
        for pid in np.unique(participant):
            m = np.flatnonzero(participant == pid)
            trial_index[m] = np.arange(m.size)

    grid = _stable_unique_grid(getattr(ds, "grid_s", tau))
    K = grid.size
    N = tau.size
    support = np.tile(grid, (N, 1))
    prob = np.zeros((N, K), dtype=float)
    mu = np.full(N, np.nan, dtype=float)
    var = np.full(N, np.nan, dtype=float)
    valid = np.zeros(N, dtype=bool)
    reason = "ok"

    for pid in np.unique(participant):
        rows = np.flatnonzero(participant == pid)
        rows = rows[np.argsort(trial_index[rows], kind="stable")]
        planned = np.array([np.sum(np.isclose(tau[rows], g, rtol=0.0, atol=1e-12))
                            for g in grid], dtype=int)
        remaining = planned.astype(int).copy()
        for row in rows:
            total = int(remaining.sum())
            if total <= 0:
                reason = "empty remaining assignment multiset"
                continue
            p = remaining / total
            prob[row, :] = p
            mu[row] = float(np.sum(p * grid))
            var[row] = float(np.sum(p * (grid - mu[row]) ** 2))
            hit = np.flatnonzero(np.isclose(grid, tau[row], rtol=0.0, atol=1e-12))
            if hit.size != 1:
                reason = "observed assignment not in declared support"
                continue
            if remaining[hit[0]] <= 0:
                reason = "observed assignment exhausted in conditional law"
                continue
            valid[row] = var[row] > 0.0 and np.isfinite(var[row])
            remaining[hit[0]] -= 1

    return {
        "support": support,
        "prob": prob,
        "mu": mu,
        "var": var,
        "valid": valid,
        "law_type": "fixed_multiset_without_replacement",
        "reason": reason,
    }


def conditional_assignment_table(ds, cfg):
    """Return the current-trial conditional assignment law in dataset row order.

    Currently supported:
        assignment_law.type: fixed_multiset_without_replacement
        assignment_law.within: participant
    """
    law_cfg = cfg.get("assignment_law", {}) or {}
    law_type = law_cfg.get("type", "fixed_multiset_without_replacement")
    within = law_cfg.get("within", "participant")
    if law_type != "fixed_multiset_without_replacement":
        raise ValueError(f"unsupported assignment_law.type: {law_type}")
    if within != "participant":
        raise ValueError(f"unsupported assignment_law.within: {within}")
    return fixed_multiset_without_replacement(ds)
