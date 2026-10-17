#!/usr/bin/env bash
# Link every skill in ./skills into the opencode (and optionally Claude Code) skill folders.
# Re-runnable: existing links are refreshed; a real directory with the same name is left
# alone and reported, never overwritten.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGETS=("${HOME}/.config/opencode/skills")
if [[ "${1:-}" == "--claude" ]]; then
  TARGETS+=("${HOME}/.claude/skills")
fi

for target in "${TARGETS[@]}"; do
  mkdir -p "${target}"
  for skill in "${KIT}"/skills/*/; do
    name="$(basename "${skill}")"
    link="${target}/${name}"
    if [[ -e "${link}" && ! -L "${link}" ]]; then
      echo "skip   ${link} exists and is not a link; move it away and re-run"
      continue
    fi
    ln -sfn "${KIT}/skills/${name}" "${link}"
    echo "linked ${link} -> ${KIT}/skills/${name}"
  done
done
