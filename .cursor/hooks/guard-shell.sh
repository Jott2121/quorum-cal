#!/usr/bin/env bash
# beforeShellExecution guard. Reads {"command": "...", "cwd": "..."} on stdin.
# Denies irreversible / publishing commands; asks on network fetches. Fails closed (hooks.json failClosed: true).
# hooks.json matches "rebase", not "git rebase": `git pull --rebase` does not
# contain the substring "git rebase", so a narrower matcher would never start
# this script. The rebase arm then denies any command containing "rebase".
# Force flags are their own arguments. `git push origin main --force` does not
# contain the contiguous text "push --force".
set -euo pipefail
input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("command",""))')"
deny() { printf '{"permission":"deny","user_message":"%s","agent_message":"%s Open a PR instead; a human will do this step."}\n' "$1" "$1"; exit 0; }
ask()  { printf '{"permission":"ask","user_message":"%s"}\n' "$1"; exit 0; }
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
