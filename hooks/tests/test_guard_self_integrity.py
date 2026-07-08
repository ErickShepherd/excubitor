#!/usr/bin/env python3
"""Tests for the guard-self-integrity.py PreToolUse hook.

Drives the hook as a subprocess with a crafted PreToolUse stdin payload, asserting the deny/defer
contract: deny = exit 0 + JSON permissionDecision=deny on stdout; defer = exit 0 with no decision.
Pins the security-load-bearing properties: it is INACTIVE unless CLAUDE_LOOP_GUARD is set (either
mode); while armed it denies Edit/Write/NotebookEdit targeting any guard kill-switch (the
allow-default-branch marker, the guard hook scripts, a .claude settings.json) including through a
symlink, and denies Bash commands naming one; it does NOT block ordinary work (the seatbelt stays
wearable); and it fails OPEN on unparseable input.

Stdlib unittest only. Run:
  python3 hooks/tests/test_guard_self_integrity.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "guard-self-integrity.py"


def _run(payload_or_raw, *, guard: "bool | str" = True) -> "tuple[int, str]":
    env = dict(os.environ)
    env.pop("CLAUDE_LOOP_GUARD", None)
    if guard:  # True → conservative "1"; a str sets that mode; False → unset (inactive)
        env["CLAUDE_LOOP_GUARD"] = guard if isinstance(guard, str) else "1"
    raw = payload_or_raw if isinstance(payload_or_raw, str) else json.dumps(payload_or_raw)
    p = subprocess.run([sys.executable, str(HOOK)], input=raw, capture_output=True, text=True, env=env)
    return p.returncode, p.stdout


def _denied(stdout: str) -> bool:
    try:
        return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    except (ValueError, KeyError):
        return False


def _write(path: str, cwd: str = "/tmp") -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": cwd}


def _bash(command: str, cwd: str = "/tmp") -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}


class TestFileToolDenials(unittest.TestCase):
    DENY_TARGETS = [
        "/repo/.claude/allow-default-branch",              # the per-repo disarm marker
        ".claude/allow-default-branch",                    # relative form resolves against cwd
        "~/.claude/hooks/guard-loop-vc.py",                # the loop fence itself
        "/anywhere/at/all/guard-default-branch.py",        # guard scripts match by basename
        "/repo/hooks/guard-one-unit.py",
        "/repo/hooks/guard-self-integrity.py",             # this guard may not rewrite itself
        "/home/u/.claude/settings.json",                   # hook registration (global)
        "/repo/.claude/settings.json",                     # hook registration (project)
        "/repo/.claude/settings.local.json",
    ]

    ALLOW_TARGETS = [
        "/repo/README.md",
        "/repo/hooks/tests/test_guard_loop_vc.py",         # editing a TEST disarms nothing at runtime
        "/repo/.vscode/settings.json",                     # settings.json outside .claude is not ours
        "/repo/settings.json",                             # ditto: no .claude component
        "/repo/.claude/some-other-file",                   # .claude content that is not a kill-switch
        "/repo/docs/allow-default-branch.md",              # basename differs (suffix)
    ]

    def test_deny_targets(self):
        for tool in ("Edit", "Write", "NotebookEdit"):
            for target in self.DENY_TARGETS:
                key = "notebook_path" if tool == "NotebookEdit" else "file_path"
                rc, out = _run({"tool_name": tool, "tool_input": {key: target}, "cwd": "/repo"})
                self.assertEqual(rc, 0, f"must exit 0 (fail-open contract): {tool} {target}")
                self.assertTrue(_denied(out), f"should be DENIED but was allowed: {tool} {target}")

    def test_allow_targets(self):
        for target in self.ALLOW_TARGETS:
            rc, out = _run(_write(target, cwd="/repo"))
            self.assertEqual((rc, out.strip()), (0, ""), f"should DEFER but didn't: {target}")

    def test_symlink_to_guard_is_denied(self):
        # A symlink named something innocent must not launder a write into a guard script.
        with tempfile.TemporaryDirectory() as td:
            real = Path(td, "guard-loop-vc.py")
            real.write_text("# guard")
            link = Path(td, "innocent.py")
            link.symlink_to(real)
            rc, out = _run(_write(str(link), cwd=td))
            self.assertTrue(_denied(out), "a symlink to a guard script must be denied")

    def test_yolo_mode_also_denies(self):
        rc, out = _run(_write("/repo/.claude/allow-default-branch"), guard="yolo")
        self.assertTrue(_denied(out), "YOLO leans on the guards harder, not softer")


class TestBashDenials(unittest.TestCase):
    DENY = [
        "touch /repo/.claude/allow-default-branch",
        "touch .claude/allow-default-branch",
        "mkdir -p .claude && touch .claude/allow-default-branch",   # compound: second segment names it
        "(rm hooks/guard-loop-vc.py)",                              # subshell glue must not hide it
        "echo $(rm hooks/guard-default-branch.py)",                 # command substitution
        "`rm hooks/guard-one-unit.py`",                             # backtick substitution
        "echo disarm > /repo/.claude/allow-default-branch",         # redirect target
        "echo disarm >.claude/allow-default-branch",                # attached redirect
        "rm -f ~/.claude/hooks/guard-loop-vc.py",
        "rm -f hooks/guard-loop-vc.py # with a trailing comment",  # real path BEFORE # → still caught
        "mv hooks/guard-default-branch.py /tmp/parked.py",
        "cp /dev/null hooks/guard-one-unit.py",
        "sed -i 's/PreToolUse/Disabled/' /home/u/.claude/settings.json",
        "python3 -c 'open(\"x\")' /r/.claude/settings.local.json",
        "tee /repo/.claude/allow-default-branch < /dev/null",
        "chmod -x /any/hooks/guard-self-integrity.py",
    ]

    # Ordinary loop work must stay unblocked — the seatbelt is wearable.
    ALLOW = [
        "git add -A && git commit -m 'progress'",
        "git switch -c fix/thing",
        "python3 -m pytest -q",
        "ls hooks/",
        "touch README.md",
        "echo note >> notes.txt",
        "cat docs/telos/app.md",
        "code --list-extensions > .vscode/settings.json",   # settings.json outside .claude
        "git -C /repo status",
        # a guard name QUOTED mid-sentence (no path tail) is not promoted to a command → allow; the
        # round-2 segmentation false-deny (a `(...)` in a commit message) is what this pins as fixed
        'git commit -m "refactor (see guard-loop-vc.py) later"',
        "echo 'the fourth guard is guard-self-integrity in spirit'",
        "rm nothing.txt # then edit guard-loop-vc.py by hand",  # name only in a comment → bash never acts
        "ls -la # guard-one-unit.py notes",
    ]

    def test_deny_set(self):
        for cmd in self.DENY:
            rc, out = _run(_bash(cmd, cwd="/repo"))
            self.assertEqual(rc, 0, f"must exit 0 (fail-open contract): {cmd}")
            self.assertTrue(_denied(out), f"should be DENIED but was allowed: {cmd}")

    def test_allow_set(self):
        for cmd in self.ALLOW:
            rc, out = _run(_bash(cmd, cwd="/repo"))
            self.assertEqual((rc, out.strip()), (0, ""), f"should DEFER but didn't: {cmd}")

    def test_mention_denies_even_reads(self):
        # Documented bluntness: Bash MENTIONS deny, reads included (the Read tool still works).
        rc, out = _run(_bash("cat ~/.claude/hooks/guard-loop-vc.py"))
        self.assertTrue(_denied(out))


class TestAcceptedResiduals(unittest.TestCase):
    """Documented bypasses that this seatbelt deliberately does NOT catch (see the hook's SCOPE /
    LIMITS). Pinned BIDIRECTIONALLY: each asserts the bypass currently ALLOWS (defers), so if a
    future change starts catching one, this test fails and forces an honest update to the SCOPE /
    LIMITS wording + KNOWN-BYPASSES.md rather than a silent scope change. Closing these would mean
    reimplementing shell expansion or denying every metacharacter (breaking ordinary globbing) — the
    deny-set-completeness creep the repo's honest-limits brand exists to resist."""

    # word expansions that mutate the path token before bash resolves it → the guard never sees the
    # kill-switch basename, so it defers. These are REAL disarms at the shell but out of scope here.
    RESIDUAL_ALLOW = [
        "rm hooks/guard-loop-vc.p*",                     # glob
        "rm hooks/guard-loop-vc.p?",                     # single-char glob
        "rm .claude/settings.jso{n,}",                   # brace expansion → settings.json
        "rm .claude/allow-default-branch{,}",            # brace expansion → the marker
        "B=allow-default-branch; rm .claude/$B",         # basename hidden in a shell variable
        "python3 -c \"open('.claude/allow-default-branch','w')\"",  # interpreter builds the path
        'echo "$(rm hooks/guard-loop-vc.py)"',           # LIVE substitution inside double quotes
    ]
    # NB the near-miss `F=.claude/allow-default-branch; rm $F` is DENIED, not allowed: the assignment
    # token's own basename is `allow-default-branch`, so the guard catches the literal path in the
    # assignment even though `rm $F` alone would slip. Only hiding the BASENAME in the variable
    # (`B=allow-default-branch`) evades it — hence the specific form above.

    def test_documented_bypasses_still_allow(self):
        for cmd in self.RESIDUAL_ALLOW:
            rc, out = _run(_bash(cmd, cwd="/repo"))
            self.assertEqual(
                (rc, out.strip()), (0, ""),
                f"ACCEPTED-RESIDUAL CHANGED: this bypass used to slip past (documented in the hook's "
                f"SCOPE / LIMITS); it is now being caught. Update the SCOPE / LIMITS + KNOWN-BYPASSES.md "
                f"to match, then move it out of TestAcceptedResiduals: {cmd}")


