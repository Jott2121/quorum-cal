"""Tests for check_no_employer_data.py. Run: python -m unittest -v scripts/test_*.py

Every planted term is synthetic and lives only in a temp git repo with a temp
hash file. Nothing here names a real employer.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().with_name("check_no_employer_data.py")
REPO = SCRIPT.parents[1]
COMMITTED_HASHES = REPO / ".github" / "blocked-terms.sha256"
PLANTED_WORD = "zorblaxcorp"
PLANTED_PHRASE = "quillon dynamics"


def digest(term: str) -> str:
    return hashlib.sha256(term.encode("utf-8")).hexdigest()


class TempRepo:
    def __init__(self, files: dict[str, str], hashes: list[str] | None) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        if hashes is not None:
            files = {
                ".github/blocked-terms.sha256": "# test\n" + "\n".join(hashes) + "\n",
                **files,
            }
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)

    def scan(self, *args: str, markers: str | None = None):
        env = {k: v for k, v in os.environ.items() if k != "EMPLOYER_MARKERS"}
        if markers is not None:
            env["EMPLOYER_MARKERS"] = markers
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def close(self) -> None:
        self._tmp.cleanup()


CLEAN = {
    "README.md": "An LLM judge panel, an LMS, and a helm chart.\n",
    "AGENTS.md": "No employer data from any employer's systems.\n",
}
HASHES = [digest(PLANTED_WORD), digest(PLANTED_PHRASE)]


class ScannerTest(unittest.TestCase):
    def repo(self, files: dict[str, str], hashes: list[str] | None = HASHES):
        repo = TempRepo(files, hashes)
        self.addCleanup(repo.close)
        return repo

    def test_clean_tree_passes(self):
        result = self.repo(CLEAN).scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no employer terms", result.stdout)

    def test_planted_word_is_caught_without_echoing_it(self):
        files = {**CLEAN, "runs/data.jsonl": '{"note": "ZorblaxCorp internal"}\n'}
        result = self.repo(files).scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("runs/data.jsonl:1: blocked term", result.stderr)
        self.assertNotIn(PLANTED_WORD, result.stderr.lower())

    def test_planted_phrase_across_a_line_break_is_caught(self):
        files = {**CLEAN, "docs/x.md": "ok\nQuillon\nDynamics site\n"}
        result = self.repo(files).scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/x.md:3: blocked term", result.stderr)

    def test_policy_files_are_scanned(self):
        for rel in ("AGENTS.md", ".cursor/rules/x.mdc", ".github/workflows/ci.yml"):
            with self.subTest(rel=rel):
                files = {**CLEAN, rel: f"never use {PLANTED_WORD} data\n"}
                result = self.repo(files).scan()
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"{rel}:1: blocked term", result.stderr)

    def test_longer_tokens_do_not_match_a_short_blocked_word(self):
        files = {**CLEAN, "x.txt": "QQX and QXS are fine\n"}
        result = self.repo(files, hashes=[digest("qx")]).scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        files = {**CLEAN, "x.txt": "the QX team\n"}
        self.assertEqual(self.repo(files, hashes=[digest("qx")]).scan().returncode, 1)

    def test_build_output_is_skipped(self):
        files = {**CLEAN, "node_modules/pkg/index.js": f"// {PLANTED_WORD}\n"}
        self.assertEqual(self.repo(files).scan().returncode, 0)

    def test_missing_hash_file_fails_closed(self):
        result = self.repo(CLEAN, hashes=None).scan()
        self.assertEqual(result.returncode, 2)
        self.assertIn("hash file missing", result.stderr)

    def test_empty_hash_file_fails_closed(self):
        result = self.repo(CLEAN, hashes=[]).scan()
        self.assertEqual(result.returncode, 2)
        self.assertIn("no hashes", result.stderr)

    def test_malformed_hash_file_fails_closed(self):
        result = self.repo(CLEAN, hashes=["not-a-hash"]).scan()
        self.assertEqual(result.returncode, 2)

    def test_employer_markers_env_adds_terms(self):
        files = {**CLEAN, "x.txt": "Acme Widgets roster\n"}
        repo = self.repo(files)
        self.assertEqual(repo.scan().returncode, 0)
        result = repo.scan(markers="acme widgets|globex")
        self.assertEqual(result.returncode, 1)
        self.assertIn("x.txt:1: EMPLOYER_MARKERS match", result.stderr)
        self.assertNotIn("acme", result.stderr.lower())

    def test_blank_employer_markers_is_ignored(self):
        self.assertEqual(self.repo(CLEAN).scan(markers="  ").returncode, 0)

    def test_bad_employer_markers_fail_closed(self):
        repo = self.repo(CLEAN)
        self.assertEqual(repo.scan(markers="(unclosed").returncode, 2)
        self.assertEqual(repo.scan(markers="a|").returncode, 2)

    def test_paths_mode_scans_one_file(self):
        files = {**CLEAN, "x.py": f"# {PLANTED_WORD}\n"}
        repo = self.repo(files)
        hit = repo.scan("--paths", str(repo.root / "x.py"))
        self.assertEqual(hit.returncode, 1)
        clean = repo.scan("--paths", str(repo.root / "README.md"))
        self.assertEqual(clean.returncode, 0)

    def test_committed_junk_fails(self):
        files = {**CLEAN, "pkg/__pycache__/m.cpython-312.pyc": "x"}
        result = self.repo(files).scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("JUNK:", result.stderr)

    def test_committed_hash_file_is_loaded(self):
        lines = [
            ln.strip()
            for ln in COMMITTED_HASHES.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        self.assertGreater(len(lines), 0)
        self.assertTrue(all(len(ln) == 64 for ln in lines))

    def test_this_repo_is_clean_without_a_secret(self):
        env = {k: v for k, v in os.environ.items() if k != "EMPLOYER_MARKERS"}
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
