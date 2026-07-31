# Reviewer reproduction guide

## 1. Environment

For exact verification on Windows, use Python 3.12 and the committed dependency
lock:

```powershell
py -3.12 -m venv .venv312
$Py = (Resolve-Path .\.venv312\Scripts\python.exe).Path
& $Py -m pip install -r requirements-lock-py312.txt
& $Py -m pip install -e . --no-deps
```

The certified run records Python 3.12.7, NumPy 2.5.0, SciPy 1.18.0,
pandas 3.0.3, Matplotlib 3.11.0 and PyYAML 6.0.3. The committed lock is the
authoritative environment specification for exact verification. The looser
`environment.yml` and `requirements.txt` files remain suitable for exploratory
use, not byte-level certification checks.

## 2. One-minute sanity check

```bash
python scripts/run_all.py --smoke
python scripts/verify_outputs.py --smoke
pytest -q
```

`verify_outputs.py` checks false-support control, recovery power, audit blocking,
the collider scope test, component-disagreement routing, participant-estimability
diagnostics, opposite-direction diagnostic classification, and false-adequacy
rates under material endpoint-level departures. It exits non-zero on failure.

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
python scripts/make_worked_example.py --run-hash $RUN_HASH
```

## Certified manuscript run

The certified manuscript run is the hash committed in
`manuscript/certified_run_counts.json`. It uses `M=1200` Monte Carlo datasets per
scenario, `P=24` participants, five assigned-delay bins, and `n/bin=24` planned
trials per assigned-delay bin.

Pointwise Wilson intervals are descriptive. Certification uses the one-sided,
Bonferroni-adjusted Clopper-Pearson simultaneous upper-bound envelope across
the complete declared 40-cell route-by-direction-by-magnitude family. A
route-direction operating point is certified only when the envelope at that
magnitude and all larger evaluated magnitudes is at or below
`p_FA_max = 0.05`.

The certified false-adequacy file is:

```text
outputs/<certified-run-hash>/summary/false_adequacy_rates.csv
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

### Adequacy operating-characteristic certification

Verify the committed route-specific certificate without regenerating it:

~~~powershell
$RunHash = (Get-Content manuscript\certified_run_counts.json |
  ConvertFrom-Json).run_hash
$Py = (Resolve-Path .\.venv312\Scripts\python.exe).Path
& $Py scripts\verify_adequacy_operating_characteristic.py `
  --run-hash $RunHash
if ($LASTEXITCODE -ne 0) {
  throw "Adequacy certification verification failed."
}
~~~

The committed manifest `configs/adequacy_certification.yaml` declares the
complete grid `5, 10, 15, 20, 30, 40, 50, 60, 75, 90`, both directions and both
inference routes, for 40 cells in total. Independent regeneration must use that
manifest and a separate output root containing an independently reproduced
parent benchmark run. It must not overwrite the committed certified outputs.
Pointwise Wilson intervals remain descriptive; certification uses the
one-sided, Bonferroni-adjusted Clopper-Pearson familywise upper-bound envelope.

