"""Label-blind, cross-fitted forward-only comparator.

The comparator predicts the committed endpoint A_pre from past-adapted covariates
only. It is fit by K-fold cross-fitting so each trial's prediction comes from a
model trained on other folds, and the residual array is frozen before any
assignment-calibrated inference. The current assigned delay tau_L is never a
predictor, by construction (see dgp.covariate_matrix).
"""

from __future__ import annotations

import numpy as np

from .dgp import Dataset, covariate_matrix


def _standardise_fit(Xtr):
    """Column standardisation parameters from the training fold (intercept in
    column 0 is left untouched)."""
    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0)
    mu[0] = 0.0
    sd[0] = 1.0
    sd = np.where(sd > 0, sd, 1.0)
    return mu, sd


def _ridge_fit(X, y, lam):
    p = X.shape[1]
    A = X.T @ X + lam * np.eye(p)
    # do not penalise the intercept column (assumed column 0)
    A[0, 0] -= lam
    beta = np.linalg.solve(A, X.T @ y)
    return beta


def cross_fitted_residual(ds: Dataset, n_folds: int = 5, lam: float = 1.0,
                          rng: np.random.Generator | None = None):
    """Return the frozen residual on the retained analysis sample.

    Parameters
    ----------
    ds : Dataset
    n_folds : int
        Number of cross-fitting folds, assigned by participant so that whole
        participants are held out together.
    lam : float
        Ridge penalty (label-blind, fixed before unblinding).

    Returns
    -------
    resid : np.ndarray
        Frozen residual A_pre - g_hat(X) on retained trials.
    idx_ret : np.ndarray
        Indices of retained trials (S == 1) in original order.
    info : dict
    """
    if rng is None:
        rng = np.random.default_rng(0)
    ret = ds.S == 1
    idx_ret = np.flatnonzero(ret)
    X = covariate_matrix(ds)
    y = ds.A_pre
    part = ds.participant

    # fold assignment by participant (whole participants held out together)
    uniq = np.unique(part[ret])
    fold_of_part = {pid: int(i % n_folds) for i, pid in enumerate(rng.permutation(uniq))}
    fold = np.array([fold_of_part.get(pid, -1) for pid in part])

    resid_full = np.full(y.shape[0], np.nan)
    for k in range(n_folds):
        train = ret & (fold != k) & (fold != -1)
        test = ret & (fold == k)
        if test.sum() == 0:
            continue
        if train.sum() < X.shape[1] + 2:
            train = ret & (fold != -1)  # fall back to all retained if a fold is tiny
        mu, sd = _standardise_fit(X[train])
        Xtr = (X[train] - mu) / sd
        Xte = (X[test] - mu) / sd
        beta = _ridge_fit(Xtr, y[train], lam)
        resid_full[test] = y[test] - Xte @ beta

    resid = resid_full[idx_ret]
    info = {"n_folds": n_folds, "lam": lam,
            "resid_sd": float(np.nanstd(resid)),
            "n_retained": int(ret.sum())}
    return resid, idx_ret, info


def blind_residual_sd(ds: Dataset, n_folds: int = 5, lam: float = 1.0,
                      rng: np.random.Generator | None = None) -> float:
    """Label-blind residual noise scale used to set the resolution floor.

    Estimated from the cross-fitted residual on the qualification (here, the
    full retained) sample without any delay information.
    """
    resid, _, _ = cross_fitted_residual(ds, n_folds=n_folds, lam=lam, rng=rng)
    return float(np.nanstd(resid))
