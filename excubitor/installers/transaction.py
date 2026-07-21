"""The install transaction: atomic staging, exact registration, rollback, and crash recovery.

This is the write half of the installer. It executes a :class:`~excubitor.installers.plan.InstallPlan`
as an all-or-nothing transaction:

1. **Recover** any prior interrupted transaction for this target first (crash consistency).
2. **Validate** the target settings.json and policy — a malformed structure or unknown version stops
   here, before a single byte is written.
3. **Journal** the exact prior state (the settings bytes and every staged file's prior bytes, or
   "absent") to the state dir *before* mutating, so an interruption is always recoverable.
4. **Stage** each artifact atomically (write-temp-then-`os.replace`) and verify its hash.
5. **Register** the exact-tuple hooks into settings.json, preserving unrelated entries.
6. **Commit** a hash-bound receipt, then delete the journal.

If any step after journalling fails, :func:`rollback` restores the journalled prior state exactly —
files we created are deleted, files we overwrote are restored, and the settings file is restored
verbatim — and only then is the failure surfaced. Rollback and uninstall touch **only** receipt- or
journal-owned bytes; unrelated configuration is never removed.

Byte preservation contract: settings.json is rewritten in canonical JSON (2-space indent, insertion
order). Unrelated entries are carried through as their exact parsed values, so for a file already in
canonical form an install→uninstall cycle is byte-for-byte. A mid-transaction rollback restores the
prior file verbatim from the journal regardless of formatting.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from excubitor.installers import receipts as receipts_mod
from excubitor.installers import validate
from excubitor.installers.plan import InstallPlan, build_install_plan
from excubitor.installers.receipts import (
    OwnedFile,
    OwnedRegistration,
    Receipt,
    matcher_key,
    receipt_path,
    state_home_dir,
)
from excubitor.installers.runtime import RuntimeProfile, RuntimeTarget

__all__ = ["TransactionError", "InstallResult", "apply_install", "rollback", "recover"]

_FILE_MODE = 0o644
_STATE_MODE = 0o600


class TransactionError(RuntimeError):
    """A transaction failed after validation; the prior state has been rolled back before it is raised."""


@dataclass(frozen=True)
class InstallResult:
    """The outcome of a successful (or idempotent no-op) install."""

    receipt: Receipt
    changed: bool
    messages: "tuple[str, ...]"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _journal_path(runtime: str, scope: str, state_home: "str | None",
                  environ: "dict[str, str] | None") -> Path:
    return state_home_dir(state_home, environ) / "journals" / f"{runtime}-{scope}.json"


def _atomic_write_bytes(path: Path, data: bytes, mode: int) -> None:
    """Write ``data`` to ``path`` atomically: temp in the same dir, fsync, ``os.replace``, chmod."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    os.chmod(path, mode)


def _b64(data: "bytes | None") -> "str | None":
    return None if data is None else base64.b64encode(data).decode("ascii")


def _unb64(text: "str | None") -> "bytes | None":
    return None if text is None else base64.b64decode(text.encode("ascii"))


def _read_bytes_or_none(path: Path) -> "bytes | None":
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


# --- settings registration merge -------------------------------------------------------------------

def _canonical_entry(reg: OwnedRegistration) -> dict:
    return {
        "matcher": reg.matcher,
        "hooks": [{"type": reg.handler_type, "command": reg.command, "timeout": reg.timeout}],
    }


def _handler_tuple(entry_matcher: object, handler: dict) -> tuple:
    return (
        matcher_key(entry_matcher if isinstance(entry_matcher, str) else ""),
        handler.get("type"),
        handler.get("command"),
        handler.get("timeout"),
    )


