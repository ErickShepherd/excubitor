#!/usr/bin/env python3
"""Tests for claude_usage.py — the subscription-usage reader (vendored for the session-limit gate).

Pins the documented contract: malformed credentials degrade to the friendly RuntimeError (never an
undocumented AttributeError/JSONDecodeError), and no token content ever appears in a failure message.
Network is never touched here — transport failures are mocked at `urlopen` or its response reader.

Stdlib unittest only. Run:
  python3 skills/ralph-loop/tests/test_claude_usage.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        # A well-formed credential file reaches urlopen. Model lower layers that include request
        # material in their text; neither the RuntimeError nor its rendered traceback may repeat it.
        secret = "sk-" + "SUPERSECRETTOKENVALUE" + "-do-not-leak"
        creds = self._creds(json.dumps({"claudeAiOauth": {"accessToken": secret}}))
        failures = (
            ("urlopen timeout", "urlopen", TimeoutError(f"Bearer {secret} timed out"),
             "usage request timed out"),
            ("urlopen URL error", "urlopen", cu.urllib.error.URLError(f"Bearer {secret} failed"),
             "could not reach usage endpoint"),
            ("read timeout", "read", TimeoutError(f"Bearer {secret} timed out"),
             "usage request timed out"),
            ("read URL error", "read", cu.urllib.error.URLError(f"Bearer {secret} failed"),
             "could not reach usage endpoint"),
        )
        for label, stage, failure, expected in failures:
            with self.subTest(label=label):
                if stage == "urlopen":
                    transport = patch.object(cu.urllib.request, "urlopen", side_effect=failure)
                else:
                    response = MagicMock()
                    response.__enter__.return_value.read.side_effect = failure
                    transport = patch.object(cu.urllib.request, "urlopen", return_value=response)
                with transport as urlopen, self.assertRaisesRegex(RuntimeError, expected) as raised:
                    cu.get_usage(creds)
                urlopen.assert_called_once()
                self.assertNotIn(secret, str(raised.exception))
                self.assertNotIn(secret, "".join(traceback.format_exception(raised.exception)))
        # a no-token creds file raises the "no access token" RuntimeError (real coverage; nothing to leak).
        with self.assertRaises(RuntimeError):
            cu.get_usage(self._creds(json.dumps({"claudeAiOauth": {}})))


if __name__ == "__main__":
    unittest.main(verbosity=2)
