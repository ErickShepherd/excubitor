"""Tests for receipt-owned uninstall (C2.6).

The load-bearing property: uninstall removes only what the receipt owns and preserves unrelated
configuration byte-for-byte — an install→uninstall round trip returns a canonical settings file to its
exact prior bytes. Also covers hash-bound file removal (a drifted file is preserved), dropping a file
we created, dry-run, and the CLI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from excubitor.cli import main as cli_main
from excubitor.installers import runtime as rt
from excubitor.installers import transaction as tx


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    state = tmp_path / "state"
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(state))
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home=home, project_root=None)
    return home, state, target


def _install(target, **kw):
    return tx.apply_install(rt.CLAUDE_CODE, target, **kw)


def _uninstall(target, **kw):
    return tx.apply_uninstall(
        "claude-code", "user", profile=rt.CLAUDE_CODE, target=target, **kw
    )


def test_uninstall_removes_owned_files_and_registrations(env) -> None:
    home, state, target = env
    _install(target)
    result = _uninstall(target)
    assert result.found
    assert len(result.removed_files) == 5
    assert result.removed_registrations == 4
    hooks = home / ".claude" / "hooks"
    assert not any(hooks.glob("guard-*.py"))
    assert not (state / "receipts" / "claude-code-user.json").exists()


def test_roundtrip_preserves_unrelated_config_byte_for_byte(env) -> None:
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    original = {
        "model": "opus",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user"}]}
            ],
            "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "log.sh"}]}],
        },
        "otherKey": {"nested": [1, 2, 3]},
    }
    settings_path.write_text(json.dumps(original, indent=2) + "\n")
    before = settings_path.read_bytes()

    _install(target)
    assert settings_path.read_bytes() != before  # our entries were added
    _uninstall(target)
    assert settings_path.read_bytes() == before  # …and removing them restores the exact prior bytes


def test_uninstall_deletes_a_settings_file_it_created(env) -> None:
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    assert not settings_path.exists()
    _install(target)
    assert settings_path.exists()  # install created it
    _uninstall(target)
    assert not settings_path.exists()  # uninstall restores 'absent'


def test_uninstall_preserves_a_created_settings_file_with_user_content(env) -> None:
    """If the user added their own content after install, the created file is kept (only our bits go)."""
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    _install(target)
    data = json.loads(settings_path.read_text())
    data["model"] = "sonnet"  # user edits the file we created
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    _uninstall(target)
    assert settings_path.exists()
    after = json.loads(settings_path.read_text())
    assert after == {"model": "sonnet", "hooks": {"PreToolUse": []}}


def test_drifted_owned_file_is_preserved_not_removed(env) -> None:
    home, _state, target = env
    _install(target)
    guard = home / ".claude" / "hooks" / "guard-loop-vc.py"
    guard.write_text("# user modified this after install\n")  # drift
    result = _uninstall(target)
    assert guard.exists()  # not ours to remove — bytes changed
    assert str(guard) in result.preserved_drifted


def test_uninstall_of_nothing_is_a_clean_noop(env) -> None:
    _home, _state, target = env
    result = _uninstall(target)
    assert result.found is False


def test_dry_run_uninstall_writes_nothing(env) -> None:
    home, state, target = env
    _install(target)
    settings_bytes = (home / ".claude" / "settings.json").read_bytes()
    result = _uninstall(target, dry_run=True)
    assert result.dry_run and result.found
    assert len(result.removed_files) == 5
    # Nothing was actually removed.
    assert (home / ".claude" / "hooks" / "guard-loop-vc.py").exists()
    assert (home / ".claude" / "settings.json").read_bytes() == settings_bytes
    assert (state / "receipts" / "claude-code-user.json").exists()


def test_uninstall_leaves_user_pretooluse_hook_in_place(env) -> None:
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    user_entry = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
    settings_path.write_text(json.dumps({"hooks": {"PreToolUse": [user_entry]}}, indent=2) + "\n")
    _install(target)
    _uninstall(target)
    after = json.loads(settings_path.read_text())
    assert user_entry in after["hooks"]["PreToolUse"]


def test_cli_uninstall(env, capsys) -> None:
    home, _state, target = env
    _install(target)
    code = cli_main([
        "uninstall", "--runtime", "claude-code", "--scope", "user", "--home", str(home)
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "removed 5 file(s), 4 registration(s)" in out
