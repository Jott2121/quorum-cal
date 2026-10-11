#!/usr/bin/env python3
"""Fail if tracked files contain employer terms, export-control markers, or junk.

Employer terms are never stored in plain text. `.github/blocked-terms.sha256`
holds the SHA-256 of each lowercased term. Every tracked file is lowercased
and split into words (runs of [a-z0-9]). Each word and each pair of adjacent
words, joined by one space, is hashed and compared against that file. A hit
reports path, line, and hash prefix, never the matched text, so CI logs do
not repeat the term.

EMPLOYER_MARKERS, when set (CI passes the Actions secret of the same name), is
a case-insensitive regex alternation of extra terms checked against every
line of the same files. Unset or blank means hash terms only.

The employer scan covers the whole tree, policy files included. It skips only
the hash file and build output. It fails closed: a missing, empty, or
malformed hash file, an invalid EMPLOYER_MARKERS regex, or a git error exits 2.

The export-control marker scan (MARKER below) keeps a narrower scope. Policy
files that state that prohibition name those markers on purpose, so
AGENTS.md, .cursor/, .github/, and this script are excluded from it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASH_FILE = Path(".github") / "blocked-terms.sha256"
MARKERS_ENV = "EMPLOYER_MARKERS"
CONFIG_ERROR = 2

MARKER = re.compile(
    r"\bCUI\b|\bITAR\b|EXPORT CONTROLLED|\bPROPRIETARY\b",
    re.IGNORECASE,
)
MARKER_EXCLUDES = (
    ":!.cursor",
    ":!AGENTS.md",
    ":!.github",
    ":!scripts/check_no_employer_data.py",
)
BUILD_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "build",
        "dist",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        ".nox",
        "htmlcov",
    }
)
WORD = re.compile(r"[a-z0-9]+")
HEX64 = re.compile(r"[0-9a-f]{64}")


class ConfigError(Exception):
    """The scan cannot run as configured. Callers must treat this as a failure."""


def sha256_hex(term: str) -> str:
    return hashlib.sha256(term.encode("utf-8")).hexdigest()


def load_hashes(path: Path) -> frozenset[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"blocked-term hash file missing: {path}") from exc
    hashes = set()
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not HEX64.fullmatch(line):
            raise ConfigError(f"{path}:{lineno}: not a lowercase SHA-256 hex digest")
        hashes.add(line)
    if not hashes:
        raise ConfigError(f"blocked-term hash file has no hashes: {path}")
    return frozenset(hashes)


def load_markers(value: str | None) -> re.Pattern[str] | None:
    if value is None or not value.strip():
        return None
    try:
        pattern = re.compile(value.strip(), re.IGNORECASE)
    except re.error as exc:
        raise ConfigError(f"{MARKERS_ENV} is not a valid regex: {exc}") from exc
    if pattern.search(""):
        raise ConfigError(f"{MARKERS_ENV} matches the empty string")
    return pattern


def candidates(text: str) -> Iterator[tuple[int, str]]:
    """Yield (line number, term) for every word and adjacent word pair."""
    lowered = text.lower()
    prev: str | None = None
    lineno, pos = 1, 0
    for match in WORD.finditer(lowered):
        lineno += lowered.count("\n", pos, match.start())
        pos = match.start()
        word = match.group()
        yield lineno, word
        if prev is not None:
            yield lineno, f"{prev} {word}"
        prev = word


def scan_text(
    rel: str,
    text: str,
    hashes: frozenset[str],
    markers: re.Pattern[str] | None,
) -> list[str]:
    hits = []
    seen = set()
    for lineno, term in candidates(text):
        digest = sha256_hex(term)
        if digest in hashes and (lineno, digest) not in seen:
            seen.add((lineno, digest))
            hits.append(f"{rel}:{lineno}: blocked term (sha256 {digest[:12]})")
    if markers is not None:
        for lineno, line in enumerate(text.splitlines(), 1):
            if markers.search(line):
                hits.append(f"{rel}:{lineno}: {MARKERS_ENV} match")
    return hits


def read_for_scan(path: Path) -> str | None:
    if path.is_symlink():
        return os.readlink(path)
    if not path.is_file():
        return None
    return path.read_bytes().decode("utf-8", errors="replace")


def is_build_output(rel: str) -> bool:
    parts = Path(rel).parts
    return any(p in BUILD_DIRS or p.endswith(".egg-info") for p in parts[:-1])


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def tracked_files(root: Path) -> list[str]:
    result = git(root, "ls-files", "-z")
    if result.returncode != 0:
        raise ConfigError(f"git ls-files failed: {result.stderr.strip()}")
    files = [p for p in result.stdout.split("\0") if p]
    if not files:
        raise ConfigError("no tracked files to scan")
    return files


def employer_hits(
    root: Path,
    rels: list[str],
    hash_file: Path,
    markers: re.Pattern[str] | None,
) -> tuple[list[str], int]:
    hashes = load_hashes(hash_file)
    hash_rel = hash_file.resolve()
    hits = []
    scanned = 0
    for rel in rels:
        path = root / rel
        if path.resolve() == hash_rel or is_build_output(rel):
            continue
        text = read_for_scan(path)
        if text is None:
            continue
        scanned += 1
        hits.extend(scan_text(rel, text, hashes, markers))
    if scanned == 0:
        raise ConfigError("no files were scanned")
    return hits, scanned


def export_control_hits(root: Path) -> list[str]:
    result = git(root, "grep", "-nIiE", MARKER.pattern, "--", ".", *MARKER_EXCLUDES)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise ConfigError(f"git grep failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line]


def committed_junk(rels: list[str]) -> list[str]:
    return [
        p for p in rels if "__pycache__/" in p or p.endswith(".pyc") or p == ".coverage"
    ]


def assert_tuning() -> None:
    """Word splitting must not turn longer tokens into short blocked words."""
    words = [t for _, t in candidates("LLM-judge LMS")]
    if words != ["llm", "judge", "llm judge", "lms", "judge lms"]:
        raise SystemExit(f"word splitting changed: {words}")
    if MARKER.search("Author: t <t@t>") or MARKER.search("military"):
        raise SystemExit("author lines and the word military must not match")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="repo to scan")
    parser.add_argument(
        "--hash-file",
        type=Path,
        default=None,
        help=f"blocked-term hashes (default: <root>/{HASH_FILE})",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=None,
        help="scan only these files for employer terms (used by the edit hook)",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    hash_file = args.hash_file or root / HASH_FILE
    markers = load_markers(os.environ.get(MARKERS_ENV))
    if args.paths is not None:
        rels = [os.path.relpath(Path(p).resolve(), root) for p in args.paths]
        hits, _ = employer_hits(root, rels, hash_file, markers)
        for hit in hits:
            print(f"EMPLOYER: {hit}", file=sys.stderr)
        return 1 if hits else 0

    rels = tracked_files(root)
    hits, scanned = employer_hits(root, rels, hash_file, markers)
    marker_hits = export_control_hits(root)
    junk = committed_junk(rels)
    if not hits and not marker_hits and not junk:
        extra = "set" if markers is not None else "unset"
        print(
            f"scanned {scanned} tracked files; no employer terms "
            f"({MARKERS_ENV} {extra}), no export-control markers, "
            "no committed build junk"
        )
        return 0
    for hit in hits:
        print(f"EMPLOYER: {hit}", file=sys.stderr)
    for hit in marker_hits:
        print(f"MARKER: {hit}", file=sys.stderr)
    for path in junk:
        print(f"JUNK: {path}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> None:
    assert_tuning()
    try:
        code = run(parse_args(argv))
    except ConfigError as exc:
        print(f"CONFIG: {exc}", file=sys.stderr)
        code = CONFIG_ERROR
    sys.exit(code)


if __name__ == "__main__":
    main()
