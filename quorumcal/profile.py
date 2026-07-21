"""Risk profiles: the machine-readable contract between a calibration run and
the consumers (fleet-mode, oracle-gate) that certify work with a panel."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from quorumcal.goldset import GoldTask
from quorumcal.judges import _INSTRUCTION, LENS_PROMPTS, PROMPT_VERSION, JudgeSpec
from quorumcal.panel import cache_key

PROFILE_VERSION = 1


def prompt_fingerprint() -> str:
    h = hashlib.sha256()
    h.update(PROMPT_VERSION.encode())
    h.update(_INSTRUCTION.encode())
    for lens in sorted(LENS_PROMPTS):
        h.update(lens.encode())
        h.update(LENS_PROMPTS[lens].encode())
    return h.hexdigest()


def build_profile(report: dict, panels: dict[str, list[JudgeSpec]],
                  panel_name: str, baseline: dict, *, domain: str,
                  emitted_at: str, q: int | None = None,
                  expiry_days: int = 30,
                  observed_models: dict[str, list[str]] | None = None) -> dict:
    if panel_name not in report["panels"] or panel_name not in panels:
        raise ValueError(f"unknown panel {panel_name!r}")
    rp = report["panels"][panel_name]
    q_min, q_max = rp["q_min"], rp["q_max"]
    chosen = q_min if q is None else q
    if not (q_min <= chosen <= q_max):
        raise ValueError(f"q={chosen} outside feasible window [{q_min},{q_max}]")
    specs = panels[panel_name]
    observed_models = observed_models or {}
    allowed = {s.model for s in specs}
    for models in observed_models.values():
        allowed.update(models)
    expires = date.fromisoformat(emitted_at) + timedelta(days=expiry_days)
    return {
        "profile_version": PROFILE_VERSION,
        "panel": panel_name,
        "domain": domain,
        "committee": [dataclasses.asdict(s) for s in specs],
        "q": chosen,
        "q_window": [q_min, q_max],
        "delta": report["delta"],
        "epsilon": report["epsilon"],
        "budgets": {"e_delta": rp["e_delta"], "u_epsilon": rp["u_epsilon"]},
        "n_effective": rp["n_effective"],
        "n_eff_ci": rp["n_eff_ci"],
        "rho_bar": rp["rho_bar"],
        "per_judge_wrong_rate": rp["per_judge_wrong_rate"],
        "per_judge_wrong_upper": rp["per_judge_wrong_upper"],
        "baseline": baseline,
        "provenance": {
            "prompt_fingerprint": prompt_fingerprint(),
            "prompt_version": PROMPT_VERSION,
            "allowed_models": sorted(allowed),
            "observed_models": observed_models,
            "tool_schemas": "none",      # judges are toolless by construction
        },
        "emitted_at": emitted_at,
        "expires_at": expires.isoformat(),
    }


def check_profile(profile: dict, *, today: str,
                  current_prompt_fingerprint: str | None = None) -> dict:
    reasons = []
    fp_now = (current_prompt_fingerprint
              if current_prompt_fingerprint is not None else prompt_fingerprint())
    fp_cal = profile["provenance"]["prompt_fingerprint"]
    drifted = fp_now != fp_cal
    if drifted:
        reasons.append(
            f"prompt fingerprint drifted (calibrated {fp_cal[:12]}…, "
            f"current {fp_now[:12]}…) — recalibrate before certifying")
    expired = date.fromisoformat(today) > date.fromisoformat(profile["expires_at"])
    if expired:
        reasons.append(f"profile expired {profile['expires_at']} (today {today})")
    if drifted:
        status = "provenance-drifted"      # drift forces recalibration regardless
    elif expired:
        status = "expired"
    else:
        status = "valid"
    return {"status": status, "reasons": reasons}


def panel_baseline(tasks: list[GoldTask], specs: list[JudgeSpec],
                   cache_dir) -> dict:
    # Both rates are DECISION-level (per task), matching the monitor's
    # per-decision indicators exactly — mixing units (cell-level abstention
    # vs decision-level indicator) guarantees a false CUSUM alarm.
    disagree = abstain = 0
    for t in tasks:
        verdicts = []
        for s in specs:
            cell = Path(cache_dir) / f"{cache_key(s, t.task_id)}.json"
            verdicts.append(json.loads(cell.read_text(encoding="utf-8"))["verdict"])
        if "abstain" in verdicts:
            abstain += 1
        if len(set(verdicts)) > 1:
            disagree += 1
    return {"disagreement_rate": disagree / len(tasks),
            "abstain_rate": abstain / len(tasks),
            "n_tasks": len(tasks)}
