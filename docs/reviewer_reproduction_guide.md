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
classification, and the derived false-adequacy rates under material endpoint-level
departures). It exits non-zero on failure.

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

## Certified manuscript run

The certified manuscript run is `71d6a56c10a1c0ed`. It uses `M=1200` Monte Carlo
datasets per scenario, `P=24` participants, five assigned-delay bins, and
`n/bin=24` planned trials per assigned-delay bin.

Affirmative-null certification requires both the false-adequacy point estimate
and the Wilson 95% upper confidence bound to be at or below `p_FA_max = 0.05`.

The certified false-adequacy file is:

```text
outputs/71d6a56c10a1c0ed/summary/false_adequacy_rates.csv
```
## 4. What to inspect

* `summary/operating_characteristics.csv` underlies the SI operating-characteristics
  table and the Figure 2 panel rates.
* `summary/false_adequacy_rates.csv` is derived from `summary/operating_characteristics.csv`
  and reports the rate at which a material endpoint-level departure is classified
  as forward-only adequate.
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

### Adequacy operating-characteristic sweep

To reproduce the magnitude-indexed D2 certificate, run:

~~~powershell
$RunHash = (Get-Content outputs\LATEST_RUN.txt).Trim()
.\.venv312\Scripts\python.exe scripts\make_adequacy_operating_characteristic.py `
  --run-hash $RunHash `
  --M 1200 `
  --deltas "20,30,40,50,60,75,90" `
  --overwrite
~~~

The resulting CSV and LaTeX table are archived under
`outputs/<run_hash>/summary/` and `outputs/<run_hash>/tables/`. The certificate
uses the monotone Wilson upper-bound envelope across all evaluated magnitudes at
or above the reported threshold.
