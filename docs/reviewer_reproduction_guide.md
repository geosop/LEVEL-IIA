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

## 3. Full independent benchmark reproduction

Run a full reproduction in a separate output root so the committed certified
run directory remains untouched:

```powershell
& $Py scripts\run_all.py --all --outdir outputs_reproduced
$RunHash = (Get-Content outputs_reproduced\LATEST_RUN.txt).Trim()

& $Py scripts\make_figure2.py `
  --run-hash $RunHash `
  --outdir outputs_reproduced `
  --no-copy
& $Py scripts\make_tables.py `
  --run-hash $RunHash `
  --outdir outputs_reproduced `
  --no-copy
& $Py scripts\verify_outputs.py `
  --run-hash $RunHash `
  --outdir outputs_reproduced
& $Py scripts\make_worked_example.py `
  --run-hash $RunHash `
  --outdir outputs_reproduced
```

This reproduction path may regenerate derived artefacts inside
`outputs_reproduced`; it does not modify the committed certified directory under
`outputs/`.

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
  table and the synthetic-validation figure panel rates.
* `summary/false_adequacy_rates.csv` is derived from `summary/operating_characteristics.csv`
  and reports the rate at which a material endpoint-level departure is classified
  as forward-only adequate.
* `summary/collider_sweep.csv` underlies the collider scope subtable: marginal
  retention imbalance stays small while the manufactured slope and the interaction
  diagnostic fire rate grow.
* `summary/representative_index.json` records the exact replicate shown in each
  synthetic-validation figure panel (regenerated from its deterministic seed,
  not hand-picked). The legacy internal generator/file identifiers are
  `make_figure2.py` and `figure2_validation.pdf`.
* `metadata/run_metadata.json` records seeds, package versions, and the run hash.

## 5. Notes

* Monte Carlo size `M` is a command-line argument (`--M`). The manuscript run uses
  the value recorded in `run_metadata.json`. Larger `M` tightens the reported rates;
  pass/fail invariants are insensitive to `M` above a few hundred.
* The collider scenario uses a resolution-floor multiple kappa = 1 (recorded in
  `configs/collider_selection.yaml`) so that the manufactured slope is material;
  this is the configuration that isolates the endpoint-by-delay interaction
  diagnostic as the operative guard. All other scenarios use kappa = 2.

### False-adequacy operating-characteristic certification

Verify the committed route-specific certificate without regenerating it:

~~~powershell
$RunHash = (Get-Content manuscript\certified_run_counts.json |
  ConvertFrom-Json).run_hash
$Py = (Resolve-Path .\.venv312\Scripts\python.exe).Path
& $Py scripts\verify_adequacy_operating_characteristic.py `
  --run-hash $RunHash
if ($LASTEXITCODE -ne 0) {
  throw "False-adequacy certification verification failed."
}
~~~

The committed manifest `configs/adequacy_certification.yaml` declares the
complete grid `5, 10, 15, 20, 30, 40, 50, 60, 75, 90`, both directions and both
inference routes, for 40 cells in total. Independent regeneration must use that
manifest and a separate output root containing an independently reproduced
parent benchmark run. It must not overwrite the committed certified outputs.
Pointwise Wilson intervals remain descriptive; certification uses the
one-sided, Bonferroni-adjusted Clopper-Pearson familywise upper-bound envelope.


## Rendering-only terminology alignment of the certified run

Reader-facing terminology repairs to generated tables and the
synthetic-validation figure are applied as a presentation layer over the frozen
certified run. They do **not** rerun
`run_all.py`, regenerate adequacy Monte Carlo cells, or alter any raw/summary
evidence file. The executable outcome field remains `forward_only_adequate`; the
legacy raw indicator name `null` is retained in data structures for provenance.

On Windows PowerShell, regenerate only the manuscript-facing rendering from the
certified run as follows:

```powershell
$RunHash = (Get-Content manuscript\certified_run_counts.json |
  ConvertFrom-Json).run_hash
$Py = (Resolve-Path .\.venv312\Scripts\python.exe).Path

& $Py scripts\export_manuscript_tables.py --run-hash $RunHash
& $Py scripts\make_figure2.py --run-hash $RunHash

& $Py scripts\verify_outputs.py --run-hash $RunHash --strict-manuscript
& $Py scripts\verify_adequacy_operating_characteristic.py --run-hash $RunHash

if ($LASTEXITCODE -ne 0) {
  throw "Certified-run rendering verification failed."
}

git diff --exit-code -- "outputs/$RunHash/raw" "outputs/$RunHash/summary"
if ($LASTEXITCODE -ne 0) {
  throw "Rendering repair changed protected raw/summary evidence."
}
```

`export_manuscript_tables.py` updates the table-rendering checksum chains,
including the route-matched and adequacy table metadata, while asserting that
the protected raw and summary evidence tree is unchanged. `make_figure2.py`
performs the analogous evidence-tree check for the figure, updates
`figure2_rendering.json`, and refreshes the certified-output checksum manifest.
The certified parent run hash and adequacy experiment ID therefore remain fixed
while the presentation artefacts receive new checksums.
