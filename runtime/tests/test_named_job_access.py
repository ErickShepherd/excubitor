"""Offline prerequisites; these never provision or authenticate a Windows sandbox."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.runs import RunError  # noqa: E402
from runtime.probes.named_job_access import (  # noqa: E402
    PROTECTED_NATIVE_FILES,
    existing_native_home,
    native_fingerprints,
)


class TestExistingSandboxPrerequisites(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "native-home"

    def fixture(self):
        for name, data in (
            ("config.toml", b'[windows]\nsandbox = "elevated"\n'),
            (".sandbox/setup_marker.json", json.dumps({"version": 5}).encode()),
            (".sandbox-secrets/sandbox_users.json", b"opaque-native-fixture"),
        ):
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def test_missing_home_does_not_trigger_setup_or_create_files(self):
        with self.assertRaises(RunError):
            existing_native_home(self.home)
        self.assertFalse(self.home.exists())

    def test_prerequisites_return_only_digests_without_copying_or_editing_bytes(self):
        self.fixture()
        before = {name: (self.home / name).read_bytes() for name in PROTECTED_NATIVE_FILES}
        expected = {name: hashlib.sha256(data).hexdigest() for name, data in before.items()}
        self.assertEqual(existing_native_home(self.home), expected)
        self.assertEqual({name: (self.home / name).read_bytes() for name in before}, before)
        self.assertEqual(len([path for path in self.root.rglob("*") if path.is_file()]), 3)

    def test_weaker_missing_or_changed_setup_is_refused(self):
        for target, data in (
            ("config.toml", b'[windows]\nsandbox = "unelevated"\n'),
            (".sandbox/setup_marker.json", b'{"version": 6}'),
            (".sandbox/setup_marker.json", b"[]"),
            (".sandbox-secrets/sandbox_users.json", None),
        ):
            with self.subTest(target=target, data=data):
                self.fixture()
                path = self.home / target
                if data is None:
                    path.unlink()
                else:
                    path.write_bytes(data)
                with self.assertRaises(RunError):
                    existing_native_home(self.home)

    def test_configuration_and_credential_drift_are_detectable(self):
        self.fixture()
        baseline = existing_native_home(self.home)
        for name in PROTECTED_NATIVE_FILES:
            with self.subTest(name=name):
                self.fixture()
                path = self.home / name
                path.write_bytes(path.read_bytes() + b"\n")
                self.assertNotEqual(native_fingerprints(self.home), baseline)


if __name__ == "__main__":
    unittest.main()
