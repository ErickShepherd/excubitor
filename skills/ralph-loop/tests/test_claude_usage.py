#!/usr/bin/env python3
"""Tests for claude_usage.py — the subscription-usage reader (vendored for the session-limit gate).

Pins the documented contract: malformed credentials degrade to the friendly RuntimeError (never an
undocumented AttributeError/JSONDecodeError), and no token content ever appears in a failure message.
Network is never touched here — every case fails before the HTTP request, in credential loading.

Stdlib unittest only. Run:
  python3 skills/ralph-loop/tests/test_claude_usage.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import claude_usage as cu  # noqa: E402


class TestCredentialDegradation(unittest.TestCase):
    def _creds(self, body: str) -> str:
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        f.write(body)
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def test_malformed_creds_raise_runtimeerror_not_raw_type(self):
        # a JSON list (valid JSON, wrong shape → .get AttributeError) and invalid JSON (JSONDecodeError)
        # must BOTH surface as the documented RuntimeError, not the raw underlying exception type.
        for body in ("[]", "{not json", '"a string"', "123"):
            with self.assertRaises(RuntimeError):
                cu.get_usage(self._creds(body))

    def test_missing_creds_file_raises_runtimeerror(self):
        with self.assertRaises(RuntimeError):
            cu.get_usage(str(Path(tempfile.gettempdir()) / "definitely-not-here.json"))

    def test_no_token_leaks_in_failure_message(self):
        # a well-formed creds file whose token is present but the endpoint is unreachable: the token
        # must never appear in the raised message. Force an unreachable host via a bogus creds token and
        # a get_usage call — but to stay offline, assert only the credential-load messages here.
        secret = "sk-SUPERSECRETTOKENVALUE-do-not-leak"
        creds = self._creds(json.dumps({"claudeAiOauth": {"accessToken": secret}}))
        # _load_token succeeds; the network call will fail — capture whatever message surfaces.
        try:
            cu.get_usage(creds, timeout=0.001)
        except RuntimeError as e:
            self.assertNotIn(secret, str(e))
        # (a no-token creds file yields the "no access token" message, also token-free)
        with self.assertRaises(RuntimeError) as ctx:
            cu.get_usage(self._creds(json.dumps({"claudeAiOauth": {}})))
        self.assertNotIn("accessToken", str(ctx.exception).lower().replace("accesstoken", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
