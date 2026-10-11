#!/usr/bin/env python3
"""Check published quorum-cal numbers against committed artifacts.

Compares the README and WRITEUP headline tables to runs/phase2c/report.json.
Does not call judge CLIs and does not rebuild the report from the public
goldset (that file is filtered; the aggregates include withheld tasks).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

from quorumcal.metrics import wilson_upper
from quorumcal.profile import prompt_fingerprint

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "runs" / "phase2c" / "report.json"
REPORT_V1_PATH = ROOT / "runs" / "phase2c" / "report-v1.0.0.json"
GOLDSET_PATH = ROOT / "runs" / "phase2c" / "goldset.jsonl"
README_PATH = ROOT / "README.md"
WRITEUP_PATH = ROOT / "WRITEUP.md"

README_PANELS = {
    "identical (one model, one prompt)": "identical-sonnet",
    "diverse lenses (one model, 3 prompts)": "diverse-lens-sonnet",
    "three lineages (Claude + OpenAI + xAI)": "three-lineage",
}
WRITEUP_PANELS = (
    "identical-sonnet",
    "diverse-lens-sonnet",
    "mixed-tier",
    "claude-plus-codex",
    "claude-plus-grok",
    "three-lineage",
)
PROFILES = {
    "three-lineage": ROOT / "profiles" / "three-lineage.json",
    "diverse-lens-sonnet": ROOT / "profiles" / "diverse-lens-sonnet.json",
}
PUBLISHED_TEST_COUNT = 132

ROW = re.compile(
    r"^\|\s*(?P<label>[^|]+?)\s*\|\s*\**(?P<neff>\d+\.\d+)\**\s*\|"
    r"\s*\[(?P<lo>\d+\.\d+),\s*(?P<hi>\d+\.\d+)\]\s*\|"
    r"\s*(?P<rho>\d+\.\d+)\s*\|\s*(?P<window>\[[^\]]+\]|infeasible)\s*\|\s*$",
    re.MULTILINE,
)


def fail(errors: list[str]) -> None:
    for err in errors:
        print(f"FAIL: {err}", file=sys.stderr)
    sys.exit(1)


def section(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        raise ValueError(f"missing section start: {start!r}")
    j = text.find(end, i + len(start))
    if j < 0:
        raise ValueError(f"missing section end: {end!r}")
    return text[i:j]


def published_row(panel: dict) -> dict[str, str]:
    lo, hi = panel["n_eff_ci"]
    if panel["feasible"]:
        window = f"[{panel['q_min']}, {panel['q_max']}]"
    else:
        window = "infeasible"
    return {
        "neff": f"{panel['n_effective']:.2f}",
        "lo": f"{lo:.2f}",
        "hi": f"{hi:.2f}",
        "rho": f"{panel['rho_bar']:.2f}",
        "window": window,
    }


def parse_rows(text: str) -> dict[str, re.Match[str]]:
    return {m.group("label"): m for m in ROW.finditer(text)}


def check_table(
    errors: list[str],
    where: str,
    rows: dict[str, re.Match[str]],
    report: dict,
    labels: dict[str, str],
) -> None:
    for label, key in labels.items():
        match = rows.get(label)
        if match is None:
            errors.append(f"{where}: missing row {label!r}")
            continue
        expected = published_row(report["panels"][key])
        got = {name: match.group(name) for name in expected}
        if got != expected:
            errors.append(
                f"{where}: {label} published {got} != report {key} rounded {expected}"
            )


def count_tests() -> int:
    total = 0
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                total += 1
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef) and sub.name.startswith(
                        "test_"
                    ):
                        total += 1
    return total


def main() -> None:
    errors: list[str] = []
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    previous = json.loads(REPORT_V1_PATH.read_text(encoding="utf-8"))
    readme = README_PATH.read_text(encoding="utf-8")
    writeup = WRITEUP_PATH.read_text(encoding="utf-8")

    gold = report["goldset"]
    if (gold["n_tasks"], gold["n_invalid"], gold["n_valid"]) != (180, 99, 81):
        errors.append(f"report goldset counts changed: {gold}")
    public_rows = [
        line
        for line in GOLDSET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not public_rows or len(public_rows) >= gold["n_tasks"]:
        errors.append(
            "public phase2c goldset should be a non-empty filtered subset of "
            f"the {gold['n_tasks']}-task aggregate, got {len(public_rows)} lines"
        )

    try:
        readme_rows = parse_rows(
            section(readme, "## The headline", "## What's in the box")
        )
    except ValueError as exc:
        errors.append(f"README: {exc}")
        readme_rows = {}
    try:
        writeup_rows = parse_rows(section(writeup, "**Act IV", "CIs overlap heavily"))
    except ValueError as exc:
        errors.append(f"WRITEUP: {exc}")
        writeup_rows = {}
    check_table(errors, "README", readme_rows, report, README_PANELS)
    check_table(errors, "WRITEUP", writeup_rows, report, {k: k for k in WRITEUP_PANELS})

    if "132 tests" not in readme or "132 tests" not in writeup:
        errors.append("README and WRITEUP must keep the published '132 tests' count")
    found = count_tests()
    if found != PUBLISHED_TEST_COUNT:
        errors.append(
            f"test function count is {found}, published suite is {PUBLISHED_TEST_COUNT}"
        )

    # 0 shared false endorsements / 99 bugs, 95% Wilson upper bound, published as ≈3%.
    bound = wilson_upper(0, 99, confidence=0.95)
    if round(bound * 100) != 3:
        errors.append(f"95% Wilson upper bound on 0/99 is {bound:.4f}, expected ≈3%")
    if "≈3%" not in writeup and "~3%" not in writeup:
        errors.append("WRITEUP no longer states the ≈3% / ~3% shared-event bound")

    old_ident = previous["panels"]["identical-sonnet"]
    new_ident = report["panels"]["identical-sonnet"]
    if old_ident["feasible"] is not True or new_ident["feasible"] is not False:
        errors.append(
            "v1.0.0 identical-sonnet must stay feasible and the corrected "
            "report must stay infeasible"
        )
    if old_ident["n_effective"] != new_ident["n_effective"]:
        errors.append(
            "identical-sonnet N_eff drifted between v1.0.0 and the corrected report"
        )

    fingerprint = prompt_fingerprint()
    for name, path in PROFILES.items():
        profile = json.loads(path.read_text(encoding="utf-8"))
        panel = report["panels"][name]
        if profile["panel"] != name:
            errors.append(f"{path.name}: panel name {profile['panel']!r}")
        for field in ("n_effective", "n_eff_ci", "rho_bar", "e_delta"):
            if field == "e_delta":
                got = profile["budgets"]["e_delta"]
                expected = panel["e_delta"]
            else:
                got = profile[field]
                expected = panel[field]
            if got != expected:
                errors.append(f"{path.name}: {field} {got} != report {expected}")
        if profile["budgets"]["u_epsilon"] != panel["u_epsilon"]:
            errors.append(f"{path.name}: u_epsilon drifted from the report")
        if profile["q_window"] != [panel["q_min"], panel["q_max"]]:
            errors.append(f"{path.name}: q_window {profile['q_window']} != report")
        q_min, q_max = panel["q_min"], panel["q_max"]
        if not q_min <= profile["q"] <= q_max:
            errors.append(f"{path.name}: q={profile['q']} outside [{q_min}, {q_max}]")
        if profile["provenance"]["prompt_fingerprint"] != fingerprint:
            errors.append(
                f"{path.name}: prompt fingerprint drifted from quorumcal.judges "
                "(recalibrate; do not edit the profile in place)"
            )

    if errors:
        fail(errors)
    print(
        "receipts ok: README + WRITEUP match runs/phase2c/report.json; "
        f"{found} tests; public goldset {len(public_rows)}/{gold['n_tasks']} lines"
    )


if __name__ == "__main__":
    main()
