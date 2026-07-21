import json
from pathlib import Path
import pytest
from quorumcal.goldset import GoldTask
from quorumcal.judges import JudgeSpec
from quorumcal.panel import cache_key
from quorumcal.report import build_report, collect_rows, format_table

SPECS = [JudgeSpec(f"j{i}", "m", "correctness") for i in range(3)]


def _seed_cache(tmp_path, tasks, verdict_fn):
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        for s in SPECS:
            rec = {"task_id": t.task_id, "judge_id": s.judge_id,
                   "verdict": verdict_fn(t, s), "rationale": "",
                   "cost_usd": 0.01, "model_requested": "m",
                   "model_reported": "m-x", "raw_result": ""}
            (cache / f"{cache_key(s, t.task_id)}.json").write_text(json.dumps(rec))
    return tmp_path / "cache"


def _goldset(tmp_path, n=4):
    from quorumcal.goldset import write_goldset
    tasks = [GoldTask(task_id=f"t{i}" * 6, repo="demo",
                      label="invalid" if i % 2 else "valid",
                      diff="+x\n" * (3 if i % 2 else 10), provenance={})
             for i in range(n)]
    p = tmp_path / "goldset.jsonl"
    write_goldset(p, tasks)
    return p, tasks


def _panels(tmp_path):
    p = tmp_path / "panels.json"
    p.write_text(json.dumps({"pan": [
        {"judge_id": s.judge_id, "model": s.model, "lens": s.lens}
        for s in SPECS]}))
    return p


def test_collect_rows_missing_cell_raises(tmp_path):
    _, tasks = _goldset(tmp_path)
    with pytest.raises(RuntimeError):
        collect_rows(tasks, SPECS, tmp_path / "empty-cache")


def test_collect_rows_corrupt_cell_raises_runtime_error_naming_file(tmp_path):
    _, tasks = _goldset(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    cell = cache / f"{cache_key(SPECS[0], tasks[0].task_id)}.json"
    cell.write_text("not valid json {{{")
    with pytest.raises(RuntimeError) as excinfo:
        collect_rows(tasks, SPECS, cache)
    assert str(cell) in str(excinfo.value)
    assert "panel run" in str(excinfo.value)


def test_build_report_end_to_end(tmp_path):
    gs, tasks = _goldset(tmp_path)
    cache = _seed_cache(tmp_path, tasks,
                        lambda t, s: "reject" if t.label == "invalid" else "endorse")
    rep = build_report(gs, _panels(tmp_path), cache)
    pan = rep["panels"]["pan"]
    assert pan["n_effective"] == pytest.approx(3.0)
    assert pan["feasible"] is True
    assert pan["cost_usd"] == pytest.approx(0.12)      # 4 tasks × 3 judges × 0.01
    assert pan["mean_diff_lines"]["invalid"] < pan["mean_diff_lines"]["valid"]
    assert rep["goldset"]["n_invalid"] == 2


def test_build_report_includes_n_eff_ci(tmp_path):
    gs, tasks = _goldset(tmp_path)
    cache = _seed_cache(tmp_path, tasks,
                        lambda t, s: "reject" if t.label == "invalid" else "endorse")
    rep = build_report(gs, _panels(tmp_path), cache)
    pan = rep["panels"]["pan"]
    assert "n_eff_ci" in pan
    lo, hi = pan["n_eff_ci"]
    assert lo <= pan["n_effective"] <= hi
    assert "wrong_vectors" not in pan     # internal field must not leak into the report


def test_format_table_mentions_the_number(tmp_path):
    gs, tasks = _goldset(tmp_path)
    cache = _seed_cache(tmp_path, tasks, lambda t, s: "endorse")
    out = format_table(build_report(gs, _panels(tmp_path), cache))
    assert "N_eff" in out and "pan" in out


def test_error_guard_reflected(tmp_path):
    gs, tasks = _goldset(tmp_path)
    cache = _seed_cache(tmp_path, tasks,
                        lambda t, s: "error" if t.task_id.startswith("t1") else "reject")
    rep = build_report(gs, _panels(tmp_path), cache)
    assert rep["panels"]["pan"]["error_guard_tripped"] is True
