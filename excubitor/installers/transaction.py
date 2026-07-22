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
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from excubitor.installers import receipts as receipts_mod
from excubitor.installers import validate
from excubitor.installers.filesystem import (
    absolute_path,
    atomic_write_bytes,
    durable_unlink,
    ensure_contained_no_symlinks,
)
from excubitor.installers.plan import InstallPlan, build_install_plan
from excubitor.installers.receipts import (
    OwnedFile,
    OwnedRegistration,
    Receipt,
    matcher_key,
    receipt_path,
    state_home_dir,
)
from excubitor.installers.runtime import RuntimeProfile, RuntimeTarget, profile_for

__all__ = [
    "TransactionError",
    "RecoveryError",
    "InstallResult",
    "UninstallResult",
    "apply_install",
    "apply_uninstall",
    "rollback",
    "recover",
]

_FILE_MODE = 0o644
_STATE_MODE = 0o600
JOURNAL_SCHEMA = "excubitor.transaction.v3"
_SHA256_HEX_LENGTH = 64


class TransactionError(RuntimeError):
    """A transaction failed after validation; the prior state has been rolled back before it is raised."""


class RecoveryError(TransactionError):
    """A pending journal is invalid or does not match the selected installation target."""


@dataclass(frozen=True)
class InstallResult:
    """The outcome of a successful (or idempotent no-op) install."""

    receipt: Receipt
    changed: bool
    messages: "tuple[str, ...]"


@dataclass(frozen=True)
class UninstallResult:
    """The outcome (or dry-run preview) of an uninstall.

    ``removed_files`` are receipt-owned files whose bytes still matched (safe to remove);
    ``preserved_drifted`` are receipt-owned paths whose bytes changed since install (NOT removed —
    the user's edit is kept); ``settings_deleted`` is True when a file this install created and this
    uninstall emptied was removed.
    """

    found: bool
    removed_files: "tuple[str, ...]" = ()
    preserved_drifted: "tuple[str, ...]" = ()
    removed_registrations: int = 0
    settings_deleted: bool = False
    dry_run: bool = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _journal_path(runtime: str, scope: str, state_home: "str | None",
                  environ: "dict[str, str] | None") -> Path:
    return state_home_dir(state_home, environ) / "journals" / f"{runtime}-{scope}.json"


def _state_root(state_home, environ) -> Path:
    return absolute_path(state_home_dir(state_home, environ))


def _atomic_write_bytes(path: Path, data: bytes, mode: int, root: "Path | None" = None) -> None:
    atomic_write_bytes(path, data, mode, root or path.parent)


def _b64(data: "bytes | None") -> "str | None":
    return None if data is None else base64.b64encode(data).decode("ascii")


def _unb64(text: "str | None") -> "bytes | None":
    if text is None:
        return None
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError("invalid base64 backup data") from exc


def _read_bytes_or_none(path: Path, root: "Path | None" = None) -> "bytes | None":
    if root is not None:
        ensure_contained_no_symlinks(path, root, label="read target")
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _sha256_or_none(data: "bytes | None") -> "str | None":
    return None if data is None else hashlib.sha256(data).hexdigest()


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
    except FileNotFoundError:
        return None
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"invalid install receipt at {path}: {exc}") from exc


def _target_roots(target: RuntimeTarget, plan: InstallPlan, state_home, environ) -> tuple[Path, Path]:
    control = absolute_path(target.control_dir)
    base = control.parent
    ensure_contained_no_symlinks(control, base, label="control directory")
    ensure_contained_no_symlinks(target.settings_path, control, label="settings path")
    ensure_contained_no_symlinks(target.hooks_dir, control, label="hooks directory")
    for action in plan.staged_files:
        ensure_contained_no_symlinks(action.target_path, target.hooks_dir, label="artifact path")
    state_root = _state_root(state_home, environ)
    ensure_contained_no_symlinks(_journal_path(target.runtime, target.scope.value, state_home, environ),
                                 state_root, label="journal path")
    ensure_contained_no_symlinks(receipt_path(target.runtime, target.scope.value, state_home, environ),
                                 state_root, label="receipt path")
    return control, state_root


