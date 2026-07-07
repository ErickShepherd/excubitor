#!/usr/bin/env python3
"""Session-limit handling for a self-paced Ralph loop: the suspend / surface / proceed verdict.

A long Ralph loop can exhaust the Claude plan's rolling-window usage caps mid-run. There are two
windows — a **5-hour** cap (resets in minutes-to-hours) and a **7-day** cap (resets days away). A
forced pause at a cap is NEITHER of the loop's existing outcomes: the loop is healthy and work
remains (so it is not a *stop*), but it cannot safely do a unit right now (so it is not a *continue*).
This script collapses the live usage reading into the single verdict the loop body acts on:

    PROCEED  — headroom remains; run the iteration normally.
    SUSPEND  — 5h window is at/over the threshold. Leave a CLEAN tree (the prior unit is already
               committed) and poll for the 5h reset, then auto-resume. Short, self-healing gap.
    SURFACE  — the 7-day window is the binding limit (reset days away). Do NOT hold the loop open
               for days: stop-and-surface for a human, exactly like a normal terminal stop.

It is a THIN wrapper over `check-usage`'s vendored `claude_usage.py` reader (the OAuth token stays
OS-side, never in context) plus the fixed 5h-auto / 7d-surface policy. The loop body owns the act
(reschedule vs. surface); this script only reports the verdict and a clamped poll delay.

The suspend/surface decision is ORTHOGONAL to the stop predicate and the act-fence. The loop must
evaluate its anchor's stop predicate (done / stuck) FIRST; only a loop that WOULD have continued may
consult this verdict and downgrade continue -> suspend. A stuck or done loop still terminates — a
suspend must never be reachable from a stop condition, or auto-continuation would mask a spin into an
indefinite poll. SUSPEND never merges, pushes, or marks work done; CLAUDE_LOOP_GUARD stays armed
across the pause. This adds unattended runtime, not a new act.

FAIL-OPEN (deliberately, unlike the YOLO immutability checks). If usage cannot be read (endpoint
down, no creds), the verdict is PROCEED with a warning — a usage blip must never wedge a healthy loop
into an indefinite false suspend. A real hard cap still surfaces as an actual harness pause; the worst
case here is one iteration that tries and is throttled, which is recoverable on re-read.

Exit codes: 0 = PROCEED; 10 = SUSPEND (5h); 20 = SURFACE (7d); 1 = usage unavailable (proceeds).

Usage:
    suspend_verdict.py [--threshold 90] [--max-poll-seconds 1800]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import the usage reader. The vendored copy sits next to this script; a full check-usage skill
# installed in the runtime (which may be newer) takes precedence when present.
_CANDIDATES = [
    Path.home() / ".claude" / "skills" / "check-usage",
    Path(__file__).resolve().parent,
]
for _d in _CANDIDATES:
    if (_d / "claude_usage.py").is_file():
        sys.path.insert(0, str(_d))
        break
try:
    import claude_usage  # noqa: E402
except ImportError:
    claude_usage = None  # handled as fail-open below


def _util(window: "dict | None") -> "float | None":
    """Utilization percent for a window dict, or None if absent/malformed."""
    if not isinstance(window, dict) or window.get("utilization") is None:
        return None
    try:
        return float(window["utilization"])
    except (TypeError, ValueError):
        return None


def _seconds_to_reset(window: "dict | None", *, cap: int) -> int:
    """Whole seconds until `resets_at`, clamped to [60, cap]. Falls back to `cap` if unparseable."""
    iso = (window or {}).get("resets_at") if isinstance(window, dict) else None
    if isinstance(iso, str):
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            delta = (dt - datetime.now(timezone.utc)).total_seconds()
            return max(60, min(cap, int(delta)))
        except (ValueError, TypeError):
            pass
    return cap


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Ralph-loop session-limit suspend/surface/proceed verdict.")
    ap.add_argument("--threshold", type=float, default=90.0,
                    help="utilization%% at/above which a window is treated as out of headroom (default 90)")
    ap.add_argument("--max-poll-seconds", type=int, default=1800,
                    help="cap for the suggested next-poll delay (ScheduleWakeup clamps to <=3600; default 1800)")
    args = ap.parse_args(argv)

    if claude_usage is None:
        print("verdict=PROCEED")
        print("reason=usage reader not found (claude_usage.py missing) — proceeding, will surface if "
              "the harness pauses on a real cap")
        return 1
    try:
        data = claude_usage.get_usage()
        # get_usage does not assert the body is a JSON *object* — a valid-JSON null/list/string/number (a
        # degraded or changed endpoint, e.g. an empty 200) would return intact and then crash the .get()
        # calls below OUTSIDE this guard. Validate the shape here so a non-object body fails open too.
        if not isinstance(data, dict):
            raise RuntimeError(f"usage body is not a JSON object ({type(data).__name__})")
    except Exception as e:  # noqa: BLE001 — deliberately broad: fail-open is the whole point here.
        # get_usage documents "raises RuntimeError", but the UNDOCUMENTED OAuth endpoint can also leak a
        # json.JSONDecodeError (malformed body), a UnicodeDecodeError, or a socket TimeoutError (a read
        # timeout is an OSError, NOT the URLError get_usage handles) straight through. ANY read failure must
        # fail open to PROCEED — a crash here would wedge a healthy loop exactly when the endpoint is flaky,
        # the failure mode this posture exists to absorb. A real hard cap still surfaces as a harness pause.
        print("verdict=PROCEED")
        print(f"reason=usage unavailable ({type(e).__name__}: {e}) — fail-open so a usage blip cannot wedge "
              f"the loop")
        return 1

    five = data.get("five_hour") or {}
    seven = data.get("seven_day") or {}
    u5, u7 = _util(five), _util(seven)
    print(f"5h_util_pct={u5:.0f}" if u5 is not None else "5h_util_pct=")
    print(f"5h_resets_at={five.get('resets_at', '')}")
    print(f"7d_util_pct={u7:.0f}" if u7 is not None else "7d_util_pct=")
    print(f"7d_resets_at={seven.get('resets_at', '')}")

    # 7-day cap is binding -> surface (days-away reset; do not hold the loop open).
    if u7 is not None and u7 >= args.threshold:
        print("verdict=SURFACE")
        print("binding_window=7d")
        print(f"reason=7d window at {u7:.0f}% (>= {args.threshold:.0f}% threshold); reset is days away — "
              f"stop-and-surface rather than parking the loop branch open")
        return 20

    # 5-hour cap is binding -> suspend and poll for the (near-term) reset.
    if u5 is not None and u5 >= args.threshold:
        # Cap at the caller's max AND ScheduleWakeup's hard 3600s ceiling, so next_poll_seconds is always a
        # valid wake-up delay no matter what --max-poll-seconds is passed.
        poll = _seconds_to_reset(five, cap=min(args.max_poll_seconds, 3600))
        print("verdict=SUSPEND")
        print("binding_window=5h")
        print(f"next_poll_seconds={poll}")
        print(f"reason=5h window at {u5:.0f}% (>= {args.threshold:.0f}% threshold); leave a clean tree and "
              f"poll for the 5h reset (~{poll}s), then auto-resume")
        return 10

    print("verdict=PROCEED")
    # One decimal here (the verdict lines above round to whole %): avoids a misleading "5h 90%, threshold
    # 90% — proceeding" at e.g. 89.6%, which would look like the >= boundary is broken.
    head = f"5h {u5:.1f}%" if u5 is not None else "5h n/a"
    tail = f"7d {u7:.1f}%" if u7 is not None else "7d n/a"
    print(f"reason=headroom remains ({head}, {tail}; threshold {args.threshold:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
