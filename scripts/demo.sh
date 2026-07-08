#!/usr/bin/env bash
# excubitor — 60-second, zero-install crash test.
#
# Shows a guard turning an unattended, UNRECOVERABLE act into a stop — then shows the wreck the
# same act causes with the guard off. Requires only `python3` and `git`. It does NOT install
# anything, does NOT touch ~/.claude, and does NOT modify this repo: everything happens in a
# throwaway temp git repo that is deleted on exit.
#
# It drives the real guard hook exactly as Claude Code's PreToolUse dispatch does — a JSON payload
# on stdin, a deny/defer decision on stdout — so what you see is the shipped code deciding, not a
# mock. (That stdin→decision contract is the same one hooks/tests/ exercises.)
#
# Usage:  scripts/demo.sh          # run the crash test
#         NO_COLOR=1 scripts/demo.sh   # plain text (also auto-disabled when not a TTY)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$REPO/hooks/guard-loop-vc.py"

# --- presentation ---------------------------------------------------------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; CYN=$'\033[36m'; RST=$'\033[0m'
else
  BOLD=; DIM=; RED=; GRN=; YEL=; CYN=; RST=
fi
say()  { printf '%s\n' "$*"; }
rule() { say "${DIM}────────────────────────────────────────────────────────────${RST}"; }
pause(){ sleep "${DEMO_PAUSE:-0.7}"; }

# Feed the guard a PreToolUse payload for a Bash command; echo its raw decision JSON ("" = defer/allow).
guard_decision() { # guard_decision <CLAUDE_LOOP_GUARD value or empty> <command>
  local marker="$1" cmd="$2" payload
  payload="$(CMD="$cmd" python3 -c 'import json,os; print(json.dumps({"tool_name":"Bash","tool_input":{"command":os.environ["CMD"]}}))')"
  if [[ -n "$marker" ]]; then
    printf '%s' "$payload" | CLAUDE_LOOP_GUARD="$marker" python3 "$GUARD"
  else
    printf '%s' "$payload" | env -u CLAUDE_LOOP_GUARD python3 "$GUARD"
  fi
}

# Extract the human reason from a deny decision (empty string if it was a defer/allow).
guard_reason() {
  python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d["hookSpecificOutput"]["permissionDecisionReason"])
except Exception:
    print("")'
}

# --- throwaway repo -------------------------------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/excubitor-demo.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT
git -C "$WORK" init -q -b main
git -C "$WORK" config user.email demo@example.com
git -C "$WORK" config user.name demo
git -C "$WORK" commit -q --allow-empty -m "initial"
# The precious thing: work that is NOT committed and has NO reflog — `git clean` is unrecoverable.
printf 'the results of 3 hours of work the loop never committed\n' > "$WORK/UNSAVED_WORK.txt"
# Cosmetic only: DEMO_STABLE_PATH prints a fixed path instead of the random mktemp one, so the
# committed scripts/demo.svg is byte-reproducible. The real file still lives at $WORK.
DISPLAY_WORK="${DEMO_STABLE_PATH:+/tmp/excubitor-demo}"; DISPLAY_WORK="${DISPLAY_WORK:-$WORK}"

ROGUE="git clean -fd"   # deletes untracked files with no reflog — strictly worse than reset --hard

[[ -t 1 && -z "${NO_COLOR:-}" ]] && { clear 2>/dev/null || true; }
say "${BOLD}excubitor — crash test${RST}  ${DIM}(60s, zero-install; deletes nothing outside a temp dir)${RST}"
rule
say "An unattended loop has decided it is ${BOLD}done${RST} and reaches for a cleanup:"
say "    ${YEL}\$ ${ROGUE}${RST}"
say "In its working tree sits an untracked file it never committed:"
say "    ${CYN}$DISPLAY_WORK/UNSAVED_WORK.txt${RST}   ${DIM}← no commit, no reflog, no undo${RST}"
pause; rule

# --- Scene 1: guard ARMED -------------------------------------------------
say "${BOLD}① With the loop guard armed${RST}  ${DIM}(CLAUDE_LOOP_GUARD=1)${RST}"
DECISION="$(guard_decision 1 "$ROGUE")"
REASON="$(printf '%s' "$DECISION" | guard_reason)"
if [[ -n "$REASON" ]]; then
  say "   ${GRN}${BOLD}DENIED${RST} — the tool call never runs. The guard says:"
  say "   ${GRN}❯${RST} ${DIM}$(printf '%s' "$REASON" | fold -s -w 68 | sed "2,\$s/^/     /")${RST}"
else
  say "   ${RED}(unexpected: no deny decision — is $GUARD present?)${RST}"
fi
pause; rule

# --- Scene 2: the wreck, guard OFF ---------------------------------------
say "${BOLD}② The same act with the guard off${RST}  ${DIM}(CLAUDE_LOOP_GUARD unset)${RST}"
DECISION="$(guard_decision "" "$ROGUE")"
if [[ -z "$DECISION" ]]; then
  say "   ${DIM}guard defers → the runtime runs the command:${RST}"
  say "   ${YEL}\$ ${ROGUE}${RST}"
  ( cd "$WORK" && git clean -fd ) | sed "s/^/   /"
  if [[ -f "$WORK/UNSAVED_WORK.txt" ]]; then
    say "   ${RED}(unexpected: the file survived)${RST}"
  else
    say "   ${RED}${BOLD}✗ UNSAVED_WORK.txt is gone.${RST} No reflog, no undo. Three hours, unattended."
  fi
else
  # symmetric with Scene 1: if the guard misbehaves and DENIES while unarmed (the exact regression this
  # crash-test exists to catch), surface it rather than silently swallowing the malfunction.
  say "   ${RED}(unexpected: guard denied while unarmed — a regression; the demo drives the real guard)${RST}"
fi
pause; rule

# --- close ----------------------------------------------------------------
say "${BOLD}That is the whole idea.${RST} A loop cannot bless its own \"done\" and then act on it:"
say "the irreversible tail is fenced ${BOLD}outside the model${RST}, in a PreToolUse hook."
say ""
say "  Install ...... ${CYN}scripts/install.sh${RST}   ${DIM}(symlinks the guards into ~/.claude)${RST}"
say "  How it decides  ${CYN}hooks/guard-loop-vc.py${RST}   ${DIM}·  the full model: THREAT-MODEL.md${RST}"
say "  Honest limits   ${CYN}KNOWN-BYPASSES.md${RST}   ${DIM}(this is a seatbelt, not a sandbox)${RST}"
rule
