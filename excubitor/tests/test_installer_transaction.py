"""Tests for the install transaction: staging, registration, rollback, recovery (C2.5).

Every test isolates the state dir via ``EXCUBITOR_STATE_HOME`` so nothing touches the real user state.
The load-bearing properties: atomic staging with hash verification, exact-tuple registration that
preserves unrelated entries, a full rollback on failure, idempotent re-install, downgrade refusal, and
recovery from an interrupted (journalled-but-uncommitted) transaction.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from excubitor.installers import receipts as receipts_mod
from excubitor.installers import runtime as rt
from excubitor.installers import transaction as tx
from excubitor.installers.receipts import Receipt


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    """An isolated (home, state_home) and the resolved Claude Code target."""
    home = tmp_path / "home"
    home.mkdir()
    state = tmp_path / "state"
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(state))
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home=home, project_root=None)
    return home, state, target


def _install(target, **kw) -> tx.InstallResult:
    return tx.apply_install(rt.CLAUDE_CODE, target, **kw)


# --- staging + registration ------------------------------------------------------------------------

def test_apply_stages_files_registers_and_writes_receipt(env) -> None:
    home, state, target = env
    result = _install(target)
    hooks = home / ".claude" / "hooks"
    for name in ("guard-loop-vc.py", "guard-default-branch.py", "guard-one-unit.py",
                 "guard-self-integrity.py", "_denial_log.py"):
        assert (hooks / name).exists()
    # settings has the four exact registrations.
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    pre = settings["hooks"]["PreToolUse"]
    matchers = {e["matcher"] for e in pre}
    assert {"Bash", "Edit|Write|NotebookEdit", "*", "Bash|Edit|Write|NotebookEdit"} <= matchers
    # receipt is hash-bound to the staged bytes.
    receipt = Receipt.from_json(
        (state / "receipts" / "claude-code-user.json").read_text()
    )
    for owned in receipt.files:
        assert Receipt.hash_file(owned.path) == owned.sha256
    assert result.changed


def test_staged_file_content_matches_source(env) -> None:
    home, _state, target = env
    _install(target)
    src = Path(rt.__file__).resolve().parent.parent.parent / "hooks" / "guard-loop-vc.py"
    staged = home / ".claude" / "hooks" / "guard-loop-vc.py"
    assert staged.read_bytes() == src.read_bytes()


# --- unrelated config preserved --------------------------------------------------------------------

def test_unrelated_settings_preserved_and_roundtrips(env) -> None:
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    original = {
        "model": "opus",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user-hook"}]}
            ],
            "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "log.sh"}]}],
        },
        "otherKey": {"nested": [1, 2, 3]},
    }
    settings_path.write_text(json.dumps(original, indent=2) + "\n")
    _install(target)
    after = json.loads(settings_path.read_text())
    # Unrelated top-level keys survive untouched.
    assert after["model"] == "opus"
    assert after["otherKey"] == {"nested": [1, 2, 3]}
    assert after["hooks"]["PostToolUse"] == original["hooks"]["PostToolUse"]
    # The user's own Bash PreToolUse hook survives (not ours to remove).
    user_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user-hook"}]}
    assert user_hook in after["hooks"]["PreToolUse"]


def test_reinstall_is_idempotent(env) -> None:
    home, _state, target = env
    _install(target)
    settings_bytes = (home / ".claude" / "settings.json").read_bytes()
    second = _install(target)
    assert (home / ".claude" / "settings.json").read_bytes() == settings_bytes  # byte-identical
    assert second.changed is False


# --- rollback on failure ---------------------------------------------------------------------------

def test_failure_rolls_back_to_exact_prior_state(env, monkeypatch) -> None:
    home, state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    prior = json.dumps({"model": "sonnet", "hooks": {"PreToolUse": []}}, indent=2) + "\n"
    settings_path.write_text(prior)
    prior_bytes = settings_path.read_bytes()

    # Force a failure after staging by making the hash check fail.
    real_hash = Receipt.hash_file
    monkeypatch.setattr(Receipt, "hash_file", staticmethod(lambda p: "deadbeef"))
    with pytest.raises(tx.TransactionError):
        _install(target)
    monkeypatch.setattr(Receipt, "hash_file", staticmethod(real_hash))

    # Everything restored: settings verbatim, no staged files, no receipt, no journal.
    assert settings_path.read_bytes() == prior_bytes
    assert not (home / ".claude" / "hooks" / "guard-loop-vc.py").exists()
    assert not (state / "receipts" / "claude-code-user.json").exists()
    assert not (state / "journals" / "claude-code-user.json").exists()


def test_malformed_settings_stops_before_mutation(env) -> None:
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"hooks": {"PreToolUse": [ {"matcher": 5} ]}}')
    before = settings_path.read_bytes()
    with pytest.raises(ValueError):
        _install(target)
    assert settings_path.read_bytes() == before  # not one byte written
    assert not (home / ".claude" / "hooks" / "guard-loop-vc.py").exists()


def test_non_json_settings_is_refused(env) -> None:
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("this is not json")
    with pytest.raises(ValueError):
        _install(target)


# --- interrupted-install recovery ------------------------------------------------------------------

def test_recovery_rolls_back_an_interrupted_transaction(env) -> None:
    home, state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    prior = json.dumps({"model": "x", "hooks": {"PreToolUse": []}}, indent=2) + "\n"
    settings_path.write_text(prior)

    # Simulate an interruption: a journal exists (mid-transaction), a guard was partly staged, and the
    # settings were partly written — but no receipt was committed.
    hooks = home / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    partial = hooks / "guard-loop-vc.py"
    partial.write_text("# half-written\n")
    settings_path.write_text('{"model": "x", "hooks": {"PreToolUse": [{"matcher": "Bash"}]}}')
    import base64

    journal = {
        "runtime": "claude-code", "scope": "user",
        "settings_path": str(settings_path),
        "settings_backup": base64.b64encode(prior.encode()).decode(),
        "file_backups": {str(partial): None},  # None = we created it → rollback deletes it
        "created_at": "t",
    }
    jpath = state / "journals" / "claude-code-user.json"
    jpath.parent.mkdir(parents=True)
    jpath.write_text(json.dumps(journal))

    assert tx.recover("claude-code", "user") is True
    assert settings_path.read_text() == prior  # settings restored verbatim
    assert not partial.exists()  # the partially-staged file removed
    assert not jpath.exists()  # journal cleared


def test_apply_recovers_before_installing(env) -> None:
    """A leftover journal from a crash is cleaned up automatically at the start of the next apply."""
    home, state, target = env
    jpath = state / "journals" / "claude-code-user.json"
    jpath.parent.mkdir(parents=True)
    settings_path = home / ".claude" / "settings.json"
    jpath.write_text(json.dumps({
        "runtime": "claude-code", "scope": "user", "settings_path": str(settings_path),
        "settings_backup": None, "file_backups": {}, "created_at": "t",
    }))
    _install(target)
    assert not jpath.exists()  # recovered, then a clean install committed
    assert (state / "receipts" / "claude-code-user.json").exists()


# --- downgrade refusal -----------------------------------------------------------------------------

def test_downgrade_is_refused(env, monkeypatch) -> None:
    home, state, target = env
    # Plant a receipt from a newer Excubitor.
    newer = Receipt(runtime="claude-code", scope="user",
                    settings_path=str(home / ".claude" / "settings.json"),
                    excubitor_version="99.0.0", installed_at="t")
    rpath = state / "receipts" / "claude-code-user.json"
    rpath.parent.mkdir(parents=True)
    rpath.write_text(newer.to_json())
    with pytest.raises(ValueError, match="downgrade"):
        _install(target)
    # But --allow-downgrade proceeds.
    result = _install(target, allow_downgrade=True)
    assert result.receipt.excubitor_version == receipts_mod.current_version()
