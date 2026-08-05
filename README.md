# Level II-A post-endpoint randomisation benchmark

[![DOI](https://zenodo.org/badge/1282699237.svg)](https://doi.org/10.5281/zenodo.21804380)

Reproducible benchmark pipeline for the Level II-A post-endpoint randomisation
operating-characteristic study.

This repository contains executable code, scenario configurations, synthetic-data
generators, tests, and generated benchmark artefacts used to reproduce the
software-validation results. The Perspective manuscript and Supplementary
Information source files are maintained outside this repository and are not
included in the GitHub/Zenodo software archive.

This repository is therefore a code-and-benchmark companion, not a manuscript
source package. It can be cited as the reproducibility source for benchmark
operating characteristics reported in an external manuscript, provided the cited
run hash is stated explicitly.

## Certified benchmark run

External manuscripts may cite a certified full benchmark run. The certified run
is identified by its run hash, Monte Carlo settings, and generated output
directory. Because the manuscript and SI source files are maintained outside this
repository, the run hash is the reproducibility anchor for benchmark numbers, not
a pointer to manuscript source files.

### Certified version 1.2.0 benchmark

Version 1.2.0 is certified against full benchmark run
`0cd4cac11153c546`, generated with 1,200 Monte Carlo datasets per
scenario under source commit
`e45455e359646c4784b1d7b847ef44dd8f3499fd`. The run passed the declared
operating-characteristic, invariant, false-adequacy and strict
manuscript-lock checks. Its exact mutually exclusive outcome counts are
stored in `manuscript/certified_run_counts.json`.

The canonical outputs are stored under
`outputs/0cd4cac11153c546/`. Smoke and exploratory runs are development
checks only and must not be cited as certified results.

The route-specific adequacy certification evaluates both departure directions
over the declared magnitude grid. Under its simultaneous familywise
upper-bound rule, false-adequacy control is certified from
`|Delta| = 15` for
`assignment_isolation` and from
`|Delta| = 30` for
`sequential_evalue`. These are route-specific resolution boundaries for an
affirmative adequacy classification. They are not directional-power claims.

The certified full-run design is:

```text
M:        1200 Monte Carlo datasets per scenario
P:        24 participants
n/bin:    24 planned trials per assigned-delay bin
R:        999 randomisation draws where assignment-isolation calibration is used
B:        999 participant bootstrap replicates
support:  [0, 20] ms
```

The canonical numeric source for the certified operating characteristics is:

```text
outputs/0cd4cac11153c546/summary/operating_characteristics.csv
```

The material-departure false-adequacy results are stored in:

```text
outputs/0cd4cac11153c546/summary/false_adequacy_rates.csv
outputs/0cd4cac11153c546/summary/adequacy_operating_characteristic.csv
```

The scenario-level checks in `false_adequacy_rates.csv` retain the
registered Wilson 95% upper confidence bound for the designated
material-departure scenarios. The route-general adequacy certificate in
`adequacy_operating_characteristic.csv` is separate: pointwise Wilson intervals
are descriptive, while certification uses the one-sided,
Bonferroni-adjusted Clopper-Pearson simultaneous upper-bound envelope across
the complete declared route-by-direction-by-magnitude family. A
route-direction operating point is certified only when its envelope at that
magnitude and all larger evaluated magnitudes is at or below
`p_FA_max = 0.05`.

The manuscript-facing LaTeX tables are generated from the certified outputs:

```text
outputs/0cd4cac11153c546/tables/operating_characteristics_design.tex
outputs/0cd4cac11153c546/tables/operating_characteristics_intervals.tex
outputs/0cd4cac11153c546/tables/operating_characteristics_outcomes.tex
outputs/0cd4cac11153c546/tables/adequacy_operating_characteristic_assignment_isolation.tex
outputs/0cd4cac11153c546/tables/adequacy_operating_characteristic_sequential_evalue.tex
outputs/0cd4cac11153c546/tables/collider_sweep.tex
outputs/0cd4cac11153c546/tables/route_matched_null_comparison.tex
outputs/0cd4cac11153c546/tables/v12_result_macros.tex
outputs/0cd4cac11153c546/tables/worked_decision_example.tex
outputs/0cd4cac11153c546/tables/worked_decision_example_values.tex
outputs/0cd4cac11153c546/tables/worked_decision_example_bins.tex
outputs/0cd4cac11153c546/tables/worked_decision_example_slopes.tex
outputs/0cd4cac11153c546/tables/worked_decision_example_decision.tex
```

Earlier certified and lower-retained-trial reference runs are retained only for
historical reproduction and pipeline-architecture comparison. They do not
certify version 1.2.0.

## What the benchmark establishes

The locked pipeline consists of:

* committed endpoint;
* label-blind cross-fitted forward-only comparator;
* frozen residual array;
* participant-level slope estimand with retained delay centred within participant;
* prospective participant-estimability and retained-leverage qualification;
* route-specific calibration:
  * `assignment_isolation`: plus-one randomisation under endpoint-array invariance;
  * `sequential_evalue`: martingale/e-value calibration for carryover-sensitive scenarios;
* studentised participant bootstrap-t upper bound;
* materiality floor;
* audit battery;
* scalar selection-sensitivity gate, applicable only to a resolved material departure;
* endpoint-by-delay collider diagnostic;
* component-disagreement routing to the inconclusive class;
* non-compensatory final classifier.

The negative tail is the sole confirmatory level-alpha hypothesis. The positive
tail is a prespecified opposite-direction diagnostic and is not represented as a
level-alpha omnibus class rejection. The executable classifier uses the frozen
residual analysis. An unadjusted committed-endpoint slope may be reported
descriptively as an adjustment-sensitivity diagnostic, but it is neither a
support criterion nor a veto.

The pipeline is required to behave as designed under seven scenarios.

| Scenario             | Required behaviour                                                          |
| -------------------- | --------------------------------------------------------------------------- |
| `clean_null`         | False-support control under a clean forward-only null                       |
| `injected_residual`  | Recovery of a declared negative endpoint-level residual                     |
| `leakage`            | Temporal-leakage audit fires and blocks support                             |
| `selection_standard` | Retention audit or selection route blocks support                           |
| `collider_selection` | Endpoint-by-delay collider is classified selection-limited, never supported |
| `adversarial_null`   | False-support control under hard forward-only nuisance structure, including carryover, using the sequential e-value route |
| `opposite_direction` | Positive injection is classified opposite-direction, not support            |

The benchmark establishes operating characteristics of the software decision pipeline on simulated data. It is not empirical evidence for an anticipatory EEG effect.

## Inference routes

The benchmark distinguishes two locked inferential routes.

`assignment_isolation` is the finite-sample randomisation route. It holds the
frozen endpoint or residual array fixed under admissible reassignment and is used
only when endpoint-array invariance is justified. Its calibration is the plus-one
assignment randomisation test.

`sequential_evalue` is the carryover-sensitive route. It uses current-trial
assignment increments under the declared conditional scheduler law and calibrates
the resulting score by a predeclared martingale/e-value construction. It does
not condition on a globally reassigned endpoint array and does not regenerate
counterfactual endpoint trajectories.

The `adversarial_null` scenario uses `sequential_evalue`.

## Validity-matched inference-route comparison

The clean-null and adversarial-null rows in the seven-scenario table use
different inference routes and are not interpreted as identifying a generator
effect. Auxiliary experiment `route_match_1be69ec6cd081a58`,
parented to run `0cd4cac11153c546`, separates the route and generator
comparisons with three validity-respecting cells:

* identical clean-null datasets analysed by `assignment_isolation`;
* the same clean-null datasets analysed by `sequential_evalue`;
* the full adversarial null analysed by `sequential_evalue`.

Each cell used 1,200 Monte Carlo datasets.

The full adversarial generator is not analysed by assignment isolation because
its carryover structure does not satisfy the frozen endpoint-array invariance
required for global reassignment.

The paired clean-route contrast
`clean_sequential_minus_clean_assignment` has estimate
`+0.100833` and 95% paired-bootstrap interval
`[+0.083333, +0.119167]`.

The matched generator contrast
`adversarial_sequential_minus_clean_sequential` has estimate
`+0.006667` and 95% paired-bootstrap interval
`[-0.001210, +0.015233]`.

The matched generator 95% paired-bootstrap interval includes zero. The
auxiliary experiment therefore does not resolve a non-zero generator
difference. The larger
cross-route ordering in the original scenario rows is not interpreted as a
generator effect, and the route-matched result is not an equivalence claim.

## Install

```bash
conda env create -f environment.yml
conda activate leveliia
pip install -e .
```

Alternatively, without conda:

```bash
pip install -e .
```

## Run

Fast smoke run:

```bash
python scripts/run_all.py --smoke
python scripts/verify_outputs.py --smoke
```

Full benchmark run in a separate reproduction directory:

```bash
python scripts/run_all.py --all --outdir outputs_reproduced
```

The repository already contains the certified benchmark run. Re-running the same
configuration targets the same deterministic run hash and is refused by default
to protect the frozen output directory. Use `--resume` only for an incomplete
run directory, or `--overwrite` only when intentionally regenerating a run from
scratch.

Resume an interrupted reproduction run in that same separate directory:

```bash
python scripts/run_all.py --all --outdir outputs_reproduced --resume
```

Verify the certified benchmark and both auxiliary certifications:

```powershell
$RunHash = (Get-Content manuscript\certified_run_counts.json | ConvertFrom-Json).run_hash
python scripts\verify_outputs.py --run-hash $RunHash --strict-manuscript
python scripts\verify_adequacy_operating_characteristic.py --run-hash $RunHash
python scripts\verify_route_matched_null_comparison.py --run-hash $RunHash
```

Regenerate benchmark tables, figures and the worked example from that run:

```powershell
python scripts\make_figure2.py --run-hash $RunHash
python scripts\make_split_oc_tables.py --run-hash $RunHash
python scripts\make_tables.py --run-hash $RunHash
python scripts\make_worked_example.py --run-hash $RunHash
```

Export the complete certified manuscript-facing table set from the locked run
and validity-matched route experiment:

```powershell
python scripts\export_manuscript_tables.py --run-hash $RunHash --experiment-id route_match_1be69ec6cd081a58
```

This command reads the existing certified outputs and refreshes only the
manuscript-facing table copies and their rendering/checksum metadata. It does
not run Monte Carlo generation, regenerate raw or summary artefacts, or create
a new run hash. In the committed release state, repeating the command is
byte-idempotent and leaves the working tree clean.

Run unit tests:

```bash
pytest -q
```

Run a single scenario manually:

```bash
python scripts/run_benchmark.py --config configs/anchor.yaml --M 500
```

## Verification policy

`verify_outputs.py` has two layers.

First, it checks exact internal invariants:

* required scenarios are present;
* final-outcome counts are nonnegative integer counts;
* final-outcome counts do not exceed `M`;
* final-outcome rates equal count divided by `M`;
* mutually exclusive final-outcome counts sum to `M`;
* mutually exclusive final-outcome rates sum to one;
* diagnostic rates lie in `[0,1]`;
* row-level run hashes match the verified output directory when recorded.

Second, it checks operating-characteristic qualification thresholds:

* false-support control under the clean assignment-isolation null and the
  adversarial carryover-sensitive forward-only null;
* recovery under injected negative residual;
* leakage, selection and collider failures are blocked;
* opposite-direction injections are not counted as directional support;
* false-adequacy rates under material endpoint-level departures equal the
  corresponding forward-only adequate counts divided by `M`;
* scenario-level false-adequacy qualification requires both the point estimate
  and its Wilson 95% upper confidence bound to be at or below
  `p_FA_max = 0.05`.

The separate route-general adequacy certificate is verified by
`scripts/verify_adequacy_operating_characteristic.py`. That verifier checks the
one-sided, Bonferroni-adjusted Clopper-Pearson simultaneous upper-bound
envelope across the complete declared route-by-direction-by-magnitude family
and requires the route- and direction-specific envelope at the candidate
magnitude and all larger evaluated magnitudes to be at or below
`p_FA_max = 0.05`.

The optional `--strict-manuscript` flag checks the run hash and exact final-outcome
counts in `manuscript/certified_run_counts.json`. After a corrected full run has
passed all qualification and false-adequacy checks,
`--write-manuscript-lock` prospectively freezes its exact counts for manuscript
release checking.

## Seed and run-hash policy

* **Deterministic seeds.** Each scenario has a `base_seed`; Monte Carlo replicate `i` uses seed `base_seed * 1_000_000 + i`.
* **Replicate reproducibility.** Re-running a replicate reproduces it exactly, which is also how Figure 2 panels and the SI worked example are rebuilt.
* **Run hash.** `metadata.compute_run_hash` is a SHA-256 digest, truncated to the first 16 hex characters, over the resolved configuration bundle, package version, seed family and deterministic executable-source fingerprint. The same configurations and hashed source map to the same hash; changing either the configuration bundle or fingerprinted source changes the hash.
* **No overwrite by default.** `run_all.py` writes to a deterministic `<outdir>/<run_hash>/` directory. Repeating the same configuration, seed family and package version targets the same directory and is refused by default. Changed configurations produce changed hashes. Use `--outdir` for independent reproduction, `--resume` for incomplete runs, and `--overwrite` only for deliberate clean regeneration.
* **Latest run pointer.** `<outdir>/LATEST_RUN.txt` records the hash of the most recent completed all-scenario `run_all.py` execution within that output root, including smoke runs. The certified benchmark run is always identified explicitly by the committed hash in `manuscript/certified_run_counts.json`.

## Output layout

```text
outputs/<run_hash>/
  raw/*.csv                         per-replicate decision objects
  summary/operating_characteristics.csv
  summary/false_adequacy_rates.csv
  summary/collider_sweep.csv
  summary/representative_index.json
  tables/operating_characteristics_design.tex
  tables/operating_characteristics_outcomes.tex
  tables/collider_sweep.tex
  figures/figure2_validation.pdf
  metadata/run_metadata.json
```

Generated benchmark artefacts can be exported to the stable manuscript-facing
paths:

```text
manuscript/tables/
manuscript/figures/
```

These paths contain generated artefact copies only. The Perspective manuscript
and SI `.tex` files remain outside this repository and outside the Zenodo software
archive.

The SI worked example is generated from the locked representative-index
file and the frozen per-replicate rows.

## Certified auxiliary artefacts

The route-specific adequacy certification is
`adequacy_498657101acbb4e6`. The validity-matched inference-route comparison is
`route_match_1be69ec6cd081a58`. Both are parented to certified benchmark run
`0cd4cac11153c546`.

Canonical artefacts are stored at:

```text
outputs/0cd4cac11153c546/metadata/adequacy_certification.json
outputs/0cd4cac11153c546/summary/adequacy_operating_characteristic.csv
outputs/0cd4cac11153c546/tables/adequacy_operating_characteristic_assignment_isolation.tex
outputs/0cd4cac11153c546/tables/adequacy_operating_characteristic_sequential_evalue.tex

outputs/0cd4cac11153c546/metadata/route_matched_null_comparison.json
outputs/0cd4cac11153c546/summary/route_matched_null_comparison.csv
outputs/0cd4cac11153c546/summary/route_matched_null_contrasts.csv
outputs/0cd4cac11153c546/tables/route_matched_null_comparison.tex
```

The corresponding content-addressed auxiliary directories are:

```text
outputs/0cd4cac11153c546/auxiliary/adequacy_498657101acbb4e6/
outputs/0cd4cac11153c546/auxiliary/route_match_1be69ec6cd081a58/
```

## Reviewer reproduction guide

See

```text
docs/reviewer_reproduction_guide.md
```

The shortest reviewer path is:

```bash
python scripts/run_all.py --smoke
python scripts/verify_outputs.py --smoke
pytest -q
```

To rerun the full manuscript benchmark without touching the locked manuscript
output directory, run:

```bash
python scripts/run_all.py --all --outdir outputs_reproduced
```

To verify the certified benchmark package included in this repository, read the
committed hash from `manuscript/certified_run_counts.json` and run all three
verification commands shown above. Those commands verify the seven-scenario
parent run, the route-specific adequacy certification and the validity-matched
inference-route comparison.

If a new full run is generated for a later manuscript revision, update the manuscript, SI, figure captions, tables, data accessibility statement and release notes to point to the new run hash.

## Archival

The certified software-and-benchmark release `v1.2.0` is archived on
Zenodo.

- **Version-specific DOI for the exact `v1.2.0` archive:** [`10.5281/zenodo.21804381`](https://doi.org/10.5281/zenodo.21804381)
- **Concept DOI representing all software versions:** [`10.5281/zenodo.21804380`](https://doi.org/10.5281/zenodo.21804380)
- **Git tag:** `v1.2.0`
- **Release commit:** `6415e578cb4aa4a9923236a8a50ab468e9636a54`
- **Certified benchmark run:** `0cd4cac11153c546`
- **Route-specific adequacy certification:** `adequacy_498657101acbb4e6`
- **Validity-matched route comparison:** `route_match_1be69ec6cd081a58`

For exact reproduction or citation of the certified release, use the
version-specific DOI together with the certified run hash. The concept DOI is
used by the repository badge and resolves to the latest available software
release.

The archive covers the executable code, configurations, tests, synthetic-data
generators and committed benchmark artefacts. It does not include the
Perspective manuscript or Supplementary Information source files, which are
maintained separately.

## Honesty note

The numbers reported are operating characteristics of a software pipeline on simulated data. They establish that the locked decision procedure behaves as designed under the declared synthetic generators. They are not empirical evidence about human EEG and not a mechanism claim.

## Route-specific adequacy certification

The affirmative-adequacy certificate is magnitude-indexed and route-specific.
The committed certification `adequacy_498657101acbb4e6` is parented to
benchmark run `0cd4cac11153c546` and evaluates both departure directions over
the declared magnitude grid. The evaluated absolute magnitudes were
`|Delta| in {5, 10, 15, 20, 30, 40, 50, 60, 75, 90}` for both directions
under each inference route. Each route-direction-magnitude cell used 1,200
Monte Carlo datasets.

The certified resolution boundaries are:

* `assignment_isolation`: `|Delta| = 15`;
* `sequential_evalue`: `|Delta| = 30`.

These values are route-specific false-adequacy resolution boundaries. They are
not directional-power claims and do not imply that smaller departures are
absent.

Verify the committed certification without regenerating it:

```powershell
$RunHash = (Get-Content manuscript\certified_run_counts.json | ConvertFrom-Json).run_hash
python scripts\verify_adequacy_operating_characteristic.py --run-hash $RunHash
```

Verify the route-matched comparison without regenerating it:

```powershell
python scripts\verify_route_matched_null_comparison.py --run-hash $RunHash
```

Independent benchmark reproduction should use a separate output root such as
`outputs_reproduced`. Certified directories are protected from accidental
overwrite.
