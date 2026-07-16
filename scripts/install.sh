#!/usr/bin/env bash
# Thin installer for Claude Code: symlink the skills and hooks into ~/.claude (so the live files
# ARE the repo files — edits here are immediately live, nothing to re-copy), then idempotently
# register the four guards in ~/.claude/settings.json (merged in only if missing; every other
# setting preserved — settings.json carries machine/preference bits, so it is never symlinked).
#
# Usage:
#   scripts/install.sh              # install everything into ~/.claude
#   scripts/install.sh <skill>...   # symlink only the named skill(s); skip hooks/settings
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$HOME/.claude/skills"
HOOKS_DIR="$HOME/.claude/hooks"

link() { # link <target> <linkname>
  local target=$1 linkname=$2
  if [[ -L $linkname && $(readlink "$linkname") == "$target" ]]; then
    echo "ok      $linkname"
  elif [[ -e $linkname && ! -L $linkname ]]; then
    echo "SKIP    $linkname exists and is not a symlink — resolve by hand" >&2
  else
    ln -sfn "$target" "$linkname"
    echo "linked  $linkname -> $target"
  fi
}

# --- skills ---------------------------------------------------------------
mkdir -p "$SKILLS_DIR"
if [[ $# -gt 0 ]]; then
  names=("$@")
else
  names=()
  shopt -s nullglob  # an empty skills/ must yield no iterations, not the literal '*/'
  for d in "$REPO"/skills/*/; do names+=("$(basename "$d")"); done
  shopt -u nullglob
fi
for name in "${names[@]}"; do
  src="$REPO/skills/$name"
  [[ -f "$src/SKILL.md" ]] || { echo "SKIP    no such skill: $name" >&2; continue; }
  link "$src" "$SKILLS_DIR/$name"
done

# Named-skill installs stop here; hooks + settings are the full-install path.
[[ $# -gt 0 ]] && exit 0

# --- hooks ----------------------------------------------------------------
# _denial_log.py is a shared helper the guards load from their resolved directory, NOT a hook —
# linked so even a COPIED (non-symlinked) guard in ~/.claude/hooks finds it; never registered below.
mkdir -p "$HOOKS_DIR"
for hook in guard-default-branch.py guard-loop-vc.py guard-one-unit.py guard-self-integrity.py \
            _denial_log.py; do
  link "$REPO/hooks/$hook" "$HOOKS_DIR/$hook"
done

# --- settings.json hook registration (idempotent, exact-tuple merge) -------
# The merge is a tested module (R-07): full nested validation before reading, ownership by parsed
# command target (never a substring), semantic matcher comparison, and repair of stale/mismatched
# Excubitor-owned entries without touching unrelated user entries.
python3 "$REPO/scripts/install_settings.py" \
  || echo "settings.json registration skipped (python3 unavailable?)" >&2

echo "done — restart or reload Claude Code sessions to pick up newly linked skills"
