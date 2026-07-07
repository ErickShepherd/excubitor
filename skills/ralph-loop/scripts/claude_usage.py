"""Claude subscription usage — read the plan's rate-limit utilization dynamically.

Calls the same OAuth usage endpoint the Claude CLI uses (`/api/oauth/usage`), authenticating with the
access token stored OS-side in `~/.claude/.credentials.json`. The token is read here, OS-side, and
never enters the model's context; only the non-secret usage summary is returned. Stdlib-only (urllib).

NOTE: this endpoint is UNDOCUMENTED (it's what the CLI's `/usage` uses) and may change with CLI
updates; failures degrade to a friendly message.
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
DEFAULT_CREDS = "~/.claude/.credentials.json"


def _load_token(creds_path: str) -> str:
    data = json.loads(Path(creds_path).expanduser().read_text())
    return (data.get("claudeAiOauth") or {}).get("accessToken", "")


def get_usage(creds_path: str = DEFAULT_CREDS, *, timeout: float = 20.0) -> dict:
    """Fetch the usage JSON. Raises RuntimeError with a friendly message on failure."""
    try:
        token = _load_token(creds_path)
    except OSError as e:
        raise RuntimeError(f"no Claude credentials at {creds_path} ({e})") from e
    if not token:
        raise RuntimeError("no Claude OAuth access token found in credentials")
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "User-Agent": "excubitor-usage/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Claude token expired/unauthorized — re-auth the CLI") from e
        raise RuntimeError(f"usage endpoint returned HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach usage endpoint ({e.reason})") from e


def _reset_str(iso: "str | None") -> str:
    if not isinstance(iso, str) or not iso:
        return ""   # a non-string resets_at (a changed/malformed endpoint) must not raise AttributeError
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return f", resets {dt:%a %H:%M}"
    except (ValueError, TypeError):
        return ""


def _window(label: str, w: "dict | None") -> "str | None":
    # Defensive against a malformed/changed endpoint (it's UNDOCUMENTED): a non-dict window value would
    # make `.get` raise AttributeError, and a non-numeric utilization would make float() raise — either
    # way, drop just this window so the rest of the summary still renders.
    if not isinstance(w, dict) or w.get("utilization") is None:
        return None
    try:
        return f"{label} {float(w['utilization']):.0f}%{_reset_str(w.get('resets_at'))}"
    except (ValueError, TypeError):
        return None


def summarize(data: dict) -> str:
    """Human/spoken-friendly one-liner. Never includes the token or any secret."""
    parts = []
    for key, label in (("five_hour", "5-hour:"), ("seven_day", "7-day:"),
                       ("seven_day_opus", "7-day Opus:"), ("seven_day_sonnet", "7-day Sonnet:")):
        s = _window(label, data.get(key))
        if s:
            parts.append(s)
    extra = data.get("extra_usage")
    if isinstance(extra, dict) and extra.get("is_enabled") and extra.get("utilization") is not None:
        with contextlib.suppress(ValueError, TypeError):
            parts.append(f"extra-usage {float(extra['utilization']):.0f}%")
    return "Claude usage — " + "; ".join(parts) if parts else "Claude usage: no data returned"
