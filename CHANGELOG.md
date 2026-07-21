# Changelog

## v1.0.1 — 2026-07-21

Corrections from a cross-model adversarial review (OpenAI-lineage reviewer
over the published files), run one day after v1.0. Material fixes:

- metrics: liveness (u_epsilon / q_max) now counts non-endorsements on valid
  tasks, not abstentions only. Identical-sonnet's quorum window is empty
  under the corrected accounting; two diverse windows tightened to [1,1].
- metrics: undefined (zero-variance) pairwise phi is None and counted
  (`n_phi_pairs` / `n_phi_undefined` report fields), never silently 0.0;
  clean-subset independence claims restated as event counts with bounds.
- report regenerated (`runs/phase2c/report.json`); v1.0.0 report preserved.

Defect fixes with no numeric impact:

- grok adapter: served-model provenance now uses the shared
  requested-when-proven-else-dominant rule (latent first-entry bug).
- grok adapter: prompt via file, not argv.
- CLI binary resolution: `QC_CODEX_BIN`/`QC_GROK_BIN` env -> PATH -> error
  (personal fallback paths removed).
- gold-set build: verdict-JSON injection guard; module docstring updated.
- `goldset build` CLI now produces the truth-by-construction valid stratum
  (`--n-revert`, default = n-invalid) and applies the strict commit filter
  by default (`--loose-valid` to disable).

## v1.0 — 2026-07-21

Initial public release: calibration instrument, four-act writeup, runtime
discipline (risk profiles, CUSUM drift monitor, provenance triggers).
