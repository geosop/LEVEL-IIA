# Level II-A post-endpoint randomisation benchmark

Reproducible benchmark pipeline for the Perspective **"Testing past-adapted
accounts of anticipatory EEG with post-endpoint randomisation."**

This repository qualifies the locked Level II-A analysis pipeline on **simulated
data with known generating processes**. It is a design-stage falsification and
validation framework. It does **not** analyse human EEG, and it makes **no
mechanism claim**. Every benchmark number quoted in the Perspective, the
electronic supplementary material, Figure 2, and this README is produced by the
code here and recorded under a run hash.

## What the benchmark establishes

The locked pipeline (committed endpoint, label-blind cross-fitted forward-only
comparator, frozen residual, participant-slope estimand, plus-one randomisation
test, studentised participant bootstrap-t bound, audit battery, scalar
selection-sensitivity gate, endpoint-by-delay collider diagnostic, and
non-compensatory decision rule) is required to behave as designed under seven
scenarios:

| scenario | required behaviour |
|---|---|
| clean forward-only null | false-support rate at the nominal level |
| injected endpoint residual | recovers the negative slope at the planned power |
| leakage artefact | temporal-leakage audit fires and blocks support |
| standard selection | retention audit / selection gate block support |
| pure endpoint-by-delay collider | classified selection-limited, never supported |
| adversarial forward-only null | false-support control under hard nuisance structure |
| opposite-direction injection | classified opposite-direction, not support |

## Install

```bash
conda env create -f environment.yml
conda activate cri-leveliia
pip install -e .
```

`pip install -e .` (with `requirements.txt`) is sufficient without conda.

## Run

```bash
python scripts/run_all.py --smoke              # fast low-M sanity run
python scripts/verify_outputs.py --smoke       # check qualification invariants
python scripts/run_all.py --all                # full manuscript run (writes a run dir)
python scripts/run_all.py --all --resume       # resume an interrupted full run
python scripts/make_figure2.py --run-hash <RUN_HASH>
python scripts/make_tables.py  --run-hash <RUN_HASH>
python scripts/verify_outputs.py --run-hash <RUN_HASH>
pytest -q                                       # unit tests
```

A single scenario:

```bash
python scripts/run_benchmark.py --config configs/anchor.yaml --M 500
```

## Seed and run-hash policy

* **Deterministic seeds.** Each scenario has a `base_seed`; Monte Carlo replicate
  `i` uses seed `base_seed * 1_000_000 + i`. Re-running a replicate reproduces it
  exactly, which is also how Figure 2 panels and the worked example are rebuilt.
* **Run hash.** `metadata.compute_run_hash` is a SHA-256 (first 16 hex) over the
  resolved configuration bundle plus the code version and seed family. The same
  configs and code always map to the same hash; changing any config changes it.
* **No overwrite by default.** `run_all.py` writes to `outputs/<run_hash>/`. A new
  run writes a new directory unless `--overwrite` is passed. `outputs/LATEST_RUN.txt`
  records the hash of the last completed full run.

## Output layout

```
outputs/<run_hash>/
  raw/<scenario>.csv                 per-replicate decision objects
  summary/operating_characteristics.csv
  summary/collider_sweep.csv
  summary/representative_index.json  replicate shown in each Figure 2 panel
  tables/operating_characteristics.tex
  tables/collider_sweep.tex
  figures/figure2_validation.pdf
  metadata/run_metadata.json         seeds, versions, timestamp, hash
```

## Reviewer reproduction guide

See `docs/reviewer_reproduction_guide.md`. In short: create the environment,
`pip install -e .`, run `python scripts/run_all.py --smoke` then
`python scripts/verify_outputs.py --smoke` (about a minute), and for the full
result run `python scripts/run_all.py --all` and re-point the manuscript's data
accessibility statement at the resulting run hash.

## Archival

A Zenodo archive and DOI will be minted from the first public GitHub release. After release archiving, the DOI will be added here and to the repository citation metadata.

## Honesty note

The numbers reported are operating characteristics of a software pipeline on
simulated data. They establish that the locked decision procedure behaves as
designed. They are not empirical evidence about human EEG and not a mechanism
claim.