class TestActivationAndContract(unittest.TestCase):
    def test_inactive_without_marker(self):
        for payload in (
            _write("/repo/.claude/allow-default-branch"),
            _bash("rm -f ~/.claude/hooks/guard-loop-vc.py"),
        ):
            rc, out = _run(payload, guard=False)
            self.assertEqual((rc, out.strip()), (0, ""), "must be inactive without CLAUDE_LOOP_GUARD")

    def test_unmatched_tool_defers(self):
        rc, out = _run({"tool_name": "Read",
                        "tool_input": {"file_path": "/repo/.claude/allow-default-branch"}, "cwd": "/repo"})
        self.assertEqual((rc, out.strip()), (0, ""), "reads are not fenced — the seatbelt stays wearable")

    def test_unparseable_stdin_fails_open(self):
        rc, out = _run("this is not json {{{")
        self.assertEqual((rc, out.strip()), (0, ""))  # fail open, never crash

    def test_missing_target_defers(self):
        rc, out = _run({"tool_name": "Write", "tool_input": {}, "cwd": "/repo"})
        self.assertEqual((rc, out.strip()), (0, ""))

    def test_non_object_json_fails_open(self):
        # non-object JSON must fail open, not crash on payload.get(...).
        for raw in ("5", "[]", "null"):
            rc, out = _run(raw)
            self.assertEqual((rc, out.strip()), (0, ""), f"non-object payload must defer: {raw!r}")

    def test_nul_byte_does_not_crash_or_suppress_sibling(self):
        # A NUL byte in one segment used to raise ValueError out of realpath (uncaught) → non-zero exit
        # → under fail-open the whole compound command ran, disarming the guard. Now the NUL segment is
        # skipped and the real kill-switch in the next segment is still caught (DENY, exit 0).
        rc, out = _run(_bash("rm \x00x ; rm hooks/guard-loop-vc.py", cwd="/repo"))
        self.assertEqual(rc, 0, "must exit 0 (fail-open process contract)")
        self.assertTrue(_denied(out), "the NUL must not suppress the sibling kill-switch write")


if __name__ == "__main__":
    unittest.main(verbosity=2)
