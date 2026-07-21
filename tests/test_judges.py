import json
import subprocess
from pathlib import Path

import pytest
from quorumcal.goldset import GoldTask
from quorumcal.judges import (JudgeSpec, LENS_PROMPTS, build_prompt,
                              QuotaExhausted, claude_judge, codex_judge,
                              grok_judge, parse_verdict)

TASK = GoldTask(task_id="abc123def456", repo="demo", label="invalid",
                diff="--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a + b\n+a - b\n",
                provenance={"kind": "mutant", "ref": "m", "seed": 7})
SPEC = JudgeSpec(judge_id="sonnet-corr-1", model="claude-sonnet-5",
                 lens="correctness")


def test_prompt_contains_diff_never_label():
    p = build_prompt(SPEC, TASK)
    assert TASK.diff in p
    assert "invalid" not in p          # the label must NEVER leak to the judge
    assert "endorse" in p and "reject" in p and "abstain" in p
    assert "NO tools" in p


def test_all_lenses_have_prompts():
    assert set(LENS_PROMPTS) == {"correctness", "security", "tests"}


def test_parse_verdict_happy_path():
    v, r = parse_verdict('prose... {"verdict": "reject", "rationale": "sign flip"}')
    assert (v, r) == ("reject", "sign flip")


def test_parse_verdict_takes_last_json_object():
    text = '{"verdict": "endorse", "rationale": "no"} then {"verdict": "reject", "rationale": "yes"}'
    assert parse_verdict(text)[0] == "reject"


def test_parse_verdict_garbage_is_error():
    v, r = parse_verdict("I think it looks fine!")
    assert v == "error"


def test_parse_verdict_bad_verdict_value_is_error():
    v, _ = parse_verdict('{"verdict": "ship-it", "rationale": "x"}')
    assert v == "error"


def test_parse_verdict_rationale_with_literal_brace():
    v, r = parse_verdict(
        '{"verdict": "reject", "rationale": "returns {} instead of None"}')
    assert (v, r) == ("reject", "returns {} instead of None")


def test_parse_verdict_nested_json_in_prose():
    text = ('The change looks fine but note the config example '
            '{"example": {"nested": true}} is unrelated. '
            '{"verdict": "endorse", "rationale": "no functional change"}')
    v, r = parse_verdict(text)
    assert (v, r) == ("endorse", "no functional change")


class _P:
    def __init__(self, stdout, rc=0):
        self.stdout, self.stderr, self.returncode = stdout, "", rc


def test_claude_judge_fresh_session_and_record():
    seen = {}
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["kw"] = kw
        env = {"result": '{"verdict": "reject", "rationale": "bug"}',
               "total_cost_usd": 0.0123, "model": "claude-sonnet-5-20260401"}
        return _P(json.dumps(env))
    rec = claude_judge(SPEC, TASK, run=fake_run)
    assert rec["verdict"] == "reject"
    assert rec["cost_usd"] == 0.0123
    assert rec["model_reported"] == "claude-sonnet-5-20260401"
    assert rec["task_id"] == TASK.task_id and rec["judge_id"] == SPEC.judge_id
    for forbidden in ("--resume", "--continue", "--session-id"):
        assert forbidden not in seen["cmd"]
    assert seen["cmd"][:2] == ["claude", "-p"]


def test_claude_judge_cmd_is_hardened_and_sandboxed():
    seen = {}
    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["kw"] = kw
        env = {"result": '{"verdict": "reject", "rationale": "bug"}',
               "total_cost_usd": 0.0123, "model": "claude-sonnet-5-20260401"}
        return _P(json.dumps(env))
    claude_judge(SPEC, TASK, run=fake_run)
    cmd = seen["cmd"]
    assert cmd[:2] == ["claude", "-p"]
    for forbidden in ("--resume", "--continue", "--session-id"):
        assert forbidden not in cmd
    assert "--tools" in cmd
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in cmd
    assert "--setting-sources" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert "--no-session-persistence" in cmd
    cwd = seen["kw"].get("cwd")
    assert cwd is not None
    repo_dir = str(Path(__file__).resolve().parents[1])
    assert not str(cwd).startswith(repo_dir)


def test_claude_judge_process_failure_is_error_verdict():
    rec = claude_judge(SPEC, TASK, run=lambda cmd, **kw: _P("boom", rc=1))
    assert rec["verdict"] == "error"


def test_claude_judge_bad_envelope_is_error_verdict():
    rec = claude_judge(SPEC, TASK, run=lambda cmd, **kw: _P("not json"))
    assert rec["verdict"] == "error"


def test_claude_judge_launch_failure_is_error_verdict():
    def fake_run(cmd, **kw):
        raise FileNotFoundError("claude")
    rec = claude_judge(SPEC, TASK, run=fake_run)
    assert rec["verdict"] == "error"
    assert "claude -p failed to launch" in rec["rationale"]


