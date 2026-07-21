import pytest
from quorumcal.judges import JudgeSpec
from quorumcal.profile import build_profile, prompt_fingerprint

REPORT = {"delta": 0.1, "epsilon": 0.1, "panels": {"p": {
    "n_effective": 2.43, "n_eff_ci": [2.18, 3.0], "rho_bar": 0.12,
    "e_delta": 0.0, "u_epsilon": 1.0, "q_min": 1, "q_max": 2,
    "feasible": True, "n_judges": 3,
    "per_judge_wrong_rate": [0.01, 0.02, 0.03],
    "per_judge_wrong_upper": [0.04, 0.05, 0.06]}}}
PANELS = {"p": [
    JudgeSpec(judge_id="sonnet-corr", model="claude-sonnet-5", lens="correctness"),
    JudgeSpec(judge_id="codex-corr", model="gpt-5.6-sol", lens="correctness", lineage="codex"),
    JudgeSpec(judge_id="grok-corr", model="grok-4.5", lens="correctness", lineage="grok")]}
BASELINE = {"disagreement_rate": 0.2, "abstain_rate": 0.05, "n_tasks": 180}


def _profile(**kw):
    return build_profile(REPORT, PANELS, "p", BASELINE,
                         domain="code-change verification",
                         emitted_at="2026-07-21", **kw)


def test_prompt_fingerprint_is_stable_hex():
    a, b = prompt_fingerprint(), prompt_fingerprint()
    assert a == b and len(a) == 64 and int(a, 16) >= 0


def test_build_profile_core_fields():
    p = _profile()
    assert p["panel"] == "p" and p["domain"] == "code-change verification"
    assert p["q"] == 1                                # defaults to q_min
    assert p["q_window"] == [1, 2]
    assert p["delta"] == 0.1 and p["epsilon"] == 0.1
    assert p["budgets"]["e_delta"] == 0.0 and p["budgets"]["u_epsilon"] == 1.0
    assert p["n_effective"] == 2.43 and p["n_eff_ci"] == [2.18, 3.0]
    assert p["baseline"] == BASELINE
    assert p["committee"][1]["judge_id"] == "codex-corr"
    assert p["committee"][1]["lineage"] == "codex"
    assert p["provenance"]["prompt_fingerprint"] == prompt_fingerprint()
    assert p["provenance"]["tool_schemas"] == "none"
    assert p["emitted_at"] == "2026-07-21"
    assert p["expires_at"] == "2026-08-20"             # 30 days later


def test_build_profile_q_override_and_window_enforced():
    assert _profile(q=2)["q"] == 2
    with pytest.raises(ValueError):
        _profile(q=3)                                  # outside [1,2]


def test_build_profile_unknown_panel_raises():
    with pytest.raises(ValueError):
        build_profile(REPORT, PANELS, "nope", BASELINE,
                      domain="d", emitted_at="2026-07-21")


def test_build_profile_records_observed_models():
    p = _profile(observed_models={"grok-corr": ["grok-4.5-build"]})
    assert "grok-4.5-build" in p["provenance"]["allowed_models"]
    assert "claude-sonnet-5" in p["provenance"]["allowed_models"]   # spec models always allowed


def test_check_profile_valid():
    from quorumcal.profile import check_profile
    p = _profile()
    r = check_profile(p, today="2026-08-01")
    assert r == {"status": "valid", "reasons": []}


def test_check_profile_expired():
    from quorumcal.profile import check_profile
    p = _profile()
    r = check_profile(p, today="2026-08-21")
    assert r["status"] == "expired"
    assert any("expire" in s for s in r["reasons"])


def test_check_profile_drifted_beats_expired():
    from quorumcal.profile import check_profile
    p = _profile()
    r = check_profile(p, today="2026-08-21",
                      current_prompt_fingerprint="deadbeef")
    assert r["status"] == "provenance-drifted"
    assert len(r["reasons"]) == 2      # drift AND expiry both reported


def test_panel_baseline_from_cache(tmp_path):
    import json
    from quorumcal.goldset import GoldTask
    from quorumcal.panel import cache_key
    from quorumcal.profile import panel_baseline
    specs = PANELS["p"]
    t1 = GoldTask(task_id="t1t1t1", repo="r", label="valid", diff="d", provenance={})
    t2 = GoldTask(task_id="t2t2t2", repo="r", label="valid", diff="d", provenance={})
    grid = {("t1t1t1"): ["endorse", "endorse", "endorse"],       # unanimous
            ("t2t2t2"): ["endorse", "reject", "abstain"]}         # disagree + 1 abstain
    for t in (t1, t2):
        for s, v in zip(specs, grid[t.task_id]):
            (tmp_path / f"{cache_key(s, t.task_id)}.json").write_text(
                json.dumps({"verdict": v}))
    b = panel_baseline([t1, t2], specs, tmp_path)
    assert b["n_tasks"] == 2
    assert b["disagreement_rate"] == 0.5
    # DECISION-level (any judge abstained), matching the monitor's indicator —
    # a cell-level rate here caused a guaranteed false alarm (caught in smoke)
    assert b["abstain_rate"] == 0.5
