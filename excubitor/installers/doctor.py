"""``excubitor doctor`` — diagnose an installation and, with ``--probe``, attempt a harmless-denial probe.

Doctor validates the installed state (versions, files present/undrifted, registrations present in the
settings file) and, when asked to ``--probe``, runs the harmless-denial probe framework. The rule it
exists to keep is the contract's: **installation is not "protected" until a real host probe succeeds,
and if a real host cannot be exercised, report ``needs-probe`` — never ``protected``.**

The CLI can drive the installed guard *script* as a subprocess (a hook-level witness that the hook
vetoes the synthetic action), but it **cannot** drive the real Claude Code runtime to dispatch that
hook. So the runtime-dispatch witness is absent, and doctor records ``needs-probe`` — surfacing the
manual command a user runs inside the real host to confirm enforcement. A future campaign that drives a
real isolated host is what can record ``protected``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import excubitor
from excubitor import probe as probe_mod
from excubitor.installers.filesystem import absolute_path, atomic_write_bytes, ensure_contained_no_symlinks
from excubitor.installers.receipts import Receipt, matcher_key, receipt_path, state_home_dir
from excubitor.installers.status import PROBE_SCHEMA, probe_path

__all__ = ["DOCTOR_SCHEMA", "run_doctor", "record_probe_state"]

DOCTOR_SCHEMA = "excubitor.doctor.v1"
_GUARD_DEFAULT_BRANCH = "guard-default-branch.py"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_receipt(runtime: str, scope: str, state_home, environ) -> "Receipt | None":
    try:
        return Receipt.from_json(receipt_path(runtime, scope, state_home, environ).read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def _file_checks(receipt: Receipt) -> dict:
    present, drifted, missing = [], [], []
    for owned in receipt.files:
        path = Path(owned.path)
        if not path.exists():
            missing.append(owned.path)
        elif Receipt.hash_file(path) == owned.sha256:
            present.append(owned.path)
        else:
            drifted.append(owned.path)
    return {"present": len(present), "drifted": drifted, "missing": missing}


def _registration_checks(receipt: Receipt) -> dict:
    """Confirm each receipt-owned registration is actually present in the live settings file."""
    try:
        settings = json.loads(Path(receipt.settings_path).read_text("utf-8"))
        pre = settings.get("hooks", {}).get("PreToolUse", [])
    except (FileNotFoundError, ValueError, AttributeError):
        pre = []
    live = set()
    for entry in pre if isinstance(pre, list) else []:
        if not isinstance(entry, dict):
            continue
        for handler in entry.get("hooks", []) if isinstance(entry.get("hooks"), list) else []:
            if isinstance(handler, dict):
                live.add((matcher_key(entry.get("matcher", "")), handler.get("command"),
                          handler.get("timeout")))
    missing = [r.command for r in receipt.registrations
               if (matcher_key(r.matcher), r.command, r.timeout) not in live]
    return {"expected": len(receipt.registrations), "missing": missing}


def _staged_guard(receipt: Receipt, basename: str) -> "str | None":
    for owned in receipt.files:
        if os.path.basename(owned.path) == basename:
            return owned.path
    return None


def record_probe_state(runtime: str, scope: str, state: str, detail: str,
                       state_home=None, environ=None, now: "str | None" = None) -> None:
    """Persist only Campaign-2-honest states; ``protected`` requires a future witness schema."""
    if state not in {"needs-probe", "failed"}:
        raise ValueError(
            f"Campaign 2 cannot record probe state {state!r}; protected requires a versioned host witness"
        )
    path = probe_path(runtime, scope, state_home, environ)
    root = absolute_path(state_home_dir(state_home, environ))
    ensure_contained_no_symlinks(path, root, label="probe state path")
    record = {"schema": PROBE_SCHEMA, "state": state, "at": now or _now_iso(), "detail": detail}
    atomic_write_bytes(
        path, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"), 0o600, root
    )


def run_doctor(runtime: str, scope: str, do_probe: bool = False, state_home: "str | None" = None,
               environ: "dict[str, str] | None" = None, now: "str | None" = None) -> dict:
    """Diagnose ``runtime``/``scope`` and, if ``do_probe``, run the harmless-denial probe.

    Returns a schema-tagged report. The ``protection`` verdict is ``needs-probe`` unless a real
    runtime-dispatch witness confirms enforcement — which the CLI cannot produce for Claude Code, so
    ``--probe`` here yields (and records) ``needs-probe``, plus a hook-level diagnostic and the manual
    command to confirm on a real host.
    """
    receipt = _load_receipt(runtime, scope, state_home, environ)
    report: dict = {
        "schema": DOCTOR_SCHEMA,
        "runtime": runtime,
        "scope": scope,
        "excubitor_version": excubitor.__version__,
        "installed": receipt is not None,
    }
    if receipt is None:
        report["protection"] = "not-installed"
        return report

    report["installed_version"] = receipt.excubitor_version
    report["files"] = _file_checks(receipt)
    report["registrations"] = _registration_checks(receipt)

    if not do_probe:
        report["protection"] = "needs-probe"
        report["probe"] = {"state": "needs-probe", "detail": "run with --probe to attempt a probe"}
        return report

    # --- the probe -------------------------------------------------------------------------------
    guard = _staged_guard(receipt, _GUARD_DEFAULT_BRANCH)
    hook_witness: dict
    if guard is None:
        hook_witness = {"ran": False, "denied": False, "detail": "staged guard not found in receipt"}
    else:
        try:
            sandbox = probe_mod.create_sandbox()
        except RuntimeError as exc:
            hook_witness = {"ran": False, "denied": False, "detail": str(exc)}
        else:
            try:
                # Give the staged guard a PYTHONPATH to the installed core (as a pip-installed host has),
                # so the hook-level diagnostic reflects the hook's real decision rather than an import miss.
                env = dict(os.environ if environ is None else environ)
                pkg_parent = str(Path(excubitor.__file__).resolve().parent.parent)
                env["PYTHONPATH"] = os.pathsep.join(filter(None, [pkg_parent, env.get("PYTHONPATH", "")]))
                outcome = probe_mod.run_hook_subprocess(guard, sandbox, env=env)
                hook_witness = {"ran": True, "denied": outcome.denied,
                                "marker_untouched": outcome.marker_untouched,
                                "reason": outcome.reason, "detail": outcome.detail}
            finally:
                sandbox.cleanup()

    # No real RUNTIME-dispatch witness is available from the CLI → needs-probe, never protected.
    state = "needs-probe"
    detail = (
        "hook-level probe " + ("denied the synthetic action" if hook_witness.get("denied")
                               else "did NOT deny (see hook_witness)")
        + "; no real runtime-dispatch witness — run the manual command inside the host to confirm"
    )
    record_probe_state(runtime, scope, state, detail, state_home, environ, now)
    report["protection"] = state
    report["probe"] = {"state": state, "detail": detail, "hook_witness": hook_witness}
    report["manual_verification"] = (
        "Inside the real runtime, on a throwaway repo checked out on its default branch, attempt an "
        "Edit/Write and confirm the host reports Excubitor's structured denial and no file was created."
    )
    return report
