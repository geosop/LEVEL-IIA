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
from scipy.special import logsumexp


# --------------------------------------------------------------------------- #
# Estimand
# --------------------------------------------------------------------------- #


def center_within_participant(values, participant):
    """Centre a trial-level design variable within participant.

    The assignment-isolation slope includes a participant/stratum intercept, so
    the retained assigned-delay regressor must sum to zero within each retained
    participant rather than merely around the planned grid mean.
    """
    values = np.asarray(values, dtype=float)
    participant = np.asarray(participant)
    if values.shape != participant.shape:
        raise ValueError("values and participant must have the same shape")
    out = np.full(values.shape, np.nan, dtype=float)
    for pid in np.unique(participant):
        m = participant == pid
        finite = m & np.isfinite(values)
        if np.any(finite):
            out[finite] = values[finite] - np.mean(values[finite])
    return out

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

    This routine is valid only for the assignment-isolation route, where the
    frozen residual array is invariant under admissible reassignment of the
    assigned-delay labels. It is not valid for carryover-sensitive designs in
    which assigned labels may affect later endpoints or histories.

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
# Sequential martingale/e-value route for carryover-sensitive designs
# --------------------------------------------------------------------------- #
def participant_sequential_slopes(resid, participant, delta_tau, var_tau):
    """Return participant-level sequential-score slopes.

    beta_seq_p = sum_j r_pj * (tau_pj - E[tau_pj | F_pre_pj])
                 / sum_j Var(tau_pj | F_pre_pj).

    Trials with nonpositive conditional assignment variance are excluded from
    the denominator and numerator. Participants with zero total conditional
    variance are dropped. This estimand is used by the sequential e-value route
    and is not a frozen-array permutation estimand.
    """
    resid = np.asarray(resid, dtype=float)
    participant = np.asarray(participant)
    delta_tau = np.asarray(delta_tau, dtype=float)
    var_tau = np.asarray(var_tau, dtype=float)
    uniq = np.unique(participant)
    slopes, denoms, keep = [], [], []
    for pid in uniq:
        m = (participant == pid) & np.isfinite(resid) & np.isfinite(delta_tau) & np.isfinite(var_tau) & (var_tau > 0)
        den = float(np.sum(var_tau[m]))
        if den <= 0 or not np.isfinite(den):
            continue
        slopes.append(float(np.sum(resid[m] * delta_tau[m]) / den))
        denoms.append(den)
        keep.append(pid)
    slopes = np.asarray(slopes, dtype=float)
    denoms = np.asarray(denoms, dtype=float)
    beta_tau = float(np.mean(slopes)) if slopes.size else np.nan
    return slopes, denoms, np.asarray(keep), beta_tau


def _normalise_evalue_weights(lambda_grid, weights):
    lam = np.asarray(lambda_grid, dtype=float)
    if lam.ndim != 1 or lam.size == 0 or np.any(~np.isfinite(lam)) or np.any(lam <= 0):
        raise ValueError("lambda_grid must be a nonempty one-dimensional array of positive finite values")
    if weights is None or (isinstance(weights, str) and weights == "equal"):
        w = np.ones(lam.size, dtype=float) / lam.size
    else:
        w = np.asarray(weights, dtype=float)
        if w.shape != lam.shape:
            raise ValueError("weights must have the same length as lambda_grid")
        if np.any(w < 0) or not np.any(w > 0):
            raise ValueError("weights must be nonnegative with at least one positive entry")
        w = w / np.sum(w)
    return lam, w


def _normalise_fold_weights(fold_ids, weights):
    folds = np.asarray(sorted(np.unique(fold_ids)), dtype=int)
    if folds.size < 2:
        raise ValueError("sequential fold mixture requires at least two folds")
    if weights is None or (isinstance(weights, str) and weights == "equal"):
        w = np.ones(folds.size, dtype=float) / folds.size
    else:
        w = np.asarray(weights, dtype=float)
        if w.shape != folds.shape:
            raise ValueError("fold_weights must have one value per observed fold")
        if np.any(w < 0) or not np.any(w > 0):
            raise ValueError(
                "fold_weights must be nonnegative with at least one positive entry"
            )
        w = w / np.sum(w)
    return folds, w


