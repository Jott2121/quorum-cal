"""CUSUM drift monitor: is the live panel still behaving like the calibrated
one? Consumes verdict-log JSONL from real panel runs; alarms via non-zero exit
in the CLI. Launchd wiring is documented in docs/runtime-discipline.md, not
bundled (spec §4)."""
from __future__ import annotations

import json


def cusum(xs: list[int], p0: float, *, k: float | None = None,
          h: float = 4.0) -> dict:
    """One-sided upper CUSUM on 0/1 indicators. Alarm on sustained rate
    increase above baseline p0; k is the allowance (half the shift we care
    about), floored at 0.01 so a zero baseline still tolerates rare events."""
    if k is None:
        k = max(0.5 * p0, 0.01)
    s = 0.0
    alarm_index = None
    for i, x in enumerate(xs):
        s = max(0.0, s + x - (p0 + k))
        if alarm_index is None and s >= h:
            alarm_index = i
    return {"alarm": alarm_index is not None, "alarm_index": alarm_index,
            "final_stat": s}


def run_monitor(profile: dict, log_lines: list[str]) -> dict:
    allowed = set(profile["provenance"]["allowed_models"])
    disagree_xs, abstain_xs, unknown = [], [], []
    n = 0
    for line in log_lines:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        verdicts = rec["verdicts"]
        n += 1
        disagree_xs.append(1 if len(set(verdicts)) > 1 else 0)
        abstain_xs.append(1 if "abstain" in verdicts else 0)
        for m in rec.get("models") or []:
            if m not in allowed and m not in unknown:
                unknown.append(m)
    base = profile["baseline"]
    streams = {
        "disagreement": cusum(disagree_xs, base["disagreement_rate"]),
        "abstention": cusum(abstain_xs, base["abstain_rate"]),
    }
    return {"n": n, "streams": streams, "unknown_models": unknown,
            "alarm": any(s["alarm"] for s in streams.values()),
            "provenance_alarm": bool(unknown)}
