#!/usr/bin/env python3
"""Idempotent, exact-tuple registration of the Excubitor guards in a Claude Code settings.json.

Extracted from the install.sh heredoc (R-07): the old merge validated only the OUTER
`hooks.PreToolUse` list shape — a malformed nested entry crashed with a misleading message — and
counted any command containing a script-name SUBSTRING as "already registered", even under the wrong
matcher, wrong path, or wrong timeout, so a broken registration was never repaired.

This module owns registrations by an exact, normalized tuple:

    (event=PreToolUse, matcher-alternative-set, handler type, command, timeout)

- **Validation first.** Every entry, matcher, and handler in `hooks.PreToolUse` is type-checked
  before anything reads it. Malformed nested data → a precise diagnostic naming the offending
  index/field, and NO write. Never crash, never corrupt someone else's config.
- **Ownership is a direct guard-LAUNCH shape, not a token anywhere in the command.** An
  entry/handler is Excubitor-owned iff its command *executes* one of our guard scripts: the command
  word itself has a guard script's exact basename (`~/.claude/hooks/guard-loop-vc.py`), or the
  command word is a Python interpreter and the SCRIPT it runs (the first non-option argument; `-c`
  and `-m` forms are never ours) has a guard script's exact basename (`python3
  /stale/guard-loop-vc.py` — a stale path is still ours to repair). A guard basename appearing in
  any OTHER argument position is somebody else's data, not ownership — `echo guard-loop-vc.py` and
  `python3 some-wrapper.py guard-loop-vc.py` are user handlers and must survive byte-for-byte
  (2026-07-16 independent review, finding 3: the any-token rule deleted exactly such handlers). A
  user's `xguard-loop-vc.py.bak` is not ours either; basenames must match exactly.
- **Matcher comparison is semantic.** `Write|Edit|NotebookEdit` equals `Edit|Write|NotebookEdit`
  (the alternative-set, not the string), so a cosmetic ordering difference is never "repaired".
- **Repair, don't duplicate.** A mismatched owned registration (wrong matcher, path, type, or
  timeout) is repaired to canonical. Our handler is stripped from mixed entries (user handlers in
  the same group are preserved in place); entries left empty are dropped; duplicates collapse.
  Unrelated entries are never altered.

Exit code is always 0 (an installer convenience must never wedge an install); the diagnostics are
the messages. `--settings <path>` targets an isolated file for tests.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path

CANON_TIMEOUT = 10
WANTED: list[tuple[str, str]] = [
    ("guard-default-branch.py", "Edit|Write|NotebookEdit"),
    ("guard-loop-vc.py", "Bash"),
    ("guard-one-unit.py", "*"),
    ("guard-self-integrity.py", "Bash|Edit|Write|NotebookEdit"),
]
_SCRIPTS = {s for s, _ in WANTED}


def _canonical_entry(script: str, matcher: str) -> dict:
    return {"matcher": matcher,
            "hooks": [{"type": "command",
                       "command": f"python3 ~/.claude/hooks/{script}",
                       "timeout": CANON_TIMEOUT}]}


def _matcher_key(matcher: object) -> tuple:
    """Matcher semantics: the set of `|`-alternatives (or the `*` wildcard), not the raw string."""
    m = matcher.strip() if isinstance(matcher, str) else ""
    return ("*",) if m == "*" else tuple(sorted(t for t in m.split("|") if t))


# A Python interpreter command word: python, python3, python3.12, … — the only launcher shape our
# own registrations ever used, so it is the only one ownership recognizes.
_PY_INTERP = re.compile(r"^python[0-9.]*$")
# CPython options that consume the FOLLOWING token as their value; skipping them keeps a value from
# being misread as the script path (`python3 -W ignore /stale/guard-loop-vc.py`).
_PY_VALUE_OPTS = {"-W", "-X", "--check-hash-based-pycs"}


def _command_target(command: str) -> str | None:
    """The Excubitor guard script a command LAUNCHES, or None for every non-Excubitor command.

    Ownership is a launch shape, never token membership: the command word itself (direct
    execution), or — for a Python interpreter command word — the script operand (the first
    non-option argument). A guard basename in any other argument position is user data
    (`echo guard-loop-vc.py`, `python3 some-wrapper.py guard-loop-vc.py`): inferring ownership from
    it deleted unrelated user hooks (2026-07-16 review, finding 3). `-c`/`-m` interpreter forms run
    code/modules, not a script operand, so they are never ours; on any unmodeled spelling the safe
    direction is None — treating our own stale entry as a user's only adds a duplicate canonical
    registration, while treating a user's entry as ours would delete it."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None
    head = os.path.basename(tokens[0])
    if head in _SCRIPTS:
        return head  # direct execution: /path/to/guard-x.py [args]
    if not _PY_INTERP.fullmatch(head):
        return None  # not an interpreter launch → the guard name can only be argument data
    j = 1
    while j < len(tokens):
        t = tokens[j]
        if t == "--":
            j += 1
            break  # end of options: the very next token is the script operand
        if t in _PY_VALUE_OPTS:
            j += 2  # separate-value option: its value is never the script
            continue
        if t.startswith("-") and len(t) > 1:
            # `-c`/`-m` (bare, attached, or inside a short cluster) switch python to code/module
            # mode — there is no script operand, so the command launches no guard of ours.
            if not t.startswith("--") and ("c" in t[1:] or "m" in t[1:]):
                return None
            j += 1  # any other flag (attached values included) — step over it
            continue
        break  # first non-option token: the script operand
    if j >= len(tokens):
        return None
    base = os.path.basename(tokens[j])
    return base if base in _SCRIPTS else None


