# quorum-cal

**How many votes is your AI judge panel actually worth?**

Multi-agent systems certify work by majority vote of LLM judges. The vote
count assumes independent votes. quorum-cal measures whether they are — on
gold sets whose labels are guaranteed by construction (mutants killed by the
subject repo's own test suite, and the fixes that provably revert them),
judged by fully sandboxed, toolless, fresh-process CLI judges across three
model lineages.

## The headline (180 tasks, ~2,000 judge calls, July 2026)

| panel (3 judges) | effective votes | 95% CI | error corr. | q window |
|---|---|---|---|---|
| identical (one model, one prompt) | **1.31** | [1.06, 2.40] | 0.65 | infeasible |
| diverse lenses (one model, 3 prompts) | **2.43** | [2.17, 3.00] | 0.12 | [1, 1] |
| three lineages (Claude + OpenAI + xAI) | **2.28** | [1.40, 3.00] | 0.16 | [1, 1] |

- Three identical judges are ~1.3 real votes wearing three hats — and under
  honest liveness accounting their feasible quorum window is EMPTY.
- Diversity — different prompts **or** different lineages — retains most of
  the independence: the diverse panels shared **0 false endorsements across
  99 truth-by-construction bugs** (95% upper bound ≈3%); identical-model
  panels demonstrably shared theirs. CIs overlap among diverse forms — the
  data separates identical-vs-diverse, not a ranking between them.
- Our first cross-lineage number was a flashy 3.00 that dissolved under a
  larger sample — the culprit was gold-set label noise, not the judges. The
  full four-act story, including the fix, is in [WRITEUP.md](WRITEUP.md) —
  as is the v1.0.1 corrections section from running a different-lineage
  adversarial review on our own published claims one day after release.

## What's in the box

- `quorumcal/` — gold-set builder (truth-by-construction both sides), hardened
  judge adapters (Claude / Codex / Grok CLIs, per-call served-model
  provenance, quota-aware halt), cached resumable panel runner, f-free metrics
  (empirical error budgets, Kish N_eff, bootstrap CIs, feasible quorum
  windows).
- **Runtime discipline** — risk profiles with expiry and provenance
  fingerprints (`profile emit/check`, exit codes consumers script against), a
  CUSUM drift monitor over live verdict logs (`monitor`), and
  recalibration-on-change. See [docs/runtime-discipline.md](docs/runtime-discipline.md).
- `runs/` — the receipts: reports, run logs, and gold sets for every
  measurement act (84 of 180 tasks derive from a private repo and are
  withheld; all aggregates include them — see WRITEUP §6).
- 132 tests; stdlib-only core.

## Quickstart

```bash
python -m quorumcal.cli goldset build --repo <path> --name <n> \
  --workdir /tmp/qc-work --out goldset.jsonl --source-path <pkg/mod.py>
python -m quorumcal.cli panel run --goldset goldset.jsonl --panels panels.json --cache-dir cache
python -m quorumcal.cli report --goldset goldset.jsonl --panels panels.json --cache-dir cache --out report.json
python -m quorumcal.cli profile emit --report report.json --panels panels.json \
  --goldset goldset.jsonl --cache-dir cache --panel <name> --out profile.json
python -m quorumcal.cli profile check --profile profile.json   # 0 valid / 2 expired / 4 drifted
```

## Provenance

Built and operated by one human directing AI agents; every number in the
writeup comes from a logged, cached, re-runnable cell. The instrument caught
two defects in its own plumbing before they could pollute a published number
(WRITEUP §5) — receipts over hype is the whole point.

MIT license.
