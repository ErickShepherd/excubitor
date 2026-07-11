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

# --- settings.json hook registration (idempotent merge) --------------------
python3 - <<'PY' || echo "settings.json registration skipped (python3 unavailable?)" >&2
import json
import sys
from pathlib import Path

p = Path.home() / ".claude" / "settings.json"
try:
    data = json.loads(p.read_text()) if p.exists() else {}
except (OSError, ValueError):
    print("settings.json unreadable — skipping hook registration", file=sys.stderr)
    raise SystemExit(0)

# An existing settings.json can carry an unexpected shape (`"hooks": null`, a non-list PreToolUse).
# setdefault only fills an ABSENT key, so a present-but-wrong-typed one would crash .setdefault/.append
# with a confusing "python3 unavailable?" message. Validate the shape and skip cleanly instead — never
# corrupt or crash on someone else's config.
if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict) \
        or not isinstance(data.get("hooks", {}).get("PreToolUse", []), list):
    print("settings.json has an unexpected hooks shape — skipping hook registration (resolve by hand)",
          file=sys.stderr)
    raise SystemExit(0)
pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
changed = False
WANTED = [
    ("guard-default-branch.py", "Edit|Write|NotebookEdit"),
    ("guard-loop-vc.py", "Bash"),
    ("guard-one-unit.py", "*"),
    ("guard-self-integrity.py", "Bash|Edit|Write|NotebookEdit"),
]
for script, matcher in WANTED:
    if any(script in h.get("command", "") for e in pre for h in e.get("hooks", [])):
        print(f"ok      {script} already registered")
        continue
    pre.append({"matcher": matcher,
                "hooks": [{"type": "command",
                           "command": f"python3 ~/.claude/hooks/{script}",
                           "timeout": 10}]})
    changed = True
    print(f"added   {script} (matcher: {matcher})")

if changed:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote   {p}")
PY

echo "done — restart or reload Claude Code sessions to pick up newly linked skills"