def _validate(pre: list) -> str | None:
    """Type-check every entry/matcher/handler BEFORE any logic reads them. Returns a precise
    diagnostic, or None when the whole list is safely readable."""
    for i, e in enumerate(pre):
        loc = f"hooks.PreToolUse[{i}]"
        if not isinstance(e, dict):
            return f"{loc} is not an object (got {type(e).__name__})"
        if "matcher" in e and not isinstance(e["matcher"], str):
            return f"{loc}.matcher is not a string (got {type(e['matcher']).__name__})"
        hooks = e.get("hooks", [])
        if not isinstance(hooks, list):
            return f"{loc}.hooks is not a list (got {type(hooks).__name__})"
        for j, h in enumerate(hooks):
            hloc = f"{loc}.hooks[{j}]"
            if not isinstance(h, dict):
                return f"{hloc} is not an object (got {type(h).__name__})"
            if "type" in h and not isinstance(h["type"], str):
                return f"{hloc}.type is not a string"
            if "command" in h and not isinstance(h["command"], str):
                return f"{hloc}.command is not a string"
            if "timeout" in h and not isinstance(h["timeout"], (int, float)):
                return f"{hloc}.timeout is not a number"
    return None


def _handler_is_canonical(h: dict, script: str) -> bool:
    return (h.get("type") == "command"
            and h.get("command") == f"python3 ~/.claude/hooks/{script}"
            and h.get("timeout") == CANON_TIMEOUT)


def _entry_is_canonical(e: dict, script: str, matcher: str) -> bool:
    """Exactly our canonical registration: right matcher-set, one handler, ours, exact tuple."""
    if _matcher_key(e.get("matcher")) != _matcher_key(matcher):
        return False
    hooks = e.get("hooks", [])
    return (len(hooks) == 1
            and _command_target(hooks[0].get("command", "")) == script
            and _handler_is_canonical(hooks[0], script))


def merge(data: dict) -> tuple[bool, list[str]]:
    """Merge the four canonical registrations into `data` (mutated in place).

    Returns (changed, messages). On any validation failure, returns (False, [diagnostic]) without
    touching `data` — the caller must not write."""
    if not isinstance(data.get("hooks", {}), dict) \
            or not isinstance(data.get("hooks", {}).get("PreToolUse", []), list):
        return False, ["settings.json has an unexpected hooks shape — skipping hook registration "
                       "(resolve by hand)"]
    pre = data.get("hooks", {}).get("PreToolUse", [])
    problem = _validate(pre)
    if problem is not None:
        return False, [f"settings.json is malformed: {problem} — skipping hook registration, "
                       f"nothing written (resolve by hand)"]

    messages: list[str] = []
    changed = False
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    for script, matcher in WANTED:
        owned = [i for i, e in enumerate(pre)
                 if any(_command_target(h.get("command", "")) == script for h in e.get("hooks", []))]
        if len(owned) == 1 and _entry_is_canonical(pre[owned[0]], script, matcher):
            messages.append(f"ok      {script} already registered")
            continue
        if owned:
            # Repair: strip OUR handlers from every owned entry (user handlers sharing a group stay
            # in place); drop entries that held only ours; then append one canonical entry.
            for i in sorted(owned, reverse=True):
                kept = [h for h in pre[i].get("hooks", [])
                        if _command_target(h.get("command", "")) != script]
                if kept:
                    pre[i]["hooks"] = kept
                else:
                    del pre[i]
            messages.append(f"repair  {script}: stale/mismatched registration replaced with canonical")
        else:
            messages.append(f"added   {script} (matcher: {matcher})")
        pre.append(_canonical_entry(script, matcher))
        changed = True
    return changed, messages


def main() -> int:
    ap = argparse.ArgumentParser(description="Register the Excubitor guards in settings.json.")
    ap.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json",
                    help="settings.json path (default: ~/.claude/settings.json)")
    args = ap.parse_args()
    p = args.settings

    try:
        data = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        print("settings.json unreadable — skipping hook registration", file=sys.stderr)
        return 0
    if not isinstance(data, dict):
        print("settings.json is not a JSON object — skipping hook registration (resolve by hand)",
              file=sys.stderr)
        return 0

    changed, messages = merge(data)
    for m in messages:
        out = sys.stderr if ("skipping" in m or "malformed" in m) else sys.stdout
        print(m, file=out)
    if changed:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2) + "\n")
        print(f"wrote   {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