def _validate_receipt_target(receipt: Receipt, target: RuntimeTarget) -> None:
    if (receipt.runtime, receipt.scope, receipt.settings_path) != (
        target.runtime, target.scope.value, str(absolute_path(target.settings_path))
    ):
        raise ValueError("existing receipt does not match the selected runtime, scope, and settings path")
    for owned in receipt.files:
        ensure_contained_no_symlinks(owned.path, target.hooks_dir, label="receipt-owned artifact")


def _journal_bytes(*, operation: str, runtime: str, scope: str, settings_path: Path,
                   settings_backup: "bytes | None", receipt_file: Path,
                   receipt_backup: "bytes | None", file_backups: dict[str, "str | None"],
                   post_settings_sha256: "str | None", post_receipt_sha256: "str | None",
                   post_file_sha256: dict[str, "str | None"],
                   now: str) -> bytes:
    record = {
        "schema": JOURNAL_SCHEMA,
        "operation": operation,
        "runtime": runtime,
        "scope": scope,
        "settings_path": str(absolute_path(settings_path)),
        "settings_backup": _b64(settings_backup),
        "receipt_path": str(absolute_path(receipt_file)),
        "receipt_backup": _b64(receipt_backup),
        "owned_paths": sorted(file_backups),
        "file_backups": file_backups,
        "post_state": {
            "settings_sha256": post_settings_sha256,
            "receipt_sha256": post_receipt_sha256,
            "file_sha256": post_file_sha256,
        },
        "created_at": now,
    }
    return (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()


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
    control_root, state_root = _target_roots(target, plan, state_home, environ)

    # Recovery is target-bound. A malformed or mismatched journal is retained and fails closed.
    recover(runtime, scope, state_home, environ, profile=profile, target=target, plan=plan)

    prior_receipt = _load_prior_receipt(runtime, scope, state_home, environ)
    if prior_receipt is not None:
        _validate_receipt_target(prior_receipt, target)
    if prior_receipt is not None and not allow_downgrade:
        if _is_newer(prior_receipt.excubitor_version, receipts_mod.current_version()):
            raise ValueError(
                f"refusing downgrade: {runtime}/{scope} was installed by Excubitor "
                f"{prior_receipt.excubitor_version}, this is {receipts_mod.current_version()} "
                f"(pass allow_downgrade to override)"
            )

    # 1. Validate the destination settings (and policy is validated by the caller/CLI); stop on problems.
    settings_path = absolute_path(target.settings_path)
    prior_settings_bytes = _read_bytes_or_none(settings_path, control_root)
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

    # 2. Prove ownership before mutation. A pathname alone is never enough.
    artifacts = {a.basename: a for a in profile.artifacts()}
    staged_targets = [absolute_path(a.target_path) for a in plan.staged_files]
    new_paths = {str(p) for p in staged_targets}
    prior_by_path = {f.path: f for f in prior_receipt.files} if prior_receipt else {}
    for dest in staged_targets:
        current = _read_bytes_or_none(dest, target.hooks_dir)
        if current is None:
            continue
        owned = prior_by_path.get(str(dest))
        if owned is None:
            raise ValueError(f"refusing install: unowned artifact-path collision at {dest}")
        current_hash = hashlib.sha256(current).hexdigest()
        if current_hash != owned.sha256:
            raise ValueError(
                f"refusing upgrade: receipt-owned artifact drifted at {dest} "
                f"(expected {owned.sha256}, found {current_hash})"
            )

    stale_owned = [f for f in (prior_receipt.files if prior_receipt else ()) if f.path not in new_paths]
    for owned in stale_owned:
        current = _read_bytes_or_none(Path(owned.path), target.hooks_dir)
        if current is not None and hashlib.sha256(current).hexdigest() != owned.sha256:
            raise ValueError(f"refusing upgrade: stale receipt-owned artifact drifted at {owned.path}")

    # 3. Compute the complete committed state, then journal both sides of every mutation. Recovery may
    # restore a surface only when its current bytes still equal either the pre-state or this post-state.
    backup_paths = sorted(new_paths | {f.path for f in stale_owned})
    file_backups = {
        p: _b64(_read_bytes_or_none(Path(p), target.hooks_dir)) for p in backup_paths
    }
    rpath = absolute_path(receipt_path(runtime, scope, state_home, environ))
    receipt_backup = _read_bytes_or_none(rpath, state_root)
    wanted = [
        OwnedRegistration(matcher=r.matcher, command=r.command, timeout=r.timeout,
                          handler_type=r.handler_type, event=r.event)
        for r in profile.registrations(target)
    ]
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    prior_regs = list(prior_receipt.registrations) if prior_receipt else []
    merge_registrations(pre, wanted, prior_regs)
    new_settings = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    settings_written = new_settings != (prior_settings_bytes or b"")
    transaction_time = now or _now_iso()
    receipt = Receipt(
        runtime=runtime,
        scope=scope,
        settings_path=str(settings_path),
        excubitor_version=receipts_mod.current_version(),
        installed_at=transaction_time,
        files=tuple(
            OwnedFile(path=str(absolute_path(action.target_path)), sha256=artifacts[action.basename].sha256)
            for action in plan.staged_files
        ),
        registrations=tuple(wanted),
        settings_preexisted=(prior_receipt.settings_preexisted if prior_receipt is not None
                             else prior_settings_bytes is not None),
    )
    receipt_bytes = receipt.to_json().encode()
    post_file_sha256 = {
        path: (artifacts[Path(path).name].sha256 if path in new_paths else None)
        for path in backup_paths
    }
    jpath = _journal_path(runtime, scope, state_home, environ)
    _atomic_write_bytes(
        jpath,
        _journal_bytes(
            operation="install", runtime=runtime, scope=scope, settings_path=settings_path,
            settings_backup=prior_settings_bytes, receipt_file=rpath, receipt_backup=receipt_backup,
            file_backups=file_backups,
            post_settings_sha256=_sha256_or_none(new_settings),
            post_receipt_sha256=_sha256_or_none(receipt_bytes),
            post_file_sha256=post_file_sha256,
            now=transaction_time,
        ),
        _STATE_MODE,
        state_root,
    )

    try:
        # 4. Stage each artifact atomically and verify its hash.
        owned_files = list(receipt.files)
        files_changed = False
        for action in plan.staged_files:
            artifact = artifacts[action.basename]
            dest = absolute_path(action.target_path)
            prior = _unb64(file_backups.get(str(dest)))
            if prior is None or hashlib.sha256(prior).hexdigest() != artifact.sha256:
                files_changed = True
            _atomic_write_bytes(dest, artifact.content, _FILE_MODE, absolute_path(target.hooks_dir))
            actual = Receipt.hash_file(dest)
            if actual != artifact.sha256:
                raise TransactionError(f"staged file hash mismatch at {dest}")

        for owned in stale_owned:
            if _read_bytes_or_none(Path(owned.path), target.hooks_dir) is not None:
                durable_unlink(Path(owned.path), absolute_path(target.hooks_dir))
                files_changed = True

        # 5. Register the exact-tuple hooks, preserving unrelated entries.
        if settings_written:
            _atomic_write_bytes(settings_path, new_settings, _FILE_MODE, control_root)

        # 6. Commit the receipt. Deleting the journal is the transaction commit boundary.
        _atomic_write_bytes(rpath, receipt_bytes, _STATE_MODE, state_root)
    except Exception as exc:  # any post-journal failure → roll back the exact prior state, then surface
        rollback(runtime, scope, state_home, environ, profile=profile, target=target, plan=plan)
        if isinstance(exc, TransactionError):
            raise
        raise TransactionError(f"install failed and was rolled back: {exc}") from exc

    durable_unlink(jpath, state_root)
    messages = (f"staged {len(owned_files)} file(s)",
                "settings updated" if settings_written else "settings already current")
    return InstallResult(receipt=receipt, changed=settings_written or files_changed, messages=messages)


def _load_valid_journal(runtime: str, scope: str, state_home, environ, *,
                        profile: "RuntimeProfile | None", target: "RuntimeTarget | None",
                        plan: "InstallPlan | None") -> "tuple[dict, Path, Path, Path] | None":
    state_root = _state_root(state_home, environ)
    jpath = absolute_path(_journal_path(runtime, scope, state_home, environ))
    ensure_contained_no_symlinks(jpath, state_root, label="journal path")
    try:
        raw = jpath.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise RecoveryError(f"cannot read pending recovery journal {jpath}: {exc}") from exc
    try:
        journal = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"malformed or truncated recovery journal {jpath}: {exc}") from exc
    required = {
        "schema", "operation", "runtime", "scope", "settings_path", "settings_backup",
        "receipt_path", "receipt_backup", "owned_paths", "file_backups", "post_state", "created_at",
    }
    if not isinstance(journal, dict) or set(journal) != required:
        raise RecoveryError(f"recovery journal {jpath} has an invalid field set")
    if journal["schema"] != JOURNAL_SCHEMA or journal["operation"] not in {"install", "uninstall"}:
        raise RecoveryError(f"recovery journal {jpath} has an unsupported schema or operation")
    if (journal["runtime"], journal["scope"]) != (runtime, scope):
        raise RecoveryError(f"recovery journal {jpath} does not match {runtime}/{scope}")
    expected_receipt = absolute_path(receipt_path(runtime, scope, state_home, environ))
    if journal["receipt_path"] != str(expected_receipt):
        raise RecoveryError(f"recovery journal {jpath} names an unexpected receipt path")
    if target is None or profile is None:
        raise RecoveryError("pending recovery requires the selected runtime target; refusing to guess")
    expected_settings = absolute_path(target.settings_path)
    if journal["settings_path"] != str(expected_settings):
        raise RecoveryError(f"recovery journal {jpath} names an unexpected settings path")
    backups = journal["file_backups"]
    owned_paths = journal["owned_paths"]
    if (not isinstance(backups, dict) or not isinstance(owned_paths, list)
            or owned_paths != sorted(backups) or not all(isinstance(p, str) for p in owned_paths)):
        raise RecoveryError(f"recovery journal {jpath} has invalid owned paths")
    post_state = journal["post_state"]
    if not isinstance(post_state, dict) or set(post_state) != {
        "settings_sha256", "receipt_sha256", "file_sha256"
    }:
        raise RecoveryError(f"recovery journal {jpath} has invalid post-state")
    post_files = post_state["file_sha256"]
    if not isinstance(post_files, dict) or set(post_files) != set(owned_paths):
        raise RecoveryError(f"recovery journal {jpath} post-state paths do not match owned paths")

    def valid_digest(value: object) -> bool:
        return value is None or (
            isinstance(value, str)
            and len(value) == _SHA256_HEX_LENGTH
            and all(char in "0123456789abcdef" for char in value)
        )

    if not valid_digest(post_state["settings_sha256"]) or not valid_digest(
        post_state["receipt_sha256"]
    ) or not all(valid_digest(value) for value in post_files.values()):
        raise RecoveryError(f"recovery journal {jpath} contains invalid post-state digests")
    expected_paths = set()
    if plan is not None and journal["operation"] == "install":
        expected_paths.update(str(absolute_path(a.target_path)) for a in plan.staged_files)
    try:
        prior_bytes = _unb64(journal["receipt_backup"])
        if prior_bytes is not None:
            prior = Receipt.from_json(prior_bytes.decode("utf-8"))
            _validate_receipt_target(prior, target)
            expected_paths.update(f.path for f in prior.files)
        _unb64(journal["settings_backup"])
        for value in backups.values():
            _unb64(value)
    except (ValueError, UnicodeDecodeError, KeyError, TypeError) as exc:
        raise RecoveryError(f"recovery journal {jpath} contains invalid backup data: {exc}") from exc
    if set(owned_paths) != expected_paths:
        raise RecoveryError(f"recovery journal {jpath} owned paths do not match the selected target")
    hooks_root = absolute_path(target.hooks_dir)
    for owned_path in owned_paths:
        ensure_contained_no_symlinks(owned_path, hooks_root, label="journal-owned artifact")
    ensure_contained_no_symlinks(expected_settings, target.control_dir, label="journal settings path")
    return journal, jpath, state_root, absolute_path(target.control_dir)


