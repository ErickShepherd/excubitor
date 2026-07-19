#!/usr/bin/env python3
"""Tests for excubitor.core.events — the canonical, model-blind event and decision types.

These pin the two load-bearing rules of the neutral core (see the module docstring of
`excubitor/core/events.py`):

  1. the passing outcome serializes as "pass", NEVER "allow";
  2. the value types are pure — the core module names no host/provider and reads no environment.

Stdlib unittest only. Run:
  python3 excubitor/tests/test_core_events.py
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]  # repo root holds the importable `excubitor/` package
sys.path.insert(0, str(_REPO_ROOT))

from excubitor.core import (  # noqa: E402
    SCHEMA,
    Capability,
    Decision,
    LoopMode,
    Outcome,
    PreToolEvent,
)
import excubitor.core.events as events  # noqa: E402


class TestEnumWireValues(unittest.TestCase):
    """The serialized strings are a contract with adapters — pin them so a typo can't slip through."""

    def test_capability_values(self):
        self.assertEqual(Capability.SHELL_EXECUTE.value, "shell.execute")
        self.assertEqual(Capability.FILE_MUTATE.value, "file.mutate")
        self.assertEqual(Capability.NOTEBOOK_MUTATE.value, "notebook.mutate")
        self.assertEqual(Capability.OTHER.value, "other")

    def test_loop_mode_values(self):
        self.assertEqual(LoopMode.CONSERVATIVE.value, "conservative")
        self.assertEqual(LoopMode.VERIFIABLE.value, "verifiable")

    def test_outcome_values_and_no_allow(self):
        self.assertEqual(Outcome.PASS.value, "pass")
        self.assertEqual(Outcome.DENY.value, "deny")
        # The core must never introduce an "allow" outcome (it can skip a host permission prompt).
        self.assertNotIn("allow", [o.value for o in Outcome])

    def test_schema_marker(self):
        self.assertEqual(SCHEMA, "excubitor.pre_tool.v1")


class TestDecision(unittest.TestCase):
    def test_pass_semantics(self):
        d = Decision.pass_()
        self.assertTrue(d.is_pass)
        self.assertFalse(d.is_deny)
        self.assertIs(d.outcome, Outcome.PASS)
        self.assertIsNone(d.reason)
        self.assertIsNone(d.policy)

    def test_pass_serializes_minimal_and_never_allow(self):
        self.assertEqual(Decision.pass_().to_dict(), {"decision": "pass", "reason": None})

    def test_deny_semantics(self):
        d = Decision.deny("may not push", policy="loop-vc")
        self.assertTrue(d.is_deny)
        self.assertFalse(d.is_pass)
        self.assertIs(d.outcome, Outcome.DENY)
        self.assertEqual(d.reason, "may not push")
        self.assertEqual(d.policy, "loop-vc")

    def test_deny_serializes_with_policy(self):
        self.assertEqual(
            Decision.deny("may not push", policy="loop-vc").to_dict(),
            {"decision": "deny", "reason": "may not push", "policy": "loop-vc"},
        )

    def test_deny_without_policy_omits_key(self):
        # No policy set → the "policy" key is absent, not a null (keeps the shape minimal).
        self.assertEqual(Decision.deny("nope").to_dict(), {"decision": "deny", "reason": "nope"})

    def test_immutable(self):
        d = Decision.pass_()
        with self.assertRaises(FrozenInstanceError):
            d.outcome = Outcome.DENY  # type: ignore[misc]


class TestPreToolEvent(unittest.TestCase):
    def test_minimal_construction_defaults(self):
        e = PreToolEvent(capability=Capability.OTHER)
        self.assertIs(e.capability, Capability.OTHER)
        self.assertIsNone(e.runtime)
        self.assertIsNone(e.native_tool)
        self.assertIsNone(e.cwd)
        self.assertIsNone(e.command)
        self.assertEqual(e.targets, ())
        self.assertIsNone(e.session_id)
        self.assertIsNone(e.loop_mode)
        self.assertEqual(e.control_paths, ())
        self.assertEqual(e.schema, SCHEMA)

    def test_shell_event_to_dict(self):
        e = PreToolEvent(
            capability=Capability.SHELL_EXECUTE,
            runtime="generic",
            native_tool="Bash",
            cwd="/repo",
            command="git push origin main",
            session_id="abc",
            loop_mode=LoopMode.CONSERVATIVE,
            control_paths=("/repo/.claude/settings.json",),
        )
        self.assertEqual(
            e.to_dict(),
            {
                "schema": "excubitor.pre_tool.v1",
                "runtime": "generic",
                "native_tool": "Bash",
                "capability": "shell.execute",
                "cwd": "/repo",
                "command": "git push origin main",
                "targets": [],
                "session_id": "abc",
                "loop_mode": "conservative",
                "control_paths": ["/repo/.claude/settings.json"],
            },
        )

    def test_multi_target_and_null_loop_mode(self):
        # `targets` must carry EVERY mutated path (a patch can touch several); unarmed → loop_mode null.
        e = PreToolEvent(
            capability=Capability.FILE_MUTATE,
            targets=("/repo/app.py", "/repo/tests/test_app.py"),
        )
        d = e.to_dict()
        self.assertEqual(d["targets"], ["/repo/app.py", "/repo/tests/test_app.py"])
        self.assertIsNone(d["loop_mode"])
        self.assertEqual(d["command"], None)

    def test_immutable(self):
        e = PreToolEvent(capability=Capability.OTHER)
        with self.assertRaises(FrozenInstanceError):
            e.command = "rm -rf /"  # type: ignore[misc]


class TestCorePurity(unittest.TestCase):
    """The defining property of the neutral core: it names no host/provider and reads no environment.

    This is the design doc's "no file under core/ contains runtime/provider names or reads
    environment/global paths" invariant, seeded on the value-types module. It is scoped to the files
    this unit created; later units extend the coverage to their own pure modules (a `git_state.py`
    that legitimately shells out to read-only git is the documented carve-out — a policy module is
    not).
    """

    # (token, why it must not appear in a pure core value-types module). Tokens are chosen to be
    # code-specific (e.g. `os.environ`, not bare `environ`) so prose that *describes* the neutrality
    # invariant — "reads no environment", "no child processes" — cannot self-trip the scan.
    _FORBIDDEN = [
        ("claude", "provider/host identity"),
        ("anthropic", "provider identity"),
        ("codex", "host identity"),
        ("openai", "provider identity"),
        ("gemini", "host/provider identity"),
        ("copilot", "host identity"),
        ("os.environ", "environment read"),
        ("getenv", "environment read"),
        ("expanduser", "home-directory read"),
        ("subprocess", "host process call"),
        ("sys.stdin", "host I/O"),
        ("sys.stdout", "host I/O"),
        ("sys.exit", "process exit"),
    ]

    _PURE_FILES = [
        _REPO_ROOT / "excubitor" / "core" / "events.py",
        _REPO_ROOT / "excubitor" / "core" / "__init__.py",
    ]

    def test_no_host_coupling_tokens(self):
        for path in self._PURE_FILES:
            src = path.read_text(encoding="utf-8").lower()
            for token, why in self._FORBIDDEN:
                self.assertNotIn(
                    token, src,
                    f"{path.relative_to(_REPO_ROOT)} must stay host-neutral but contains "
                    f"{token!r} ({why})",
                )

    def test_events_module_has_no_io_imports(self):
        # Pure value types pull in only dataclasses/enum/typing — no os/sys/subprocess/json.
        for banned in ("import os", "import sys", "import subprocess", "import json"):
            self.assertNotIn(banned, Path(events.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
