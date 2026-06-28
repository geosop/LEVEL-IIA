"""Data-generating processes for the Level II-A benchmark.

Every generator produces a *committed pre-event endpoint* A_pre per trial, an
*assigned post-endpoint delay* tau_L drawn independently of the endpoint and of
the past-adapted covariates, and an *inclusion indicator* S. The forward-only
backbone is past-adapted: the endpoint depends only on covariates that are known
before the delay is assigned (elapsed foreperiod, conditional hazard, previous
foreperiod, previous assigned delay as carryover). The delay term, when present,
is injected at the endpoint-generating level, before comparator fitting, so the
full locked pipeline is exercised.

Units: A_pre and the residual noise are in microvolts; tau_L is in seconds in the
arrays (millisecond grids are converted on construction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np


# --------------------------------------------------------------------------- #
# Container
# --------------------------------------------------------------------------- #
@dataclass
class Dataset:
    """One simulated dataset prior to comparator fitting."""

    participant: np.ndarray          # int participant id per trial
    e: np.ndarray                    # elapsed foreperiod (s)
    prev_e: np.ndarray               # previous-trial elapsed foreperiod (s)
    hazard: np.ndarray               # conditional hazard at e
    tau_prev: np.ndarray             # previous assigned delay (s), carryover covariate
    tau_assigned: np.ndarray         # assigned post-endpoint delay (s)
    tau_delivered: np.ndarray        # delivered delay including jitter (s)
    A_pre: np.ndarray                # committed pre-event endpoint (uV)
    S: np.ndarray                    # inclusion indicator (1 retained, 0 excluded)
    bin_index: np.ndarray            # assigned-delay bin index
    grid_s: np.ndarray               # delay grid (s)
    leak_probe: np.ndarray           # pre-endpoint leakage probe value (uV)
    meta: dict = field(default_factory=dict)

    @property
    def n_trials(self) -> int:
        return self.A_pre.shape[0]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _zscore(x: np.ndarray) -> np.ndarray:
    sd = x.std()
    if sd <= 0:
        return np.zeros_like(x)
    return (x - x.mean()) / sd


def _foreperiod_block(rng, n, grid_fp_s):
    """Draw an elapsed foreperiod sequence from a discrete uniform grid and
    return e, prev_e, hazard and the signed change."""
    idx = rng.integers(0, len(grid_fp_s), size=n)
    e = grid_fp_s[idx]
    # hazard of a discrete-uniform foreperiod increases toward the end
    order = np.argsort(grid_fp_s)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(len(grid_fp_s))
    # P(elapsed reaches this grid point | not earlier) = 1 / (#remaining)
    remaining = len(grid_fp_s) - ranks[idx]
    hazard = 1.0 / np.maximum(remaining, 1)
    prev_e = np.empty_like(e)
    prev_e[0] = e[0]
    prev_e[1:] = e[:-1]
    return e, prev_e, hazard


def _ar1(rng, n, sd, rho):
    """Stationary AR(1) noise with marginal sd."""
    if rho == 0.0:
        return rng.normal(0.0, sd, size=n)
    innov_sd = sd * np.sqrt(1.0 - rho ** 2)
    out = np.empty(n)
    out[0] = rng.normal(0.0, sd)
    for t in range(1, n):
        out[t] = rho * out[t - 1] + rng.normal(0.0, innov_sd)
    return out


# --------------------------------------------------------------------------- #
# Main generator
# --------------------------------------------------------------------------- #
def generate_dataset(rng: np.random.Generator, cfg: dict) -> Dataset:
    """Generate one dataset under the configuration ``cfg``.

    Configuration keys (with defaults) are documented in configs/*.yaml. The
    same function produces every scenario; behaviour is switched by flags so a
    single locked pipeline is exercised throughout.
    """
    P = int(cfg.get("n_participants", 24))
    n_bin = int(cfg.get("trials_per_bin", 12))
    grid_ms = np.asarray(cfg.get("delay_grid_ms", [0, 5, 10, 15, 20]), float)
    grid_s = grid_ms / 1000.0
    grid_mean = grid_s.mean()

    sigma_resid = float(cfg.get("sigma_resid", 1.0))
    beta_inj = float(cfg.get("beta_inj", 0.0))            # uV/s, endpoint-level
    # forward-only coefficients (past-adapted structure, uV per covariate unit)
    a_e = float(cfg.get("coef_foreperiod", 6.0))
    a_h = float(cfg.get("coef_hazard", 4.0))
    a_pe = float(cfg.get("coef_prev_foreperiod", 2.0))
    a_carry = float(cfg.get("coef_carryover", 0.0))       # carryover from tau_prev
    nl_amp = float(cfg.get("nonlinear_amp", 0.0))         # comparator-misspec driver

    # noise structure
    rho = float(cfg.get("noise_ar1_rho", 0.0))
    hetero = float(cfg.get("noise_hetero", 0.0))          # sd scales with foreperiod
    t_df = cfg.get("participant_t_df", None)              # heavy-tailed heterogeneity
    tau_beta = float(cfg.get("participant_slope_sd", 12.0))  # benign het. of slope (uV/s)

    # delivery / timing
    jitter_sd_ms = float(cfg.get("delivery_jitter_ms", 0.2))

    # retention / selection
    sel_mode = cfg.get("selection_mode", "random")        # random|monotone|collider|none
    base_retention = float(cfg.get("base_retention", 0.80))
    sel_strength = float(cfg.get("selection_strength", 0.0))
    collider_gamma = float(cfg.get("collider_gamma", 0.0))

    grid_fp_s = np.asarray(cfg.get("foreperiod_grid_s", [0.4, 0.8, 1.2, 1.6, 2.0]), float)

    n_per_part = n_bin * len(grid_s)
    parts, es, pes, hzs = [], [], [], []
    tau_prev_all, tau_assigned_all, bins_all = [], [], []
    A_all, leak_all = [], []
    S_logit_all = []

    # benign per-participant slope heterogeneity (does not violate the boundary:
    # it is heterogeneity of the *injected* term, zero under forward-only nulls)
    if beta_inj != 0.0:
        if t_df is not None and t_df > 2:
            scale = tau_beta / np.sqrt(t_df / (t_df - 2.0))
            slope_p = beta_inj + scale * rng.standard_t(df=t_df, size=P)
        else:
            slope_p = rng.normal(beta_inj, tau_beta, size=P)
    else:
        slope_p = np.zeros(P)

    for p in range(P):
        e, prev_e, hazard = _foreperiod_block(rng, n_per_part, grid_fp_s)
        # balanced assigned-delay design within participant, then shuffled
        bins = np.repeat(np.arange(len(grid_s)), n_bin)
        rng.shuffle(bins)
        tau = grid_s[bins]
        tau_prev = np.empty_like(tau)
        tau_prev[0] = grid_mean
        tau_prev[1:] = tau[:-1]

        # forward-only mean (past-adapted only)
        mu = (a_e * (e - e.mean())
              + a_h * (hazard - hazard.mean())
              + a_pe * (prev_e - prev_e.mean())
              + a_carry * (tau_prev - grid_mean))
        if nl_amp != 0.0:
            mu = mu + nl_amp * np.sin(2.0 * np.pi * (e - e.min()) / (np.ptp(e) + 1e-9))

        # noise
        sd_vec = sigma_resid * (1.0 + hetero * _zscore(e))
        sd_vec = np.clip(sd_vec, 0.2 * sigma_resid, None)
        noise = _ar1(rng, n_per_part, 1.0, rho) * sd_vec

        # endpoint-level injection (before comparator and residualisation)
        inj = slope_p[p] * (tau - grid_mean)

        A = mu + inj + noise

        # leakage probe: a pre-endpoint feature that must be delay-independent.
        # Under leakage, post-t1 delay-correlated content bleeds into the probe
        # and into the committed endpoint, manufacturing a negative apparent
        # slope that would otherwise clear materiality.
        leak = rng.normal(0.0, sigma_resid, size=n_per_part)
        if cfg.get("leakage", False):
            leak_amp = float(cfg.get("leakage_amp", 0.0))
            delaystd = (tau - grid_mean) / (grid_s.std() + 1e-12)
            leak = leak + leak_amp * delaystd
            A = A - leak_amp * delaystd

        # inclusion logit
        sel_inter = float(cfg.get("selection_interaction", 0.0))
        if sel_mode == "none":
            s_logit = np.full(n_per_part, 50.0)  # keep all
        elif sel_mode == "random":
            s_logit = np.full(n_per_part, np.log(base_retention / (1 - base_retention)))
        elif sel_mode == "monotone":
            # "Standard" selection: a delay main effect (marginal imbalance the
            # retention audit catches) together with an endpoint-by-delay
            # interaction that induces a material retained-sample slope.
            delaystd = (tau - grid_mean) / (grid_s.std() + 1e-12)
            s_logit = (np.log(base_retention / (1 - base_retention))
                       + sel_strength * delaystd
                       + sel_inter * _zscore(A) * delaystd)
        elif sel_mode == "collider":
            # pure endpoint-by-delay collider: inclusion depends on the PRODUCT
            # of endpoint and centred delay, with no main delay effect, so the
            # marginal retention rate by delay bin stays (approximately) flat.
            s_logit = (np.log(base_retention / (1 - base_retention))
                       + collider_gamma * _zscore(A) * (tau - grid_mean)
                       / (grid_s.std() + 1e-12))
        else:
            raise ValueError(f"unknown selection_mode {sel_mode}")

        parts.append(np.full(n_per_part, p))
        es.append(e); pes.append(prev_e); hzs.append(hazard)
        tau_prev_all.append(tau_prev); tau_assigned_all.append(tau); bins_all.append(bins)
        A_all.append(A); leak_all.append(leak); S_logit_all.append(s_logit)

    participant = np.concatenate(parts)
    e = np.concatenate(es); prev_e = np.concatenate(pes); hazard = np.concatenate(hzs)
    tau_prev = np.concatenate(tau_prev_all)
    tau_assigned = np.concatenate(tau_assigned_all)
    bin_index = np.concatenate(bins_all)
    A_pre = np.concatenate(A_all)
    leak_probe = np.concatenate(leak_all)
    s_logit = np.concatenate(S_logit_all)

    # delivery jitter
    tau_delivered = tau_assigned + rng.normal(0.0, jitter_sd_ms / 1000.0, size=A_pre.shape[0])

    # draw inclusion
    p_inc = 1.0 / (1.0 + np.exp(-s_logit))
    S = (rng.random(A_pre.shape[0]) < p_inc).astype(int)

    return Dataset(
        participant=participant, e=e, prev_e=prev_e, hazard=hazard,
        tau_prev=tau_prev, tau_assigned=tau_assigned, tau_delivered=tau_delivered,
        A_pre=A_pre, S=S, bin_index=bin_index, grid_s=grid_s, leak_probe=leak_probe,
        meta={"P": P, "n_per_part": n_per_part, "grid_mean": grid_mean,
              "sigma_resid": sigma_resid, "beta_inj": beta_inj,
              "sel_mode": sel_mode},
    )


def covariate_matrix(ds: Dataset) -> np.ndarray:
    """Past-adapted covariate design for the forward-only comparator.

    Includes a quadratic foreperiod basis, the conditional hazard, the previous
    foreperiod, and the previous assigned delay (carryover). It deliberately does
    NOT include the current assigned delay tau_L.
    """
    e = ds.e
    X = np.column_stack([
        np.ones_like(e),
        e, e ** 2,
        ds.hazard,
        ds.prev_e,
        ds.tau_prev,
    ])
    return X