def sequential_evalue_pvalue(resid, tau_obs, support, prob, mu, participant=None,
                             fold=None, fold_weights=None, lambda_grid=None,
                             weights=None, alternative="less"):
    """Cross-fitted sequential e-value mixture.

    Each fold product is evaluated using residuals predicted by a comparator
    trained entirely outside that participant fold. Lambda-specific products are
    combined by a fixed convex mixture within fold; fold e-values are then
    combined by a second fixed convex mixture. Fold products are never
    multiplied together.

    Parameters
    ----------
    resid : array-like, shape (n,)
        Frozen residuals on prospectively included trials. Final estimability
        must not select these rows.
    tau_obs : array-like, shape (n,)
        Observed assigned delays on retained trials.
    support : array-like, shape (n, k)
        Conditional support values for each retained trial.
    prob : array-like, shape (n, k)
        Conditional probabilities for each retained trial.
    mu : array-like, shape (n,)
        Conditional assignment mean for each retained trial.
    participant : array-like, shape (n,)
        Participant identifiers, used for fold provenance summaries.
    fold : array-like, shape (n,)
        Prospectively fixed participant fold for each term.
    fold_weights : array-like or "equal"
        Fixed convex mixture weights over observed folds.
    lambda_grid : array-like
        Predeclared positive e-value tuning grid.
    weights : array-like or "equal"
        Convex mixture weights over lambda_grid.
    alternative : {"less", "greater"}
        "less" tests a negative assigned-delay slope.

    Returns
    -------
    dict
        p_seq, log_e_mix, per-fold log e-values, tuning grids, term and
        participant counts, validity flag, and reason.
    """
    if lambda_grid is None:
        lambda_grid = np.array([1, 2, 5, 10, 20, 50, 100, 200], dtype=float)
    lam, w = _normalise_evalue_weights(lambda_grid, weights)

    resid = np.asarray(resid, dtype=float)
    tau_obs = np.asarray(tau_obs, dtype=float)
    support = np.asarray(support, dtype=float)
    prob = np.asarray(prob, dtype=float)
    mu = np.asarray(mu, dtype=float)
    if participant is None:
        participant = np.arange(resid.size, dtype=int)
    participant = np.asarray(participant)
    if fold is None:
        return {
            "p_seq": 1.0,
            "log_e_mix": -np.inf,
            "log_e_grid": np.full((0, lam.size), -np.inf),
            "log_e_fold": np.asarray([], dtype=float),
            "lambda_grid": lam,
            "weights": w,
            "fold_ids": np.asarray([], dtype=int),
            "fold_weights": np.asarray([], dtype=float),
            "n_terms": 0,
            "n_terms_by_fold": np.asarray([], dtype=int),
            "n_participants": 0,
            "n_participants_by_fold": np.asarray([], dtype=int),
            "valid": False,
            "reason": "prospectively fixed fold assignments are required",
        }
    fold = np.asarray(fold)

    if support.shape != prob.shape or support.ndim != 2:
        return {
            "p_seq": 1.0,
            "log_e_mix": -np.inf,
            "log_e_grid": np.full((0, lam.size), -np.inf),
            "log_e_fold": np.asarray([], dtype=float),
            "lambda_grid": lam,
            "weights": w,
            "fold_ids": np.asarray([], dtype=int),
            "fold_weights": np.asarray([], dtype=float),
            "n_terms": 0,
            "n_terms_by_fold": np.asarray([], dtype=int),
            "n_participants": 0,
            "n_participants_by_fold": np.asarray([], dtype=int),
            "valid": False,
            "reason": (
                "support and prob must be two-dimensional arrays with matching shape"
            ),
        }
    n_rows = resid.size
    one_dimensional = [tau_obs, mu, participant, fold]
    if any(np.asarray(x).shape != (n_rows,) for x in one_dimensional):
        return {
            "p_seq": 1.0,
            "log_e_mix": -np.inf,
            "log_e_grid": np.full((0, lam.size), -np.inf),
            "log_e_fold": np.asarray([], dtype=float),
            "lambda_grid": lam,
            "weights": w,
            "fold_ids": np.asarray([], dtype=int),
            "fold_weights": np.asarray([], dtype=float),
            "n_terms": 0,
            "n_terms_by_fold": np.asarray([], dtype=int),
            "n_participants": 0,
            "n_participants_by_fold": np.asarray([], dtype=int),
            "valid": False,
            "reason": "all one-dimensional inputs must have the same length",
        }
    if support.shape[0] != n_rows:
        return {
            "p_seq": 1.0,
            "log_e_mix": -np.inf,
            "log_e_grid": np.full((0, lam.size), -np.inf),
            "log_e_fold": np.asarray([], dtype=float),
            "lambda_grid": lam,
            "weights": w,
            "fold_ids": np.asarray([], dtype=int),
            "fold_weights": np.asarray([], dtype=float),
            "n_terms": 0,
            "n_terms_by_fold": np.asarray([], dtype=int),
            "n_participants": 0,
            "n_participants_by_fold": np.asarray([], dtype=int),
            "valid": False,
            "reason": "support rows must match the residual length",
        }

    finite = (np.isfinite(resid) & np.isfinite(tau_obs) & np.isfinite(mu) &
              np.all(np.isfinite(support), axis=1) & np.all(np.isfinite(prob), axis=1) &
              np.isclose(np.sum(prob, axis=1), 1.0, atol=1e-8) &
              np.all(prob >= -1e-12, axis=1))
    finite &= np.any(prob > 0, axis=1)
    if not np.any(finite):
        return {
            "p_seq": 1.0,
            "log_e_mix": -np.inf,
            "log_e_grid": np.full((0, lam.size), -np.inf),
            "log_e_fold": np.asarray([], dtype=float),
            "lambda_grid": lam,
            "weights": w,
            "fold_ids": np.asarray([], dtype=int),
            "fold_weights": np.asarray([], dtype=float),
            "n_terms": 0,
            "n_terms_by_fold": np.asarray([], dtype=int),
            "n_participants": 0,
            "n_participants_by_fold": np.asarray([], dtype=int),
            "valid": False,
            "reason": "no valid conditional assignment rows",
        }

    r = resid[finite]
    t = tau_obs[finite]
    s = support[finite]
    p = np.clip(prob[finite], 0.0, 1.0)
    p = p / p.sum(axis=1, keepdims=True)
    m = mu[finite]
    part = participant[finite]
    fold_valid = fold[finite].astype(int)
    n = r.size

    try:
        fold_ids, fold_w = _normalise_fold_weights(
            fold_valid,
            fold_weights,
        )
    except ValueError as exc:
        return {
            "p_seq": 1.0,
            "log_e_mix": -np.inf,
            "log_e_grid": np.full((0, lam.size), -np.inf),
            "log_e_fold": np.asarray([], dtype=float),
            "lambda_grid": lam,
            "weights": w,
            "fold_ids": np.asarray([], dtype=int),
            "fold_weights": np.asarray([], dtype=float),
            "n_terms": int(n),
            "n_terms_by_fold": np.asarray([], dtype=int),
            "n_participants": int(np.unique(part).size),
            "n_participants_by_fold": np.asarray([], dtype=int),
            "valid": False,
            "reason": str(exc),
        }

    for pid in np.unique(part):
        if np.unique(fold_valid[part == pid]).size != 1:
            return {
                "p_seq": 1.0,
                "log_e_mix": -np.inf,
                "log_e_grid": np.full((0, lam.size), -np.inf),
                "log_e_fold": np.asarray([], dtype=float),
                "lambda_grid": lam,
                "weights": w,
                "fold_ids": fold_ids,
                "fold_weights": fold_w,
                "n_terms": int(n),
                "n_terms_by_fold": np.asarray([], dtype=int),
                "n_participants": int(np.unique(part).size),
                "n_participants_by_fold": np.asarray([], dtype=int),
                "valid": False,
                "reason": "a participant appears in more than one e-value fold",
            }

    if alternative not in {"less", "greater"}:
        raise ValueError("alternative must be 'less' or 'greater'")
    sign = -1.0 if alternative == "less" else 1.0
    x_obs = sign * r * (t - m)
    z_support = sign * r[:, None] * (s - m[:, None])
    with np.errstate(divide="ignore"):
        log_p = np.where(p > 0.0, np.log(p), -np.inf)

    log_e_grid = np.empty((fold_ids.size, lam.size), dtype=float)
    log_e_fold = np.empty(fold_ids.size, dtype=float)
    n_terms_by_fold = np.empty(fold_ids.size, dtype=int)
    n_participants_by_fold = np.empty(fold_ids.size, dtype=int)

    for i, fold_id in enumerate(fold_ids):
        in_fold = fold_valid == fold_id
        n_terms_by_fold[i] = int(np.sum(in_fold))
        n_participants_by_fold[i] = int(np.unique(part[in_fold]).size)
        if n_terms_by_fold[i] == 0:
            return {
                "p_seq": 1.0,
                "log_e_mix": -np.inf,
                "log_e_grid": log_e_grid[:i],
                "log_e_fold": log_e_fold[:i],
                "lambda_grid": lam,
                "weights": w,
                "fold_ids": fold_ids,
                "fold_weights": fold_w,
                "n_terms": int(n),
                "n_terms_by_fold": n_terms_by_fold[:i],
                "n_participants": int(np.unique(part).size),
                "n_participants_by_fold": n_participants_by_fold[:i],
                "valid": False,
                "reason": f"e-value fold {fold_id} has no terms",
            }
        for ell, la in enumerate(lam):
            log_mgf = logsumexp(
                log_p[in_fold] + la * z_support[in_fold],
                axis=1,
            )
            log_e_grid[i, ell] = float(
                np.sum(la * x_obs[in_fold] - log_mgf)
            )
        log_e_fold[i] = float(logsumexp(np.log(w) + log_e_grid[i]))

    log_e_mix = float(logsumexp(np.log(fold_w) + log_e_fold))
    p_seq = float(min(1.0, np.exp(-log_e_mix))) if np.isfinite(log_e_mix) else 1.0
    return {
        "p_seq": p_seq,
        "log_e_mix": log_e_mix,
        "log_e_grid": log_e_grid,
        "log_e_fold": log_e_fold,
        "lambda_grid": lam,
        "weights": w,
        "fold_ids": fold_ids,
        "fold_weights": fold_w,
        "n_terms": int(n),
        "n_terms_by_fold": n_terms_by_fold,
        "n_participants": int(np.unique(part).size),
        "n_participants_by_fold": n_participants_by_fold,
        "valid": True,
        "reason": "ok",
    }


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