def _verify_recovery_surfaces(journal: dict, *, hooks_root: Path, control_root: Path,
                              state_root: Path) -> None:
    """Refuse rollback unless every surface is still at the journalled pre- or post-state."""
    surfaces: list[tuple[Path, bytes | None, str | None, Path, str]] = []
    post = journal["post_state"]
    for path_str, backup in journal["file_backups"].items():
        surfaces.append((
            Path(path_str), _unb64(backup), post["file_sha256"][path_str], hooks_root, "artifact"
        ))
    surfaces.extend((
        (
            Path(journal["settings_path"]), _unb64(journal["settings_backup"]),
            post["settings_sha256"], control_root, "settings",
        ),
        (
            Path(journal["receipt_path"]), _unb64(journal["receipt_backup"]),
            post["receipt_sha256"], state_root, "receipt",
        ),
    ))
    for path, prior, expected_post, root, label in surfaces:
        current = _read_bytes_or_none(path, root)
        if current == prior or _sha256_or_none(current) == expected_post:
            continue
        raise RecoveryError(
            f"pending recovery {label} changed outside the journalled transaction: {path}"
        )


def rollback(runtime: str, scope: str, state_home: "str | None" = None,
             environ: "dict[str, str] | None" = None, *, profile: "RuntimeProfile | None" = None,
             target: "RuntimeTarget | None" = None, plan: "InstallPlan | None" = None) -> bool:
    """Restore the exact state recorded in this target's journal, then remove the journal.

    Files we created are deleted; files we overwrote are restored to their prior bytes; the settings
    file is restored verbatim (or deleted if it did not exist before). A no-op when no journal exists.
    Returns whether a rollback happened.
    """
    loaded = _load_valid_journal(runtime, scope, state_home, environ,
                                 profile=profile, target=target, plan=plan)
    if loaded is None:
        return False
    journal, jpath, state_root, control_root = loaded
    hooks_root = absolute_path(target.hooks_dir)  # type: ignore[union-attr]
    _verify_recovery_surfaces(
        journal, hooks_root=hooks_root, control_root=control_root, state_root=state_root
    )

    for path_str, backup in journal["file_backups"].items():
        path = Path(path_str)
        prior = _unb64(backup)
        if prior is None:
            durable_unlink(path, hooks_root)
        else:
            _atomic_write_bytes(path, prior, _FILE_MODE, hooks_root)

    settings_path = Path(journal["settings_path"])
    settings_backup = _unb64(journal.get("settings_backup"))
    if settings_backup is None:
        durable_unlink(settings_path, control_root)
    else:
        _atomic_write_bytes(settings_path, settings_backup, _FILE_MODE, control_root)

    rpath = Path(journal["receipt_path"])
    receipt_backup = _unb64(journal["receipt_backup"])
    if receipt_backup is None:
        durable_unlink(rpath, state_root)
    else:
        _atomic_write_bytes(rpath, receipt_backup, _STATE_MODE, state_root)

    durable_unlink(jpath, state_root)
    return True


