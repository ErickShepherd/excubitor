"""Cross-platform installer robustness tests (C2.11).

The same transaction surface — clean install, repeat install, upgrade, downgrade refusal, uninstall,
rollback, malformed configuration, and interrupted operations — is exercised across path shapes that
break naive installers: directories with spaces and with non-ASCII characters. These run on whatever OS
executes the suite; the CI matrix (`.github/workflows/ci.yml`) runs them on Linux, macOS, and Windows.

Real-runner evidence for macOS and Windows is produced by that CI matrix, not locally — until it runs,
the macOS/Windows rows remain explicitly PENDING (a mock cannot substitute for a real runner).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from excubitor.installers import runtime as rt
from excubitor.installers import transaction as tx
from excubitor.installers.receipts import Receipt

# Path shapes that trip up naive installers: a plain name, spaces, and non-ASCII characters.
PATH_SHAPES = ["plain", "a home with spaces", "ünïcödé-家-мир"]


@pytest.fixture(params=PATH_SHAPES, ids=lambda s: s.replace(" ", "_"))
def env(request, tmp_path: Path, monkeypatch):
    home = tmp_path / request.param
    home.mkdir()
    state = tmp_path / (request.param + "-state")
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(state))
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home=home, project_root=None)
    return home, state, target


def _install(target, **kw):
    return tx.apply_install(rt.CLAUDE_CODE, target, **kw)


# --- clean install across path shapes --------------------------------------------------------------

def test_clean_install(env) -> None:
    home, state, target = env
    result = _install(target)
    assert result.changed
    assert (home / ".claude" / "hooks" / "guard-loop-vc.py").exists()
    receipt = Receipt.from_json((state / "receipts" / "claude-code-user.json").read_text())
    for owned in receipt.files:
        assert Receipt.hash_file(owned.path) == owned.sha256  # hash-bound even through odd paths


def test_registration_command_quotes_the_path(env) -> None:
    home, _state, target = env
    _install(target)
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    for entry in settings["hooks"]["PreToolUse"]:
        for handler in entry["hooks"]:
            # The staged script path is double-quoted, so spaces/non-ASCII don't split the command.
            assert handler["command"].startswith('python3 "')
            assert handler["command"].endswith('.py"')


def test_repeat_install_is_idempotent(env) -> None:
    _home, _state, target = env
    _install(target)
    settings_path = Path(target.settings_path)
    first = settings_path.read_bytes()
    second = _install(target)
    assert settings_path.read_bytes() == first
    assert second.changed is False


def test_uninstall_roundtrip_is_byte_for_byte(env) -> None:
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    original = json.dumps({"model": "opus", "hooks": {"PreToolUse": []}}, indent=2) + "\n"
    settings_path.write_text(original, encoding="utf-8")
    before = settings_path.read_bytes()
    _install(target)
    tx.apply_uninstall("claude-code", "user")
    assert settings_path.read_bytes() == before


# --- upgrade / downgrade across path shapes --------------------------------------------------------

def test_upgrade_over_older_receipt_succeeds(env) -> None:
    home, state, target = env
    _install(target)
    # Rewrite the receipt to look like an older install, then re-install (an upgrade).
    rpath = state / "receipts" / "claude-code-user.json"
    receipt = Receipt.from_json(rpath.read_text())
    older = Receipt(**{**receipt.__dict__, "excubitor_version": "0.0.1"})
    rpath.write_text(older.to_json())
    result = _install(target)  # must NOT be refused
    assert result.receipt.excubitor_version != "0.0.1"


def test_downgrade_over_newer_receipt_is_refused(env) -> None:
    home, state, target = env
    newer = Receipt(runtime="claude-code", scope="user",
                    settings_path=str(home / ".claude" / "settings.json"),
                    excubitor_version="99.0.0", installed_at="t")
    rpath = state / "receipts" / "claude-code-user.json"
    rpath.parent.mkdir(parents=True)
    rpath.write_text(newer.to_json())
    with pytest.raises(ValueError, match="downgrade"):
        _install(target)


# --- failure modes across path shapes --------------------------------------------------------------

def test_malformed_settings_stops_before_mutation(env) -> None:
    home, _state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"hooks": {"PreToolUse": [{"matcher": 7}]}}', encoding="utf-8")
    before = settings_path.read_bytes()
    with pytest.raises(ValueError):
        _install(target)
    assert settings_path.read_bytes() == before
    assert not (home / ".claude" / "hooks" / "guard-loop-vc.py").exists()


def test_rollback_restores_exact_prior_state(env, monkeypatch) -> None:
    home, state, target = env
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    prior = json.dumps({"model": "x", "hooks": {"PreToolUse": []}}, indent=2) + "\n"
    settings_path.write_text(prior, encoding="utf-8")
    prior_bytes = settings_path.read_bytes()
    monkeypatch.setattr(Receipt, "hash_file", staticmethod(lambda p: "deadbeef"))
    with pytest.raises(tx.TransactionError):
        _install(target)
    assert settings_path.read_bytes() == prior_bytes
    assert not (home / ".claude" / "hooks" / "guard-loop-vc.py").exists()
    assert not (state / "receipts" / "claude-code-user.json").exists()


def test_interrupted_operation_recovers(env) -> None:
    home, state, target = env
    # A leftover journal (crash mid-transaction) is recovered at the next apply.
    jpath = state / "journals" / "claude-code-user.json"
    jpath.parent.mkdir(parents=True)
    jpath.write_text(json.dumps({
        "runtime": "claude-code", "scope": "user",
        "settings_path": str(home / ".claude" / "settings.json"),
        "settings_backup": None, "file_backups": {}, "created_at": "t",
    }))
    _install(target)
    assert not jpath.exists()
    assert (state / "receipts" / "claude-code-user.json").exists()
