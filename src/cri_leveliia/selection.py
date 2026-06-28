"""Scalar selection-sensitivity gate.

The gate compares the marginal retention imbalance the audit permits with the
imbalance that would be required, under a declared monotone (Lee) selection
model, to manufacture the observed retained-sample slope. It passes when the
required imbalance lower bound exceeds the audited imbalance upper bound.

This gate is built on the *marginal* retention imbalance summary. Its scope
boundary is the subject of the collider module: a pure endpoint-by-delay collider
can manufacture a slope with near-zero marginal imbalance, which this gate does
not see.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def _inverse_mills(c):
    """E[Z | Z > c] for the standard normal."""
    return stats.norm.pdf(c) / np.clip(stats.norm.sf(c), 1e-12, None)


def required_imbalance(beta_hat, support_s, sigma_y, p_high=0.8):
    """Differential retention required to manufacture ``beta_hat`` under a
    monotone (Lee) one-sided trimming model.

    The slope implies a between-extreme-bin mean shift of |beta_hat| * support.
    Inverting the one-sided trim map E[Z|Z>c] = shift / sigma_y gives the kept
    fraction 1 - t, hence the required differential retention t * p_high.
    """
    shift = abs(beta_hat) * support_s
    target = shift / max(sigma_y, 1e-9)
    # solve E[Z|Z>c] = target for c by bisection. The inverse Mills ratio is
    # increasing in c, so move the lower bound up when it is still below target.
    lo, hi = -8.0, 12.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if _inverse_mills(mid) < target:
            lo = mid
        else:
            hi = mid
    c = 0.5 * (lo + hi)
    kept = float(stats.norm.sf(c))
    t_req = max(0.0, 1.0 - kept)
    return float(t_req * p_high)


def selection_gate(beta_hat, support_s, sigma_y, audited_imbalance, n_per_bin,
                   p_high=0.8, level=0.95):
    """Confidence-limit selection gate.

    Returns the required and audited imbalances with one-sided confidence limits
    and the pass flag LCB(required) > UCB(audited).
    """
    z = stats.norm.ppf(level)
    req = required_imbalance(beta_hat, support_s, sigma_y, p_high=p_high)
    # sampling allowance on the audited imbalance (binomial se of a retention rate)
    se_aud = np.sqrt(max(p_high * (1 - p_high), 1e-6) / max(n_per_bin, 1))
    ucb_aud = audited_imbalance + z * se_aud
    # coarse one-sided lower bound on the required imbalance
    lcb_req = max(0.0, req - z * se_aud)
    passed = bool(lcb_req > ucb_aud)
    return {"required": req, "audited": float(audited_imbalance),
            "lcb_required": float(lcb_req), "ucb_audited": float(ucb_aud),
            "passed": passed}