def recover(runtime: str, scope: str, state_home: "str | None" = None,
            environ: "dict[str, str] | None" = None, *, profile: "RuntimeProfile | None" = None,
            target: "RuntimeTarget | None" = None, plan: "InstallPlan | None" = None) -> bool:
    """Recover from an interrupted install: if a journal exists, roll its target back. Idempotent."""
    return rollback(runtime, scope, state_home, environ, profile=profile, target=target, plan=plan)


def remove_registrations(pre: list, owned: "list[OwnedRegistration]") -> bool:
    """Remove receipt-owned handlers (exact tuple) from ``pre`` (mutated in place), preserving all else.

    A handler is removed only when its ``(matcher-set, type, command, timeout)`` exactly matches a
    receipt-owned registration — never a substring. User handlers sharing an entry are kept in place;
    an entry left with no handlers is dropped. Returns whether anything changed.
    """
    owned_tuples = {(matcher_key(r.matcher), r.handler_type, r.command, r.timeout) for r in owned}
    result: list = []
    changed = False
    for entry in pre:
        if not isinstance(entry, dict):
            result.append(entry)
            continue
        handlers = entry.get("hooks", [])
        if not isinstance(handlers, list):
            result.append(entry)
            continue
        kept = [h for h in handlers
                if not (isinstance(h, dict) and _handler_tuple(entry.get("matcher"), h) in owned_tuples)]
        if len(kept) != len(handlers):
            changed = True
            if kept:
                new_entry = dict(entry)
                new_entry["hooks"] = kept
                result.append(new_entry)
            # else: entry held only our handlers → drop it
        else:
            result.append(entry)
    pre[:] = result
    return changed


