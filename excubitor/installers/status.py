"""Gather the installed-state inventory for ``excubitor status`` — with honest support boundaries.

The one rule this module exists to keep: **never infer safety from file presence alone.** A staged
guard file and a settings registration mean an install *happened*, not that enforcement *works* — that
is only established by a real harmless-denial host probe (C2.8/C2.9). So every installation reports a
``protection`` verdict that comes from the recorded probe result, defaulting to ``needs-probe`` until a
probe has actually succeeded on a real host. Files present with no probe is ``needs-probe``, never
``protected``. Campaign 2 has no trusted producer for that evidence, so even a hand-written
``state=protected`` v1 record is rejected as invalid evidence and resolves to ``needs-probe``.

Runtime-level support is a separate claim. Codex earned a bounded support claim from a checked-in,
sanitized real-host witness: the Windows TUI dispatched the installed user ``PreToolUse`` hook for
``Bash`` and ``apply_patch``, allowed a harmless status command, and blocked a harmless marker patch.
The status payload names those exact surfaces and keeps MCP/specialized tools and other host modes
explicitly unverified.

The output is a plain dict with a schema marker so the ``--json`` form is stable and machine-readable.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import excubitor
from excubitor.core.events import SCHEMA as CORE_PROTOCOL
from excubitor.installers.receipts import Receipt, matcher_key, receipt_path, state_home_dir
from excubitor.installers.runtime import profile_for

__all__ = [
    "STATUS_SCHEMA",
    "PROBE_SCHEMA",
    "HOST_WITNESS_SCHEMA",
    "SUPPORTED_RUNTIMES",
    "ENFORCEMENT_COVERAGE",
    "AVAILABLE_ADAPTERS",
    "DESIGNED_NOT_SUPPORTED",
    "probe_path",
    "registration_fingerprint",
    "implementation_fingerprint",
    "host_executable_fingerprint",
    "read_probe_state",
    "gather_status",
]

STATUS_SCHEMA = "excubitor.status.v2"
PROBE_SCHEMA = "excubitor.probe.v1"
HOST_WITNESS_SCHEMA = "excubitor.host-witness.v1"

#: Codex has a bounded real-host allow/deny witness. Installation-specific protection still requires
#: evidence for that exact registration and therefore remains independent of this capability claim.
AVAILABLE_ADAPTERS = ("claude-code", "codex")
SUPPORTED_RUNTIMES: tuple[str, ...] = ("codex",)
ENFORCEMENT_COVERAGE = {
    "codex": {
        "verified_host": "Codex TUI on Windows with a user-scope PreToolUse registration",
        "verified_tools": ("Bash", "apply_patch"),
        "unverified_tools": ("MCP mutation tools", "other specialized tools"),
        "unverified_host_surfaces": ("codex exec", "project-scope hooks", "non-Windows hosts"),
    },
}
#: Runtimes designed in docs/design but with no installable adapter profile.
DESIGNED_NOT_SUPPORTED = ("gemini-cli", "github-copilot")


def probe_path(runtime: str, scope: str, state_home: "str | None" = None,
               environ: "dict[str, str] | None" = None) -> Path:
    """The probe-result record path for one runtime+scope under the state dir."""
    return state_home_dir(state_home, environ) / "probes" / f"{runtime}-{scope}.json"


def registration_fingerprint(receipt: Receipt) -> str:
    """Bind a host witness to one exact receipt-owned registration definition."""
    bound = {
        "runtime": receipt.runtime,
        "scope": receipt.scope,
        "settings_path": receipt.settings_path,
        "registrations": [registration.to_dict() for registration in receipt.registrations],
    }
    encoded = json.dumps(bound, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def implementation_fingerprint() -> str:
    """Hash the importable enforcement implementation, excluding tests and interpreter caches."""
    package_file = str(excubitor.__file__)
    pyz_marker = ".pyz" + os.sep
    if pyz_marker in package_file:
        archive = Path(package_file.split(pyz_marker, 1)[0] + ".pyz")
        return hashlib.sha256(archive.read_bytes()).hexdigest()

    package_root = Path(package_file).resolve().parent
    members = []
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root)
        if "tests" in relative.parts or "__pycache__" in relative.parts:
            continue
        members.append((relative.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    encoded = json.dumps(members, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def host_executable_fingerprint(runtime: str) -> "tuple[str, str]":
    """Resolve and hash the native host executable whose dispatch behavior was witnessed."""
    executable_name = {"codex": "codex"}.get(runtime)
    resolved = shutil.which(executable_name) if executable_name else None
    if not resolved:
        raise ValueError(f"cannot resolve the {runtime} host executable")
    path = Path(resolved).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"the {runtime} host executable is not a regular file")
    return str(path), hashlib.sha256(path.read_bytes()).hexdigest()


def _invalid_witness(data: dict, detail: str) -> dict:
    return {"state": "needs-probe", "at": data.get("at"), "detail": detail}


def _read_host_witness(data: dict, runtime: str, scope: str, receipt: "Receipt | None") -> dict:
    fields = {
        "schema", "state", "at", "detail", "runtime", "scope", "registration_sha256",
        "implementation_sha256", "host", "verified_tools", "allow", "deny", "limitations",
    }
    if set(data) != fields or data.get("state") != "protected":
        return _invalid_witness(data, "invalid host witness field set or state")
    if data.get("runtime") != runtime or data.get("scope") != scope or receipt is None:
        return _invalid_witness(data, "host witness does not match an installed runtime and scope")
    if data.get("registration_sha256") != registration_fingerprint(receipt):
        return _invalid_witness(data, "host witness is stale for the current receipt registration")
    if data.get("implementation_sha256") != implementation_fingerprint():
        return _invalid_witness(data, "host witness is stale for the current enforcement implementation")
    coverage = ENFORCEMENT_COVERAGE.get(runtime)
    if coverage is None or data.get("verified_tools") != list(coverage["verified_tools"]):
        return _invalid_witness(data, "host witness claims unsupported tool coverage")
    host = data.get("host")
    if (
        not isinstance(host, dict)
        or set(host) != {
            "version", "mode", "operating_system", "executable_path", "executable_sha256",
        }
        or any(not isinstance(value, str) or not value for value in host.values())
    ):
        return _invalid_witness(data, "host witness has invalid host metadata")
    try:
        executable_path, executable_sha256 = host_executable_fingerprint(runtime)
    except (OSError, ValueError):
        return _invalid_witness(data, "host witness executable can no longer be resolved")
    if (
        os.path.normcase(host["executable_path"]) != os.path.normcase(executable_path)
        or host["executable_sha256"] != executable_sha256
    ):
        return _invalid_witness(data, "host witness is stale for the current host executable")
    allow = data.get("allow")
    deny = data.get("deny")
    if allow != {"tool": "Bash", "hook_dispatched": True, "tool_executed": True}:
        return _invalid_witness(data, "host witness lacks the required harmless allow observation")
    if deny != {
        "tool": "apply_patch",
        "hook_dispatched": True,
        "hook_blocked": True,
        "tool_executed": False,
        "marker_created": False,
    }:
        return _invalid_witness(data, "host witness lacks the required harmless denial observation")
    limitations = data.get("limitations")
    if not isinstance(limitations, list) or not limitations or any(
        not isinstance(item, str) or not item for item in limitations
    ):
        return _invalid_witness(data, "host witness must preserve explicit coverage limitations")
    if not isinstance(data.get("at"), str) or not isinstance(data.get("detail"), str):
        return _invalid_witness(data, "host witness has invalid time or detail metadata")
    return {
        "state": "protected",
        "at": data["at"],
        "detail": data["detail"],
        "host": host,
        "verified_tools": data["verified_tools"],
        "limitations": limitations,
    }


def read_probe_state(runtime: str, scope: str, state_home: "str | None" = None,
                     environ: "dict[str, str] | None" = None,
                     receipt: "Receipt | None" = None) -> dict:
    """Read the recorded probe result, or a ``needs-probe`` default when none has run.

    The default is the honest one: absent evidence of a successful probe means enforcement is
    unverified, never that it works.
    """
    path = probe_path(runtime, scope, state_home, environ)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"state": "needs-probe", "at": None, "detail": "no host probe has been recorded"}
    if not isinstance(data, dict):
        return {"state": "needs-probe", "at": None, "detail": "unreadable probe record"}
    if data.get("schema") == HOST_WITNESS_SCHEMA:
        if receipt is None:
            try:
                receipt = Receipt.from_json(
                    receipt_path(runtime, scope, state_home, environ).read_text(encoding="utf-8")
                )
            except (FileNotFoundError, OSError, ValueError):
                receipt = None
        return _read_host_witness(data, runtime, scope, receipt)
    if data.get("schema") != PROBE_SCHEMA:
        return {"state": "needs-probe", "at": data.get("at"), "detail": "unreadable probe record"}
    state = data.get("state")
    if state == "protected":
        return {
            "state": "needs-probe", "at": data.get("at"),
            "detail": "invalid Campaign 2 evidence: protected requires a future versioned host witness",
        }
    if state not in {"needs-trust", "needs-probe", "failed"}:
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


def _registrations_intact(receipt: Receipt) -> bool:
    try:
        settings = json.loads(Path(receipt.settings_path).read_text(encoding="utf-8"))
        entries = settings.get("hooks", {}).get("PreToolUse", [])
    except (FileNotFoundError, OSError, ValueError, AttributeError):
        return False
    live = set()
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        handlers = entry.get("hooks", [])
        for handler in handlers if isinstance(handlers, list) else []:
            if isinstance(handler, dict):
                live.add((
                    matcher_key(entry.get("matcher", "")),
                    handler.get("type"),
                    handler.get("command"),
                    handler.get("commandWindows"),
                    handler.get("timeout"),
                ))
    return all((
        matcher_key(registration.matcher),
        registration.handler_type,
        registration.command,
        registration.command_windows,
        registration.timeout,
    ) in live for registration in receipt.registrations)


def _installation_status(receipt: Receipt, state_home, environ) -> dict:
    probe = read_probe_state(receipt.runtime, receipt.scope, state_home, environ, receipt)
    files = _file_dispositions(receipt)
    registrations_intact = _registrations_intact(receipt)
    witness_current = (
        probe["state"] == "protected"
        and not files["drifted"]
        and not files["missing"]
        and registrations_intact
    )
    if probe["state"] == "protected" and not witness_current:
        probe = {
            "state": "needs-probe",
            "at": probe.get("at"),
            "detail": "host witness is stale because installed files or registrations drifted",
        }
    try:
        requires_trust = profile_for(receipt.runtime).requires_trust_review
    except KeyError:
        requires_trust = False
    trust = {
        "state": (
            "witnessed-current-definition" if witness_current else
            "needs-review" if requires_trust else "not-required-by-profile"
        ),
        "detail": (
            "The host dispatched the exact receipt-bound hook definition during the recorded witness."
            if witness_current else
            "Unmanaged Codex hook trust is bound to the exact definition and must be reviewed in /hooks."
            if requires_trust else "This installer profile has no separate native trust-review gate."
        ),
    }
    # Protection verdict: ONLY a recorded successful probe yields "protected". Everything else — files
    # present, registrations intact, but no probe — is unprotected. Codex first reports the earlier
    # ``needs-trust`` gate; file presence is never evidence that Codex loaded the hook.
    protection = "protected" if witness_current else "failed" if probe["state"] == "failed" else (
        "needs-trust" if requires_trust else "needs-probe"
    )
    return {
        "runtime": receipt.runtime,
        "scope": receipt.scope,
        "installed_version": receipt.excubitor_version,
        "installed_at": receipt.installed_at,
        "settings_path": receipt.settings_path,
        "files": files,
        "registrations": len(receipt.registrations),
        "trust": trust,
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
        "enforcement_coverage": {
            runtime: {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in coverage.items()
            }
            for runtime, coverage in ENFORCEMENT_COVERAGE.items()
        },
        "available_adapters": list(AVAILABLE_ADAPTERS),
        "designed_not_supported": list(DESIGNED_NOT_SUPPORTED),
        "installations": installations,
    }
