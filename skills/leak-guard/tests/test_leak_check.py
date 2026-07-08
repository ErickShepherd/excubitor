#!/usr/bin/env python3
"""Tests for leak_check.py — the deterministic private→public leak scanner.

Pins the load-bearing properties: it detects built-in structured secrets and caller-supplied private
tokens; it EXITS NON-ZERO on a finding (CI-gating) and clean-exits 0; it FAILS CLOSED (unreadable /
missing path → non-zero, never a silent pass); whitelisting is EXPLICIT and reported (an allowed match
is suppressed AND counted, and only the exact allowed text is suppressed); findings are MASKED (the raw
secret is never printed); a bad private-token regex fails loud.

Stdlib unittest only. Run:
  python3 skills/leak-guard/tests/test_leak_check.py
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))  # skills/leak-guard/ (leak_check.py)
import leak_check as lc  # noqa: E402


def _run(argv: list[str]) -> "tuple[int, str, str]":
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = lc.main(argv)
        except SystemExit as e:  # argparse / loud regex failures
            # Mirror real interpreter semantics so the test verifies the TRUE exit code:
            # SystemExit(None)→0, SystemExit(int)→int, SystemExit(str/other)→1 (Python prints it, exits 1).
            code = e.code
            rc = 0 if code is None else code if isinstance(code, int) else 1
    return rc, out.getvalue(), err.getvalue()


def _file(dirp: Path, name: str, body: str) -> Path:
    p = dirp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# A real-shaped AWS key that the built-in pattern must catch (fabricated, not a live credential).
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"[:16]


class TestBuiltinDetection(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_detects_private_key_block(self):
        f = _file(self.dir, "leaked.pem", "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n")
        rc, out, _ = _run([str(f)])
        self.assertEqual(rc, 1)
        self.assertIn("private-key-block", out)

    def test_detects_aws_and_github_and_url_creds(self):
        f = _file(self.dir, "conf.txt",
                  f"key={AWS_KEY}\n"
                  "tok=ghp_" + "A" * 36 + "\n"
                  "db=postgres://admin:s3cr3tpw@db.internal:5432/prod\n")
        rc, out, _ = _run([str(f)])
        self.assertEqual(rc, 1)
        self.assertIn("aws-access-key-id", out)
        self.assertIn("github-token", out)
        self.assertIn("url-credentials", out)

    def test_clean_file_exits_zero(self):
        f = _file(self.dir, "ok.md", "# A perfectly ordinary document\nNo secrets here.\n")
        rc, out, err = _run([str(f)])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertIn("clean", err)

    def test_finding_is_masked_not_raw(self):
        # The raw secret must NEVER appear in output (printing it re-leaks it).
        f = _file(self.dir, "leaked.txt", f"key={AWS_KEY}\n")
        rc, out, err = _run([str(f)])
        self.assertEqual(rc, 1)
        self.assertNotIn(AWS_KEY, out + err)
        self.assertIn("[20 chars]", out)  # AKIA + 16 = 20

    def test_directory_scanned_recursively(self):
        _file(self.dir, "sub/deep/leaked.env", f"AWS={AWS_KEY}\n")
        _file(self.dir, "sub/clean.txt", "nothing\n")
        rc, out, _ = _run([str(self.dir)])
        self.assertEqual(rc, 1)
        self.assertIn("leaked.env", out)


class TestPrivateTokens(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_literal_private_token_case_insensitive_substring(self):
        canon = _file(self.dir, "private.txt", "# my canon\nAcme Confidential Project\n")
        art = _file(self.dir, "resume.md", "Led the acme confidential project to launch.\n")
        rc, out, _ = _run([str(art), "--private-tokens", str(canon)])
        self.assertEqual(rc, 1)
        self.assertIn("private-literal:Acme Confidential Project", out)

    def test_private_regex(self):
        canon = _file(self.dir, "private.txt", "re:\\b555-\\d{4}\\b\n")
        art = _file(self.dir, "bio.md", "call me at 555-0134 anytime\n")
        rc, out, _ = _run([str(art), "--private-tokens", str(canon)])
        self.assertEqual(rc, 1)
        self.assertIn("private-regex", out)

    def test_no_builtin_scans_only_private(self):
        # With --no-builtin, an AWS key is ignored; only the private token fires.
        canon = _file(self.dir, "private.txt", "TopSecretName\n")
        art = _file(self.dir, "a.txt", f"AWS={AWS_KEY}\nabout TopSecretName here\n")
        rc, out, _ = _run([str(art), "--private-tokens", str(canon), "--no-builtin"])
        self.assertEqual(rc, 1)
        self.assertIn("private-literal:TopSecretName", out)
        self.assertNotIn("aws-access-key-id", out)

    def test_bad_regex_fails_loud(self):
        canon = _file(self.dir, "private.txt", "re:[unclosed\n")
        art = _file(self.dir, "a.txt", "hello\n")
        rc, _, err = _run([str(art), "--private-tokens", str(canon)])
        self.assertEqual(rc, 2)  # loud SystemExit, not a silently-skipped rule


class TestWhitelistIsExplicit(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_allow_suppresses_and_reports(self):
        # An intentionally-public token: whitelisted → suppressed, but the suppression is REPORTED.
        canon = _file(self.dir, "private.txt", "PublicBrandName\n")
        art = _file(self.dir, "site.md", "Welcome to PublicBrandName.\n")
        rc, out, err = _run([str(art), "--private-tokens", str(canon), "--allow", "PublicBrandName"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertIn("1 match(es) suppressed by explicit whitelist", err)

    def test_allow_is_exact_not_blanket(self):
        # Whitelisting one token must NOT suppress a DIFFERENT leak.
        canon = _file(self.dir, "private.txt", "PublicBrandName\nSecretClient\n")
        art = _file(self.dir, "site.md", "PublicBrandName works with SecretClient.\n")
        rc, out, _ = _run([str(art), "--private-tokens", str(canon), "--allow", "PublicBrandName"])
        self.assertEqual(rc, 1)
        self.assertIn("private-literal:SecretClient", out)
        self.assertNotIn("private-literal:PublicBrandName", out)


class TestFailClosed(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_missing_path_is_error_nonzero(self):
        rc, _, err = _run([str(self.dir / "does-not-exist.txt")])
        self.assertNotEqual(rc, 0)
        self.assertIn("not a file or directory", err)

    def test_missing_private_tokens_file_fails_closed(self):
        art = _file(self.dir, "a.txt", "hello\n")
        rc, _, err = _run([str(art), "--private-tokens", str(self.dir / "nope.txt")])
        self.assertEqual(rc, 2)
        self.assertIn("not found", err)

    def test_no_patterns_at_all_is_error(self):
        art = _file(self.dir, "a.txt", "hello\n")
        rc, _, _ = _run([str(art), "--no-builtin"])
        self.assertEqual(rc, 2)  # nothing to scan for → refuse, don't claim clean

    def test_binary_file_skipped_not_crash(self):
        p = self.dir / "img.png"
        p.write_bytes(b"\x89PNG\x00\x00" + AWS_KEY.encode() + b"\x00")  # secret-shaped bytes in a binary
        rc, out, err = _run([str(p)])
        self.assertEqual(rc, 0)  # skipped by ext + NUL probe; not a crash, not a finding
        self.assertNotIn("aws", out.lower())


class TestContractWitness(unittest.TestCase):
    """The single witness for TELOS-010: non-zero on a finding AND on an unreadable target
    (fail-closed), zero only on a clean completion. One method so the claim's contract is proven
    end-to-end by one executable."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_contract(self):
        # 1) a finding → non-zero (gates the build)
        leaked = _file(self.dir, "leaked.txt", f"key={AWS_KEY}\n")
        rc, _, _ = _run([str(leaked)])
        self.assertEqual(rc, 1, "a finding must gate (non-zero)")
        # 2) an unreadable target → non-zero (fail-closed, never a silent pass)
        rc, _, _ = _run([str(self.dir / "missing.txt")])
        self.assertNotEqual(rc, 0, "an un-scannable target must fail closed")
        # 3) a clean scan → zero (and only then)
        clean = _file(self.dir, "clean.md", "an ordinary document with nothing sensitive\n")
        rc, out, _ = _run([str(clean)])
        self.assertEqual(rc, 0, "a clean scan exits zero")
        self.assertEqual(out.strip(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