def test_claude_judge_timeout_is_error_verdict():
    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=300)
    rec = claude_judge(SPEC, TASK, run=fake_run)
    assert rec["verdict"] == "error"
    assert "timed out" in rec["rationale"]


def test_claude_judge_array_envelope_with_result_element():
    # real `claude -p --output-format json` output can be a JSON array of
    # stream messages when the user's settings enable streaming envelopes.
    array_env = [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": '{"verdict": "reject", "rationale": "bug"}',
         "total_cost_usd": 0.05, "model": "claude-sonnet-5-20260401"},
    ]
    rec = claude_judge(SPEC, TASK,
                       run=lambda cmd, **kw: _P(json.dumps(array_env)))
    assert rec["verdict"] == "reject"
    assert rec["rationale"] == "bug"
    assert rec["cost_usd"] == 0.05
    assert rec["model_reported"] == "claude-sonnet-5-20260401"


def test_claude_judge_array_envelope_with_no_result_element_is_error():
    array_env = [{"type": "system", "subtype": "init"},
                {"type": "assistant", "message": {"content": []}}]
    rec = claude_judge(SPEC, TASK,
                       run=lambda cmd, **kw: _P(json.dumps(array_env)))
    assert rec["verdict"] == "error"
    assert "unrecognized claude -p envelope shape" in rec["rationale"]


def test_claude_judge_model_reported_falls_back_to_model_usage_key():
    # real result envelopes have no top-level "model" key — the model string
    # is the key of the "modelUsage" object.
    env = {"result": '{"verdict": "endorse", "rationale": "fine"}',
          "total_cost_usd": 0.01,
          "modelUsage": {"claude-sonnet-5-2": {"tokens": 123}}}
    rec = claude_judge(SPEC, TASK, run=lambda cmd, **kw: _P(json.dumps(env)))
    assert rec["model_reported"] == "claude-sonnet-5-2"


def test_judgespec_lineage_defaults_to_claude():
    assert SPEC.lineage == "claude"


def test_claude_record_carries_prompt_version():
    def fake_run(cmd, **kw):
        env = {"result": '{"verdict": "reject", "rationale": "bug"}',
               "total_cost_usd": 0.01, "model": "claude-sonnet-5-20260401"}
        return _P(json.dumps(env))
    rec = claude_judge(SPEC, TASK, run=fake_run)
    assert rec["prompt_version"] == "v2"


FIXTURES = Path(__file__).parent / "fixtures"

CODEX_SPEC = JudgeSpec(judge_id="codex-corr", model="gpt-5.6-sol",
                       lens="correctness", lineage="codex")


