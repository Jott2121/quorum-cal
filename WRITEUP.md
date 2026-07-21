# How many votes is your AI judge panel actually worth?

*An empirical calibration of LLM judge-panel independence, with the runtime
discipline to keep it honest. July 2026.*

## Abstract

Multi-agent systems increasingly certify work by majority vote of an LLM judge
panel: three judges look at a change, two endorsements ship it. The vote count
assumes the votes are independent. We built an instrument that measures whether
they are, on gold sets whose labels are guaranteed by construction rather than
by anyone's opinion. Headline results, measured over 180 labeled code-review
tasks and ~2,000 sandboxed judge calls: **three identical judges (same model,
same prompt) are worth about 1.3 independent votes** (pairwise error
correlation 0.65); **three diverse judges — three review lenses on one model,
or three model lineages (Claude, OpenAI, xAI) on one lens — are worth 2.3 to
3.0**, and in our sample **no diverse panel ever shared a false endorsement of
a real bug**, while identical-model panels demonstrably did. We also report a
cautionary tale: our first measurement of cross-lineage panels produced a
flashy "perfect independence" number (3.00 of 3) that dissolved when we grew
the sample, and the culprit was label noise in the gold set, not the judges.
Fixing the labels — making the *valid* side truth-by-construction too —
restored a sharper, defensible result. The instrument, the receipts, and the
runtime guardrails (risk profiles, CUSUM drift monitoring, provenance-triggered
recalibration) are in this repo.

## 1. Motivation

The "Honest Quorum Problem" line of work (arXiv 2607.16109; see also
2605.29800, "Nine Judges, Two Effective Votes") argues that a panel of
protocol-compliant LLM validators can unanimously certify a wrong answer
because their reasoning errors are correlated: shared lineage, shared prompts,
shared blind spots make vote counts overstate real independence. The theory
paper ships no empirics. This project is the missing instrument: it measures
the actual effective independence of real panel configurations the way an
operator would actually run them, and derives quorum thresholds from measured
error budgets instead of vibes.

## 2. Method

**Truth by construction.** Grading judges requires an answer key no opinion
touched. *Invalid* tasks are mutants — small deliberate bugs injected by
mutation tooling — kept only if the subject repository's own test suite kills
them: a guaranteed behavioral bug. *Valid* tasks (after Act III below) are the
mirror image: for surplus killed mutants never used as invalid tasks, the
inverted diff provably takes the failing suite back to green — valid by
construction. A second, strictly filtered stratum of real merged commits is
kept for realism and reported separately. No LLM ever screens or labels a
task; that would bias the gold set toward LLM-judge agreement. Diffs are
normalized so no formatting artifact distinguishes classes (a leakage gate
caught the mutation tool printing its own answer key into diffs before any
quota was spent), and after the valid-side fix the two classes have identical
size profiles (means 9.9 vs 10.1 lines).

**Judges.** One fresh, fully sandboxed, toolless CLI process per (judge, task):
no repository access, no session reuse (session reuse would fake correlation,
which is the quantity under measurement), no inherited user configuration.
Three lineages: Claude (`claude -p`), OpenAI (`codex exec`), xAI (`grok
--single`), each hardened with its CLI's isolation flags and recording the
served model per call. Judges reply endorse / reject / abstain with a
rationale; adapter failures are first-class `error` verdicts, excluded from
budgets, never silently dropped.

**Math (f-free; single operator).** Per-task panel outcome vectors give the
empirical distribution of false-endorsement counts on invalid tasks; the
budget e_delta is its (1-delta) quantile — measuring correlation directly
instead of multiplying marginals. Same for abstention (u_epsilon) on valid
tasks. Effective independence N_eff = N / (1 + (N-1)·rho-bar) (Kish design
effect) over the pairwise error-correlation matrix, bootstrap CIs. Feasible
quorum window: safety q ≥ floor(e_delta)+1, liveness q ≤ N − u_epsilon.

**Panels.** Six configurations of three judges each: identical (same model,
same prompt — the maximally correlated baseline), diverse-lens (one model,
three review angles: correctness / security / test-impact), mixed-tier (three
Claude tiers), and three mixed-lineage panels (one or two non-Claude judges).

## 3. Results: four acts

**Act I (n=59).** The collapse is real: identical-sonnet N_eff **1.15** of 3
(rho 0.80). Judges individually strong — 90th-percentile false-endorsement
count 0 — but their rare errors almost perfectly shared. Prompt diversity
nearly doubled independence (1.93); tier diversity bought less (1.72). A
pre-committed gate (proceed only if N_eff ≤ 2.0) passed.

**Act II (n=59, +2 lineages).** Cross-lineage panels looked spectacular:
three-lineage N_eff **3.00** of 3, pairwise error correlation −0.01. Perfect
independence — and, as it turned out, overstated.

**Act III (n=150).** We grew the gold set to tighten the confidence intervals.
Every panel converged into an undifferentiated 1.8–2.2 band. The error anatomy
showed why: every correlated "error" was a *valid* task that multiple lineages
independently rejected — real merged commits that reasonable judges flag when
shown only the diff. "Merged and history-green" is not the same label as
"endorsable from the diff alone." The gold set's valid side was noisy, and at
sufficient sample size the noise dominated the metric.

**Act IV (n=180, clean labels).** With the valid side rebuilt
truth-by-construction (mutant-revert fixes; partition-guarded; canonical diff
form so no format cue survives) and real commits kept as a strict-filtered
separate stratum:

