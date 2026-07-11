# Level II-A post-endpoint randomisation benchmark

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

### Certification transition status

Version 1.1.0 changes the non-compensatory classifier, participant-level
estimability qualification, retained-design leverage handling, conditional
selection-gate reporting, and benchmark provenance. The currently committed
lock points to legacy run `f930a51c1c594275`, which was generated under version
1.0.0. That run is retained only for historical reproduction and does not
certify the revised version 1.1.0 pipeline.

After this source revision is committed, a complete candidate benchmark with
1,200 Monte Carlo datasets per scenario and the associated magnitude-indexed
adequacy sweep will be generated and independently verified. Only after those
checks pass will the candidate run be promoted, the manuscript count lock be
replaced, and the README, generated tables, figures, release metadata and
external manuscript references be updated. Smoke runs are execution checks
only and must not be cited as certified results.

The currently locked legacy full benchmark run is identified in
`manuscript/certified_run_counts.json`. That committed lock preserves the exact
run hash and mutually exclusive outcome counts from the last certified
manuscript-facing benchmark package. It will be replaced only after the revised
version 1.1.0 full run passes all verification and adequacy checks. The planned
full-run design is:

```text
M:        1200 Monte Carlo datasets per scenario
P:        24 participants
n/bin:    24 planned trials per assigned-delay bin
R:        999 randomisation draws where assignment-isolation calibration is used
B:        999 participant bootstrap replicates
support:  [0, 20] ms
```

The corresponding output directory is `outputs/<certified-run-hash>/`, where
`<certified-run-hash>` is read from the committed lock file.

The canonical numeric source for the certified operating characteristics is

```text
outputs/<certified-run-hash>/summary/operating_characteristics.csv
```

The false-adequacy rates under material endpoint-level departures are derived
from the same certified operating-characteristics CSV and written as

```text
outputs/<certified-run-hash>/summary/false_adequacy_rates.csv
```

An operating point licenses affirmative-null certification only if the
false-adequacy point estimate and the Wilson 95% upper confidence bound are both
at or below `p_FA_max = 0.05`.

The manuscript-facing LaTeX tables are generated from the certified CSV as split
design and outcome tables:

```text
outputs/<certified-run-hash>/tables/operating_characteristics_design.tex
outputs/<certified-run-hash>/tables/operating_characteristics_outcomes.tex
```

The earlier lower-retained-trial reference run is retained only as a
pipeline-architecture demonstration and is not used to license affirmative-null
certification.
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

## Install

```bash
conda env create -f environment.yml
conda activate cri-leveliia
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

The repository already contains the locked manuscript run. Re-running the same
configuration targets the same deterministic run hash and is refused by default
to protect the frozen output directory. Use `--resume` only for an incomplete
run directory, or `--overwrite` only when intentionally regenerating a run from
scratch.

Resume an interrupted reproduction run in that same separate directory:

```bash
python scripts/run_all.py --all --outdir outputs_reproduced --resume
```

Verify the locked manuscript run in PowerShell:

```powershell
$RunHash = (Get-Content manuscript\certified_run_counts.json | ConvertFrom-Json).run_hash
python scripts\verify_outputs.py --run-hash $RunHash --strict-manuscript
```

Regenerate benchmark tables, figures and the worked example from that run:

```powershell
python scripts\make_figure2.py --run-hash $RunHash
python scripts\make_split_oc_tables.py --run-hash $RunHash
python scripts\make_tables.py --run-hash $RunHash
python scripts\make_worked_example.py --run-hash $RunHash
```

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
* affirmative-null certification requires both the false-adequacy point
  estimate and the Wilson 95% upper confidence bound to be at or below
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
* **Latest run pointer.** `<outdir>/LATEST_RUN.txt` records the hash of the most recent completed all-scenario `run_all.py` execution within that output root, including smoke runs. The locked manuscript run is always identified explicitly by the committed hash in `manuscript/certified_run_counts.json`.

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

Generated benchmark artefacts can be exported for an external manuscript workflow.
Some helper scripts may copy generated tables or figures into local manuscript
workspaces such as:

```text
manuscript/tables/
CRI_Perspective/Tables/
CRI_Perspective/Figures/
```

These local manuscript workspaces are not part of the public manuscript source
package. The Perspective manuscript and SI `.tex` files remain outside this
repository and outside the Zenodo software archive.

The SI worked example is generated from the locked representative-index file and the frozen per-replicate rows.

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

To verify the locked manuscript package included in this repository, read the
committed hash from `manuscript/certified_run_counts.json` and run
`verify_outputs.py --strict-manuscript` as shown above.

If a new full run is generated for a later manuscript revision, update the manuscript, SI, figure captions, tables, data accessibility statement and release notes to point to the new run hash.

## Archival

A Zenodo archive and DOI will be minted from the public GitHub release of this
benchmark repository. The archive covers the code, configurations, tests,
synthetic generators, and benchmark artefacts included in the release. It does
not include the Perspective manuscript or Supplementary Information source
files, which are maintained separately.

## Honesty note

The numbers reported are operating characteristics of a software pipeline on simulated data. They establish that the locked decision procedure behaves as designed under the declared synthetic generators. They are not empirical evidence about human EEG and not a mechanism claim.

## Adequacy operating-characteristic sweep

The D2 affirmative-null certificate is magnitude-indexed. The adequacy operating
characteristic must be regenerated against the same committed run after every
classifier-semantic change. It is generated by:

~~~powershell
$RunHash = (Get-Content outputs\LATEST_RUN.txt).Trim()
.\.venv312\Scripts\python.exe scripts\make_adequacy_operating_characteristic.py `
  --run-hash $RunHash `
  --M 1200 `
  --deltas "20,30,40,50,60,75,90" `
  --overwrite
~~~

This writes:

- `outputs/<run_hash>/summary/adequacy_operating_characteristic.csv`
- `outputs/<run_hash>/tables/adequacy_operating_characteristic.tex`
- `outputs/<run_hash>/metadata/adequacy_sweep_metadata.json`
- copied manuscript tables under `CRI_Perspective/Tables/` and `manuscript/tables/`

The certified magnitude is defined from the monotone Wilson upper-bound envelope:
for a given direction, all evaluated magnitudes at or above the certified
magnitude must have false-adequacy point estimate and Wilson 95% upper bound at
or below `p_FA_max = 0.05`.

