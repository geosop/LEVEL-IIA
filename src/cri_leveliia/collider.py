"""Endpoint-by-delay collider-selection diagnostics.

A pure endpoint-by-delay collider makes the inclusion indicator depend on the
joint configuration of the committed endpoint and the assigned delay, with no
main delay effect on retention. The marginal retention rate by delay bin can then
stay flat while the *retained* endpoint distribution shifts across delay bins,
manufacturing a retained-sample slope although the full pre-selection sample
obeys the post-endpoint randomisation boundary.

The committed pre-event endpoint is available for every trial (it is computed
before the delay is assigned), so a retained-versus-excluded comparison and an
endpoint-by-delay interaction model for inclusion are both computable. These are
the predeclared diagnostics that detect the collider when the marginal-imbalance
gate cannot.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def _zscore(x):
    sd = x.std()
    return (x - x.mean()) / sd if sd > 0 else np.zeros_like(x)


def _logit_irls_clustered(
    X,
    y,
    cluster,
    iters=100,
    ridge=1e-8,
    tol=1e-9,
):
    """Logistic IRLS with participant-clustered CR1 covariance."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    cluster = np.asarray(cluster)
    n, q = X.shape
    groups = np.unique(cluster)
    if y.shape != (n,) or cluster.shape != (n,):
        raise ValueError("X, y, and cluster have incompatible shapes")
    if groups.size < 3:
        raise ValueError("at least three participant clusters are required")
    if n <= q:
        raise ValueError("the collider inclusion model is not estimable")

    beta = np.zeros(q, dtype=float)
    converged = False
    penalty = ridge * np.eye(q)
    penalty[0, 0] = 0.0
    for _ in range(iters):
        eta = X @ beta
        eta = np.clip(eta, -30, 30)
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(mu * (1 - mu), 1e-6, None)
        z = eta + (y - mu) / w
        WX = X * w[:, None]
        H = X.T @ WX + penalty
        g = X.T @ (w * z)
        new = np.linalg.solve(H, g)
        if np.max(np.abs(new - beta)) < tol:
            beta = new
            converged = True
            break
        beta = new
    if not converged:
        raise RuntimeError("clustered logistic IRLS did not converge")

    eta = np.clip(X @ beta, -30, 30)
    mu = 1.0 / (1.0 + np.exp(-eta))
    w = np.clip(mu * (1 - mu), 1e-6, None)
    bread = np.linalg.inv(X.T @ (X * w[:, None]) + penalty)
    score = X * (y - mu)[:, None]
    meat = np.zeros((q, q), dtype=float)
    for group in groups:
        cluster_score = np.sum(score[cluster == group], axis=0)
        meat += np.outer(cluster_score, cluster_score)

    cr1 = (groups.size / (groups.size - 1.0)) * ((n - 1.0) / (n - q))
    cov = cr1 * (bread @ meat @ bread)
    cov = 0.5 * (cov + cov.T)
    se = np.sqrt(np.diag(cov))
    if np.any(~np.isfinite(beta)) or np.any(~np.isfinite(se)) or np.any(se <= 0):
        raise RuntimeError("non-finite clustered logistic coefficient or standard error")
    return beta, se, {
        "converged": True,
        "n_rows": int(n),
        "n_parameters": int(q),
        "n_clusters": int(groups.size),
        "covariance": "participant_clustered_CR1",
    }


def _participant_fixed_effects(participant):
    participant = np.asarray(participant)
    levels = np.unique(participant)
    if levels.size < 2:
        raise ValueError("participant fixed effects require at least two participants")
    return np.column_stack(
        [(participant == level).astype(float) for level in levels[1:]]
    )


def _delay_main_effects(bin_index):
    bin_index = np.asarray(bin_index)
    levels = np.unique(bin_index)
    if levels.size < 2:
        raise ValueError("delay main effects require at least two bins")
    return np.column_stack(
        [(bin_index == level).astype(float) for level in levels[1:]]
    )


def interaction_diagnostic(ds, z_thresh=3.0):
    """Endpoint-by-delay interaction in the inclusion model.

    Fits the prospectively fixed model over all assigned trials:

    S ~ participant fixed effects + cubic endpoint basis + categorical delay
        main effects + z(A_pre):z(tau_assigned).

    The interaction coefficient is tested with participant-clustered CR1
    uncertainty. Numerical failure fires conservatively.
    """
    A = _zscore(ds.A_pre)
    d = _zscore(ds.tau_assigned - ds.meta["grid_mean"])
    inter = A * d
    endpoint_basis = np.column_stack(
        [
            A,
            A ** 2 - 1.0,
            A ** 3 - 3.0 * A,
        ]
    )
    participant_fe = _participant_fixed_effects(ds.participant)
    delay_main = _delay_main_effects(ds.bin_index)
    X = np.column_stack(
        [
            np.ones_like(A),
            participant_fe,
            endpoint_basis,
            delay_main,
            inter,
        ]
    )
    y = ds.S.astype(float)
    if y.sum() == 0 or y.sum() == y.size:
        return {
            "z": np.nan,
            "p": np.nan,
            "coef": np.nan,
            "se": np.nan,
            "fired": True,
            "valid": False,
            "reason": "inclusion indicator is constant",
            "z_thresh": float(z_thresh),
        }
    try:
        beta, se, fit = _logit_irls_clustered(
            X,
            y,
            cluster=ds.participant,
        )
        idx = X.shape[1] - 1
        zval = float(beta[idx] / se[idx])
        pval = float(2.0 * stats.norm.sf(abs(zval)))
        return {
            "z": zval,
            "p": pval,
            "coef": float(beta[idx]),
            "se": float(se[idx]),
            "fired": bool(abs(zval) > z_thresh),
            "valid": True,
            "reason": "ok",
            "z_thresh": float(z_thresh),
            **fit,
        }
    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
        return {
            "z": np.nan,
            "p": np.nan,
            "coef": np.nan,
            "se": np.nan,
            "fired": True,
            "valid": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "z_thresh": float(z_thresh),
        }


