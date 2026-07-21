# Phase 2 run log — 2026-07-20

Question: does genuine lineage diversity beat the prompt diversity Phase 1 measured?

## Setup
- Codex CLI installed this session (`npm i -g @openai/codex`, codex-cli 0.144.6); auth
  pre-existing at ~/.codex/auth.json (ChatGPT plan). Served model: gpt-5.6-sol
  (pinned via -m, stderr-header provenance recorded per call).
- Grok CLI 0.2.101 (~/.local/bin/grok, Grok 4.5 plan). Served model: grok-4.5-build
  (modelUsage-key provenance per call). Note: `grok models` claims "not authenticated"
  but headless `--single` calls work — red herring.
- Both adapters written TDD against envelopes CAPTURED from live smokes run BEFORE any
  adapter code (Phase 1 mock-drift lesson). Fixtures in tests/fixtures/.
- Live 2x2 mini-smoke (2 invalid tasks × codex-corr, grok-corr): 4/4 verdicts, 0 errors,
  receipts in smoke-cache/ (committed).
- Cache seeded by copying all 472 Phase 1 cells into runs/phase2/cache (identical
  cache_key filenames — Phase 1 receipts stay immutable in runs/phase1/).

## Run
- 590 cells total = 472 cached Claude cells (free) + 118 live (codex-corr x59,
  grok-corr x59). Zero error verdicts, zero quota halts, zero healing needed.
- Baselines reproduced EXACTLY from cache (1.15 / 1.93 / 1.72) — cache integrity check.
- New-judge verdict mix: codex-corr 42 reject / 12 endorse / 5 abstain;
  grok-corr 38 reject / 14 endorse / 7 abstain. Grok made zero wrong calls
  (abstentions are budgeted separately in u_eps); codex 2/59 wrong.

## RESULT — 2026-07-20

  identical-sonnet     N_eff 1.15 [1.00,3.00]  rho  0.80  u_e 2.0  q[1,1]   (Phase 1 baseline)
  diverse-lens-sonnet  N_eff 1.93 [1.69,3.00]  rho  0.28  u_e 1.0  q[1,2]   (Phase 1 baseline)
  mixed-tier           N_eff 1.72 [1.58,3.00]  rho  0.37  u_e 2.0  q[1,1]   (Phase 1 baseline)
  claude-plus-codex    N_eff 2.10 [1.83,3.00]  rho  0.21  u_e 2.0  q[1,1]
  claude-plus-grok     N_eff 2.04 [1.80,3.00]  rho  0.23  u_e 2.0  q[1,1]
  three-lineage        N_eff 3.00 [3.00,3.00]  rho -0.01  u_e 1.0  q[1,2]

e_delta = 0.0 on every panel (90th-pct false-endorsement count is 0 — rare errors, but
Phase 1 showed they are SHARED within a lineage; across lineages they are not).

## Reading
- ONE added lineage: swapping one of three identical sonnets for a different-lineage
  judge nearly doubles effective independence (1.15 -> 2.10 codex / 2.04 grok) and
  slightly beats full prompt diversity (1.93) with zero prompt engineering.
- TWO added lineages: 3.00 of 3, pairwise error correlation ~0. Within the resolution
  of this gold set, three lineages under the SAME prompt behave as fully independent
  votes. Lineage diversity > prompt diversity > tier diversity, in that order.
- Liveness bonus: three-lineage also has the widest feasible quorum window ([1,2],
  u_eps 1.0) — diverse panels abstain less correlatedly too.

## Caveats (for the writeup)
- Rare-error regime: per-judge wrong rates 0-3.4% at n=59 → the rho estimate for
  three-lineage is noisy and its bootstrap CI is degenerate at the N=3 clamp
  ([3.00,3.00] means "no resample produced correlated errors", not "zero uncertainty").
  Growing the gold set is the power fix (cache makes re-runs incremental).
- Baseline CI uppers still reach 3.0 (same power problem, flagged in Phase 1).
- Cache keys carry no prompt hash; 16/472 Phase 1 cells were judged under the v2
  prompt. All Phase 2 records now carry an explicit prompt_version field ("v2").
- Diff-size confound (invalid ~10 lines, valid ~46) unchanged from Phase 1.
- Codex provenance: gpt-5.6-sol is whatever tier the ChatGPT plan serves, not a pinned
  API model; recorded per call. Same for grok-4.5-build.
- Costs: codex/grok cells are plan-billed (~$0 marginal). The cost$ column counts only
  cells with recorded total_cost_usd (claude cached cells + grok notional).
