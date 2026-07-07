#!/usr/bin/env python3
"""Tests for suspend_verdict.py — the Ralph-loop session-limit suspend/surface/proceed verdict.

Drives the verdict logic with SYNTHETIC usage data (monkeypatching the vendored reader's
`get_usage`), so the policy is pinned independent of the live OAuth endpoint: 5h-over-threshold ->
SUSPEND (exit 10), 7d-over-threshold -> SURFACE (exit 20, and 7d takes precedence over 5h), headroom
-> PROCEED (exit 0), and a usage-read failure -> fail-open PROCEED (exit 1). Also pins the poll-delay
clamp and the threshold boundary (`>=`).

Stdlib unittest only. Run:
  python3 skills/ralph-loop/tests/test_suspend_verdict.py
"""
from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "suspend_verdict.py"
_spec = importlib.util.spec_from_file_location("suspend_verdict", SCRIPT)
sv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sv)


def _iso(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _usage(u5: "float | None", u7: "float | None", *, reset5_h: float = 2.0, reset7_h: float = 60.0) -> dict:
    return {
        "five_hour": None if u5 is None else {"utilization": u5, "resets_at": _iso(reset5_h)},
        "seven_day": None if u7 is None else {"utilization": u7, "resets_at": _iso(reset7_h)},
    }


class TestSuspendVerdict(unittest.TestCase):
    def _run(self, data, *args: str) -> tuple[int, dict]:
        """Run main() with get_usage stubbed to `data` (a dict or an Exception); return (code, kv)."""
        orig = sv.claude_usage.get_usage

        def fake_get_usage():
            if isinstance(data, Exception):
                raise data
            return data

        sv.claude_usage.get_usage = fake_get_usage
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = sv.main(list(args))
        finally:
            sv.claude_usage.get_usage = orig
        kv = dict(
            line.split("=", 1) for line in buf.getvalue().splitlines() if "=" in line
        )
        return code, kv

    def test_proceed_when_both_low(self) -> None:
        code, kv = self._run(_usage(9, 55))
        self.assertEqual(code, 0)
        self.assertEqual(kv["verdict"], "PROCEED")

    def test_suspend_when_5h_high_7d_low(self) -> None:
        code, kv = self._run(_usage(95, 40))
        self.assertEqual(code, 10)
        self.assertEqual(kv["verdict"], "SUSPEND")
        self.assertEqual(kv["binding_window"], "5h")
        self.assertTrue(0 < int(kv["next_poll_seconds"]) <= 1800)

    def test_surface_when_7d_high(self) -> None:
        code, kv = self._run(_usage(20, 92))
        self.assertEqual(code, 20)
        self.assertEqual(kv["verdict"], "SURFACE")
        self.assertEqual(kv["binding_window"], "7d")

    def test_7d_takes_precedence_over_5h(self) -> None:
        # Both windows over threshold: surfacing wins (no point suspending for a 5h reset
        # when the 7d wall is days away).
        code, kv = self._run(_usage(99, 95))
        self.assertEqual(code, 20)
        self.assertEqual(kv["verdict"], "SURFACE")

    def test_threshold_is_inclusive(self) -> None:
        # Exactly at the threshold counts as over (>=).
        code, kv = self._run(_usage(90, 10), "--threshold", "90")
        self.assertEqual(code, 10)
        self.assertEqual(kv["verdict"], "SUSPEND")

    def test_poll_delay_clamped_to_max(self) -> None:
        # A 5h reset 4h out still yields a poll no larger than the cap.
        code, kv = self._run(_usage(95, 10, reset5_h=4.0), "--max-poll-seconds", "1800")
        self.assertEqual(code, 10)
        self.assertEqual(int(kv["next_poll_seconds"]), 1800)

    def test_fail_open_on_usage_unavailable(self) -> None:
        # Every read-failure type get_usage can leak must fail OPEN, not crash — including the ones it does
        # NOT wrap in RuntimeError: a malformed body (json.JSONDecodeError) and a read timeout (TimeoutError,
        # an OSError that is NOT a urllib URLError). The fail-open posture is the design's load-bearing claim.
        import json
        for exc in (
            RuntimeError("endpoint down"),
            json.JSONDecodeError("bad body", "", 0),
            TimeoutError("read timed out"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
        ):
            with self.subTest(exc=type(exc).__name__):
                code, kv = self._run(exc)
                self.assertEqual(code, 1)
                self.assertEqual(kv["verdict"], "PROCEED")

    def test_fail_open_on_non_object_body(self) -> None:
        # A valid-JSON body that is NOT an object (a degraded/changed endpoint: null, list, string, number)
        # returns from get_usage WITHOUT raising; the shape guard must still fail open, not crash on .get().
        for body in (None, [], "x", 42):
            with self.subTest(body=repr(body)):
                code, kv = self._run(body)
                self.assertEqual(code, 1)
                self.assertEqual(kv["verdict"], "PROCEED")

    def test_missing_5h_window_does_not_crash(self) -> None:
        code, kv = self._run(_usage(None, 30))
        self.assertEqual(code, 0)
        self.assertEqual(kv["verdict"], "PROCEED")

    def test_poll_delay_never_exceeds_schedulewakeup_ceiling(self) -> None:
        # Even with a --max-poll-seconds above ScheduleWakeup's 3600s hard ceiling and a far-out reset,
        # next_poll_seconds stays a valid wake-up delay.
        code, kv = self._run(_usage(95, 10, reset5_h=4.0), "--max-poll-seconds", "9000")
        self.assertEqual(code, 10)
        self.assertLessEqual(int(kv["next_poll_seconds"]), 3600)

    def test_poll_delay_floored_when_reset_already_past(self) -> None:
        # A stale/past resets_at must not yield a zero/negative wake-up — the floor keeps it at 60s.
        code, kv = self._run(_usage(95, 10, reset5_h=-1.0))
        self.assertEqual(code, 10)
        self.assertEqual(int(kv["next_poll_seconds"]), 60)

    def test_proceed_reason_shows_decimal_near_boundary(self) -> None:
        # Just under the threshold: verdict is PROCEED and the reason must not read as "90% vs 90%".
        code, kv = self._run(_usage(89.6, 10), "--threshold", "90")
        self.assertEqual(code, 0)
        self.assertIn("89.6%", kv["reason"])


if __name__ == "__main__":
    unittest.main()
