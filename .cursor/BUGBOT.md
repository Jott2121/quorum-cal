# .cursor/BUGBOT.md — review rules for quorum-cal
# (Bugbot does NOT read .cursor/rules/*.mdc; it reads this file.)

Flag as **blocking**:
1. Any guard, gate, validator, or refusal path that now fails OPEN (returns allow/True/endorse on exception, timeout, empty, or malformed input). Judge adapter failures must stay `error` verdicts.
2. Lowered thresholds: `--cov-fail-under`, mutation score floors, MIN_SCORE-style constants, retry/timeout bounds removed.
3. Tests that were deleted, skipped, xfailed, or had assertions weakened without a stated reason in the PR body. The published suite is 132 tests.
4. README/WRITEUP/docs numbers that changed without a reproducing command or artifact in the PR. Headline figures must match `runs/phase2c/report.json`.
5. Any content that looks like employer/corporate data: company names (Lockheed, LM, LMCO), internal acronyms, CUI/ITAR markings, real-looking employee records, internal URLs. The author's public GitHub bio is not a license to add employer material. This repo is personal work only.
6. Secrets, tokens, `.env` files, or absolute personal paths committed (the v1.0.1 release removed personal CLI fallback paths).
7. Unpinned GitHub Actions (must be full SHA) or widened workflow `permissions:`.
8. Live network / model calls added to the default test path.
9. Rebuilding `runs/phase2c/report.json` from the filtered public goldset, deleting `report-v1.0.0.json`, or refreshing committed profile `expires_at` so `profile check` looks valid.

Flag as **non-blocking**:
- New runtime dependency without justification.
- Non-deterministic code in eval paths (unseeded RNG, unordered iteration in hashes/output).
- Exceptions swallowed in non-decision code.

Do not comment on: formatting handled by ruff; naming bikesheds. Do not ask for a repo-wide ruff format of `quorumcal/` or `tests/` — that tree is intentionally unformatted.
