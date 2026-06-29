# Level II-A post-endpoint randomisation benchmark

Reproducible benchmark pipeline for the Perspective **"Testing past-adapted accounts of anticipatory EEG by post-endpoint randomisation."**

This repository qualifies the locked Level II-A analysis pipeline on **simulated data with known generating processes**. It is a design-stage falsification and validation framework. It does **not** analyse human EEG, and it makes **no mechanism claim**.

Every benchmark number quoted in the Perspective, the electronic supplementary material, Figure 2, and the manuscript tables is produced from the code and recorded under a run hash.

## Locked manuscript run

The manuscript and electronic supplementary material use the frozen full benchmark run

```text
run hash: 9d2658d6d147de10
M:        1200 Monte Carlo datasets per scenario
P:        24 participants
support:  [0, 20] ms
```

The corresponding output directory is

```text
outputs/9d2658d6d147de10/
```

The complete machine-generated operating-characteristics table is archived at

```text
outputs/9d2658d6d147de10/tables/operating_characteristics.tex
```

For page-width readability, the manuscript may print a split version of the same values, separating design summaries from diagnostic and final-outcome summaries. The authoritative numeric source remains the frozen run directory.

## What the benchmark establishes

The locked pipeline consists of:

* committed endpoint;
* label-blind cross-fitted forward-only comparator;
* frozen residual array;
* participant-level slope estimand;
* plus-one randomisation test;
* studentised participant bootstrap-t upper bound;
* materiality floor;
* audit battery;
* scalar selection-sensitivity gate;
* endpoint-by-delay collider diagnostic;
* non-compensatory final classifier.

The pipeline is required to behave as designed under seven scenarios.

| Scenario             | Required behaviour                                                          |
| -------------------- | --------------------------------------------------------------------------- |
| `clean_null`         | False-support control under a clean forward-only null                       |
| `injected_residual`  | Recovery of a declared negative endpoint-level residual                     |
| `leakage`            | Temporal-leakage audit fires and blocks support                             |
| `selection_standard` | Retention audit or selection route blocks support                           |
| `collider_selection` | Endpoint-by-delay collider is classified selection-limited, never supported |
| `adversarial_null`   | False-support control under hard forward-only nuisance structure            |
| `opposite_direction` | Positive injection is classified opposite-direction, not support            |

The benchmark establishes operating characteristics of the software decision pipeline on simulated data. It is not empirical evidence for an anticipatory EEG effect.

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

Full benchmark run:

```bash
python scripts/run_all.py --all
```

Resume an interrupted full run:

```bash
python scripts/run_all.py --all --resume
```

Verify the locked manuscript run:

```bash
python scripts/verify_outputs.py --run-hash 9d2658d6d147de10
python scripts/verify_outputs.py --run-hash 9d2658d6d147de10 --strict-manuscript
```

Regenerate manuscript-facing artefacts from the locked run:

```bash
python scripts/make_figure2.py --run-hash 9d2658d6d147de10
python scripts/make_tables.py --run-hash 9d2658d6d147de10
python scripts/make_worked_example.py
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

* false-support control under clean and adversarial forward-only nulls;
* recovery under injected negative residual;
* leakage, selection and collider failures are blocked;
* opposite-direction injections are not counted as directional support.

The optional `--strict-manuscript` flag checks the exact final-outcome counts used in the manuscript for run `9d2658d6d147de10`. This flag is intended for release checks of the manuscript run, not for arbitrary exploratory runs.

## Seed and run-hash policy

* **Deterministic seeds.** Each scenario has a `base_seed`; Monte Carlo replicate `i` uses seed `base_seed * 1_000_000 + i`.
* **Replicate reproducibility.** Re-running a replicate reproduces it exactly, which is also how Figure 2 panels and the SI worked example are rebuilt.
* **Run hash.** `metadata.compute_run_hash` is a SHA-256 digest, truncated to the first 16 hex characters, over the resolved configuration bundle plus the code version and seed family. The same configs and code map to the same hash; changing any config changes the hash.
* **No overwrite by default.** `run_all.py` writes to `outputs/<run_hash>/`. A new run writes a new directory unless `--overwrite` is passed.
* **Latest run pointer.** `outputs/LATEST_RUN.txt` records the hash of the last completed full run.

## Output layout

```text
outputs/<run_hash>/
  raw/*.csv                         per-replicate decision objects
  summary/operating_characteristics.csv
  summary/collider_sweep.csv
  summary/representative_index.json
  tables/operating_characteristics.tex
  tables/collider_sweep.tex
  figures/figure2_validation.pdf
  metadata/run_metadata.json
```

Manuscript-facing generated artefacts are copied or written under:

```text
CRI_Perspective/Tables/
CRI_Perspective/Figures/
```

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

To reproduce the full manuscript benchmark, run:

```bash
python scripts/run_all.py --all
python scripts/verify_outputs.py --run-hash 9d2658d6d147de10 --strict-manuscript
```

If a new full run is generated for a later manuscript revision, update the manuscript, SI, figure captions, tables, data accessibility statement and release notes to point to the new run hash.

## Archival

A Zenodo archive and DOI will be minted from the first public GitHub release. After release archiving, the DOI will be added here and to the repository citation metadata.

## Honesty note

The numbers reported are operating characteristics of a software pipeline on simulated data. They establish that the locked decision procedure behaves as designed under the declared synthetic generators. They are not empirical evidence about human EEG and not a mechanism claim.

