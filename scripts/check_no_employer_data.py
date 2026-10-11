#!/usr/bin/env python3
"""Fail if tracked files contain employer or export-control markers.

The author's public GitHub profile bio names an employer and is not internal
data. A line that contains that sentence and no other marker is ignored, so
the scan does not false-positive on the bio. Every other hit fails. README is
scanned. The bio belongs on the Jott2121 profile repo; pasting it here is
allowed only as that one sentence.

Policy files that state the prohibition name the marker on purpose and are
excluded: AGENTS.md, .cursor/, and .github/. This script is excluded too,
because it contains the search pattern.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Split so this source file does not itself contain the marker.
_EMPLOYER = "Lock" + "heed"
MARKER = re.compile(
    _EMPLOYER + r"|\blmco\b|\bCUI\b|\bITAR\b|EXPORT CONTROLLED|\bPROPRIETARY\b",
    re.IGNORECASE,
)
# The public profile bio. Word-bounded so a longer dump that merely contains
# the title still fails when another marker remains on the line.
BIO = re.compile(
    r"\bAI Foundations Lead at " + _EMPLOYER + r" Martin\b",
    re.IGNORECASE,
)
EXCLUDES = (
    ":!.cursor",
    ":!AGENTS.md",
    ":!.github",
    ":!scripts/check_no_employer_data.py",
)


def line_is_author_bio(line: str) -> bool:
    if BIO.search(line) is None:
        return False
    rest = BIO.sub("", line)
    return MARKER.search(rest) is None


def git_grep() -> list[str]:
    result = subprocess.run(
        ["git", "grep", "-nIiE", MARKER.pattern, "--", ".", *EXCLUDES],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return [line for line in result.stdout.splitlines() if line]


def committed_junk() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    bad = []
    for path in result.stdout.splitlines():
        if "__pycache__/" in path or path.endswith(".pyc") or path == ".coverage":
            bad.append(path)
    return bad


def assert_tuning() -> None:
    """The author bio is allowed; every other employer mention is not."""
    bio = f"AI Foundations Lead at {_EMPLOYER} Martin. Personal work here."
    if not line_is_author_bio(bio):
        raise SystemExit("author bio must not be flagged")
    if line_is_author_bio(f"{_EMPLOYER} Martin internal schema"):
        raise SystemExit("a non-bio employer mention must be flagged")
    if line_is_author_bio(bio + " ITAR"):
        raise SystemExit("the bio plus another marker must be flagged")
    if MARKER.search("Author: t <t@t>") or MARKER.search("military"):
        raise SystemExit("author lines and the word military must not match")


def main() -> None:
    assert_tuning()
    hits = []
    for raw in git_grep():
        # git grep: path:lineno:text (text may itself contain colons)
        try:
            _path, _lineno, text = raw.split(":", 2)
        except ValueError:
            hits.append(raw)
            continue
        if line_is_author_bio(text):
            continue
        hits.append(raw)
    junk = committed_junk()
    if not hits and not junk:
        print("no employer-data markers; no committed build junk")
        return
    for hit in hits:
        print(f"MARKER: {hit}", file=sys.stderr)
    for path in junk:
        print(f"JUNK: {path}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
