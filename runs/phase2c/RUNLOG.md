# Phase 2c run log — truth-by-construction valid side — 2026-07-21

Purpose: fix the valid-side label noise that dominated the n=150 (phase2b) numbers,
WITHOUT LLM-screening the gold set (which would bias it toward LLM-judge agreement).

## The fix
- New valid stratum: MUTANT-REVERT tasks. For killed mutants NOT used as invalid
  tasks (partition-guarded, tested), the inverted diff (mutant -> original,
  canonical unified-diff form) is a change that provably takes the subject's own
  suite red -> green. Valid by construction — the exact mirror of the invalid
  side's guarantee.
- Commit stratum retained but strict-filtered (`is_focused_commit`: no new-file
  diffs, <=40 content lines): 51 -> 26 survivors (half were new-module or
  sprawling diffs — consistent with the noise diagnosis).
- Set: 180 tasks = 99 invalid (unchanged, cached) + 55 revert (40 rag-guard,
  15 bow; the only live cells, 550) + 26 focused commits (cached).
- Spot-check gate: zero mechanical cues; canonical ordering verified; diff-size
  confound DEAD (invalid 9.9 lines vs revert 10.1; commit stratum 31.4, reported
  separately). 2050 cells total, 0 errors, 0 quota halts, no kills this run.

## RESULT — headline (all 180 tasks)

  identical-sonnet     N_eff 1.31 [1.07,2.40]  rho 0.65  u_e 2.0  q[1,1]
  diverse-lens-sonnet  N_eff 2.43 [2.18,3.00]  rho 0.12  u_e 1.0  q[1,2]
  mixed-tier           N_eff 1.96 [1.68,2.58]  rho 0.27  u_e 2.0  q[1,1]
  claude-plus-codex    N_eff 1.88 [1.66,2.45]  rho 0.30  u_e 2.0  q[1,1]
  claude-plus-grok     N_eff 1.96 [1.68,2.69]  rho 0.27  u_e 1.0  q[1,2]
  three-lineage        N_eff 2.28 [1.81,3.00]  rho 0.16  u_e 2.0  q[1,1]

e_delta 0.0 everywhere. identical-sonnet vs diverse-lens CIs barely overlap
([1.07,2.40] vs [2.18,3.00]) — the separation is real, not small-sample drama.

## Sensitivity (a): truth-by-construction only (99 invalid + 55 revert, zero label noise)

  identical-sonnet     N_eff 1.32  rho +0.63
  diverse-lens-sonnet  N_eff 3.00  rho -0.01
  mixed-tier           N_eff 1.80  rho +0.33
  claude-plus-codex    N_eff 2.26  rho +0.17
  claude-plus-grok     N_eff 1.81  rho +0.33
  three-lineage        N_eff 3.00  rho +0.00

## Sensitivity (b): invalid-only false-endorse decomposition (99 tasks — unchanged from phase2b)

  three-lineage / claude-plus-codex / diverse-lens: rho 0.00 (zero shared false
  endorsements); identical-sonnet & claude-plus-grok 0.23; mixed-tier 0.33.

## Sensitivity (c): the label-noise diagnosis, quantified

  revert stratum (valid by construction, n=55): false-reject 2.4%, abstain 13.5%
  commit stratum (valid by merge-history, n=26): false-reject 7.7%, abstain 8.8%

Judges false-reject REAL-commit valids 3x more often than construction-valids.
The phase2b muddle was substantially the labels, not the judges.

## THE STORY, END TO END
- Phase 1 (n=59): identical-sonnet collapse 1.15 — REAL, phase2c confirms (1.31).
- Phase 2 (n=59): three-lineage 3.00 — directionally right, overstated by small n.
- Phase 2b (n=150): everything converged 1.8-2.2 — an artifact of valid-side label
  noise drowning the signal.
- Phase 2c (n=180, clean labels): the true picture. Identical panels collapse
  (1.3, rho ~0.65). Diverse panels — full prompt diversity OR cross-lineage —
  restore near-full independence on clean labels (2.3-3.0), and no diverse panel
  shares false endorsements of real bugs. Prompt diversity is roughly as strong as
  lineage diversity in this measurement and costs nothing extra.

## Caveats
- Revert-valid distribution is mutant-shaped (single-line semantic fixes), not
  "typical PR"-shaped; the commit stratum covers realism and is reported apart.
- Grok abstains notably on reverts (13.5% pooled abstain is grok-heavy) — honest
  behavior, priced into u_eps/q windows, worth watching in Phase 3 drift.
- Error events still rare (false-endorse 0-3% per judge) — rho on the invalid side
  remains a small-count estimate; the loop-until-dry fix is further set growth.
- Commit-stratum n=26 is small; its 7.7% false-reject rate is indicative, not tight.

## ERRATUM — v1.0.1 (2026-07-21, cross-model review corrections)

An OpenAI-lineage adversarial review of the published repo surfaced two
material defects in the metrics; both fixed, report regenerated (original
preserved as report-v1.0.0.json).

1. LIVENESS: u_epsilon now counts NON-ENDORSEMENTS (reject+abstain) on valid
   tasks, not abstentions only — a reject withholds endorsement exactly like
   an abstain. Effect: identical-sonnet u_eps 2->3, q window [1,1] -> INFEASIBLE
   (three identical sonnets cannot reliably certify valid work at any quorum);
   diverse-lens and claude-plus-grok u_eps 1->2, q_max 2->1. e_delta, rho,
   N_eff unchanged.
2. PHI IDENTIFIABILITY: undefined (zero-variance) pairwise correlations are
   now None and COUNTED (n_phi_undefined), not silently 0.0. Full-set panels
   have 0 undefined pairs (headline N_eff table unaffected); the invalid-only
   sensitivity "rho 0.00 / N_eff 3.00" claims rested substantially on this
   convention (2/3 judges with zero false-endorsements => most pairs
   unidentified) and are restated as event counts with bounds: 0 shared false
   endorsements in 99 truth-by-construction bugs (95% upper bound ~3%).
   Bootstrap CI lower bounds widened on several panels for the same reason.

Also fixed in v1.0.1 (no numeric impact): grok adapter had the same
first-modelUsage-entry provenance bug class as the claude adapter (latent —
single-entry envelopes observed); grok prompts now pass via file, not argv;
CLI binaries resolve env->PATH (personal fallback paths removed); verdict-JSON
injection guard at gold-set build; builder now wires revert-valids and the
strict commit filter by default (public quickstart previously rebuilt the
noisy Phase-1-style set).
