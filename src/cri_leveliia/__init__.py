"""Level II-A post-endpoint randomisation benchmark pipeline.

This package implements the locked synthetic-validation pipeline for the
Perspective "Testing past-adapted accounts of anticipatory EEG with
post-endpoint randomisation". It is a design-stage validation framework on
simulated data. It does not analyse human EEG and makes no mechanism claim.

Modules
-------
dgp         : forward-only, injected-residual, leakage, selection and collider
              data-generating processes.
comparator  : label-blind, cross-fitted forward-only comparator and the frozen
              residual array.
inference   : participant-level estimand, plus-one randomisation test,
              studentised participant bootstrap-t bound (UCB and sign-reversed
              LCB).
audits      : randomisation, temporal-leakage, delivery, retention and
              implementation-swap audits.
selection   : scalar selection-sensitivity gate (Lee/Manski required-versus-
              audited marginal imbalance).
collider    : endpoint-by-delay collider-selection diagnostics.
benchmarks  : scenario runner, decision rule and operating-characteristic
              aggregation.
figures     : regeneration of the validation figure from frozen output.
tables      : LaTeX and CSV table writers.
metadata    : deterministic seed policy, run-hash and environment capture.
"""

__version__ = "1.0.0"

from . import dgp, comparator, inference, audits, selection, collider  # noqa: F401