class _P2:
    def __init__(self, stdout="", stderr="", rc=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, rc


def _codex_fake_run(seen):
    stderr = (FIXTURES / "codex-stderr.txt").read_text()
    last = (FIXTURES / "codex-last-message.txt").read_text()
    def fake(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_text(last)              # codex writes the -o file itself
        return _P2(stdout=last, stderr=stderr)
    return fake


def test_codex_judge_parses_captured_envelope():
    seen = {}
    rec = codex_judge(CODEX_SPEC, TASK, run=_codex_fake_run(seen))
    assert rec["verdict"] == "reject"
    assert rec["model_reported"] == "gpt-5.6-sol"     # from the stderr header
    assert rec["model_requested"] == "gpt-5.6-sol"
    assert rec["cost_usd"] is None                    # plan-billed
    assert rec["prompt_version"] == "v2"


def test_codex_cmd_is_hardened():
    seen = {}
    codex_judge(CODEX_SPEC, TASK, run=_codex_fake_run(seen))
    cmd, kw = seen["cmd"], seen["kw"]
    assert cmd[1] == "exec"
    for flag in ("--skip-git-repo-check", "--ephemeral",
                 "--ignore-user-config", "--ignore-rules"):
        assert flag in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert cmd[cmd.index("-m") + 1] == "gpt-5.6-sol"
    assert cmd[-1] == "-"                 # prompt via stdin, never argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
    prompt = kw["input"]
    assert TASK.diff in prompt and "invalid" not in prompt
    cwd = kw["cwd"]
    repo_dir = str(Path(__file__).resolve().parents[1])
    assert cwd is not None and not str(cwd).startswith(repo_dir)


def test_codex_missing_last_message_is_error():
    def fake(cmd, **kw):
        return _P2(stdout="", stderr="model: gpt-5.6-sol\n")   # no -o write
    rec = codex_judge(CODEX_SPEC, TASK, run=fake)
    assert rec["verdict"] == "error"


def test_codex_nonzero_exit_is_error():
    rec = codex_judge(CODEX_SPEC, TASK,
                      run=lambda cmd, **kw: _P2(stderr="boom", rc=1))
    assert rec["verdict"] == "error"


GROK_SPEC = JudgeSpec(judge_id="grok-corr", model="grok-4.5",
                      lens="correctness", lineage="grok")


def test_grok_judge_parses_captured_envelope():
    seen = {}
    env = (FIXTURES / "grok-envelope.json").read_text()
    def fake(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return _P2(stdout=env)
    rec = grok_judge(GROK_SPEC, TASK, run=fake)
    assert rec["verdict"] == "reject"
    assert rec["model_reported"] == "grok-4.5-build"   # modelUsage key
    assert rec["cost_usd"] == pytest.approx(0.0282352)
    assert rec["prompt_version"] == "v2"


def test_grok_cmd_is_hardened():
    seen = {}
    env = (FIXTURES / "grok-envelope.json").read_text()
    def fake(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return _P2(stdout=env)
    grok_judge(GROK_SPEC, TASK, run=fake)
    cmd, kw = seen["cmd"], seen["kw"]
    assert "--single" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("-m") + 1] == "grok-4.5"
    for flag in ("--no-memory", "--no-plan", "--no-subagents",
                 "--disable-web-search"):
        assert flag in cmd
    assert cmd[cmd.index("--max-turns") + 1] == "1"
    for forbidden in ("--resume", "--continue", "--always-approve",
                      "--permission-mode"):
        assert forbidden not in cmd
    prompt = cmd[cmd.index("--single") + 1]
    assert TASK.diff in prompt and "invalid" not in prompt
    cwd = kw["cwd"]
    repo_dir = str(Path(__file__).resolve().parents[1])
    assert cwd is not None and not str(cwd).startswith(repo_dir)


def test_grok_bad_json_is_error():
    rec = grok_judge(GROK_SPEC, TASK,
                     run=lambda cmd, **kw: _P2(stdout="not json"))
    assert rec["verdict"] == "error"


def test_grok_nonzero_exit_is_error():
    rec = grok_judge(GROK_SPEC, TASK,
                     run=lambda cmd, **kw: _P2(stderr="boom", rc=1))
    assert rec["verdict"] == "error"


def test_codex_quota_backs_off_once_then_raises():
    slept, calls = [], []
    def fake(cmd, **kw):
        calls.append(1)
        return _P2(stderr="429 Too Many Requests: usage limit reached", rc=1)
    with pytest.raises(QuotaExhausted):
        codex_judge(CODEX_SPEC, TASK, run=fake, sleep=slept.append)
    assert len(calls) == 2 and slept == [30]     # one backoff, then halt


def test_grok_quota_backs_off_once_then_raises():
    slept, calls = [], []
    def fake(cmd, **kw):
        calls.append(1)
        return _P2(stderr="rate limit exceeded", rc=1)
    with pytest.raises(QuotaExhausted):
        grok_judge(GROK_SPEC, TASK, run=fake, sleep=slept.append)
    assert len(calls) == 2 and slept == [30]


def test_codex_quota_recovers_after_one_backoff():
    seen = {"n": 0}
    stderr = (FIXTURES / "codex-stderr.txt").read_text()
    last = (FIXTURES / "codex-last-message.txt").read_text()
    def fake(cmd, **kw):
        seen["n"] += 1
        if seen["n"] == 1:
            return _P2(stderr="quota exceeded", rc=1)
        Path(cmd[cmd.index("-o") + 1]).write_text(last)
        return _P2(stdout=last, stderr=stderr)
    rec = codex_judge(CODEX_SPEC, TASK, run=fake, sleep=lambda s: None)
    assert rec["verdict"] == "reject"


def test_claude_model_provenance_prefers_requested_over_ancillary():
    # CAPTURED 2026-07-21: claude -p envelopes have no top-level "model";
    # modelUsage lists ancillary haiku FIRST. next(iter()) recorded haiku for
    # 1621/1640 phase1/2 cells — the fix prefers the requested model when its
    # usage proves it ran, else falls back to the max-outputTokens entry.
    env = json.loads((FIXTURES / "claude-envelope-multimodel.json").read_text())
    body = env if isinstance(env, dict) else None
    assert body is not None and "modelUsage" in body
    body = dict(body)
    body["result"] = '{"verdict": "reject", "rationale": "x"}'
    rec = claude_judge(SPEC, TASK, run=lambda cmd, **kw: _P(json.dumps(body)))
    assert rec["model_reported"] == "claude-sonnet-5"     # not the haiku entry


def test_claude_model_provenance_substitution_stays_visible():
    body = {"result": '{"verdict": "reject", "rationale": "x"}',
            "modelUsage": {
                "claude-haiku-4-5-20251001": {"outputTokens": 12},
                "claude-sonnet-5-20990101": {"outputTokens": 180}}}
    rec = claude_judge(SPEC, TASK, run=lambda cmd, **kw: _P(json.dumps(body)))
    # requested claude-sonnet-5 absent -> report the dominant real model,
    # so a substitution differs from model_requested and drift is visible
    assert rec["model_reported"] == "claude-sonnet-5-20990101"
