"""Label-blind, participant-cross-fitted forward-only comparator.

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


def participant_fold_assignment(
    participant,
    n_folds: int = 5,
    fold_seed: int = 0,
):
    """Return prospectively fixed participant folds.

    Fold assignment depends only on the sorted participant identifiers, the
    declared number of folds, and ``fold_seed``. It is therefore unchanged by
    current assignments, retention outcomes, endpoints, or final estimability.
    """
    participant = np.asarray(participant)
    if participant.ndim != 1:
        raise ValueError("participant must be one-dimensional")
    uniq = np.unique(participant)
    if n_folds < 2:
        raise ValueError("n_folds must be at least two")
    if uniq.size < n_folds:
        raise ValueError(
            f"n_folds={n_folds} exceeds the number of participants={uniq.size}"
        )

    rng = np.random.default_rng(int(fold_seed))
    permuted = rng.permutation(uniq)
    fold_of_part = {
        pid: int(i % n_folds)
        for i, pid in enumerate(permuted)
    }
    return np.asarray([fold_of_part[pid] for pid in participant], dtype=int)


def cross_fitted_residual_full(
    ds: Dataset,
    eligible,
    n_folds: int = 5,
    lam: float = 1.0,
    fold_seed: int = 0,
):
    """Predict every prospectively eligible row from other participants.

    The training set for fold ``k`` contains eligible rows only from
    participants outside fold ``k``. A small-fold fallback is intentionally
    prohibited because training on the evaluated fold would invalidate the
    sequential fold e-value.
    """
    eligible = np.asarray(eligible, dtype=bool)
    if eligible.shape != ds.A_pre.shape:
        raise ValueError("eligible must have one Boolean value per trial")
    if not np.any(eligible):
        raise ValueError("no prospectively eligible trials")

    X = covariate_matrix(ds)
    y = np.asarray(ds.A_pre, dtype=float)
    part = np.asarray(ds.participant)
    fold = participant_fold_assignment(
        part,
        n_folds=n_folds,
        fold_seed=fold_seed,
    )

    resid_full = np.full(y.shape[0], np.nan, dtype=float)
    training_participants = {}
    evaluated_participants = {}
    minimum_train_rows = X.shape[1] + 2

    for k in range(n_folds):
        train = eligible & (fold != k)
        test = eligible & (fold == k)
        if not np.any(test):
            raise ValueError(f"cross-fit fold {k} has no eligible evaluation rows")
        if int(np.sum(train)) < minimum_train_rows:
            raise ValueError(
                f"cross-fit fold {k} has {int(np.sum(train))} training rows; "
                f"at least {minimum_train_rows} are required"
            )

        train_ids = np.unique(part[train])
        test_ids = np.unique(part[test])
        if np.intersect1d(train_ids, test_ids).size:
            raise RuntimeError(
                f"training/evaluation participant overlap in fold {k}"
            )

        mu, sd = _standardise_fit(X[train])
        Xtr = (X[train] - mu) / sd
        Xte = (X[test] - mu) / sd
        beta = _ridge_fit(Xtr, y[train], lam)
        resid_full[test] = y[test] - Xte @ beta
        training_participants[str(k)] = [int(x) for x in train_ids]
        evaluated_participants[str(k)] = [int(x) for x in test_ids]

    if np.any(~np.isfinite(resid_full[eligible])):
        raise RuntimeError("cross-fitting did not predict every eligible row")

    info = {
        "n_folds": int(n_folds),
        "lam": float(lam),
        "fold_seed": int(fold_seed),
        "resid_sd": float(np.std(resid_full[eligible])),
        "n_eligible": int(np.sum(eligible)),
        "fold_full": fold,
        "training_participants": training_participants,
        "evaluated_participants": evaluated_participants,
    }
    return resid_full, fold, info


def cross_fitted_residual(
    ds: Dataset,
    n_folds: int = 5,
    lam: float = 1.0,
    rng: np.random.Generator | None = None,
    fold_seed: int = 0,
):
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
    # ``rng`` remains in the public signature for v1.1 call compatibility. Fold
    # assignment is no longer drawn from mutable pipeline RNG state.
    del rng
    ret = ds.S == 1
    idx_ret = np.flatnonzero(ret)
    resid_full, fold, info = cross_fitted_residual_full(
        ds,
        eligible=ret,
        n_folds=n_folds,
        lam=lam,
        fold_seed=fold_seed,
    )
    resid = resid_full[idx_ret]
    info["n_retained"] = int(ret.sum())
    info["fold_retained"] = fold[idx_ret]
    return resid, idx_ret, info


def blind_residual_sd(
    ds: Dataset,
    n_folds: int = 5,
    lam: float = 1.0,
    rng: np.random.Generator | None = None,
    fold_seed: int = 0,
) -> float:
    """Label-blind residual noise scale used to set the resolution floor.

    Estimated from the cross-fitted residual on the qualification (here, the
    full retained) sample without any delay information.
    """
    resid, _, _ = cross_fitted_residual(
        ds,
        n_folds=n_folds,
        lam=lam,
        rng=rng,
        fold_seed=fold_seed,
    )
    return float(np.nanstd(resid))
