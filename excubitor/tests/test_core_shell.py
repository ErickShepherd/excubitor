#!/usr/bin/env python3
"""Tests for excubitor.core.shell — the shared shell-segment splitter.

split_segments is exercised end-to-end through both policies (loop-vc + self-integrity) and their
differential oracles; this pins its behavior directly at the shared source and the neutrality invariant.

Stdlib unittest only. Run:
  python3 excubitor/tests/test_core_shell.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from excubitor.core.shell import split_segments  # noqa: E402


class TestSplitSegments(unittest.TestCase):
    def test_command_separators(self):
        self.assertEqual(split_segments("git push; echo hi"), ["git push", "echo hi"])
        self.assertEqual(split_segments("a && b"), ["a", "b"])  # && falls out of single-& splits
        self.assertEqual(split_segments("a | b"), ["a", "b"])

    def test_subshell_and_substitution_boundaries_split(self):
        self.assertEqual(split_segments("(git push)"), ["git push"])
        self.assertIn("rm x", split_segments("$(rm x)"))
        self.assertIn("git push", split_segments("`git push`"))

    def test_separator_inside_quotes_is_literal(self):
        self.assertEqual(split_segments('echo "a ; b | c"'), ['echo "a ; b | c"'])
        self.assertEqual(split_segments("echo 'a ; (b)'"), ["echo 'a ; (b)'"])

    def test_backslash_escapes_next_char(self):
        # An escaped separator (outside single quotes) is literal — one segment, backslash preserved.
        self.assertEqual(split_segments("a\\; b"), ["a\\; b"])

    def test_empty_and_whitespace_segments_stripped(self):
        self.assertEqual(split_segments(""), [])
        self.assertEqual(split_segments("   ;  ; "), [])
        self.assertEqual(split_segments("a;;b"), ["a", "b"])


class TestPurity(unittest.TestCase):
    def test_neutral_and_io_free(self):
        src = (_REPO_ROOT / "excubitor" / "core" / "shell.py").read_text("utf-8")
        for token in ("claude", "anthropic", "codex", "openai", "gemini", "copilot"):
            self.assertNotIn(token, src.lower(), f"shell must name no host: {token!r}")
        for token in ("os.environ", "getenv", "subprocess", "import os", "import sys", "import re"):
            self.assertNotIn(token, src, f"shell is pure string lexing — no {token!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
