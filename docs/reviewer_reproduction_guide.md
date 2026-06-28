# Reviewer reproduction guide

## 1. Environment

```bash
conda env create -f environment.yml
conda activate cri-leveliia
pip install -e .
```

Reference environment: Python 3.12, numpy 2.4, scipy 1.17, pandas 3.0,
matplotlib, pyyaml. `pip install -e .` against `requirements.txt` also works.

## 2. One-minute sanity check

```bash
python scripts/run_all.py --smoke
python scripts/verify_outputs.py --smoke
pytest -q
```

`verify_outputs.py` checks the qualification invariants (false-support control,
recovery power, audit blocking, the collider scope test, opposite-direction
classification). It exits non-zero on failure.

## 3. Full manuscript run

```bash
python scripts/run_all.py --all            # or: --all --resume to continue
```

This writes `outputs/<run_hash>/` and updates `outputs/LATEST_RUN.txt`. Then:

```bash
RUN_HASH=$(cat outputs/LATEST_RUN.txt)
python scripts/make_figure2.py --run-hash $RUN_HASH
python scripts/make_tables.py  --run-hash $RUN_HASH
python scripts/verify_outputs.py --run-hash $RUN_HASH
```

## 4. What to inspect

* `summary/operating_characteristics.csv` underlies the SI operating-characteristics
  table and the Figure 2 panel rates.
* `summary/collider_sweep.csv` underlies the collider scope subtable: marginal
  retention imbalance stays small while the manufactured slope and the interaction
  diagnostic fire rate grow.
* `summary/representative_index.json` records the exact replicate shown in each
  Figure 2 panel (regenerated from its deterministic seed, not hand-picked).
* `metadata/run_metadata.json` records seeds, package versions, and the run hash.

## 5. Notes

* Monte Carlo size `M` is a command-line argument (`--M`). The manuscript run uses
  the value recorded in `run_metadata.json`. Larger `M` tightens the reported rates;
  pass/fail invariants are insensitive to `M` above a few hundred.
* The collider scenario uses a resolution-floor multiple kappa = 1 (recorded in
  `configs/collider_selection.yaml`) so that the manufactured slope is material;
  this is the configuration that isolates the endpoint-by-delay interaction
  diagnostic as the operative guard. All other scenarios use kappa = 2.
