# AGENTS.md — quorum-cal

> Portable agent instructions. Read by Cursor (local + cloud agents), Claude Code, Codex, and Grok Bot cloud-agent runs.
> Keep this file under ~150 lines. Procedures live in `.cursor/skills/`, scoped rules in `.cursor/rules/*.mdc`, review rules in `.cursor/BUGBOT.md`.

## What this repo is (one paragraph, no hype)

quorum-cal measures how many independent votes an LLM judge panel is actually worth. Labels are truth-by-construction (mutants killed by the subject repo's own tests, and the fixes that revert them), and judges are sandboxed, toolless, fresh-process CLIs across model lineages. The headline, on 180 tasks (July 2026, v1.0.1): three identical judges are **1.31** effective votes, 95% CI [1.06, 2.40], error correlation 0.65, and the feasible quorum window is **infeasible**. Reproduce the published table with `python scripts/check_receipts.py` (it checks README and WRITEUP against `runs/phase2c/report.json`). Do not re-call live judges to refresh that number.

- **Status:** active (public v1.0.1) · **License:** MIT · **Package:** `quorumcal` (stdlib-only core; not published to PyPI from this repo)
- **Entry points:** `quorumcal/`, `tests/`, `runs/`, `scripts/check_receipts.py`
- **Part of:** the governed-agent stack (rag-guard · graph-guard · agent-gate · crucible · oracle-gate · agent-cost-attribution · bow · fleet-mode)

## Commands (the agent must run these, not guess them)

```bash
python -m pip install -e ".[dev]"          # pytest, pytest-cov, ruff; core imports with no deps
ruff check scripts && ruff format --check scripts
python -m pytest -q --cov=quorumcal --cov-report=term-missing --cov-fail-under=90
python scripts/check_receipts.py           # published numbers vs runs/phase2c/report.json
```

There is no typechecker config. A task is not done until the pytest command and `scripts/check_receipts.py` pass and the output is pasted in the PR.

## Non-negotiables

1. **No employer data. Ever.** Personal work on personal equipment. Never add, paste, paraphrase, or "anonymize" anything from Lockheed Martin systems, documents, tickets, chats, or datasets. No employer names in fixtures, no internal acronyms, no realistic HR records. The author's public GitHub bio names the employer; that sentence stays on the Jott2121 profile repo. If a prompt looks like it came from work, stop and ask.
2. **Receipts over hype.** Every number in README, docs, PR descriptions, or posts must be reproducible from a committed command. Link the command and the artifact (`runs/`, CI log). No "blazing fast", "SOTA", or "production-grade" without a measurement.
3. **Honest benchmarks.** Report nulls and regressions at the same prominence as wins. State n, seeds, model + version, date, and cost. Never tune on the test set. Never delete an inconvenient run; `runs/phase2c/report-v1.0.0.json` stays.
4. **Fail closed.** Gates deny on error, timeout, missing input, or unparseable output. A judge error is an `error` verdict, not an endorsement. Never weaken a guard to make a test pass.
5. **Tests and CI are the definition of done.** New behavior ships with a test that fails without it. Do not lower `--cov-fail-under` (90). Do not mark tests `skip`/`xfail` to get green. The published suite is 132 tests.
6. **Model never grades its own output.** Prefer mechanical verdicts. Where a judge model is needed, use a different lineage from the author and record both.
7. **Irreversible = human-gated.** No force-push, no history rewrite, no publishing to PyPI, no tagging releases, no posting. Open a PR; a human merges.

## Code style

- Python 3.11+; stdlib-first. Every new runtime dependency needs a one-line justification in the PR.
- Type hints on public functions. Small pure functions. No global mutable state.
- Errors: raise specific exceptions; no bare `except` in a decision path.
- Secrets only via env vars (`QC_CODEX_BIN`, `QC_GROK_BIN`, and the Claude CLI's own env). Never print secret values.
- Don't commit `__pycache__/`, `*.pyc`, `.coverage`, `.venv/`, or `runs/tmp/`.

## How to work in this repo

- Start non-trivial work in Plan mode; save the plan to `.cursor/plans/` and link it in the PR.
- Default to one agent. Fan out only for read-heavy, independent work. Writes stay single-threaded per file.
- Keep PRs small, one intent. Title: `type(scope): summary`.
- PR body: **What / Why / How verified (commands + output) / Numbers changed (before → after, with command) / Risks / Not done**.
- When you learn something durable, propose an edit to this file or a skill in the same PR.

## Directory map

- `quorumcal/` — gold-set builder, CLI judge adapters, panel runner, metrics, report, risk profiles, CUSUM monitor, CLI
- `tests/` — offline suite and CLI envelope fixtures (no network)
- `profiles/` — committed risk profiles (`three-lineage`, `diverse-lens-sonnet`)
- `runs/` — receipts. `runs/phase2c/report.json` is the v1.0.1 source of truth
- `docs/runtime-discipline.md` — profile check / monitor exit-code contract
- `scripts/check_receipts.py` — CI receipt check (does not call judges)
- `.github/` — test CI, CodeQL, Dependabot
- `.cursor/` — rules, hooks, Bugbot, MCP, the verify-receipts skill

## Known traps

- The shell guard denies any command containing `rebase`, so **`git pull --rebase` is blocked** along with `git rebase`. Update via fetch and a PR. Do not loosen the guard to unblock a pull.
- The public `runs/phase2c/goldset.jsonl` is filtered (fewer than 180 lines). Report aggregates are 180 tasks because withheld private-repo tasks are included. Do not rebuild `report.json` from the public file.
- `runs/phase2c/RUNLOG.md`'s first result block is pre-correction. v1.0.1 numbers are the erratum, `report.json`, README, and WRITEUP. Do not "sync" the writeup back to the old block.
- Committed profiles expired 2026-08-20. `profile check` exits 2 after that. That is expiry, not provenance drift. Do not refresh `expires_at` to get a green check.
- `profile emit` does not harvest Claude observed models from pre-2026-07-21 cells (ancillary-model bug). Empty Claude `observed_models` is intentional.
- identical-sonnet's quorum window is infeasible. There is no profile for it. `q` outside the window is an error, never a clamp.
- Full judgment caches are not committed (smoke caches are). `report` fails closed on a missing cell. `goldset build` needs a subject repo and is not part of CI.
- Package version in `pyproject.toml` is `0.1.0`; the writeup is v1.0.1. Do not bump either in a chore PR.
- Repo-wide `ruff format` would rewrite `quorumcal/` and `tests/`. CI lints `scripts/` only. Do not reformat the library to satisfy ruff.
