"""Audit battery for the Level II-A pipeline.

These audits guard the barrier between label-blind construction and confirmatory
inference. Each returns a scalar statistic and a boolean ``fired`` flag against a
prospectively declared tolerance. A fired audit blocks support and is reported as
a diagnostic failure, never as a null.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def temporal_leakage_audit(ds, tol=0.05, alpha=1e-3):
    """Delay dependence of a pre-endpoint leakage probe.

    The probe is, by construction, a feature that must be independent of the
    post-endpoint delay. Its absolute correlation with the centred assigned delay
    on retained trials is the excursion statistic. Firing is decided by a
    correlation t-test at level ``alpha`` so the false-firing rate is controlled
    at every sample size; ``tol`` is reported as the equivalent critical
    correlation. Under leakage, post-t1 delay-correlated content bleeds into the
    probe and the statistic exceeds the critical value.
    """
    ret = ds.S == 1
    d = ds.tau_assigned[ret] - ds.meta["grid_mean"]
    probe = ds.leak_probe[ret]
    n = int(ret.sum())
    if d.std() == 0 or probe.std() == 0 or n < 5:
        return {"excursion": 0.0, "fired": False, "tol": tol, "r_crit": tol}
    r = float(abs(np.corrcoef(probe, d)[0, 1]))
    tcrit = stats.t.ppf(1 - alpha / 2.0, df=n - 2)
    r_crit = float(tcrit / np.sqrt(n - 2 + tcrit ** 2))
    return {"excursion": r, "fired": bool(r > r_crit), "tol": tol, "r_crit": r_crit}


def delivery_audit(ds, tol_ms=2.0):
    """99th-percentile assigned-to-delivered latency error in milliseconds."""
    err_ms = np.abs(ds.tau_delivered - ds.tau_assigned)[ds.S == 1] * 1000.0
    p99 = float(np.percentile(err_ms, 99)) if err_ms.size else 0.0
    return {"p99_ms": p99, "fired": bool(p99 > tol_ms), "tol_ms": tol_ms}


def retention_audit(ds, tol=0.05, alpha=1e-3):
    """Marginal retention-rate imbalance across assigned-delay bins.

    Scalar statistic: maximum absolute deviation of binwise retention from the
    overall retention rate (the marginal-imbalance summary the selection gate is
    built on). Firing is decided by a chi-square test of retention homogeneity
    across bins at level ``alpha``, so false firing is controlled at every sample
    size.
    """
    bins = ds.bin_index
    nb = int(bins.max()) + 1
    overall = ds.S.mean()
    diffs, rates, ret_counts, tot_counts = [], [], [], []
    for b in range(nb):
        m = bins == b
        n = int(m.sum())
        ret = int(ds.S[m].sum())
        rate = ret / n if n else overall
        rates.append(rate)
        diffs.append(abs(rate - overall))
        ret_counts.append(ret)
        tot_counts.append(n)
    imbalance = float(max(diffs)) if diffs else 0.0
    # chi-square test of homogeneity of retention across bins
    ret_counts = np.array(ret_counts, float)
    tot_counts = np.array(tot_counts, float)
    exc_counts = tot_counts - ret_counts
    p = 1.0
    if overall not in (0.0, 1.0) and tot_counts.min() > 0:
        obs = np.array([ret_counts, exc_counts])
        exp = np.outer(obs.sum(axis=1), obs.sum(axis=0)) / obs.sum()
        with np.errstate(divide="ignore", invalid="ignore"):
            chi = float(np.nansum((obs - exp) ** 2 / np.where(exp > 0, exp, np.nan)))
        p = float(stats.chi2.sf(chi, df=nb - 1))
    return {"imbalance": imbalance, "binwise_retention": rates, "p": p,
            "fired": bool(p < alpha), "tol": tol}


def randomisation_balance_audit(ds, alpha=1e-3):
    """Chi-square balance of assigned-delay counts across bins on ALL assigned
    trials (the scheduler check). It is computed before retention so that
    delay-dependent retention does not masquerade as an assignment failure;
    retention imbalance is handled by the retention audit and selection gate."""
    bins = ds.bin_index
    nb = int(ds.bin_index.max()) + 1
    counts = np.array([(bins == b).sum() for b in range(nb)], float)
    expected = counts.sum() / nb
    if expected <= 0:
        return {"p": 1.0, "fired": False}
    chi = float(np.sum((counts - expected) ** 2 / expected))
    p = float(stats.chi2.sf(chi, df=nb - 1))
    return {"p": p, "fired": bool(p < alpha)}


def implementation_swap_audit(ds):
    """Implementation-swap audit.

    In simulation no hardware/software swap is modelled, so this audit passes by
    construction. It is retained as a named slot because an empirical protocol
    must run it (swap the delivery implementation and confirm invariance).
    """
    return {"fired": False, "note": "not modelled in simulation"}


def run_audit_battery(ds, tols):
    a = tols.get("balance_alpha", 1e-3)
    leak = temporal_leakage_audit(ds, tol=tols.get("leakage", 0.05),
                                  alpha=tols.get("leakage_alpha", a))
    deliv = delivery_audit(ds, tol_ms=tols.get("delivery_ms", 2.0))
    reten = retention_audit(ds, tol=tols.get("retention", 0.05),
                            alpha=tols.get("retention_alpha", a))
    bal = randomisation_balance_audit(ds, alpha=a)
    swap = implementation_swap_audit(ds)
    any_fired = any(x["fired"] for x in (leak, deliv, reten, bal, swap))
    return {"leakage": leak, "delivery": deliv, "retention": reten,
            "balance": bal, "swap": swap, "any_fired": any_fired}
