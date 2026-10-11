#!/usr/bin/env bash
# beforeShellExecution guard. Reads {"command": "...", "cwd": "..."} on stdin.
# Denies irreversible / publishing commands; asks on network fetches. Fails closed (hooks.json failClosed: true).
# The matcher includes `git pull` and `rebase`. Plain `git pull` is allowed.
# `git pull --rebase` reaches this script and the rebase arm denies it.
# A well-formed payload with an empty, blank, missing, or non-string command
# is denied. Invalid JSON exits non-zero so hooks.json failClosed blocks it.
# Force flags are their own arguments. `git push origin main --force` does not
# contain the contiguous text "push --force".
set -euo pipefail
input="$(cat)"
deny() { printf '{"permission":"deny","user_message":"%s","agent_message":"%s Open a PR instead; a human will do this step."}\n' "$1" "$1"; exit 0; }
ask()  { printf '{"permission":"ask","user_message":"%s"}\n' "$1"; exit 0; }
set +e
cmd="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    data = json.loads(sys.stdin.read())
except json.JSONDecodeError:
    sys.exit(2)
cmd = data.get("command") if isinstance(data, dict) else None
if not isinstance(cmd, str) or not cmd.strip():
    sys.exit(3)
sys.stdout.write(cmd)
')"
status=$?
set -e
if [[ "$status" -eq 3 ]]; then
  deny "Blocked: shell command was empty, blank, missing, or not a string."
fi
if [[ "$status" -ne 0 ]]; then
  exit "$status"
fi
# --force / --force-with-lease / a short cluster that includes f (-f, -uf, -fu).
# Branch names such as feature-fix do not match: the flag must be its own argument.
if [[ "$cmd" == *"git push"* ]] && [[ "$cmd" =~ (^|[[:space:]])(--force(--|$|[[:space:]=])|--force-with-lease(--|$|[[:space:]=])|-[A-Za-z]*f[A-Za-z]*(--|$|[[:space:]])) ]]; then
  deny "Force-push blocked by repo policy."
fi
case "$cmd" in
  *"push --force"*|*"push -f"*|*"--force-with-lease"*) deny "Force-push blocked by repo policy." ;;
  *"reset --hard"*|*"rebase"*)                        deny "History rewrite blocked by repo policy. This includes git pull --rebase." ;;
  *"git tag"*|*"twine upload"*|*"uv publish"*|*"gh release"*) deny "Releases/publishing are human-only." ;;
  *"rm -rf /"*|*"rm -rf ~"*|*'rm -rf $HOME'*)         deny "Destructive delete blocked." ;;
  *"curl"*"| sh"*|*"curl"*"| bash"*|*"wget"*"| sh"*)   deny "Pipe-to-shell blocked." ;;
  *"git push"*)                                       ask  "Agent wants to push a branch. Allow?" ;;
  *"curl"*|*"wget"*)                                  ask  "Agent wants network access: $cmd" ;;
esac
printf '{"permission":"allow"}\n'
