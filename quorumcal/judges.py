"""Judge adapters. One fresh isolated process per (judge, task) — session
reuse would fake correlation, which is the quantity under measurement."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass

from quorumcal.goldset import GoldTask

_INSTRUCTION = """You are reviewing a code change as an independent judge.
You have NO tools and NO repository access. Judge solely from the diff shown below.
Do not announce plans to investigate — you cannot. Reason briefly, then answer.
Reply with your reasoning, then END your reply with exactly one JSON object:
{"verdict": "endorse" | "reject" | "abstain", "rationale": "<one line>"}
endorse = the change is correct and safe to merge.
reject  = the change introduces a defect.
abstain = you cannot make a determination from the information given."""

LENS_PROMPTS = {
    "correctness": (
        "Judge ONLY functional correctness: does this change compute the right "
        "thing? Ignore style, security hardening, and test coverage.\n\n"
        + _INSTRUCTION),
    "security": (
        "Judge with a security-first eye: does this change introduce a defect "
        "or weaken an invariant an attacker or malformed input could exploit? "
        "A change with no security-relevant behavior change and no functional "
        "defect should be endorsed.\n\n" + _INSTRUCTION),
    "tests": (
        "Judge as a test engineer: would this change break the intended "
        "behavior a reasonable test suite pins down? Reject only if you can "
        "name the behavior it breaks.\n\n" + _INSTRUCTION),
}

_VALID_VERDICTS = {"endorse", "reject", "abstain"}

PROMPT_VERSION = "v2"   # provenance only — NEVER folded into cache_key


class QuotaExhausted(RuntimeError):
    """Plan quota / rate-limit window hit. The panel run halts cleanly;
    finished cells are cached, so re-running later resumes for free."""


_QUOTA_RE = re.compile(
    r"rate.?limit|quota|usage limit|too many requests|\b429\b|plan limit",
    re.IGNORECASE)

_CODEX_MODEL_RE = re.compile(r"^model:\s*(\S+)\s*$", re.MULTILINE)

_CODEX_BIN_FALLBACK = os.path.expanduser("~/.hermes/node/bin/codex")
_GROK_BIN_FALLBACK = os.path.expanduser("~/.local/bin/grok")


def _binpath(name: str, fallback: str) -> str:
    return shutil.which(name) or fallback


@dataclass(frozen=True)
class JudgeSpec:
    judge_id: str
    model: str
    lens: str
    lineage: str = "claude"


def build_prompt(spec: JudgeSpec, task: GoldTask) -> str:
    # NEVER include task.label or provenance — that is the answer key.
    return (f"{LENS_PROMPTS[spec.lens]}\n\n"
            f"Repository: {task.repo}\n"
            f"Unified diff of the change under review:\n"
            f"```diff\n{task.diff}\n```")


def parse_verdict(text: str) -> tuple[str, str]:
    text = text or ""
    decoder = json.JSONDecoder()
    best: tuple[str, str] | None = None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        v = obj.get("verdict")
        if v in _VALID_VERDICTS:
            best = (v, str(obj.get("rationale", "")))
    if best is not None:
        return best
    return "error", "no parseable verdict JSON in reply"


def claude_judge(spec: JudgeSpec, task: GoldTask,
                 *, run=subprocess.run, timeout: int = 300) -> dict:
    # Hardened and isolated: no tools, no MCP config, no inherited user
    # settings, no session persistence — a judge must never behave as a
    # full-tool bypassPermissions agent inheriting the caller's environment.
    cmd = ["claude", "-p", "--model", spec.model, "--output-format", "json",
          "--tools", "", "--strict-mcp-config", "--setting-sources", "",
          "--no-session-persistence"]
    record = {"task_id": task.task_id, "judge_id": spec.judge_id,
              "model_requested": spec.model, "model_reported": None,
              "verdict": "error", "rationale": "", "cost_usd": None,
              "raw_result": "", "prompt_version": PROMPT_VERSION}
    scratch_dir = tempfile.mkdtemp(prefix="qc-judge-")
    try:
        try:
            proc = run(cmd, input=build_prompt(spec, task),
                       capture_output=True, text=True, timeout=timeout,
                       cwd=scratch_dir)
        except subprocess.TimeoutExpired:
            record["rationale"] = f"claude -p timed out after {timeout}s"
            return record
        except OSError as exc:
            record["rationale"] = f"claude -p failed to launch: {exc}"
            return record
        if proc.returncode != 0:
            record["rationale"] = f"claude -p exit {proc.returncode}: {proc.stderr[:200]}"
            return record
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            record["rationale"] = "unparseable claude -p JSON envelope"
            return record
        env = None
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and item.get("type") == "result":
                    env = item
                    break
        elif isinstance(parsed, dict):
            env = parsed
        if env is None:
            record["rationale"] = "unrecognized claude -p envelope shape"
            return record
        if "model" in env:
            record["model_reported"] = env.get("model")
        else:
            # CAPTURED 2026-07-21: modelUsage lists the CLI's ancillary haiku
            # usage FIRST; next(iter()) mis-recorded it for 1621/1640 phase1/2
            # cells. Prefer the requested model when its usage proves it ran;
            # otherwise report the dominant entry so substitution stays visible.
            model_usage = env.get("modelUsage") or {}
            if spec.model in model_usage:
                record["model_reported"] = spec.model
            elif model_usage:
                record["model_reported"] = max(
                    model_usage,
                    key=lambda k: (model_usage[k] or {}).get("outputTokens") or 0)
        record["cost_usd"] = env.get("total_cost_usd")
        record["raw_result"] = env.get("result", "")
        verdict, rationale = parse_verdict(record["raw_result"])
        record["verdict"], record["rationale"] = verdict, rationale or record["rationale"]
        return record
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def codex_judge(spec: JudgeSpec, task: GoldTask,
                *, run=subprocess.run, timeout: int = 300,
                sleep=time.sleep) -> dict:
    """OpenAI lineage via `codex exec` on the ChatGPT plan. Plain mode, not
    --json: only the plain-mode stderr header reports the served model, and
    per-call model provenance is a spec requirement. Verdict text comes from
    the -o last-message file (guaranteed to be exactly the final message)."""
    record = {"task_id": task.task_id, "judge_id": spec.judge_id,
              "model_requested": spec.model, "model_reported": None,
              "verdict": "error", "rationale": "", "cost_usd": None,
              "raw_result": "", "prompt_version": PROMPT_VERSION}
    scratch_dir = tempfile.mkdtemp(prefix="qc-judge-")
    last = f"{scratch_dir}/last-message.txt"
    cmd = [_binpath("codex", _CODEX_BIN_FALLBACK), "exec",
           "--skip-git-repo-check", "--sandbox", "read-only",
           "--ephemeral", "--ignore-user-config", "--ignore-rules",
           "--color", "never", "-m", spec.model, "-o", last, "-"]
    try:
        for attempt in (0, 1):
            try:
                proc = run(cmd, input=build_prompt(spec, task),
                           capture_output=True, text=True, timeout=timeout,
                           cwd=scratch_dir)
            except subprocess.TimeoutExpired:
                record["rationale"] = f"codex exec timed out after {timeout}s"
                return record
            except OSError as exc:
                record["rationale"] = f"codex exec failed to launch: {exc}"
                return record
            if proc.returncode != 0:
                blob = f"{proc.stdout}\n{proc.stderr}"
                if _QUOTA_RE.search(blob):
                    if attempt == 0:
                        sleep(30)
                        continue
                    raise QuotaExhausted(
                        f"codex quota: {spec.judge_id}: {proc.stderr[:200]}")
                record["rationale"] = (
                    f"codex exec exit {proc.returncode}: {proc.stderr[:200]}")
                return record
            break
        m = _CODEX_MODEL_RE.search(proc.stderr or "")
        record["model_reported"] = m.group(1) if m else None
        try:
            with open(last, encoding="utf-8") as fh:
                record["raw_result"] = fh.read()
        except OSError:
            record["rationale"] = "codex wrote no last-message file"
            return record
        verdict, rationale = parse_verdict(record["raw_result"])
        record["verdict"] = verdict
        record["rationale"] = rationale or record["rationale"]
        return record
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def grok_judge(spec: JudgeSpec, task: GoldTask,
               *, run=subprocess.run, timeout: int = 300,
               sleep=time.sleep) -> dict:
    """xAI lineage via the Grok CLI single-turn headless mode. One JSON
    envelope on stdout; modelUsage key is the per-call served-model
    provenance; --max-turns 1 forbids tool round-trips outright."""
    record = {"task_id": task.task_id, "judge_id": spec.judge_id,
              "model_requested": spec.model, "model_reported": None,
              "verdict": "error", "rationale": "", "cost_usd": None,
              "raw_result": "", "prompt_version": PROMPT_VERSION}
    scratch_dir = tempfile.mkdtemp(prefix="qc-judge-")
    cmd = [_binpath("grok", _GROK_BIN_FALLBACK),
           "--single", build_prompt(spec, task),
           "--output-format", "json", "-m", spec.model,
           "--tools", "", "--no-memory", "--no-plan", "--no-subagents",
           "--disable-web-search", "--max-turns", "1"]
    try:
        for attempt in (0, 1):
            try:
                proc = run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=scratch_dir)
            except subprocess.TimeoutExpired:
                record["rationale"] = f"grok timed out after {timeout}s"
                return record
            except OSError as exc:
                record["rationale"] = f"grok failed to launch: {exc}"
                return record
            if proc.returncode != 0:
                blob = f"{proc.stdout}\n{proc.stderr}"
                if _QUOTA_RE.search(blob):
                    if attempt == 0:
                        sleep(30)
                        continue
                    raise QuotaExhausted(
                        f"grok quota: {spec.judge_id}: {proc.stderr[:200]}")
                record["rationale"] = (
                    f"grok exit {proc.returncode}: {proc.stderr[:200]}")
                return record
            break
        try:
            env = json.loads(proc.stdout)
        except json.JSONDecodeError:
            record["rationale"] = "unparseable grok JSON envelope"
            return record
        if not isinstance(env, dict):
            record["rationale"] = "unrecognized grok envelope shape"
            return record
        model_usage = env.get("modelUsage") or {}
        record["model_reported"] = next(iter(model_usage), None)
        record["cost_usd"] = env.get("total_cost_usd")
        record["raw_result"] = env.get("text", "")
        verdict, rationale = parse_verdict(record["raw_result"])
        record["verdict"] = verdict
        record["rationale"] = rationale or record["rationale"]
        return record
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
