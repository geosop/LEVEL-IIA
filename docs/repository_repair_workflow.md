# Classifier-alignment repository repair workflow

This workflow applies the July 11 classifier and participant-estimability repair,
validates it on a smoke run, commits the executable state, generates a new full
run, and only then promotes generated artefacts for manuscript editing.

## 1. Protect the current repository state

Run in PowerShell 7 from the repository root:

```powershell
$Repo = (git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Repo)) {
    throw 'Run this workflow from inside the repository.'
}
Set-Location $Repo

git rev-parse --show-toplevel
git log -1 --oneline
git status --short
```

The patch is based on commit `0dd09e7`. If `git status --short` reports tracked
changes, first determine whether they are line-ending-only:

```powershell
git diff --ignore-space-at-eol --quiet
$OnlyLineEndings = ($LASTEXITCODE -eq 0)
$OnlyLineEndings
```

If the result is `True` and there are no untracked files that need preserving,
restore the tracked working tree and disable automatic CRLF rewriting for this
repository:

```powershell
git restore --source=HEAD --worktree -- .
git config core.autocrlf false
```

Do not restore if the command reports real content changes. Commit or export
those changes first.

## 2. Apply the repair patch on a branch

```powershell
git switch -c fix/classifier-estimability-alignment

git apply --check 'C:\path\to\leveliia_repository_repair.patch'
git apply --whitespace=nowarn 'C:\path\to\leveliia_repository_repair.patch'

git status --short
git diff --check
```

The repair changes classifier semantics, participant-level slope centring,
participant-estimability sensitivity, generated table schemas, run hashing, and
verification logic. It intentionally does not implement raw-endpoint/residual
sign concordance as a support veto.

## 3. Create the Python 3.12 environment

```powershell
py -3.12 --version
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

For deterministic and resource-stable local checks:

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
```

## 4. Compile and test the repair

```powershell
python -m compileall -q src scripts tests

pytest -q tests\test_decision_branches.py `
          tests\test_decision_precedence.py `
          tests\test_participant_estimability.py `
          tests\test_beta_min.py `
          tests\test_collider_selection.py

pytest -q tests\test_assignment_law.py `
          tests\test_endpoint_injection.py `
          tests\test_randomisation.py `
          tests\test_sequential_evalue.py `
          tests\test_reproducibility_smoke.py

pytest -q tests\test_false_adequacy_rates.py `
          tests\test_formatting.py `
          tests\test_run_all_output_safety.py `
          tests\test_selection_gate.py
```

The adequacy-table regression test remains tied to the currently committed
certified run until the new full run and adequacy sweep are promoted.

## 5. Run and inspect a repaired smoke benchmark

```powershell
$SmokeRoot = Join-Path $Repo 'outputs_repair_smoke'
if (Test-Path $SmokeRoot) { Remove-Item $SmokeRoot -Recurse -Force }

python scripts\run_all.py --smoke --M 20 --no-sweep --outdir $SmokeRoot
$SmokeHash = (Get-Content (Join-Path $SmokeRoot 'LATEST_RUN.txt')).Trim()

python scripts\verify_outputs.py `
  --smoke `
  --run-hash $SmokeHash `
  --outdir $SmokeRoot

python scripts\make_worked_example.py `
  --run-hash $SmokeHash `
  --outdir $SmokeRoot
```

Inspect the new classifier fields:

```powershell
$SmokeCsv = Join-Path $SmokeRoot "$SmokeHash\summary\operating_characteristics.csv"
Import-Csv $SmokeCsv |
  Select-Object scenario, N_estimable_med, nonestimable_fraction_med,
                component_disagreement_rate,
                estimability_conclusion_change_rate,
                gate_applicable_rate,
                gate_pass_given_applicable_rate,
                support_rate, null_rate, selection_limited_rate,
                opposite_direction_rate, inconclusive_rate |
  Format-Table -AutoSize
```

Expected qualitative behaviour is:

- clean null: no support, mostly adequate, disagreement routed to inconclusive;
- negative injection: support;
- leakage: diagnostic failure;
- ordinary and collider selection: selection-limited;
- adversarial null: no support;
- positive injection: opposite-direction diagnostic, never negative support.

## 6. Commit the executable repair before the full run

The full-run metadata records the Git commit. Commit the code and configuration
repair before generating the certified candidate:

```powershell
git add .gitattributes CITATION.cff README.md pyproject.toml `
        configs docs scripts src tests manuscript\certified_run_counts.json

