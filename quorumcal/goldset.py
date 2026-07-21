"""Gold set: labeled judge tasks with truth by construction.

Invalid tasks are mutants the subject repo's own test suite KILLS (status
exactly "killed" — a guaranteed behavioral bug). Valid tasks are real
historical commits from the same repo. Building runs under the crucible venv
python; this module imports crucible/oracle_gate lazily so the rest of
quorumcal never needs them."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_LABELS = frozenset({"valid", "invalid"})


@dataclass(frozen=True)
class GoldTask:
    task_id: str
    repo: str
    label: str
    diff: str
    provenance: dict

    def __post_init__(self):
        if self.label not in _LABELS:
            raise ValueError(f"bad label {self.label!r}")


_GIT_HEADER_PREFIXES = (
    "diff --git", "index ", "new file mode", "old mode", "new mode",
    "similarity index", "rename from", "rename to", "commit ",
    "Author", "Date:",
)


def _strip_ab_prefix(line: str) -> str:
    for marker in ("--- ", "+++ "):
        if line.startswith(marker):
            path = line[len(marker):]
            if path.startswith("a/") or path.startswith("b/"):
                return marker + path[2:]
            return line
    return line


def normalize_diff(text: str) -> str:
    """Strip git-specific header lines so goldset diffs are format-neutral
    regardless of provenance.

    Invalid (mutmut-show) diffs are plain difflib unified diffs with no git
    headers; valid (git-show) diffs carry `diff --git` / `index` / commit
    metadata lines. Left alone, the mere presence of those lines would let a
    judge infer the label from format rather than content — format leakage.
    Also strips bare `#`-prefixed lines (e.g. mutmut's `# pkg.mod.fn: killed`
    status header) since valid unified-diff content never starts a line with
    `#` — context/added/removed lines start with space/+/-, so a `+# comment`
    code line keeps its `+` prefix and is unaffected.
    Keeps everything from each file section's first "--- " line onward:
    the @@ hunks and +/-/context lines are untouched.
    Also strips a leading "a/" or "b/" from the path on "--- "/"+++ " lines
    (git-show diffs carry it, mutmut-show diffs never do — the prefix alone
    would let a judge classify by form instead of diff content). "--- "
    lines with no path prefix (e.g. "--- /dev/null") are left unchanged."""
    lines = text.splitlines()
    kept = [ln for ln in lines
            if not ln.startswith(_GIT_HEADER_PREFIXES) and not ln.startswith("#")]
    kept = [_strip_ab_prefix(ln) for ln in kept]
    out = "\n".join(kept)
    if text.endswith("\n") and not out.endswith("\n"):
        out += "\n"
    return out


def make_task_id(repo: str, kind: str, ref: str) -> str:
    return hashlib.sha256(f"{repo}|{kind}|{ref}".encode()).hexdigest()[:12]


def write_goldset(path, tasks: list[GoldTask]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for t in tasks:
            fh.write(json.dumps(dataclasses.asdict(t), sort_keys=True) + "\n")


def read_goldset(path) -> list[GoldTask]:
    tasks = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            tasks.append(GoldTask(**json.loads(line)))
    return tasks


KILLED_STATUS = "killed"   # oracle_gate.survivors.DETECTED = {"killed", "timeout"};
                           # timeout is deliberately excluded (ambiguous cause)


def _mutmut_show(workdir: Path, mutant_id: str, run) -> str:
    proc = run([sys.executable, "-m", "mutmut", "show", mutant_id],
               cwd=str(workdir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mutmut show {mutant_id} failed: {proc.stderr}")
    return proc.stdout


def killed_mutant_tasks(workdir: Path, repo_name: str, limit: int, seed: int,
                        *, run=subprocess.run,
                        run_mutation=None, parse_results=None) -> list[GoldTask]:
    """Run mutation testing in `workdir` and return up to `limit` killed-mutant
    tasks. Requires the crucible venv unless run_mutation/parse_results are
    injected (tests inject fakes)."""
    if run_mutation is None or parse_results is None:
        from oracle_gate.runner import run_mutation as _rm        # lazy: venv-only
        from oracle_gate.survivors import parse_results as _pr
        run_mutation = run_mutation or _rm
        parse_results = parse_results or _pr

    _counts, results_text = run_mutation(workdir, run=run)
    killed = [m for m in parse_results(results_text) if m.status == KILLED_STATUS]
    if not killed:
        raise RuntimeError(
            f"no killed mutants in {workdir} — wrong scope, or the suite "
            "genuinely kills nothing (unusable subject)")
    rng = random.Random(seed)
    rng.shuffle(killed)
    tasks = []
    for m in killed[:limit]:
        tasks.append(GoldTask(
            task_id=make_task_id(repo_name, "mutant", m.id),
            repo=repo_name,
            label="invalid",
            diff=normalize_diff(_mutmut_show(workdir, m.id, run)),
            provenance={"kind": "mutant", "ref": m.id, "seed": seed},
        ))
    return tasks


def _run_ok(cmd, cwd, run, timeout=600):
    proc = run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed in {cwd}: {proc.stderr}")
    return proc.stdout


def clone_at_head(repo_path: str, workdir: Path, *, run=subprocess.run) -> Path:
    """Local clone of the subject at HEAD. NEVER build a goldset in a live tree."""
    repo_path = str(Path(repo_path).resolve())
    workdir = Path(workdir)
    workdir.parent.mkdir(parents=True, exist_ok=True)
    _run_ok(["git", "clone", "--local", "--no-hardlinks", repo_path, str(workdir)],
            cwd=workdir.parent, run=run)
    return workdir


def valid_commit_tasks(workdir: Path, repo_name: str, source_prefixes: list[str],
                       limit: int, seed: int, max_diff_lines: int = 400,
                       *, run=subprocess.run) -> list[GoldTask]:
    """Valid tasks = real historical commits touching the scoped sources.

    Label noise caveat (spec §8): 'merged and in the history of a green HEAD'
    approximates 'valid'; a historical commit may itself contain a later-fixed
    bug. Reported as a limitation, not silently ignored."""
    shas = _run_ok(["git", "log", "--no-merges", "--pretty=%H", "--",
                    *source_prefixes], cwd=workdir, run=run).split()
    rng = random.Random(seed)
    rng.shuffle(shas)
    tasks = []
    for sha in shas:
        diff = _run_ok(["git", "show", "--format=", sha, "--", *source_prefixes],
                       cwd=workdir, run=run)
        if not diff.strip() or len(diff.splitlines()) > max_diff_lines:
            continue
        tasks.append(GoldTask(
            task_id=make_task_id(repo_name, "commit", sha),
            repo=repo_name,
            label="valid",
            diff=normalize_diff(diff),
            provenance={"kind": "commit", "ref": sha, "seed": seed},
        ))
        if len(tasks) == limit:
            break
    return tasks


def build_goldset(repo_path: str, repo_name: str, workdir: Path,
                  n_invalid: int, n_valid: int, seed: int,
                  source_paths: list[str],
                  *, run=subprocess.run, write_scope=None,
                  run_mutation=None, parse_results=None) -> list[GoldTask]:
    workdir = clone_at_head(repo_path, Path(workdir), run=run)
    if write_scope is None:
        # lazy: venv-only. The real path ignores the also_copy computed below
        # and delegates scope planning to crucible.scope.detect instead: a
        # subject's test dir can import OTHER local top-level packages absent
        # from mutmut's sandbox (e.g. rag-guard's tests/test_hook.py imports
        # `bin`), which kills the stats phase — detect() finds both the
        # mutated top-level package AND those hazard tests to --ignore.
        from crucible.engine import write_scope as _crucible_write_scope
        from crucible.scope import detect as _detect

        def write_scope(pyproject, source_paths, also_copy=None, pytest_args=None):
            plan = _detect(workdir, source_paths[0])
            _crucible_write_scope(pyproject, source_paths,
                                  also_copy=plan.also_copy,
                                  pytest_args=plan.pytest_args)
    tops = sorted({p.split("/")[0] for p in source_paths if "/" in p})
    write_scope(workdir / "pyproject.toml", source_paths, also_copy=tops or None)
    invalid = killed_mutant_tasks(workdir, repo_name, n_invalid, seed, run=run,
                                  run_mutation=run_mutation,
                                  parse_results=parse_results)
    # Valid commits must draw from the SAME file scope the mutant pool did —
    # source_paths passed straight through as git pathspecs, not a derived
    # directory prefix, or the two classes see different file scopes.
    valid = valid_commit_tasks(workdir, repo_name, source_paths, n_valid, seed,
                               run=run)
    if len(invalid) < n_invalid or len(valid) < n_valid:
        print(f"WARNING: requested {n_invalid}/{n_valid}, got "
              f"{len(invalid)}/{len(valid)} — CIs will be wider", flush=True)
    tasks = invalid + valid
    random.Random(seed).shuffle(tasks)
    return tasks


_HUNK_RE = re.compile(r"^@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@(.*)$")


def invert_diff(text: str) -> str:
    """Reverse a NORMALIZED unified diff (mutant -> original becomes the fix
    direction). Output is canonical: within each contiguous change block,
    '-' lines precede '+' lines — a non-canonical ordering would let a judge
    classify revert tasks by format instead of content."""
    out = []
    minus_run, plus_run = [], []

    def flush():
        # after inversion, old '+' lines become the new minuses
        out.extend("-" + ln[1:] for ln in plus_run)
        out.extend("+" + ln[1:] for ln in minus_run)
        minus_run.clear()
        plus_run.clear()

    for ln in text.splitlines():
        m = _HUNK_RE.match(ln)
        if m:
            flush()
            out.append(f"@@ -{m.group(2)} +{m.group(1)} @@{m.group(3)}")
        elif ln.startswith("---") or ln.startswith("+++"):
            flush()
            out.append(ln)          # same path both sides; direction is in the hunks
        elif ln.startswith("-"):
            minus_run.append(ln)
        elif ln.startswith("+"):
            plus_run.append(ln)
        else:
            flush()
            out.append(ln)
    flush()
    res = "\n".join(out)
    if text.endswith("\n"):
        res += "\n"
    return res


def list_killed_mutants(workdir, *, run=subprocess.run) -> list[str]:
    proc = run([sys.executable, "-m", "mutmut", "results", "--all", "true"],
               cwd=str(workdir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mutmut results failed: {proc.stderr}")
    out = []
    for ln in proc.stdout.splitlines():
        ln = ln.strip()
        if ln.endswith(": killed"):
            out.append(ln[: -len(": killed")])
    return out


def revert_valid_tasks(workdir, repo_name: str, limit: int, seed: int,
                       exclude_refs: set[str],
                       *, run=subprocess.run) -> list[GoldTask]:
    """Truth-by-construction VALID tasks: the reverse of a killed mutant is a
    change that provably takes the subject's own suite red -> green. Same
    size/shape as invalid diffs, so it also removes the diff-size confound.
    Mutants already used as invalid tasks are excluded (partition guard)."""
    killed = [m for m in list_killed_mutants(workdir, run=run)
              if m not in exclude_refs]
    rng = random.Random(seed)
    rng.shuffle(killed)
    tasks = []
    for mid in killed:
        if len(tasks) == limit:
            break
        diff = normalize_diff(_mutmut_show(Path(workdir), mid, run))
        if "XX" in diff:                 # string mutants: machine-identifiable
            continue
        tasks.append(GoldTask(
            task_id=make_task_id(repo_name, "mutant-revert", mid),
            repo=repo_name,
            label="valid",
            diff=invert_diff(diff),
            provenance={"kind": "mutant-revert", "ref": mid, "seed": seed},
        ))
    return tasks


def is_focused_commit(diff: str, max_content_lines: int = 40) -> bool:
    """Strict filter for the real-commit valid stratum: no new-file diffs
    (unjudgeable from a diff alone) and small focused changes only."""
    lines = diff.splitlines()
    if any(ln.startswith("--- /dev/null") for ln in lines):
        return False
    content = [ln for ln in lines
               if ln.startswith(("+", "-")) and not ln.startswith(("---", "+++"))]
    return len(content) <= max_content_lines
