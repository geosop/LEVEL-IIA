# Submission-readiness verdict

Run hash `0a775ac4f1ead9d3`, M = 1000 datasets per scenario. Python 3.12, numpy
2.4.4, scipy 1.17.1, pandas 3.0.2.

## Diagnostic inventory of resolved defects

1. **Fabricated Figure 2 / abstract numbers.** The caption asserted 3000
   simulations, 98.1% power, 0.0% false support, 100% audit firing, beta_min = 33,
   injected -50. None was backed by code. Replaced with realised values from the
   benchmark: M = 1000, injected -60, support 92.8%, false support 0/1000, leakage
   audit 1000/1000, beta_min approximately 44.
2. **beta_min misinterpretation.** The "kappa = 2 implies a 10^-4 one-sided
   population test" claim was removed. beta_min is now stated as a single-participant
   resolution floor with the explicit caveat that the normal-equivalent stringency
   varies by orders of magnitude with the population SE and is not a fixed alpha; the
   confirmatory calibration is design-based.
3. **Injection language.** "On the residual scale" replaced with endpoint-level
   injection plus the clarification that the two coincide in the clean anchor.
4. **Missing operating-characteristics table.** Added (SI S9) from output, with a
   design table, an outcomes table, and the collider sweep.
5. **No collider scenario.** Added the pure endpoint-by-delay collider, its
   diagnostic, the hard support-blocking rule, and the scope-boundary language
   (main text and SI S8/S9).
6. **beta_min inconsistency (33 vs 40).** Reconciled: the benchmark and the worked
   example both use the realised beta_min approximately 44 at the anchor.
7. **Selection-gate bug.** The required-imbalance inverse-Mills bisection was
   inverted (saturated at 0.80); fixed to compute the true value (approximately
   0.54). No decision or rate changed; the gate column is now faithful.

## Findings

- False-support control holds (0/1000) under both the clean and the adversarial
  forward-only null, with the randomisation test rejecting at the nominal 0.050.
- The endpoint-level injected residual is recovered with 92.8% support.
- Leakage and standard selection are blocked by their audits and never supported.
- The opposite-direction injection is classified as such 95.3% and never supported.
- **Collider scope boundary (confirmed).** A pure endpoint-by-delay collider
  manufactures a material retained-sample slope (mean -35) with balanced marginal
  retention (audit fires 0.4%). The scalar selection gate passes 98.1% (misses it);
  the endpoint-by-delay interaction diagnostic fires 100% and blocks support, so the
  scenario is selection-limited 97.9% and supported 0%. The interaction diagnostic,
  not the scalar gate, is the operative guard.

## Verdict

The synthetic-validation component is now a real benchmarked pipeline. Every
benchmark number in the main text, Figure 2, the SI, and this package is produced
by the executable code and recorded under the run hash. Both documents compile
(pdflatex, two passes, zero undefined references). The package installs, runs
smoke and full modes, passes its unit tests and the output verifier.

**Ready for RSOS submission** subject to three pre-submission actions that require
the authors' accounts and cannot be done from inside the package:

1. Push the repository to the public GitHub URL in the data-accessibility statement
   and archive it to Zenodo; replace `10.5281/zenodo.PLACEHOLDER` in the two `.tex`
   files, `README.md`, and `CITATION.cff` with the minted DOI.
2. Re-attach the bibliography DOIs and confirm the venue of any citations carried
   from earlier drafts (a standing item independent of this benchmark work).
3. Optionally re-run `python scripts/run_all.py --all` at a larger M (for example
   5000) for tighter reported rates; the qualification invariants are insensitive to
   M above a few hundred, so the conclusions will not change.

## Honesty note

These are operating characteristics of a software pipeline on simulated data. They
establish that the locked decision procedure behaves as designed. They are not
empirical evidence about human EEG and not a mechanism claim. The collider scenario
uses kappa = 1 (documented in its config and the SI) so the manufactured slope is
material and isolates the interaction diagnostic; all other scenarios use kappa = 2.
