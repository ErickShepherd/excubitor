"""Codex project/user registration, trust handoff, rollback, and self-integrity tests."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from excubitor.adapters import codex
from excubitor.cli import main as cli_main
from excubitor.installers import doctor as doctor_mod
from excubitor.installers import plan as plan_mod
from excubitor.installers import runtime as rt
from excubitor.installers import status as status_mod
from excubitor.installers import transaction as tx
from excubitor.installers.receipts import Receipt, receipt_path


def _target(tmp_path: Path, scope: rt.Scope):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    return home, project, rt.CODEX.target(scope, home=home, project_root=project)


def test_codex_profile_and_plan_are_native_and_write_nothing(tmp_path: Path) -> None:
    home, project, user = _target(tmp_path, rt.Scope.USER)
    project_target = rt.CODEX.target(rt.Scope.PROJECT, home=home, project_root=project)
    assert user.settings_path == home / ".codex" / "hooks.json"
    assert project_target.settings_path == project / ".codex" / "hooks.json"
    assert rt.CODEX.artifacts() == []

    before = list(tmp_path.rglob("*"))
    plan = plan_mod.build_install_plan(rt.CODEX, project_target)
    rendered = plan_mod.render_plan(plan)
    after = list(tmp_path.rglob("*"))

    assert before == after
    assert plan.staged_files == ()
    assert len(plan.registrations) == 1
    registration = plan.registrations[0]
    assert registration.matcher == "Bash|apply_patch"
    assert "-m excubitor.adapters.codex" in registration.command
    assert not any(action.target_path == str(project_target.hooks_dir) for action in plan.actions)
    assert str(project_target.settings_path) in rendered
    assert "/hooks" in rendered
    assert "not performed by the installer" in rendered
    assert "project configuration trust review" in rendered


@pytest.mark.parametrize("scope", [rt.Scope.USER, rt.Scope.PROJECT])
def test_codex_install_receipt_idempotence_and_uninstall_roundtrip(
    tmp_path: Path, monkeypatch, scope: rt.Scope
) -> None:
    home, _project, target = _target(tmp_path, scope)
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(tmp_path / "state"))
    target.settings_path.parent.mkdir(parents=True)
    original = {
        "description": "user hooks",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user"}]}
            ],
            "PostToolUse": [{"hooks": [{"type": "command", "command": "echo post"}]}],
        },
    }
    target.settings_path.write_bytes((json.dumps(original, indent=2) + "\n").encode("utf-8"))
    prior = target.settings_path.read_bytes()

    first = tx.apply_install(rt.CODEX, target)
    installed_bytes = target.settings_path.read_bytes()
    second = tx.apply_install(rt.CODEX, target)

    assert first.changed is True
    assert second.changed is False
    assert target.settings_path.read_bytes() == installed_bytes
    live = json.loads(installed_bytes)
    assert live["description"] == "user hooks"
    assert original["hooks"]["PostToolUse"] == live["hooks"]["PostToolUse"]
    codex_entries = [
        entry for entry in live["hooks"]["PreToolUse"]
        if entry.get("matcher") == "Bash|apply_patch"
    ]
    assert len(codex_entries) == 1
    assert "-m excubitor.adapters.codex" in codex_entries[0]["hooks"][0]["command"]

    receipt = Receipt.from_json(receipt_path("codex", scope.value).read_text(encoding="utf-8"))
    assert receipt.settings_path == str(target.settings_path.resolve())
    assert receipt.files == ()
    assert len(receipt.registrations) == 1
    assert receipt.registrations[0].matcher == "Bash|apply_patch"

    result = tx.apply_uninstall(
        "codex", scope.value, profile=rt.CODEX, target=target
    )
    assert result.removed_files == ()
    assert result.removed_registrations == 1
    assert target.settings_path.read_bytes() == prior
    assert not target.hooks_dir.exists()
    assert home.exists()


def test_codex_config_only_failure_rolls_back_exactly(tmp_path: Path, monkeypatch) -> None:
    _home, _project, target = _target(tmp_path, rt.Scope.USER)
    state = tmp_path / "state"
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(state))
    target.settings_path.parent.mkdir(parents=True)
    prior = b'{"description": "before", "hooks": {"PreToolUse": []}}\n'
    target.settings_path.write_bytes(prior)
    rpath = receipt_path("codex", "user")
    real_write = tx._atomic_write_bytes
    failed = False

    def fail_first_receipt_write(path, data, mode, root=None):
        nonlocal failed
        if Path(path).resolve() == rpath.resolve() and not failed:
            failed = True
            raise OSError("synthetic receipt failure")
        return real_write(path, data, mode, root)

    monkeypatch.setattr(tx, "_atomic_write_bytes", fail_first_receipt_write)
    with pytest.raises(tx.TransactionError, match="rolled back"):
        tx.apply_install(rt.CODEX, target)

    assert target.settings_path.read_bytes() == prior
    assert not rpath.exists()
    assert not (state / "journals" / "codex-user.json").exists()
    assert not target.hooks_dir.exists()


@pytest.mark.parametrize("leaf", ["a home with spaces", "ünïcödé-家-мир"])
def test_codex_registration_executes_from_non_ascii_and_spaced_targets(
    tmp_path: Path, monkeypatch, leaf: str
) -> None:
    home = tmp_path / leaf
    home.mkdir()
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(tmp_path / "state"))
    target = rt.CODEX.target(rt.Scope.USER, home=home, project_root=None)
    receipt = tx.apply_install(rt.CODEX, target).receipt
    payload = {
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
    }
    environment = dict(os.environ)
    environment["EXCUBITOR_LOOP_GUARD"] = "conservative"
    result = subprocess.run(
        receipt.registrations[0].command,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        shell=True,
        env=environment,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_cli_install_and_doctor_surface_codex_trust_gate(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(tmp_path / "state"))

    assert cli_main(["install", "--runtime", "codex", "--home", str(home)]) == 0
    output = capsys.readouterr().out
    assert "installed codex/user" in output
    assert "NEEDS TRUST" in output
    assert "/hooks" in output
    assert str(home / ".codex" / "hooks.json") in output
    assert "NOT protected" in output

    report = doctor_mod.run_doctor("codex", "user", do_probe=False)
    assert report["registrations"]["missing"] == []
    assert report["trust"]["state"] == "needs-review"
    assert report["protection"] == "needs-trust"
    assert any("/hooks" in step for step in report["trust"]["handoff"])

    probe_report = doctor_mod.run_doctor("codex", "user", do_probe=True)
    assert probe_report["protection"] == "needs-trust"
    assert "runtime-dispatch witness" in probe_report["probe"]["detail"]

    installation = status_mod.gather_status()["installations"][0]
    assert installation["runtime"] == "codex"
    assert installation["files"]["present"] == 0
    assert installation["registrations"] == 1
    assert installation["trust"]["state"] == "needs-review"
    assert installation["protection"] == "needs-trust"


def test_active_codex_registration_surfaces_are_self_protected(
    tmp_path: Path, monkeypatch
) -> None:
    _home, _project, target = _target(tmp_path, rt.Scope.USER)
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(tmp_path / "state"))
    result = tx.apply_install(rt.CODEX, target)
    command = result.receipt.registrations[0].command
    assert "-m excubitor.adapters.codex" in command

    for protected_path in (Path(codex.__file__).resolve(), target.settings_path.resolve()):
        payload = {
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "apply_patch",
            "tool_input": {
                "command": (
                    f"*** Begin Patch\n*** Update File: {protected_path}\n"
                    "@@\n-old\n+new\n*** End Patch"
                )
            },
        }
        decision = codex.decide(payload, {"EXCUBITOR_LOOP_GUARD": "conservative"})
        assert decision.is_deny
        assert decision.policy == "self-integrity"

    controls = {path.name for path in rt.CODEX.control_paths(target)}
    assert controls == {"hooks.json", "config.toml"}
