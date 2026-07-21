# Runtime discipline — consuming quorum-cal at certify time

Phase 3 turns the calibration into three live guardrails: a **risk profile** a
consumer checks before trusting a panel, a **CUSUM monitor** watching live
verdict logs for drift, and **provenance triggers** that force recalibration
when the prompt or served models change.

## Profiles

Live in `profiles/` (committed). Emitted from a calibration run:

```bash
python3 -m quorumcal.cli profile emit \
  --report runs/phase2c/report.json --panels runs/phase2c/panels.json \
  --goldset runs/phase2c/goldset.jsonl --cache-dir runs/phase2c/cache \
  --panel three-lineage --out profiles/three-lineage.json
```

Fields: committee spec, chosen q (default = feasible-window minimum; `--q`
must stay inside `[q_min, q_max]` — out of window is an error, never a clamp),
delta/epsilon, budgets (e_delta, u_epsilon), N_eff + CI, decision-level
baseline rates (disagreement, abstention), prompt fingerprint,
served-model whitelist, `tool_schemas: "none"` (judges are toolless by
construction), 30-day expiry.

Known artifact (2026-07-21): claude cells recorded before the provenance fix
carry an ancillary-haiku `model_reported` — `profile emit` does NOT harvest
observed models from claude-lineage judges until the next full recalibration
runs under the fixed adapter (spec models remain whitelisted).

## The consumer preflight (fleet-mode, oracle-gate, anything that certifies)

```bash
python3 -m quorumcal.cli profile check --profile ~/quorum-cal/profiles/diverse-lens-sonnet.json \
  || { echo "panel profile not valid — recalibrate before certifying"; exit 1; }
```

## Exit-code contract

| command | 0 | 2 | 4 | 5 | 1 |
|---|---|---|---|---|---|
| `profile check` | valid | expired | provenance-drifted | — | usage/IO |
| `monitor` | quiet | — | provenance alarm (unknown served model) | CUSUM drift alarm | usage/IO |

## Verdict-log format (what consumers should log per panel decision)

One JSON object per line:

```json
{"verdicts": ["endorse", "reject", "abstain"], "models": ["claude-sonnet-5", "gpt-5.6-sol", "grok-4.5-build"]}
```

`models` is optional but enables served-model drift detection. Extra fields
(timestamps, subject ids) are ignored. **Logs must be chronological** — the
monitor is a sequential test; feeding it stratified or sorted batches makes
clustering look like drift (that is a feature against real regime shifts, a
false alarm on artificially ordered input).

## Monitoring

```bash
python3 -m quorumcal.cli monitor \
  --profile ~/quorum-cal/profiles/three-lineage.json \
  --log ~/logs/panel-verdicts.jsonl
```

One-sided CUSUM per stream (disagreement, abstention) against the calibrated
decision-level baselines; allowance k = max(0.5*p0, 0.01), threshold h = 4.0.
Non-zero exit + JSON on stdout is the whole alerting interface.

## Recalibration triggers (change-triggered, spec §4)

- `profile check` exits 4 (prompt fingerprint changed) → re-run
  `panel run` + `report` + `profile emit`. The judgment cache makes this
  incremental: only genuinely new (judge, task) cells bill quota.
- `monitor` exits 4 (unknown served model) → same, and update the committee
  spec if the model change is intentional.
- `profile check` exits 2 (30-day expiry) → same recipe; expiry exists so a
  drifting world cannot be certified against stale numbers forever.

## Launchd wiring (documented, not bundled)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.jeff.quorumcal.monitor</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-c</string>
    <string>cd ~/quorum-cal && python3 -m quorumcal.cli monitor --profile profiles/three-lineage.json --log ~/logs/panel-verdicts.jsonl || osascript -e 'display notification "quorum-cal drift alarm" with title "quorum-cal"'</string>
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer>
  </dict>
</dict></plist>
```

Swap the `osascript` for a Telegram send (the fleet-health pattern) if you
want it on the phone.