def retained_excluded_smd(ds, smd_thresh=0.30, alpha=1e-3):
    """Retained-versus-excluded committed-endpoint difference within delay bins.

    Within each delay bin, participant-level retained-minus-excluded endpoint
    contrasts are formed for participants contributing both groups. A two-sided
    one-sample t-test is applied to those participant contrasts and Bonferroni
    familywise alpha is used across bins. The maximum trial-level standardised
    mean difference remains descriptive.
    """
    bins = ds.bin_index
    nb = int(bins.max()) + 1
    worst_smd, worst_t = 0.0, 0.0
    pvalues = []
    participants_by_bin = []
    for b in range(nb):
        m = bins == b
        A = ds.A_pre[m]
        s = ds.S[m]
        part = ds.participant[m]
        nret, nexc = int((s == 1).sum()), int((s == 0).sum())
        if nret >= 2 and nexc >= 2:
            ar, ae = A[s == 1], A[s == 0]
            sd = A.std(ddof=1)
            if sd > 0:
                worst_smd = max(
                    worst_smd,
                    abs(ar.mean() - ae.mean()) / sd,
                )

        contrasts = []
        for pid in np.unique(part):
            mp = part == pid
            ar = A[mp & (s == 1)]
            ae = A[mp & (s == 0)]
            if ar.size and ae.size:
                contrasts.append(float(ar.mean() - ae.mean()))
        contrasts = np.asarray(contrasts, dtype=float)
        participants_by_bin.append(int(contrasts.size))
        if contrasts.size < 3:
            pvalues.append(np.nan)
            continue
        se = float(np.std(contrasts, ddof=1) / np.sqrt(contrasts.size))
        if not np.isfinite(se) or se <= 0:
            pvalues.append(np.nan)
            continue
        tval = float(np.mean(contrasts) / se)
        pval = float(
            2.0 * stats.t.sf(abs(tval), df=contrasts.size - 1)
        )
        worst_t = max(worst_t, abs(tval))
        pvalues.append(pval)

    finite_p = np.asarray(pvalues, dtype=float)
    valid = np.isfinite(finite_p)
    if not np.any(valid):
        return {
            "max_smd": float(worst_smd),
            "max_t": np.nan,
            "min_p": np.nan,
            "fired": True,
            "valid": False,
            "reason": "no delay bin had at least three paired participant contrasts",
            "thresh": float(smd_thresh),
            "familywise_alpha": float(alpha),
            "per_bin_alpha": float(alpha / nb),
            "participants_by_bin": participants_by_bin,
        }

    min_p = float(np.nanmin(finite_p))
    return {
        "max_smd": float(worst_smd),
        "max_t": float(worst_t),
        "min_p": min_p,
        "fired": bool(min_p < alpha / nb),
        "valid": True,
        "reason": "ok",
        "thresh": float(smd_thresh),
        "familywise_alpha": float(alpha),
        "per_bin_alpha": float(alpha / nb),
        "participants_by_bin": participants_by_bin,
    }


def retained_rank_imbalance(ds, z_thresh=3.0):
    """Association between within-participant rank of the retained committed
    endpoint and the centred assigned delay. Detects a retained-endpoint shift
    across delay bins even when retained counts are balanced."""
    ret = ds.S == 1
    part = ds.participant[ret]
    A = ds.A_pre[ret]
    d = ds.tau_assigned[ret] - ds.meta["grid_mean"]
    ranks = np.empty_like(A)
    for pid in np.unique(part):
        m = part == pid
        order = np.argsort(np.argsort(A[m]))
        ranks[m] = (order - order.mean()) / (order.std() + 1e-9)
    if d.std() == 0:
        return {"z": 0.0, "fired": False, "z_thresh": z_thresh}
    r = np.corrcoef(ranks, d)[0, 1]
    n = ranks.size
    zval = float(r * np.sqrt(max(n - 2, 1)) / np.sqrt(max(1 - r ** 2, 1e-9)))
    return {"z": zval, "corr": float(r),
            "fired": bool(abs(zval) > z_thresh), "z_thresh": z_thresh}


def run_collider_diagnostics(ds, cfg):
    inter = interaction_diagnostic(ds, z_thresh=cfg.get("interaction_z", 3.0))
    smd = retained_excluded_smd(
        ds,
        smd_thresh=cfg.get("smd_thresh", 0.30),
        alpha=cfg.get("collider_smd_alpha", 1e-3),
    )
    rank = retained_rank_imbalance(ds, z_thresh=cfg.get("rank_z", 3.0))
    # The block fires on diagnostics of the INCLUSION mechanism, which
    # distinguish collider selection from a genuine endpoint-level residual: the
    # endpoint-by-delay interaction in inclusion, and the retained-versus-excluded
    # within-bin endpoint difference. The retained-sample rank imbalance is
    # reported as a descriptive statistic only, because a genuine injected
    # residual also shifts retained endpoints across delay bins and would trip it.
    invalid = (not inter["valid"]) or (not smd["valid"])
    fired = inter["fired"] or smd["fired"] or invalid
    reasons = [
        result["reason"]
        for result in (inter, smd)
        if not result["valid"]
    ]
    return {
        "interaction": inter,
        "smd": smd,
        "rank": rank,
        "invalid": bool(invalid),
        "reason": "ok" if not reasons else "; ".join(reasons),
        "fired": bool(fired),
    }
