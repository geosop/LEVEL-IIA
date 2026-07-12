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


## Retained-delay centring and participant estimability

The assignment-isolation slope includes a participant intercept. Retained assigned
delays are therefore centred at each participant's realised retained mean before
the numerator, denominator, randomisation statistic and leverage diagnostics are
computed. The materiality floor uses the corresponding effective retained
within-participant delay scale.

Participant eligibility is fixed before assignment; slope estimability is assessed
after retention without using the sign or magnitude of the participant slope. The
prospective rule records retained usable trials, distinct retained delay levels,
and retained denominator leverage relative to the participant's planned design.
Non-estimable participants are not silently assigned zero slope. Their possible
contribution is bounded using a declared label-blind residual-scale multiple and
the exact planned design ratio, and the conclusion-opposing eligible-population
bounds are applied separately to negative support, the positive diagnostic and
affirmative adequacy. Insufficient bound information is inconclusive; a plausible
participant-selection distortion is selection-limited.

## Classifier semantics

The negative tail is the sole confirmatory level-alpha hypothesis. The positive
tail is a prespecified opposite-direction diagnostic. Inferential and magnitude
components must agree within a direction; any component disagreement is routed to
`inconclusive` and can never be counted as `forward_only_adequate`.

The scalar trial-selection sensitivity gate is evaluated only when a material
directional departure has already resolved. It asks whether audited selection
could manufacture that departure and is not an affirmative-null gate. Retention,
collider and participant-estimability qualifications apply independently.

The executable classifier uses the frozen-residual analysis. An unadjusted
committed-endpoint slope can be reported as a descriptive adjustment-sensitivity
diagnostic, but it is not a support requirement and sign disagreement is not an
automatic veto.
