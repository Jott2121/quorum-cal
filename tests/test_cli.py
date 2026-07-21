import subprocess as sp
import sys


def test_cli_goldset_build_help():
    proc = sp.run([sys.executable, "-m", "quorumcal.cli", "goldset", "build", "--help"],
                  capture_output=True, text=True)
    assert proc.returncode == 0
    assert "--n-invalid" in proc.stdout


def test_cli_panel_run_help():
    proc = sp.run([sys.executable, "-m", "quorumcal.cli", "panel", "run", "--help"],
                  capture_output=True, text=True)
    assert proc.returncode == 0
    assert "--cache-dir" in proc.stdout


def test_cli_report_help():
    proc = sp.run([sys.executable, "-m", "quorumcal.cli", "report", "--help"],
                  capture_output=True, text=True)
    assert proc.returncode == 0
    assert "--epsilon" in proc.stdout


def test_panel_run_quota_halt_exits_3(tmp_path, capsys, monkeypatch):
    import json
    from quorumcal.cli import main
    from quorumcal.judges import QuotaExhausted
    import quorumcal.panel as panel_mod
    gs = tmp_path / "gs.jsonl"
    gs.write_text(json.dumps({
        "task_id": "t1", "repo": "r", "label": "valid", "diff": "d",
        "provenance": {}}) + "\n")
    panels = tmp_path / "p.json"
    panels.write_text(json.dumps({"x": [
        {"judge_id": "codex-corr", "model": "gpt-5.6-sol",
         "lens": "correctness", "lineage": "codex"}]}))
    def exploding(spec, task):
        raise QuotaExhausted("codex quota: window exhausted")
    monkeypatch.setitem(panel_mod.JUDGE_FNS, "codex", exploding)
    rc = main(["panel", "run", "--goldset", str(gs), "--panels", str(panels),
               "--cache-dir", str(tmp_path / "cache")])
    assert rc == 3
    out = capsys.readouterr().out
    assert "QUOTA HALT" in out and "resume" in out.lower()


def _mini_calibration(tmp_path):
    """One-panel calibration fixture: goldset, panels, cache, report."""
    import json
    from quorumcal.judges import JudgeSpec
    from quorumcal.panel import cache_key
    gs = tmp_path / "gs.jsonl"
    tasks = [{"task_id": f"t{i}t{i}t{i}", "repo": "r", "label": "valid",
              "diff": "d", "provenance": {}} for i in (1, 2)]
    gs.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    panels = tmp_path / "p.json"
    pspecs = [{"judge_id": "a", "model": "m1", "lens": "correctness"},
              {"judge_id": "b", "model": "m1", "lens": "security"},
              {"judge_id": "c", "model": "m2", "lens": "correctness",
               "lineage": "codex"}]
    panels.write_text(json.dumps({"pan": pspecs}))
    cache = tmp_path / "cache"
    cache.mkdir()
    for t in tasks:
        for sp in pspecs:
            s = JudgeSpec(**sp)
            (cache / f"{cache_key(s, t['task_id'])}.json").write_text(
                json.dumps({"verdict": "endorse",
                            "model_reported": f"{sp['model']}-served"}))
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"delta": 0.1, "epsilon": 0.1, "panels": {"pan": {
        "n_effective": 2.4, "n_eff_ci": [2.0, 3.0], "rho_bar": 0.1,
        "e_delta": 0.0, "u_epsilon": 1.0, "q_min": 1, "q_max": 2,
        "feasible": True, "n_judges": 3,
        "per_judge_wrong_rate": [0.0, 0.0, 0.0],
        "per_judge_wrong_upper": [0.05, 0.05, 0.05]}}}))
    return gs, panels, cache, report


def test_profile_emit_check_and_monitor_roundtrip(tmp_path, capsys):
    import json
    from quorumcal.cli import main
    gs, panels, cache, report = _mini_calibration(tmp_path)
    out = tmp_path / "prof.json"
    rc = main(["profile", "emit", "--report", str(report), "--panels", str(panels),
               "--goldset", str(gs), "--cache-dir", str(cache), "--panel", "pan",
               "--out", str(out)])
    assert rc == 0 and out.exists()
    prof = json.loads(out.read_text())
    assert prof["panel"] == "pan"
    # claude-lineage observed models are NOT harvested (pre-fix cells carry
    # the ancillary-haiku recording artifact); spec models always whitelisted,
    # non-claude observed models harvested normally.
    assert "m1-served" not in prof["provenance"]["allowed_models"]
    assert "m2-served" in prof["provenance"]["allowed_models"]
    assert {"m1", "m2"} <= set(prof["provenance"]["allowed_models"])
    assert prof["baseline"]["n_tasks"] == 2

    assert main(["profile", "check", "--profile", str(out),
                 "--today", prof["emitted_at"]]) == 0
    assert main(["profile", "check", "--profile", str(out),
                 "--today", "2099-01-01"]) == 2

    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps({"verdicts": ["endorse", "endorse", "endorse"]}) + "\n")
    assert main(["monitor", "--profile", str(out), "--log", str(log)]) == 0
    surge = json.dumps({"verdicts": ["endorse", "reject", "endorse"]}) + "\n"
    log.write_text(surge * 50)
    assert main(["monitor", "--profile", str(out), "--log", str(log)]) == 5
    log.write_text(json.dumps({"verdicts": ["endorse", "endorse", "endorse"],
                               "models": ["rogue-model"]}) + "\n")
    assert main(["monitor", "--profile", str(out), "--log", str(log)]) == 4
