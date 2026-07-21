# Phase 2b run log — gold set grown for CI power — 2026-07-20/21

Purpose: tighten the rare-error CIs behind the n=59 Phase 2 numbers (three-lineage
CI was degenerate at [3.00,3.00]).

## Gold-set growth
- 59 -> 150 tasks (99 invalid / 51 valid; valid side 14 -> 51, the worst power gap).
- Invalid growth: rag-guard mutation scope widened 3 files -> all 13 modules
  (suite 0.07s; crucible venv build; WARNING: got 60/11 of requested 60/12 valid).
- Valid growth: bow whole-package commit history (30 new) + rag-guard package
  history (9 new). Content-keyed task ids -> every phase1/phase2 cell stayed cached.
- Leakage pass: 5 XX-string mutants dropped at merge; spot-check dropped 2 more
  (one diff mentioning mutation tooling — a valid-only cue; one header-only empty
  diff). Mechanical cue sweep over all 93 new tasks: clean.
- Diff-size confound WIDENED: new invalid ~10 lines vs new valid ~75 (disclosed).

## Run
- 1500 cells = 590 seeded from phase2 + 910 live (8 Claude judge-cells + codex +
  grok per new task). 0 error verdicts, 0 quota halts. Two external background-task
  kills mid-run (not errors, not quota — harness-side); cache resume lost nothing.
  Grok quota checked live during the run at Jeff's request: healthy, not the cause.

## RESULT — n=150 (vs n=59 in brackets)

  identical-sonnet     N_eff 1.78 [1.36,2.71]  rho 0.34   (was 1.15, rho 0.80)
  diverse-lens-sonnet  N_eff 1.90 [1.54,2.49]  rho 0.29   (was 1.93)
  mixed-tier           N_eff 2.06 [1.77,2.73]  rho 0.23   (was 1.72)
  claude-plus-codex    N_eff 2.01 [1.82,2.33]  rho 0.25   (was 2.10)
  claude-plus-grok     N_eff 2.17 [1.82,2.91]  rho 0.19   (was 2.04)
  three-lineage        N_eff 1.88 [1.54,2.68]  rho 0.30   (was 3.00, rho -0.01)

e_delta 0.0 on every panel. All CIs now finite (no degenerate bounds); most overlap.

## THE HONEST READING — the n=59 drama did not survive n=150
1. The extreme spread at n=59 (1.15 collapse; 3.00 perfect independence) was
   small-sample structure. At n=150 every configuration lands in 1.8–2.2 with
   overlapping CIs. Claude-plus-grok is nominally best (2.17); nothing separates
   decisively at delta=0.1 with these error rates.
2. ERROR ANATOMY: every 2+-wrong task in the three-lineage panel is a VALID task
   that multiple lineages independently REJECT. That is the label-noise channel the
   design spec pre-declared ("merged commit" != "endorsable from the diff alone";
   e.g. 9d0c146b76a4 = a 64-line new-module commit judges reasonably flag). The
   valid side measures judge strictness against noisy labels, not shared reasoning
   failure.
3. INVALID-ONLY SENSITIVITY (99 truth-by-construction bugs — the safety side that
   certification actually depends on):
     three-lineage      rho 0.00  N_eff 3.00   (zero shared false endorsements)
     claude-plus-codex  rho 0.00  N_eff 3.00
     diverse-lens       rho 0.00  N_eff 3.00
     claude-plus-grok   rho 0.23  N_eff 2.04
     identical-sonnet   rho 0.23  N_eff 2.04
     mixed-tier         rho 0.33  N_eff 1.80
   On false-ENDORSEMENT of real bugs, identical-model panels and mixed-tier share
   mistakes; the three-lineage and claude-plus-codex panels (and prompt-diverse
   claude) shared none in this sample. Sensitivity framing only — error events
   remain rare (per-judge false-endorse 1–3%), so these are small-count estimates.
4. Refined conclusion for the writeup: diversity (lineage or prompt) removes the
   SHARED-false-endorsement failure mode; it does not make panels agree more on
   ambiguous-but-merged changes. N_eff over mixed task distributions is dominated
   by valid-side label noise once the set grows — the safety-side decomposition is
   the meaningful metric, and the instrument now measures both.

## Caveats
- Valid-side label noise now the dominant known limitation (was: sample size).
  Fix candidates for Phase 3/writeup: human-audited valid subset, or valid tasks
  restricted to small focused diffs.
- Diff-size confound widened (see above).
- Composition shift vs phase2 (repo/module mix) means n=59 vs n=150 deltas mix
  sample-size and distribution effects; the honest claim is "n=59 numbers were
  unstable", not a paired comparison.
- Cost column counts recorded total_cost_usd only (claude + grok notional; codex
  plan-billed, None).
