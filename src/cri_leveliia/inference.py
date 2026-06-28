"""Confirmatory estimand and inference.

Participant-level slope estimand, plus-one randomisation test (assignment
isolation), and a studentised participant bootstrap-t confidence bound (upper
bound for the directional test, sign-reversed lower bound for opposite-direction
departures). All routines operate on the frozen residual array; the comparator is
never refit inside the test loop.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


# --------------------------------------------------------------------------- #
# Estimand
# --------------------------------------------------------------------------- #
def participant_slopes(resid, participant, tau_centered):
    """Return per-participant slopes, denominators, and the equal-participant
    estimate.

    beta_p = sum_j d_pj r_pj / sum_j d_pj^2, with d the centred assigned delay.
    Participants with zero delay variance are dropped.
    """
    uniq = np.unique(participant)
    slopes, denoms, keep = [], [], []
    for pid in uniq:
        m = participant == pid
        d = tau_centered[m]
        r = resid[m]
        den = np.sum(d * d)
        if den <= 0 or not np.isfinite(den):
            continue
        slopes.append(np.sum(d * r) / den)
        denoms.append(den)
        keep.append(pid)
    slopes = np.asarray(slopes)
    denoms = np.asarray(denoms)
    beta_tau = float(np.mean(slopes)) if slopes.size else np.nan
    return slopes, denoms, np.asarray(keep), beta_tau


# --------------------------------------------------------------------------- #
# Randomisation test (assignment isolation, within-participant permutation)
# --------------------------------------------------------------------------- #
def randomisation_pvalue(resid, participant, tau_centered, beta_obs,
                         R=1499, rng=None, alternative="less"):
    """One-sided plus-one randomisation p-value.

    The residuals are frozen; the centred assigned delay is permuted within each
    participant block (post-endpoint exchangeability), the equal-participant
    estimate is recomputed for each of R replicates, and the plus-one p-value is
    formed. ``alternative='less'`` tests for a negative slope.
    """
    if rng is None:
        rng = np.random.default_rng(0)

    order = np.argsort(participant, kind="stable")
    part = participant[order]
    d = tau_centered[order]
    r = resid[order]

    # block structure (contiguous after sort)
    starts = np.flatnonzero(np.r_[True, part[1:] != part[:-1]])
    block_id = np.zeros(part.shape[0], dtype=float)
    block_id[starts[1:]] = 1.0
    block_id = np.cumsum(block_id)
    P = starts.shape[0]

    # per-block denominators
    denom = np.add.reduceat(d * d, starts)
    valid = denom > 0
    if valid.sum() == 0:
        return np.nan, np.array([])

    # within-block permutation via offset argsort
    U = rng.random((R, part.shape[0]))
    keys = block_id[None, :] * 2.0 + U
    perm = np.argsort(keys, axis=1, kind="stable")
    d_perm = d[perm]                                   # (R, N)
    prod = d_perm * r[None, :]                          # (R, N)
    numer = np.add.reduceat(prod, starts, axis=1)       # (R, P)
    slopes_perm = numer / denom[None, :]
    beta_perm = slopes_perm[:, valid].mean(axis=1)      # (R,)

    if alternative == "less":
        ge = np.sum(beta_perm <= beta_obs)
    else:
        ge = np.sum(beta_perm >= beta_obs)
    p = (1.0 + ge) / (R + 1.0)
    return float(p), beta_perm


# --------------------------------------------------------------------------- #
# Studentised participant bootstrap-t
# --------------------------------------------------------------------------- #
def bootstrap_bounds(slopes, B=1499, rng=None, level=0.95):
    """Studentised participant bootstrap-t bounds plus BCa and t-interval
    sensitivity bounds.

    Returns a dict with the equal-participant estimate, its standard error, the
    bootstrap-t upper and lower confidence bounds, and BCa/t-interval upper
    bounds for sensitivity.
    """
    if rng is None:
        rng = np.random.default_rng(0)
    P = slopes.shape[0]
    beta = float(np.mean(slopes))
    se = float(np.std(slopes, ddof=1) / np.sqrt(P)) if P > 1 else np.nan
    alpha = 1.0 - level

    idx = rng.integers(0, P, size=(B, P))
    bs = slopes[idx]
    beta_star = bs.mean(axis=1)
    se_star = bs.std(axis=1, ddof=1) / np.sqrt(P)
    with np.errstate(divide="ignore", invalid="ignore"):
        t_star = np.where(se_star > 0, (beta_star - beta) / se_star, 0.0)

    q_lo = np.percentile(t_star, 100 * alpha)        # ~5th percentile (negative)
    q_hi = np.percentile(t_star, 100 * (1 - alpha))  # ~95th percentile (positive)
    ucb = beta - q_lo * se      # upper confidence bound (directional, negative test)
    lcb = beta - q_hi * se      # lower confidence bound (opposite-direction test)

    # t-interval sensitivity
    tcrit = stats.t.ppf(level, df=max(P - 1, 1))
    ucb_t = beta + tcrit * se
    lcb_t = beta - tcrit * se

    # BCa upper bound sensitivity
    z0 = stats.norm.ppf(np.clip(np.mean(beta_star < beta), 1e-6, 1 - 1e-6))
    jk = np.array([np.mean(np.delete(slopes, i)) for i in range(P)])
    jk_mean = jk.mean()
    num = np.sum((jk_mean - jk) ** 3)
    den = 6.0 * (np.sum((jk_mean - jk) ** 2) ** 1.5 + 1e-18)
    acc = num / den
    zq = stats.norm.ppf(level)
    adj = z0 + (z0 + zq) / (1 - acc * (z0 + zq))
    pct = stats.norm.cdf(adj)
    ucb_bca = float(np.percentile(beta_star, 100 * pct))

    return {
        "beta": beta, "se": se,
        "q_lo": float(q_lo), "q_hi": float(q_hi),
        "ucb": float(ucb), "lcb": float(lcb),
        "ucb_t": float(ucb_t), "lcb_t": float(lcb_t),
        "ucb_bca": ucb_bca,
    }


# --------------------------------------------------------------------------- #
# Resolution floor
# --------------------------------------------------------------------------- #
def beta_min(sigma_blind, sigma_tau, nbar_ret, kappa=2.0):
    """Single-participant resolution floor.

    beta_min = kappa * sigma_blind / (sigma_tau * sqrt(nbar_ret)). This is the
    label-blind resolvability of one participant's slope, not a population alpha
    threshold.
    """
    return float(kappa * sigma_blind / (sigma_tau * np.sqrt(nbar_ret)))


def normal_equivalent_stringency(bmin, se_pop):
    """Phi[-(beta_min/se_pop + 1.645)]: the normal-null approximation to the
    materiality-gate exceedance probability. Reported for interpretation only;
    the confirmatory calibration is design-based (randomisation and simulation).
    """
    from scipy.stats import norm
    return float(norm.cdf(-(bmin / se_pop + 1.645)))
