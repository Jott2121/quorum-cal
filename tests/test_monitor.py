import json

import pytest
from quorumcal.monitor import cusum, run_monitor


def test_cusum_quiet_at_baseline():
    xs = [1, 0, 0, 0, 0] * 20                    # 20% — exactly baseline
    r = cusum(xs, 0.2, k=0.1, h=4.0)
    assert r["alarm"] is False and r["alarm_index"] is None


def test_cusum_alarms_on_sustained_shift():
    xs = [1] * 20                                # rate jumped to 100%
    r = cusum(xs, 0.2, k=0.1, h=4.0)
    assert r["alarm"] is True
    assert r["alarm_index"] == 5                 # ceil(4.0 / (1 - 0.3)) - 1
    assert r["final_stat"] >= 4.0


def test_cusum_hand_computed_sequence():
    r = cusum([1, 1, 0], 0.5, k=0.1, h=0.7)
    # S1 = 0.4, S2 = 0.8 -> alarm at index 1
    assert r["alarm"] is True and r["alarm_index"] == 1
    assert r["final_stat"] == pytest.approx(0.2)  # S3 = max(0, 0.8 - 0.6)


def test_cusum_default_k_guard_at_zero_baseline():
    r = cusum([0] * 50, 0.0, h=4.0)
    assert r["alarm"] is False                   # k floor 0.01 keeps S at 0


PROFILE = {"baseline": {"disagreement_rate": 0.2, "abstain_rate": 0.05},
           "provenance": {"allowed_models":
                          ["claude-sonnet-5", "gpt-5.6-sol", "grok-4.5-build"]}}


def _lines(rows):
    return [json.dumps(r) for r in rows]


def test_run_monitor_quiet():
    rows = [{"verdicts": ["endorse", "endorse", "endorse"]}] * 30
    r = run_monitor(PROFILE, _lines(rows))
    assert r["n"] == 30 and r["alarm"] is False and r["provenance_alarm"] is False


def test_run_monitor_alarms_on_disagreement_surge():
    rows = [{"verdicts": ["endorse", "reject", "endorse"]}] * 30
    r = run_monitor(PROFILE, _lines(rows))
    assert r["streams"]["disagreement"]["alarm"] is True
    assert r["alarm"] is True


def test_run_monitor_flags_unknown_model():
    rows = [{"verdicts": ["endorse", "endorse", "endorse"],
             "models": ["claude-sonnet-5", "gpt-6-turbo", "grok-4.5-build"]}]
    r = run_monitor(PROFILE, _lines(rows))
    assert r["provenance_alarm"] is True and "gpt-6-turbo" in r["unknown_models"]


def test_run_monitor_skips_blank_and_ignores_extra_fields():
    rows = [{"verdicts": ["endorse", "endorse", "endorse"], "ts": "x"}]
    r = run_monitor(PROFILE, _lines(rows) + ["", "   "])
    assert r["n"] == 1