git commit -m 'Align classifier, estimability gates, and benchmark provenance'

git status --short
git log -1 --oneline
```

The working tree should be clean before the full run.

## 7. Generate and verify a full candidate run

Use a separate candidate output root so the currently certified run remains
untouched:

```powershell
$CandidateRoot = Join-Path $Repo 'outputs_candidate'
if (Test-Path $CandidateRoot) { Remove-Item $CandidateRoot -Recurse -Force }

python scripts\run_all.py --all --outdir $CandidateRoot
$NewHash = (Get-Content (Join-Path $CandidateRoot 'LATEST_RUN.txt')).Trim()
$NewHash

python scripts\verify_outputs.py `
  --run-hash $NewHash `
  --outdir $CandidateRoot
```

Do not proceed if verification fails. Inspect the complete numeric source:

```powershell
$CandidateCsv = Join-Path $CandidateRoot "$NewHash\summary\operating_characteristics.csv"
Import-Csv $CandidateCsv | Format-Table -AutoSize

Get-Content (Join-Path $CandidateRoot "$NewHash\summary\false_adequacy_rates.csv")
Get-Content (Join-Path $CandidateRoot "$NewHash\metadata\run_metadata.json")
```

Confirm that `run_metadata.json` contains the just-created code commit and a
non-empty `source_fingerprint`.

## 8. Promote the verified candidate into `outputs/`

```powershell
$SourceRun = Join-Path $CandidateRoot $NewHash
$DestinationRun = Join-Path $Repo "outputs\$NewHash"

if (Test-Path $DestinationRun) {
  throw "Destination already exists: $DestinationRun"
}

Copy-Item $SourceRun $DestinationRun -Recurse
Set-Content -Path (Join-Path $Repo 'outputs\LATEST_RUN.txt') -Value $NewHash
```

Verify the promoted copy:

```powershell
python scripts\verify_outputs.py --run-hash $NewHash
```

## 9. Regenerate the magnitude-indexed adequacy certificate

Classifier-semantic changes invalidate the prior adequacy sweep. Regenerate it
against the promoted run:

```powershell
python scripts\make_adequacy_operating_characteristic.py `
  --run-hash $NewHash `
  --M 1200 `
  --deltas '20,30,40,50,60,75,90' `
  --overwrite
```

Inspect the new direction-specific and combined certified magnitudes in:

```text
outputs/<new-hash>/summary/adequacy_operating_characteristic.csv
```

Do not assume that the earlier certified magnitude remains unchanged.

## 10. Generate all manuscript-facing artefacts

Generate the worked example before `make_tables.py`, because `make_tables.py`
copies every non-legacy generated table into the local manuscript workspace:

```powershell
python scripts\make_worked_example.py --run-hash $NewHash
python scripts\make_split_oc_tables.py --run-hash $NewHash
python scripts\make_figure2.py --run-hash $NewHash
python scripts\make_tables.py --run-hash $NewHash
```

Then freeze the exact outcome counts used by the revised manuscript:

```powershell
python scripts\verify_outputs.py `
  --run-hash $NewHash `
  --write-manuscript-lock

python scripts\verify_outputs.py `
  --run-hash $NewHash `
  --strict-manuscript
```

Run the adequacy regression test after the new table has been copied:

```powershell
pytest -q tests\test_adequacy_operating_characteristic.py
```

## 11. Commit the certified run and generated artefacts

```powershell
git add outputs\$NewHash outputs\LATEST_RUN.txt `
        manuscript\certified_run_counts.json `
        manuscript\tables manuscript\figures

git commit -m "Certify classifier-aligned benchmark run $NewHash"
```

Run the strict verification once more from the committed state:

```powershell
python scripts\verify_outputs.py --run-hash $NewHash --strict-manuscript
git status --short
```

## 12. Manuscript update checkpoint

Only after the preceding commands pass should the external main manuscript and
SI be edited. Use the new generated tables and CSVs as the sole numeric source.
The manuscript update must include:

- component disagreement routes to inconclusive;
- participant-estimability and retained-leverage qualification;
- scalar selection gate applies only to resolved material departures;
- unadjusted endpoint analysis is descriptive adjustment sensitivity only;
- negative tail is the sole confirmatory level-alpha hypothesis;
- positive tail is a prespecified diagnostic;
- route-specific slope statements and the corrected trial-local Lemma S1 scope;
- new run hash, exact outcome counts, adequacy certificate, figure and archive metadata.
