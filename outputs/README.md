# Outputs

Frozen benchmark runs live in `outputs/<run_hash>/`. Do not edit these by hand.
The manuscript-facing figures and tables are rendered from one such directory.
The certified run hash is committed in `manuscript/certified_run_counts.json`;
`outputs/LATEST_RUN.txt` is only the most recent execution pointer and may change
after smoke or independent reproduction runs.

Subdirectories: `raw/` (per-replicate decision objects), `summary/` (scenario
summaries, derived false-adequacy rates, collider sweep, representative-replicate
index), `tables/` (generated LaTeX presentation artefacts), `figures/`
(synthetic-validation rendering; legacy internal filename
`figure2_validation.pdf`), and `metadata/` (seeds, package versions, timestamp,
run hash, rendering/checksum provenance).

For a rendering-only refresh of the committed certified run, use
`scripts/export_manuscript_tables.py` and `scripts/make_figure2.py`. Those paths
must leave the protected `raw/` and `summary/` evidence unchanged. Direct table,
worked-example or Monte Carlo generators are for fresh independent reproductions,
not for hand-editing or presentation-only repair of the certified directory.
