"""Assemble the phase2c gold set. Run from ~/quorum-cal under the crucible venv:
~/ai-agentic-code-testing/.venv/bin/python runs/phase2c/build-goldset.py"""
import collections

from quorumcal.goldset import (is_focused_commit, read_goldset,
                               revert_valid_tasks, write_goldset)

base = read_goldset("runs/phase2b/goldset.jsonl")
invalid = [t for t in base if t.label == "invalid"]
commit_valid = [t for t in base if t.label == "valid"
                and is_focused_commit(t.diff)]

used = {(t.repo, t.provenance["ref"]) for t in invalid}
rg_excl = {r for repo, r in used if repo == "rag-guard"}
bow_excl = {r for repo, r in used if repo == "bow"}

reverts = (revert_valid_tasks("/tmp/qc-work-p2b-ragguard", "rag-guard",
                              limit=40, seed=9, exclude_refs=rg_excl)
           + revert_valid_tasks("/tmp/qc-work/bow", "bow",
                                limit=15, seed=9, exclude_refs=bow_excl))

tasks = invalid + reverts + commit_valid
ids = [t.task_id for t in tasks]
assert len(ids) == len(set(ids)), "task_id collision"
inv_refs = {(t.repo, t.provenance["ref"]) for t in invalid}
rev_refs = {(t.repo, t.provenance["ref"]) for t in reverts}
assert not (inv_refs & rev_refs), "partition violated"

c = collections.Counter((t.provenance["kind"], t.label) for t in tasks)
print("strata:", dict(c))
n_inv = sum(1 for t in tasks if t.label == "invalid")
print(f"TOTAL {len(tasks)} ({n_inv} invalid / {len(tasks) - n_inv} valid)")
write_goldset("runs/phase2c/goldset.jsonl", tasks)
print("wrote runs/phase2c/goldset.jsonl")
