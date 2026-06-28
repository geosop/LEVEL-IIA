# Methods validation notes

This document records the design choices that make the benchmark a fair test.

## Comparator and the blind residual scale

The forward-only comparator is cross-fitted by participant (whole participants
held out together) with per-fold covariate standardisation. The resolution floor
beta_min uses the **within-participant** residual SD, because the participant-slope
estimand centres the assigned delay within participant and is therefore invariant
to per-participant offsets. Using the within-participant residual SD makes the
blind noise scale recovered from a clean anchor equal to the simulated residual SD,
as it should.

## Endpoint-level injection

The injected delay slope is added to the committed endpoint before comparator
fitting, so the whole locked pipeline (comparator, cross-fitting, freezing,
residualisation, randomisation test, bootstrap bound, decision rule) is exercised
as a coupled system. Because the past-adapted covariates are independent of the
assigned delay by construction, endpoint-level and residual-scale injection are
close in the clean anchor; the endpoint-level form is the confirmatory benchmark.

## Audits are sample-size aware

The temporal-leakage and retention audits fire from calibrated tests (a correlation
t-test and a chi-square homogeneity test), not from fixed thresholds, so their
false-firing rate is controlled at every sample size. The randomisation-balance
audit is computed on all assigned trials (the scheduler), so delay-dependent
retention is handled by the retention audit and selection machinery rather than
masquerading as an assignment failure.

## Collider scope test

A pure endpoint-by-delay collider makes inclusion depend on the product of the
committed endpoint and the centred assigned delay, with no main delay effect, so
marginal retention by bin stays approximately balanced while the retained endpoint
distribution shifts across bins. The committed endpoint exists for every trial, so
the endpoint-by-delay interaction in inclusion (logistic regression of inclusion on
endpoint, delay, and their product over all trials) and the retained-versus-excluded
within-bin difference are both computable and both distinguish a collider from a
genuine injected residual. The retained-sample rank imbalance is reported as a
descriptive statistic only, because a genuine injected residual would also trip it.

The manufactured residual slope is Manski-bounded by the retention rate. At kappa = 2
and 80% retention the bound sits below the resolution floor, so materiality blocks
the collider incidentally. The collider scenario therefore uses a lower retention
rate (realistic for EEG artefact rejection) and kappa = 1, placing the manufactured
slope above the floor. In that regime the scalar marginal-imbalance gate passes
(misses the collider) and only the endpoint-by-delay interaction diagnostic prevents
a supported classification. This is the scope boundary the manuscript states: the
scalar selection gate protects only against selection pathways represented by the
declared audited imbalance summary and selection-model class.
