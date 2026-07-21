import json
import pytest
from quorumcal.goldset import GoldTask, write_goldset
from quorumcal.panel import run_panel
from quorumcal.report import build_report


def _sharp_judge(spec, task, **kw):
    """Deterministic judge that is right except judge j2 rubber-stamps."""
    verdict = "endorse" if (spec.judge_id == "j2" or task.label == "valid") \
        else "reject"
    return {"task_id": task.task_id, "judge_id": spec.judge_id,
            "verdict": verdict, "rationale": "", "cost_usd": 0.0,
            "model_requested": spec.model, "model_reported": "m", "raw_result": ""}


def test_pipeline_end_to_end(tmp_path):
    tasks = [GoldTask(task_id=f"{i:012d}", repo="demo",
                      label="invalid" if i < 6 else "valid",
                      diff=f"+line {i}\n", provenance={}) for i in range(12)]
    gs = tmp_path / "goldset.jsonl"
    write_goldset(gs, tasks)
    panels_path = tmp_path / "panels.json"
    panels_path.write_text(json.dumps({"smoke": [
        {"judge_id": j, "model": "m", "lens": "correctness"}
        for j in ("j1", "j2", "j3")]}))

    from quorumcal.panel import load_panels
    specs = load_panels(panels_path)["smoke"]
    run_panel(tasks, specs, tmp_path / "cache",
              judge_fn=_sharp_judge, on_progress=lambda *a: None)

    rep = build_report(gs, panels_path, tmp_path / "cache")
    pan = rep["panels"]["smoke"]
    # j2 endorses every invalid task → e_delta must charge exactly 1
    assert pan["e_delta"] == 1.0
    assert pan["q_min"] == 2
    assert pan["feasible"] is True
    # j2's errors are uncorrelated with the (error-free) j1/j3 → N_eff stays 3
    assert pan["n_effective"] == pytest.approx(3.0)
    assert pan["n_tasks_used"] == 12
