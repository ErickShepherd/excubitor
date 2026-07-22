"""Adversarial regressions for the Campaign 2 installer review remediation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from excubitor.installers import runtime as rt
from excubitor.installers import transaction as tx
from excubitor.installers.plan import build_install_plan
from excubitor.installers.receipts import Receipt


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    state = tmp_path / "state"
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(state))
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home, None)
    return home, state, target


def install(target, **kwargs):
    return tx.apply_install(rt.CLAUDE_CODE, target, **kwargs)


def uninstall(target, **kwargs):
    return tx.apply_uninstall(
        "claude-code", "user", profile=rt.CLAUDE_CODE, target=target, **kwargs
    )


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_fresh_unowned_collision_refuses_before_any_mutation(env) -> None:
    home, state, target = env
    collision = target.hooks_dir / "guard-loop-vc.py"
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"unrelated owner\n")
    before = tree_bytes(home)
    with pytest.raises(ValueError, match="unowned artifact-path collision"):
        install(target)
    assert tree_bytes(home) == before
    assert not state.exists()


def test_upgrade_drift_refuses_and_preserves_every_byte(env) -> None:
    home, state, target = env
    install(target, now="2026-01-01T00:00:00Z")
    drifted = target.hooks_dir / "guard-loop-vc.py"
    drifted.write_bytes(b"user edit\n")
    before_home = tree_bytes(home)
    before_state = tree_bytes(state)
    with pytest.raises(ValueError, match="artifact drifted"):
        install(target, now="2026-01-02T00:00:00Z")
    assert tree_bytes(home) == before_home
    assert tree_bytes(state) == before_state


def test_shrunk_artifact_set_removes_only_matching_stale_file(env, monkeypatch) -> None:
    _home, state, target = env
    install(target)
    original = rt.RuntimeProfile.artifacts
    monkeypatch.setattr(
        rt.RuntimeProfile, "artifacts",
        lambda self: [a for a in original(self) if a.basename != "_denial_log.py"],
    )
    install(target)
    assert not (target.hooks_dir / "_denial_log.py").exists()
    receipt = Receipt.from_json((state / "receipts" / "claude-code-user.json").read_text())
    assert all(not f.path.endswith("_denial_log.py") for f in receipt.files)


def test_shrunk_artifact_set_refuses_drifted_stale_file(env, monkeypatch) -> None:
    home, state, target = env
    install(target)
    stale = target.hooks_dir / "_denial_log.py"
    stale.write_bytes(b"drifted stale file\n")
    before_home, before_state = tree_bytes(home), tree_bytes(state)
    original = rt.RuntimeProfile.artifacts
    monkeypatch.setattr(
        rt.RuntimeProfile, "artifacts",
        lambda self: [a for a in original(self) if a.basename != "_denial_log.py"],
    )
    with pytest.raises(ValueError, match="stale receipt-owned artifact drifted"):
        install(target)
    assert tree_bytes(home) == before_home
    assert tree_bytes(state) == before_state


def test_repeat_install_preserves_original_settings_absence(env) -> None:
    _home, _state, target = env
    install(target)
    install(target)
    uninstall(target)
    assert not target.settings_path.exists()


def test_upgrade_preserves_original_settings_absence(env) -> None:
    _home, state, target = env
    install(target)
    rpath = state / "receipts" / "claude-code-user.json"
    receipt = Receipt.from_json(rpath.read_text())
    rpath.write_text(Receipt(**{**receipt.__dict__, "excubitor_version": "0.0.1"}).to_json())
    install(target)
    uninstall(target)
    assert not target.settings_path.exists()


def test_install_crash_after_receipt_write_recovers_old_receipt(env, monkeypatch) -> None:
    home, state, target = env
    install(target, now="2026-01-01T00:00:00Z")
    old_home, old_receipt = tree_bytes(home), tree_bytes(state)["receipts/claude-code-user.json"]
    real_unlink = tx.durable_unlink

    def crash_at_commit(path, root, **kwargs):
        if Path(path).parent.name == "journals":
            raise KeyboardInterrupt("simulated crash after receipt write")
        return real_unlink(path, root, **kwargs)

    monkeypatch.setattr(tx, "durable_unlink", crash_at_commit)
    with pytest.raises(KeyboardInterrupt):
        install(target, now="2026-01-02T00:00:00Z")
    monkeypatch.setattr(tx, "durable_unlink", real_unlink)
    plan = build_install_plan(rt.CLAUDE_CODE, target)
    assert tx.recover("claude-code", "user", profile=rt.CLAUDE_CODE, target=target, plan=plan)
    assert tree_bytes(home) == old_home
    assert (state / "receipts" / "claude-code-user.json").read_bytes() == old_receipt


def test_uninstall_crash_after_receipt_delete_recovers_full_install(env, monkeypatch) -> None:
    home, state, target = env
    install(target)
    before_home, before_receipt = tree_bytes(home), tree_bytes(state)["receipts/claude-code-user.json"]
    real_unlink = tx.durable_unlink

    def crash_at_commit(path, root, **kwargs):
        if Path(path).parent.name == "journals":
            raise KeyboardInterrupt("simulated crash after receipt deletion")
        return real_unlink(path, root, **kwargs)

    monkeypatch.setattr(tx, "durable_unlink", crash_at_commit)
    with pytest.raises(KeyboardInterrupt):
        uninstall(target)
    monkeypatch.setattr(tx, "durable_unlink", real_unlink)
    plan = build_install_plan(rt.CLAUDE_CODE, target)
    assert tx.recover("claude-code", "user", profile=rt.CLAUDE_CODE, target=target, plan=plan)
    assert tree_bytes(home) == before_home
    assert (state / "receipts" / "claude-code-user.json").read_bytes() == before_receipt


@pytest.mark.parametrize("surface", ["artifact", "settings", "receipt"])
def test_recovery_refuses_post_crash_third_state_before_any_mutation(
    env, monkeypatch, surface: str
) -> None:
    home, state, target = env
    install(target, now="2026-01-01T00:00:00Z")
    real_unlink = tx.durable_unlink

    def crash_at_commit(path, root, **kwargs):
        if Path(path).parent.name == "journals":
            raise KeyboardInterrupt("simulated crash after committed bytes")
        return real_unlink(path, root, **kwargs)

    monkeypatch.setattr(tx, "durable_unlink", crash_at_commit)
    with pytest.raises(KeyboardInterrupt):
        install(target, now="2026-01-02T00:00:00Z")
    monkeypatch.setattr(tx, "durable_unlink", real_unlink)

    if surface == "artifact":
        (target.hooks_dir / "guard-loop-vc.py").write_bytes(b"post-crash third-party bytes\n")
    elif surface == "settings":
        target.settings_path.write_bytes(b'{"post_crash": "third-party bytes"}\n')
    else:
        (state / "receipts" / "claude-code-user.json").write_bytes(b'{"post_crash": true}\n')
    before_home, before_state = tree_bytes(home), tree_bytes(state)
    plan = build_install_plan(rt.CLAUDE_CODE, target)

    with pytest.raises(tx.RecoveryError, match="changed outside"):
        tx.recover("claude-code", "user", profile=rt.CLAUDE_CODE, target=target, plan=plan)

    assert tree_bytes(home) == before_home
    assert tree_bytes(state) == before_state


@pytest.mark.parametrize("contents", [b"{", b"{}", b'{"schema":"wrong"}'])
def test_invalid_journal_fails_closed_without_mutation(env, contents: bytes) -> None:
    home, state, target = env
    jpath = state / "journals" / "claude-code-user.json"
    jpath.parent.mkdir(parents=True)
    jpath.write_bytes(contents)
    before_home = tree_bytes(home)
    with pytest.raises(tx.RecoveryError):
        install(target)
    assert tree_bytes(home) == before_home
    assert jpath.read_bytes() == contents


@pytest.mark.parametrize("field", ["settings_backup", "receipt_backup", "file_backup"])
def test_invalid_base64_journal_backup_is_retained_without_mutation(env, field: str) -> None:
    home, state, target = env
    plan = build_install_plan(rt.CLAUDE_CODE, target)
    settings = target.settings_path
    settings.parent.mkdir(parents=True)
    settings.write_bytes(b'{"model": "user-state"}\n')
    file_backups = {a.target_path: None for a in plan.staged_files}
    journal = json.loads(tx._journal_bytes(
        operation="install", runtime="claude-code", scope="user",
        settings_path=settings, settings_backup=settings.read_bytes(),
        receipt_file=state / "receipts" / "claude-code-user.json", receipt_backup=None,
        file_backups=file_backups,
        post_settings_sha256=tx._sha256_or_none(settings.read_bytes()),
        post_receipt_sha256=None, post_file_sha256={path: None for path in file_backups}, now="t",
    ))
    if field == "file_backup":
        journal["file_backups"][next(iter(journal["file_backups"]))] = "@@@"
    else:
        journal[field] = "@@@"
    jpath = state / "journals" / "claude-code-user.json"
    jpath.parent.mkdir(parents=True)
    original = (json.dumps(journal, sort_keys=True) + "\n").encode()
    jpath.write_bytes(original)
    before = tree_bytes(home)

    with pytest.raises(tx.RecoveryError, match="invalid backup data"):
        tx.recover("claude-code", "user", profile=rt.CLAUDE_CODE, target=target, plan=plan)

    assert tree_bytes(home) == before
    assert jpath.read_bytes() == original


def test_symlinked_hooks_directory_cannot_redirect_writes(env) -> None:
    home, state, target = env
    external = home.parent / "external"
    external.mkdir()
    (external / "sentinel").write_bytes(b"outside\n")
    target.control_dir.mkdir()
    target.hooks_dir.symlink_to(external, target_is_directory=True)
    before = tree_bytes(external)
    with pytest.raises(ValueError, match="symlink"):
        install(target)
    assert tree_bytes(external) == before
    assert not state.exists()


def test_symlinked_destination_file_cannot_redirect_writes(env) -> None:
    home, state, target = env
    external = home.parent / "external.py"
    external.write_bytes(b"outside\n")
    target.hooks_dir.mkdir(parents=True)
    (target.hooks_dir / "guard-loop-vc.py").symlink_to(external)
    with pytest.raises(ValueError, match="symlink"):
        install(target)
    assert external.read_bytes() == b"outside\n"
    assert not state.exists()


@pytest.mark.parametrize("kind", ["control", "settings", "state", "journal", "receipt"])
def test_symlinked_control_and_state_chains_are_rejected(env, kind: str) -> None:
    home, state, target = env
    external = home.parent / f"external-{kind}"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_bytes(b"outside\n")
    if kind == "control":
        target.control_dir.symlink_to(external, target_is_directory=True)
    elif kind == "settings":
        target.control_dir.mkdir()
        target.settings_path.symlink_to(sentinel)
    elif kind == "state":
        state.symlink_to(external, target_is_directory=True)
    else:
        leaf = state / ("journals" if kind == "journal" else "receipts") / "claude-code-user.json"
        leaf.parent.mkdir(parents=True)
        leaf.symlink_to(sentinel)
    with pytest.raises(ValueError, match="symlink"):
        install(target)
    assert sentinel.read_bytes() == b"outside\n"


def test_mismatched_valid_journal_is_retained_and_fails_closed(env) -> None:
    home, state, target = env
    plan = build_install_plan(rt.CLAUDE_CODE, target)
    jpath = state / "journals" / "claude-code-user.json"
    jpath.parent.mkdir(parents=True)
    journal = json.loads(tx._journal_bytes(
        operation="install", runtime="claude-code", scope="user",
        settings_path=target.settings_path, settings_backup=None,
        receipt_file=state / "receipts" / "claude-code-user.json", receipt_backup=None,
        file_backups={a.target_path: None for a in plan.staged_files},
        post_settings_sha256=None, post_receipt_sha256=None,
        post_file_sha256={a.target_path: None for a in plan.staged_files}, now="t",
    ))
    journal["settings_path"] = str(home.parent / "outside-settings.json")
    original = (json.dumps(journal, sort_keys=True) + "\n").encode()
    jpath.write_bytes(original)
    with pytest.raises(tx.RecoveryError, match="unexpected settings path"):
        install(target)
    assert jpath.read_bytes() == original


def test_prepositioned_fixed_temp_symlink_is_never_followed(env) -> None:
    home, _state, target = env
    external = home.parent / "external.tmp"
    external.write_bytes(b"outside\n")
    target.hooks_dir.mkdir(parents=True)
    planted = target.hooks_dir / "guard-loop-vc.py.tmp"
    planted.symlink_to(external)
    install(target)
    assert external.read_bytes() == b"outside\n"
    assert planted.is_symlink()