def merge_registrations(
    pre: list, wanted: "list[OwnedRegistration]", prior: "list[OwnedRegistration]"
) -> bool:
    """Merge ``wanted`` into the ``hooks.PreToolUse`` list ``pre`` (mutated in place). Idempotent.

    Ownership for removal is the exact tuple of ``wanted ∪ prior`` (the current canonical set plus what
    a prior receipt recorded), so a re-install or an upgrade never leaves a stale duplicate and never
    touches an unrelated user handler. Returns whether anything changed.
    """
    desired = [_canonical_entry(w) for w in wanted]
    owned = {(matcher_key(w.matcher), w.handler_type, w.command, w.timeout) for w in (*wanted, *prior)}
    changed = False

    result: list = []
    for entry in pre:
        if entry in desired:  # already exactly one of ours → keep verbatim (idempotent)
            result.append(entry)
            continue
        if not isinstance(entry, dict):
            result.append(entry)
            continue
        handlers = entry.get("hooks", [])
        if not isinstance(handlers, list):
            result.append(entry)
            continue
        kept = [h for h in handlers
                if not (isinstance(h, dict) and _handler_tuple(entry.get("matcher"), h) in owned)]
        if len(kept) != len(handlers):
            changed = True
            if kept:
                new_entry = dict(entry)
                new_entry["hooks"] = kept
                result.append(new_entry)
            # else: entry held only our handlers → drop it
        else:
            result.append(entry)

    for d in desired:
        if d not in result:
            result.append(d)
            changed = True

    pre[:] = result
    return changed


# --- the transaction -------------------------------------------------------------------------------

def _load_prior_receipt(runtime: str, scope: str, state_home, environ) -> "Receipt | None":
    path = receipt_path(runtime, scope, state_home, environ)
    try:
        return Receipt.from_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None


