import json
from pathlib import Path
from quorumcal.goldset import GoldTask
from quorumcal.judges import JudgeSpec
from quorumcal.panel import cache_key, load_panels, run_panel

T1 = GoldTask(task_id="t1t1t1t1t1t1", repo="demo", label="invalid", diff="d1",
              provenance={})
T2 = GoldTask(task_id="t2t2t2t2t2t2", repo="demo", label="valid", diff="d2",
              provenance={})
S1 = JudgeSpec(judge_id="j1", model="m", lens="correctness")
S2 = JudgeSpec(judge_id="j2", model="m", lens="security")


def _fake_judge(calls):
    def judge(spec, task, **kw):
        calls.append((spec.judge_id, task.task_id))
        return {"task_id": task.task_id, "judge_id": spec.judge_id,
                "verdict": "reject", "rationale": "", "cost_usd": 0.0,
                "model_requested": spec.model, "model_reported": "m-x",
                "raw_result": ""}
    return judge


def test_cache_key_distinct_per_judge_and_task():
    keys = {cache_key(s, t.task_id) for s in (S1, S2) for t in (T1, T2)}
    assert len(keys) == 4


def test_run_panel_runs_grid_and_caches(tmp_path):
    calls = []
    recs = run_panel([T1, T2], [S1, S2], tmp_path, judge_fn=_fake_judge(calls),
                     on_progress=lambda *a: None)
    assert len(recs) == 4 and len(calls) == 4
    # second run: fully cached, zero new judge calls
    calls2 = []
    recs2 = run_panel([T1, T2], [S1, S2], tmp_path, judge_fn=_fake_judge(calls2),
                      on_progress=lambda *a: None)
    assert len(recs2) == 4 and calls2 == []


def test_run_panel_retries_error_records(tmp_path):
    def erroring_judge(spec, task, **kw):
        return {"task_id": task.task_id, "judge_id": spec.judge_id,
                "verdict": "error", "rationale": "boom", "cost_usd": None,
                "model_requested": spec.model, "model_reported": None,
                "raw_result": ""}
    run_panel([T1], [S1], tmp_path, judge_fn=erroring_judge,
              on_progress=lambda *a: None)
    calls = []
    recs = run_panel([T1], [S1], tmp_path, judge_fn=_fake_judge(calls),
                     on_progress=lambda *a: None)
    assert calls == [("j1", T1.task_id)]      # error record was re-run
    assert recs[0]["verdict"] == "reject"


def test_run_panel_heals_corrupt_cell(tmp_path):
    cell = tmp_path / f"{cache_key(S1, T1.task_id)}.json"
    cell.write_text("not valid json {{{")
    calls = []
    recs = run_panel([T1], [S1], tmp_path, judge_fn=_fake_judge(calls),
                     on_progress=lambda *a: None)
    assert calls == [("j1", T1.task_id)]      # corrupt cell was re-run
    assert recs[0]["verdict"] == "reject"
    assert json.loads(cell.read_text())["verdict"] == "reject"


def test_run_panel_writes_atomically_no_leftover_tmp(tmp_path):
    calls = []
    run_panel([T1], [S1], tmp_path, judge_fn=_fake_judge(calls),
              on_progress=lambda *a: None)
    cell = tmp_path / f"{cache_key(S1, T1.task_id)}.json"
    assert cell.exists()
    assert not cell.with_suffix(".tmp").exists()


def test_run_panel_partial_grid_only_runs_missing_cells(tmp_path):
    tasks = [T1, T2]
    specs = [S1, S2]
    # pre-seed 1 of 4 cells
    seeded = {"task_id": T1.task_id, "judge_id": S1.judge_id,
             "verdict": "reject", "rationale": "", "cost_usd": 0.0,
             "model_requested": S1.model, "model_reported": "m-x",
             "raw_result": ""}
    (tmp_path / f"{cache_key(S1, T1.task_id)}.json").write_text(json.dumps(seeded))
    calls = []
    recs = run_panel(tasks, specs, tmp_path, judge_fn=_fake_judge(calls),
                     on_progress=lambda *a: None)
    assert len(recs) == 4
    assert len(calls) == 3     # only the 3 missing cells triggered a judge call


def test_load_panels(tmp_path):
    p = tmp_path / "panels.json"
    p.write_text(json.dumps({"pan": [
        {"judge_id": "a", "model": "m1", "lens": "correctness"}]}))
    panels = load_panels(p)
    assert panels["pan"] == [JudgeSpec(judge_id="a", model="m1", lens="correctness")]


def test_cache_key_ignores_lineage_field():
    a = JudgeSpec(judge_id="sonnet-corr", model="claude-sonnet-5",
                  lens="correctness")
    b = JudgeSpec(judge_id="sonnet-corr", model="claude-sonnet-5",
                  lens="correctness", lineage="claude")
    assert cache_key(a, "t1") == cache_key(b, "t1")
    import hashlib
    expect = hashlib.sha256(
        b"sonnet-corr|claude-sonnet-5|correctness|t1").hexdigest()[:24]
    assert cache_key(a, "t1") == expect     # pins Phase 1 cache compatibility


def test_run_panel_dispatches_by_lineage(tmp_path):
    calls = []
    def fake_codex(spec, task):
        calls.append(("codex", spec.judge_id))
        return {"task_id": task.task_id, "judge_id": spec.judge_id,
                "verdict": "endorse", "rationale": ""}
    task = GoldTask(task_id="t3t3t3t3t3t3", repo="r", label="valid", diff="d",
                    provenance={})
    spec = JudgeSpec(judge_id="codex-corr", model="gpt-5.6-sol",
                     lens="correctness", lineage="codex")
    import quorumcal.panel as panel_mod
    old = panel_mod.JUDGE_FNS.get("codex")
    panel_mod.JUDGE_FNS["codex"] = fake_codex
    try:
        run_panel([task], [spec], tmp_path, on_progress=lambda m: None)
    finally:
        if old is None:
            del panel_mod.JUDGE_FNS["codex"]
        else:
            panel_mod.JUDGE_FNS["codex"] = old
    assert calls == [("codex", "codex-corr")]


def test_load_panels_accepts_lineage(tmp_path):
    p = {"x": [{"judge_id": "codex-corr", "model": "gpt-5.6-sol",
                "lens": "correctness", "lineage": "codex"}]}
    f = tmp_path / "p.json"
    f.write_text(json.dumps(p))
    specs = load_panels(f)["x"]
    assert specs[0].lineage == "codex"