| panel | N_eff | 95% CI | rho |
|---|---|---|---|
| identical-sonnet | **1.31** | [1.07, 2.40] | 0.65 |
| diverse-lens-sonnet | **2.43** | [2.18, 3.00] | 0.12 |
| mixed-tier | 1.96 | [1.68, 2.58] | 0.27 |
| claude-plus-codex | 1.88 | [1.66, 2.45] | 0.30 |
| claude-plus-grok | 1.96 | [1.68, 2.69] | 0.27 |
| three-lineage | **2.28** | [1.81, 3.00] | 0.16 |

On the fully clean 154-task subset (invalid + revert-valid only): identical
1.32, diverse-lens 3.00, three-lineage 3.00 (rho ≈ 0 for both diverse forms).
The label-noise diagnosis, quantified: judges false-reject merged-commit
valids at **7.7%** vs **2.4%** on construction-valids — three times more.

**The safety decomposition** (false endorsements of real bugs, the failure
mode certification actually fears, 99 truth-by-construction bugs): the
three-lineage, claude-plus-codex, and diverse-lens panels shared **zero**
false endorsements (pairwise error correlation 0.00); identical-sonnet (0.23)
and mixed-tier (0.33) shared theirs. e_delta = 0.0 at the 90th percentile for
every panel — but Act I showed that when identical judges do err, they err
together.

## 4. Practical guidance

1. **Never run N identical judges.** Three copies of one model on one prompt
   measured as ~1.3 real votes wearing three hats.
2. **Diversify prompts or lineages.** Three review lenses on one model
   measured as strong as three model lineages here, and costs nothing. Cross-
   lineage adds insurance against whole-model blind spots — something a
   within-family gold set cannot fully probe — so keep one different-lineage
   judge on the highest-stakes gates.
3. **Unanimous diverse rejection of a "valid" change is information.** In our
   data it usually pointed at genuinely questionable changes, not judge error.
4. **Numbers rot; recalibrate.** Hence the runtime discipline below.

## 5. Runtime discipline

Calibration numbers are only trustworthy while the world matches the
calibration. The repo ships three guardrails (see
`docs/runtime-discipline.md` for the full contract):

- **Risk profiles** (`profiles/*.json`): committee spec, chosen quorum within
  the measured feasible window, budgets with intervals, calibrated baseline
  behavior, a fingerprint of the judge prompt, a served-model whitelist, and a
  30-day expiry. Consumers preflight with `profile check` (exit 0 valid / 2
  expired / 4 provenance-drifted) before certifying anything.
- **CUSUM drift monitor** (`monitor`): a sequential test on live verdict logs
  (disagreement and abstention streams vs calibrated baselines) plus a
  served-model check; non-zero exit is the whole alerting interface.
- **Provenance triggers**: a changed prompt fingerprint or an unknown served
  model forces recalibration — which the judgment cache makes incremental.

Building these caught two real defects in our own instrument, which is the
thesis eating its own cooking: (1) the Claude adapter had recorded the CLI's
internal ancillary model as the serving model for 1,621 of 1,640 cells — the
envelope lists helper-model usage first; confirmed by live capture; fixed so
substitution stays visible, and pre-fix cells are excluded from profile
whitelists until the next full recalibration; (2) the abstention baseline was
computed per judge-cell while the monitor watched per decision — a unit
mismatch guaranteeing a false alarm, caught by the end-to-end smoke.

## 6. Limitations

- **Rare errors.** Per-judge false-endorsement rates are 0–3%; correlation
  estimates on the invalid side are small-count estimates and several CIs
  reach the N=3 clamp. Growing the gold set is incremental (the cache never
  re-bills a judged cell).
- **Revert-valid distribution.** Construction-valid tasks are mutant-shaped
  (small semantic fixes), not PR-shaped. The strict-filtered real-commit
  stratum covers realism and is reported separately.
- **Withheld tasks.** 84 of the 180 gold tasks derive from a private
  repository and are withheld from this public release (all aggregate numbers
  include them; the published tooling rebuilds an equivalent gold set from any
  repo with a real test suite). The rag-guard-derived tasks are published in
  full.
- **Single operator.** All math is f-free (no Byzantine operators). The
  multi-operator protocol question the EBFT paper raises is out of scope.
- **One domain.** Code-change review, two subject repos, one task shape.
  Lens/lineage rankings may differ elsewhere; the instrument, not the specific
  numbers, is the transferable artifact.

## 7. Reproduction

```bash
# 1. Build a gold set from a repo with a real pytest suite (mutation tooling
#    runs under its own venv; see quorumcal/goldset.py docstrings)
python -m quorumcal.cli goldset build --repo <path> --name <name> \
  --workdir /tmp/qc-work --out goldset.jsonl --source-path <pkg/module.py> ...

# 2. Run panels (cached, resumable, quota-aware)
python -m quorumcal.cli panel run --goldset goldset.jsonl \
  --panels panels.json --cache-dir cache

# 3. The numbers
python -m quorumcal.cli report --goldset goldset.jsonl \
  --panels panels.json --cache-dir cache --out report.json

# 4. Guardrails
python -m quorumcal.cli profile emit ... && python -m quorumcal.cli profile check ...
python -m quorumcal.cli monitor --profile ... --log verdicts.jsonl
```

Receipts for every act are under `runs/` (reports, run logs, panels, filtered
gold sets). 124 tests; stdlib-only core.
