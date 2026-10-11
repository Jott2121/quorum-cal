#!/usr/bin/env bash
# afterFileEdit (notification-only): format the edited Python file and warn on employer-data / secret patterns.
# It can't block the edit; CI's no-employer-data job is the real gate.
# A line that is only the author's public GitHub bio is not a warning.
set -uo pipefail
f="$(python3 -c 'import sys,json; print(json.load(sys.stdin).get("file_path",""))')"
[ -f "$f" ] || exit 0
case "$f" in *.py) command -v ruff >/dev/null && ruff format -q "$f" && ruff check -q --fix "$f" ;; esac
if ! python3 - "$f" <<'PY'
import re, sys
marker = re.compile(
    r"lockheed|\blmco\b|\bCUI\b|\bITAR\b|EXPORT CONTROLLED|"
    r"BEGIN (RSA|OPENSSH) PRIVATE KEY|xai-[A-Za-z0-9]{20,}",
    re.I,
)
bio = re.compile(r"AI Foundations Lead at Lockheed Martin", re.I)
for line in open(sys.argv[1], errors="replace"):
    if not marker.search(line):
        continue
    rest = bio.sub("", line)
    if marker.search(rest) or not bio.search(line):
        sys.exit(1)
sys.exit(0)
PY
then
  mkdir -p .cursor/hook-logs
  echo "$(date -u +%FT%TZ) WARN employer/secret pattern in $f" >> .cursor/hook-logs/warnings.log
fi
exit 0
