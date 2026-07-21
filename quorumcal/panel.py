"""Panel runner: judge × task grid with a disk cache. Interrupted or
quota-halted runs lose nothing — re-invoke and only missing/error cells run."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from quorumcal.goldset import GoldTask
from quorumcal.judges import (JudgeSpec, claude_judge, codex_judge,
                              grok_judge)

# codex/grok lineages register here as their adapters land; run_panel
# dispatches per-spec while judge_fn= stays a test seam. An unknown
# lineage raises KeyError — never silently fall back to another lineage.
JUDGE_FNS = {"claude": claude_judge, "codex": codex_judge,
             "grok": grok_judge}


def cache_key(spec: JudgeSpec, task_id: str) -> str:
    raw = f"{spec.judge_id}|{spec.model}|{spec.lens}|{task_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def load_panels(path) -> dict[str, list[JudgeSpec]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {name: [JudgeSpec(**spec) for spec in specs]
            for name, specs in data.items()}


def _write_cell_atomic(cell: Path, rec: dict) -> None:
    tmp = cell.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, sort_keys=True), encoding="utf-8")
    os.replace(tmp, cell)


def run_panel(tasks: list[GoldTask], specs: list[JudgeSpec], cache_dir: Path,
              *, judge_fn=None,
              on_progress=lambda msg: print(msg, flush=True)) -> list[dict]:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    records = []
    total = len(tasks) * len(specs)
    done = 0
    for task in tasks:
        for spec in specs:
            done += 1
            cell = cache_dir / f"{cache_key(spec, task.task_id)}.json"
            if cell.exists():
                try:
                    rec = json.loads(cell.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    rec = None    # corrupt cell: heal by re-running
                if rec is not None and rec.get("verdict") != "error":
                    records.append(rec)
                    continue          # good record: never re-run
            fn = judge_fn or JUDGE_FNS[spec.lineage]
            rec = fn(spec, task)
            _write_cell_atomic(cell, rec)
            records.append(rec)
            on_progress(f"[{done}/{total}] {spec.judge_id} × {task.task_id}: "
                        f"{rec['verdict']}")
    return records