def _settings_effectively_empty(data: dict) -> bool:
    """True iff ``data`` carries no content beyond empty hook lists — so a file we created can be
    removed to restore 'absent' rather than leaving a hollow ``{"hooks": {"PreToolUse": []}}`` behind."""
    if not isinstance(data, dict):
        return False
    if set(data) - {"hooks"}:
        return False
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return False
    return all(not v for v in hooks.values())


def apply_uninstall(
    runtime: str,
    scope: str,
    state_home: "str | None" = None,
    environ: "dict[str, str] | None" = None,
    dry_run: bool = False,
    *,
    profile: "RuntimeProfile | None" = None,
    target: "RuntimeTarget | None" = None,
) -> UninstallResult:
    """Remove exactly what the receipt for ``runtime``/``scope`` owns; preserve everything else.

    Receipt-owned files are removed only when their bytes still match (a drifted file is preserved and
    reported); receipt-owned registrations are removed by exact tuple, keeping unrelated entries. A
    settings file this install created and this uninstall empties is removed, so the round trip is
    byte-for-byte. ``dry_run`` previews the disposition without writing. Journalled, so a failure rolls
    back the exact prior state.
    """
    profile = profile or profile_for(runtime)
    plan = build_install_plan(profile, target) if target is not None else None
    recover(runtime, scope, state_home, environ, profile=profile, target=target, plan=plan)
    receipt = _load_prior_receipt(runtime, scope, state_home, environ)
    if receipt is None:
        return UninstallResult(found=False, dry_run=dry_run)
    if target is None:
        raise TransactionError("uninstall requires the selected runtime target; refusing receipt-only paths")
    _validate_receipt_target(receipt, target)
    control_root, state_root = _target_roots(target, plan or build_install_plan(profile, target),
                                             state_home, environ)
    hooks_root = absolute_path(target.hooks_dir)

    # Disposition of owned files: removable (hash matches), drifted (kept), or already gone.
    removable: list[str] = []
    drifted: list[str] = []
    for owned in receipt.files:
        current = _read_bytes_or_none(Path(owned.path), hooks_root)
        if current is None:
            continue
        if hashlib.sha256(current).hexdigest() == owned.sha256:
            removable.append(owned.path)
        else:
            drifted.append(owned.path)

    settings_path = absolute_path(receipt.settings_path)
    prior_settings_bytes = _read_bytes_or_none(settings_path, control_root)
    if prior_settings_bytes:
        # Mirror apply_install's guarding: a user-corrupted settings.json (invalid JSON, or a valid
        # non-object root like `[]`) must fail as a clean TransactionError, not an unhandled
        # JSONDecodeError/AttributeError traceback out of the uninstall command handler.
        try:
            data = json.loads(prior_settings_bytes)
        except ValueError as exc:
            raise TransactionError(f"cannot uninstall: {settings_path} is not valid JSON ({exc})") from exc
        if not isinstance(data, dict):
            raise TransactionError(
                f"cannot uninstall: {settings_path} root is {type(data).__name__}, expected a JSON object"
            )
    else:
        data = {}
    pre = data.get("hooks", {}).get("PreToolUse", []) if isinstance(data.get("hooks"), dict) else []
    reg_changed = remove_registrations(pre, list(receipt.registrations))
    delete_settings = (not receipt.settings_preexisted) and _settings_effectively_empty(data)
    new_settings = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    settings_changes = delete_settings or (
        prior_settings_bytes is not None and new_settings != prior_settings_bytes
    )

    if dry_run:
        return UninstallResult(
            found=True, removed_files=tuple(removable), preserved_drifted=tuple(drifted),
            removed_registrations=sum(1 for _ in receipt.registrations) if reg_changed else 0,
            settings_deleted=delete_settings, dry_run=True,
        )

    # Journal the exact prior state (settings + every file we may delete) before mutating.
    file_backups = {p: _b64(_read_bytes_or_none(Path(p), hooks_root)) for p in removable}
    # Journal every receipt-owned path, including missing/drifted entries, so schema validation can prove
    # the recovery set exactly matches the receipt. Only matching files are actually removed.
    file_backups.update({f.path: _b64(_read_bytes_or_none(Path(f.path), hooks_root))
                         for f in receipt.files if f.path not in file_backups})
    rpath = absolute_path(receipt_path(runtime, scope, state_home, environ))
    receipt_backup = _read_bytes_or_none(rpath, state_root)
    jpath = _journal_path(runtime, scope, state_home, environ)
    _atomic_write_bytes(
        jpath,
        _journal_bytes(
            operation="uninstall", runtime=runtime, scope=scope, settings_path=settings_path,
            settings_backup=prior_settings_bytes, receipt_file=rpath, receipt_backup=receipt_backup,
            file_backups=file_backups,
            post_settings_sha256=(None if delete_settings else _sha256_or_none(
                new_settings if settings_changes else prior_settings_bytes
            )),
            post_receipt_sha256=None,
            post_file_sha256={
                path: (None if path in removable else _sha256_or_none(_unb64(backup)))
                for path, backup in file_backups.items()
            },
            now=_now_iso(),
        ),
        _STATE_MODE,
        state_root,
    )

    try:
        if delete_settings:
            durable_unlink(settings_path, control_root)
        elif settings_changes:
            _atomic_write_bytes(settings_path, new_settings, _FILE_MODE, control_root)
        for path_str in removable:
            durable_unlink(Path(path_str), hooks_root)
        durable_unlink(rpath, state_root)
    except Exception as exc:
        rollback(runtime, scope, state_home, environ, profile=profile, target=target, plan=plan)
        raise TransactionError(f"uninstall failed and was rolled back: {exc}") from exc

    durable_unlink(jpath, state_root)
    return UninstallResult(
        found=True, removed_files=tuple(removable), preserved_drifted=tuple(drifted),
        removed_registrations=sum(1 for _ in receipt.registrations) if reg_changed else 0,
        settings_deleted=delete_settings, dry_run=False,
    )


def _is_newer(a: str, b: str) -> bool:
    """True iff version string ``a`` is strictly newer than ``b`` (numeric dotted compare, best-effort)."""
    def parts(v: str) -> "tuple[int, ...]":
        out = []
        for token in v.split("."):
            num = "".join(ch for ch in token if ch.isdigit())
            out.append(int(num) if num else 0)
        return tuple(out)

    return parts(a) > parts(b)
