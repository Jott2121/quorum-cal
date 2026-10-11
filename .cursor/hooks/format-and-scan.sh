#!/usr/bin/env bash
# afterFileEdit (notification-only): format the edited Python file and warn on employer-data / secret patterns.
# It can't block the edit; CI's no-employer-data job is the real gate.
# Employer terms come from scripts/check_no_employer_data.py and the committed
# hash file, plus EMPLOYER_MARKERS when set. If that scan cannot run (missing
# script or hash file, bad regex), the hook warns: a scan that didn't run is not clean.
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
f="$(python3 -c 'import sys,json; print(json.load(sys.stdin).get("file_path",""))')"
[ -f "$f" ] || exit 0
case "$f" in *.py) command -v ruff >/dev/null && ruff format -q "$f" && ruff check -q --fix "$f" ;; esac
warn() {
  mkdir -p "$root/.cursor/hook-logs"
  echo "$(date -u +%FT%TZ) WARN $1 in $f" >> "$root/.cursor/hook-logs/warnings.log"
}
if ! python3 "$root/scripts/check_no_employer_data.py" --root "$root" --paths "$f" >/dev/null 2>&1; then
  warn "employer term (or employer scan could not run)"
fi
if ! python3 - "$f" <<'PY'
import re, sys
marker = re.compile(
    r"\bCUI\b|\bITAR\b|EXPORT CONTROLLED|"
    r"BEGIN (RSA|OPENSSH) PRIVATE KEY|xai-[A-Za-z0-9]{20,}",
    re.I,
)
for line in open(sys.argv[1], errors="replace"):
    if marker.search(line):
        sys.exit(1)
sys.exit(0)
PY
then
  warn "export-control/secret pattern"
fi
exit 0