def apply_install(
    profile: RuntimeProfile,
    target: RuntimeTarget,
    plan: "InstallPlan | None" = None,
    state_home: "str | None" = None,
    environ: "dict[str, str] | None" = None,
    allow_downgrade: bool = False,
    now: "str | None" = None,
) -> InstallResult:
    """Apply an install transactionally and return an :class:`InstallResult`.

    Recovers any interrupted prior transaction, validates, then stages+registers+commits atomically
    with a journal. Refuses a downgrade (an existing receipt from a newer Excubitor) unless
    ``allow_downgrade``. Raises :class:`TransactionError` (after rolling back) on any post-journal
    failure, and ``ValueError`` on a validation failure (nothing written).
    """
    runtime, scope = target.runtime, target.scope.value
    plan = plan or build_install_plan(profile, target)

    # 0. Recover any interrupted transaction for this target before doing anything else.
    recover(runtime, scope, state_home, environ)

    prior_receipt = _load_prior_receipt(runtime, scope, state_home, environ)
    if prior_receipt is not None and not allow_downgrade:
        if _is_newer(prior_receipt.excubitor_version, receipts_mod.current_version()):
            raise ValueError(
                f"refusing downgrade: {runtime}/{scope} was installed by Excubitor "
                f"{prior_receipt.excubitor_version}, this is {receipts_mod.current_version()} "
                f"(pass allow_downgrade to override)"
            )

    # 1. Validate the destination settings (and policy is validated by the caller/CLI); stop on problems.
    settings_path = Path(target.settings_path)
    prior_settings_bytes = _read_bytes_or_none(settings_path)
    if prior_settings_bytes:
        try:
            data = json.loads(prior_settings_bytes)
        except ValueError as exc:
            raise ValueError(f"refusing to write: {settings_path} is not valid JSON ({exc})") from exc
    else:
        data = {}
    result = validate.validate_settings(data)  # also rejects a non-object root
    if not result.ok:
        raise ValueError(
            f"refusing to write: {settings_path} is malformed: " + "; ".join(result.problems)
        )

    # 2. Journal the exact prior state BEFORE any mutation.
    staged_targets = [Path(a.target_path) for a in plan.staged_files]
    file_backups = {str(p): _b64(_read_bytes_or_none(p)) for p in staged_targets}
    journal = {
        "runtime": runtime,
        "scope": scope,
        "settings_path": str(settings_path),
        "settings_backup": _b64(prior_settings_bytes),
        "file_backups": file_backups,
        "created_at": now or _now_iso(),
    }
    jpath = _journal_path(runtime, scope, state_home, environ)
    _atomic_write_bytes(jpath, (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode(), _STATE_MODE)

    try:
        # 3. Stage each artifact atomically and verify its hash.
        owned_files: list[OwnedFile] = []
        files_changed = False
        artifacts = {a.basename: a for a in profile.artifacts()}
        for action in plan.staged_files:
            artifact = artifacts[action.basename]
            dest = Path(action.target_path)
            prior = _unb64(file_backups.get(str(dest)))
            if prior is None or hashlib.sha256(prior).hexdigest() != artifact.sha256:
                files_changed = True
            _atomic_write_bytes(dest, artifact.content, _FILE_MODE)
            actual = Receipt.hash_file(dest)
            if actual != artifact.sha256:
                raise TransactionError(f"staged file hash mismatch at {dest}")
            owned_files.append(OwnedFile(path=str(dest), sha256=artifact.sha256))

        # 4. Register the exact-tuple hooks, preserving unrelated entries.
        wanted = [
            OwnedRegistration(matcher=r.matcher, command=r.command, timeout=r.timeout,
                              handler_type=r.handler_type, event=r.event)
            for r in profile.registrations(target)
        ]
        pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
        prior_regs = list(prior_receipt.registrations) if prior_receipt else []
        merge_registrations(pre, wanted, prior_regs)  # mutates `pre`; byte-diff below decides `written`
        new_settings = (json.dumps(data, indent=2) + "\n").encode("utf-8")
        settings_written = new_settings != (prior_settings_bytes or b"")
        if settings_written:
            _atomic_write_bytes(settings_path, new_settings, _FILE_MODE)

        # 5. Commit the receipt, then delete the journal.
        receipt = Receipt(
            runtime=runtime,
            scope=scope,
            settings_path=str(settings_path),
            excubitor_version=receipts_mod.current_version(),
            installed_at=now or _now_iso(),
            files=tuple(owned_files),
            registrations=tuple(wanted),
        )
        _atomic_write_bytes(
            receipt_path(runtime, scope, state_home, environ), receipt.to_json().encode(), _STATE_MODE
        )
    except Exception as exc:  # any post-journal failure → roll back the exact prior state, then surface
        rollback(runtime, scope, state_home, environ)
        if isinstance(exc, TransactionError):
            raise
        raise TransactionError(f"install failed and was rolled back: {exc}") from exc

    jpath.unlink(missing_ok=True)
    messages = (f"staged {len(owned_files)} file(s)",
                "settings updated" if settings_written else "settings already current")
    return InstallResult(receipt=receipt, changed=settings_written or files_changed, messages=messages)


def rollback(runtime: str, scope: str, state_home: "str | None" = None,
             environ: "dict[str, str] | None" = None) -> bool:
    """Restore the exact state recorded in this target's journal, then remove the journal.

    Files we created are deleted; files we overwrote are restored to their prior bytes; the settings
    file is restored verbatim (or deleted if it did not exist before). A no-op when no journal exists.
    Returns whether a rollback happened.
    """
    jpath = _journal_path(runtime, scope, state_home, environ)
    try:
        journal = json.loads(jpath.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return False

    for path_str, backup in journal.get("file_backups", {}).items():
        path = Path(path_str)
        prior = _unb64(backup)
        if prior is None:
            path.unlink(missing_ok=True)  # we created it → remove it
        else:
            _atomic_write_bytes(path, prior, _FILE_MODE)  # we overwrote it → restore

    settings_path = Path(journal["settings_path"])
    settings_backup = _unb64(journal.get("settings_backup"))
    if settings_backup is None:
        settings_path.unlink(missing_ok=True)
    else:
        _atomic_write_bytes(settings_path, settings_backup, _FILE_MODE)

    jpath.unlink(missing_ok=True)
    return True


def recover(runtime: str, scope: str, state_home: "str | None" = None,
            environ: "dict[str, str] | None" = None) -> bool:
    """Recover from an interrupted install: if a journal exists, roll its target back. Idempotent."""
    return rollback(runtime, scope, state_home, environ)


def _is_newer(a: str, b: str) -> bool:
    """True iff version string ``a`` is strictly newer than ``b`` (numeric dotted compare, best-effort)."""
    def parts(v: str) -> "tuple[int, ...]":
        out = []
        for token in v.split("."):
            num = "".join(ch for ch in token if ch.isdigit())
            out.append(int(num) if num else 0)
        return tuple(out)

    return parts(a) > parts(b)
