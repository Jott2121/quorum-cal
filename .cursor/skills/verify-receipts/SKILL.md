---
name: verify-receipts
description: Use before opening or updating a PR, or when README/docs numbers change. Re-runs quorum-cal's tests and scripts/check_receipts.py, cross-checks published headline numbers against runs/phase2c/report.json, and writes a receipts block for the PR body.
---
# Verify receipts

1. Read AGENTS.md "Commands". Run `python -m pip install -e ".[dev]"`, `ruff check scripts && ruff format --check scripts`, pytest with `--cov-fail-under=90`, and `python scripts/check_receipts.py`. Capture exit codes and the last ~20 lines of each. Do not re-run `panel run` against live CLIs to refresh the headline. The 180-task judgment cache is not in the repo.
2. `git diff origin/main -- README.md docs/ WRITEUP.md CHANGELOG.md` — list every number that changed. Headline N_eff, CI, rho, and quorum window must match `runs/phase2c/report.json` rounded to 2 decimals. `runs/phase2c/RUNLOG.md`'s first result block is pre-correction; the erratum and `report.json` are the source of truth. If you can't reproduce a changed number, mark it UNVERIFIED and stop.
3. Run `python -m unittest -v scripts/test_check_no_employer_data.py` and `python scripts/check_no_employer_data.py`, then grep the diff for secret patterns (see `.cursor/rules/40-security-and-data.mdc`). Any hit = stop and report.
4. Confirm `--cov-fail-under` was not lowered and no tests were skipped, xfailed, or removed. The published suite is 132 tests.
5. Output a Markdown block:
   - Commands run + pass/fail
   - Numbers: before → after → command → reproduced? (Y/N)
   - Not verified / known gaps. `profile check` on the committed profiles exits 2 after 2026-08-20 (expired). That is not drift.
6. Paste that block into the PR's "How verified" section. Never claim a check passed that you didn't run.
