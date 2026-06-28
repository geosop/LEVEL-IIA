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


def _logit_irls(X, y, iters=50, ridge=1e-6):
    """Compact IRLS logistic regression. Returns coefficients and their standard
    errors (from the inverse Fisher information)."""
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = X @ beta
        eta = np.clip(eta, -30, 30)
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(mu * (1 - mu), 1e-6, None)
        z = eta + (y - mu) / w
        WX = X * w[:, None]
        H = X.T @ WX + ridge * np.eye(X.shape[1])
        g = X.T @ (w * z)
        new = np.linalg.solve(H, g)
        if np.max(np.abs(new - beta)) < 1e-8:
            beta = new
            break
        beta = new
    eta = np.clip(X @ beta, -30, 30)
    mu = 1.0 / (1.0 + np.exp(-eta))
    w = np.clip(mu * (1 - mu), 1e-6, None)
    cov = np.linalg.inv(X.T @ (X * w[:, None]) + ridge * np.eye(X.shape[1]))
    se = np.sqrt(np.diag(cov))
    return beta, se


def interaction_diagnostic(ds, z_thresh=3.0):
    """Endpoint-by-delay interaction in the inclusion model.

    Fits S ~ z(A_pre) + z(tau_c) + z(A_pre):z(tau_c) over ALL trials and tests
    the interaction coefficient. The interaction is the signature of an
    endpoint-by-delay collider.
    """
    A = _zscore(ds.A_pre)
    d = _zscore(ds.tau_assigned - ds.meta["grid_mean"])
    inter = A * d
    X = np.column_stack([np.ones_like(A), A, d, inter])
    y = ds.S.astype(float)
    if y.sum() == 0 or y.sum() == y.size:
        return {"z": 0.0, "coef": 0.0, "fired": False, "z_thresh": z_thresh}
    beta, se = _logit_irls(X, y)
    zval = float(beta[3] / se[3]) if se[3] > 0 else 0.0
    return {"z": zval, "coef": float(beta[3]),
            "fired": bool(abs(zval) > z_thresh), "z_thresh": z_thresh}


def retained_excluded_smd(ds, smd_thresh=0.30, alpha=1e-3):
    """Retained-versus-excluded committed-endpoint difference within delay bins.

    For each bin a Welch t-statistic compares the committed endpoint of retained
    and excluded trials. Firing uses the maximum |t| against a Bonferroni-adjusted
    normal threshold across bins, so the false-firing rate is controlled at every
    sample size. The maximum standardised mean difference is reported as a
    descriptive statistic. A genuine injected residual does not trip this test,
    because under random retention the retained and excluded endpoints share a
    distribution within a bin; a collider does, because inclusion depends on the
    endpoint within off-centre bins.
    """
    bins = ds.bin_index
    nb = int(bins.max()) + 1
    worst_smd, worst_t = 0.0, 0.0
    for b in range(nb):
        m = bins == b
        A = ds.A_pre[m]
        s = ds.S[m]
        nret, nexc = int((s == 1).sum()), int((s == 0).sum())
        if nret < 5 or nexc < 5:
            continue
        ar, ae = A[s == 1], A[s == 0]
        sd = A.std()
        if sd > 0:
            worst_smd = max(worst_smd, abs(ar.mean() - ae.mean()) / sd)
        vr, ve = ar.var(ddof=1), ae.var(ddof=1)
        se = np.sqrt(vr / nret + ve / nexc)
        if se > 0:
            worst_t = max(worst_t, abs(ar.mean() - ae.mean()) / se)
    z_crit = stats.norm.ppf(1 - alpha / (2 * nb))
    return {"max_smd": float(worst_smd), "max_t": float(worst_t),
            "fired": bool(worst_t > z_crit), "thresh": smd_thresh,
            "z_crit": float(z_crit)}


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
    smd = retained_excluded_smd(ds, smd_thresh=cfg.get("smd_thresh", 0.30))
    rank = retained_rank_imbalance(ds, z_thresh=cfg.get("rank_z", 3.0))
    # The block fires on diagnostics of the INCLUSION mechanism, which
    # distinguish collider selection from a genuine endpoint-level residual: the
    # endpoint-by-delay interaction in inclusion, and the retained-versus-excluded
    # within-bin endpoint difference. The retained-sample rank imbalance is
    # reported as a descriptive statistic only, because a genuine injected
    # residual also shifts retained endpoints across delay bins and would trip it.
    fired = inter["fired"] or smd["fired"]
    return {"interaction": inter, "smd": smd, "rank": rank, "fired": fired}
