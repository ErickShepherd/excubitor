"""Gather the installed-state inventory for ``excubitor status`` — with an honest protection verdict.

The one rule this module exists to keep: **never infer safety from file presence alone.** A staged
guard file and a settings registration mean an install *happened*, not that enforcement *works* — that
is only established by a real harmless-denial host probe (C2.8/C2.9). So every installation reports a
``protection`` verdict that comes from the recorded probe result, defaulting to ``needs-probe`` until a
probe has actually succeeded on a real host. Files present with no probe is ``needs-probe``, never
``protected``. Campaign 2 has no trusted producer for that evidence, so even a hand-written
``state=protected`` v1 record is rejected as invalid evidence and resolves to ``needs-probe``.

The output is a plain dict with a schema marker so the ``--json`` form is stable and machine-readable.
"""
from __future__ import annotations

import json
from pathlib import Path

import excubitor
from excubitor.core.events import SCHEMA as CORE_PROTOCOL
from excubitor.installers.receipts import Receipt, state_home_dir

__all__ = [
    "STATUS_SCHEMA",
    "PROBE_SCHEMA",
    "SUPPORTED_RUNTIMES",
    "AVAILABLE_ADAPTERS",
    "DESIGNED_NOT_SUPPORTED",
    "probe_path",
    "read_probe_state",
    "gather_status",
]

STATUS_SCHEMA = "excubitor.status.v1"
PROBE_SCHEMA = "excubitor.probe.v1"

#: Campaign 2 has an installable Claude Code adapter foundation but no real-host witness, so no runtime
#: has earned the project's "supported enforcement" claim yet.
AVAILABLE_ADAPTERS = ("claude-code",)
SUPPORTED_RUNTIMES: tuple[str, ...] = ()
#: Runtimes designed in docs/design but NOT supported (no built adapter, no host probe). Reported
#: honestly so `status` never implies coverage the code does not have.
DESIGNED_NOT_SUPPORTED = ("codex", "gemini-cli", "github-copilot")


def probe_path(runtime: str, scope: str, state_home: "str | None" = None,
               environ: "dict[str, str] | None" = None) -> Path:
    """The probe-result record path for one runtime+scope under the state dir."""
    return state_home_dir(state_home, environ) / "probes" / f"{runtime}-{scope}.json"


def read_probe_state(runtime: str, scope: str, state_home: "str | None" = None,
                     environ: "dict[str, str] | None" = None) -> dict:
    """Read the recorded probe result, or a ``needs-probe`` default when none has run.

    The default is the honest one: absent evidence of a successful probe means enforcement is
    unverified, never that it works.
    """
    path = probe_path(runtime, scope, state_home, environ)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"state": "needs-probe", "at": None, "detail": "no host probe has been recorded"}
    if not isinstance(data, dict) or data.get("schema") != PROBE_SCHEMA:
        return {"state": "needs-probe", "at": None, "detail": "unreadable probe record"}
    state = data.get("state")
    if state == "protected":
        return {
            "state": "needs-probe", "at": data.get("at"),
            "detail": "invalid Campaign 2 evidence: protected requires a future versioned host witness",
        }
    if state not in {"needs-probe", "failed"}:
        return {"state": "needs-probe", "at": data.get("at"), "detail": "invalid probe state"}
    return {"state": state, "at": data.get("at"), "detail": data.get("detail")}


def _file_dispositions(receipt: Receipt) -> dict:
    present, drifted, missing = 0, [], []
    for owned in receipt.files:
        path = Path(owned.path)
        if not path.exists():
            missing.append(owned.path)
        elif Receipt.hash_file(path) == owned.sha256:
            present += 1
        else:
            drifted.append(owned.path)
    return {"present": present, "drifted": drifted, "missing": missing}


def _installation_status(receipt: Receipt, state_home, environ) -> dict:
    probe = read_probe_state(receipt.runtime, receipt.scope, state_home, environ)
    # Protection verdict: ONLY a recorded successful probe yields "protected". Everything else — files
    # present, registrations intact, but no probe — is "needs-probe". Presence is never protection.
    protection = probe["state"]
    if protection != "failed":
        protection = "needs-probe"
    return {
        "runtime": receipt.runtime,
        "scope": receipt.scope,
        "installed_version": receipt.excubitor_version,
        "installed_at": receipt.installed_at,
        "settings_path": receipt.settings_path,
        "files": _file_dispositions(receipt),
        "registrations": len(receipt.registrations),
        "probe": probe,
        "protection": protection,
    }


def gather_status(state_home: "str | None" = None, environ: "dict[str, str] | None" = None) -> dict:
    """Build the full status inventory dict (schema-tagged, deterministic order)."""
    receipts_dir = state_home_dir(state_home, environ) / "receipts"
    installations: list[dict] = []
    if receipts_dir.is_dir():
        for path in sorted(receipts_dir.glob("*.json")):
            try:
                receipt = Receipt.from_json(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            installations.append(_installation_status(receipt, state_home, environ))
    return {
        "schema": STATUS_SCHEMA,
        "excubitor_version": excubitor.__version__,
        "core_protocol": CORE_PROTOCOL,
        "supported_runtimes": list(SUPPORTED_RUNTIMES),
        "available_adapters": list(AVAILABLE_ADAPTERS),
        "designed_not_supported": list(DESIGNED_NOT_SUPPORTED),
        "installations": installations,
    }
