"""Tests for `doctor --probe` (C2.9).

The load-bearing contract: doctor reports `needs-probe`, never `protected`, when no real
runtime-dispatch witness exists — even when the hook-level diagnostic passes and every file/registration
is intact. It records that verdict so `status` reflects it, and prints the manual verification command.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from excubitor.cli import main as cli_main
from excubitor.installers import doctor as doctor_mod
from excubitor.installers import runtime as rt
from excubitor.installers import status as status_mod
from excubitor.installers import transaction as tx


@pytest.fixture
def installed(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    state = tmp_path / "state"
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(state))
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home=home, project_root=None)
    tx.apply_install(rt.CLAUDE_CODE, target)
    return home, state


def test_doctor_without_probe_reports_needs_probe(installed) -> None:
    report = doctor_mod.run_doctor("claude-code", "user", do_probe=False)
    assert report["installed"] is True
    assert report["files"]["present"] == 5
    assert report["registrations"]["missing"] == []
    assert report["protection"] == "needs-probe"


def test_doctor_probe_reports_needs_probe_not_protected(installed) -> None:
    report = doctor_mod.run_doctor("claude-code", "user", do_probe=True)
    # Even though the hook-level diagnostic denies, there is no runtime-dispatch witness → needs-probe.
    assert report["probe"]["hook_witness"]["ran"] is True
    assert report["probe"]["hook_witness"]["denied"] is True
    assert report["protection"] == "needs-probe"
    assert report["protection"] != "protected"
    assert "manual_verification" in report


def test_doctor_probe_records_state_reflected_by_status(installed) -> None:
    doctor_mod.run_doctor("claude-code", "user", do_probe=True)
    # status now reads the recorded probe → still needs-probe (honest).
    inst = status_mod.gather_status()["installations"][0]
    assert inst["probe"]["state"] == "needs-probe"
    assert inst["protection"] == "needs-probe"


def test_doctor_reports_drift_and_missing_registrations(installed) -> None:
    home, _state = installed
    # Tamper: drift a file and drop a registration from settings.
    (home / ".claude" / "hooks" / "guard-loop-vc.py").write_text("# tampered\n")
    settings_path = home / ".claude" / "settings.json"
    data = json.loads(settings_path.read_text())
    data["hooks"]["PreToolUse"] = [e for e in data["hooks"]["PreToolUse"]
                                   if e.get("matcher") != "*"]  # drop guard-one-unit registration
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    report = doctor_mod.run_doctor("claude-code", "user", do_probe=False)
    assert any("guard-loop-vc.py" in p for p in report["files"]["drifted"])
    assert report["registrations"]["missing"]  # the dropped registration is detected


def test_doctor_not_installed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(tmp_path / "empty"))
    report = doctor_mod.run_doctor("claude-code", "user", do_probe=True)
    assert report["installed"] is False
    assert report["protection"] == "not-installed"


# --- CLI -------------------------------------------------------------------------------------------

def test_cli_doctor_probe_json(installed, capsys) -> None:
    assert cli_main(["doctor", "--probe", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "excubitor.doctor.v1"
    assert report["protection"] == "needs-probe"


def test_cli_doctor_probe_text_shows_needs_probe(installed, capsys) -> None:
    assert cli_main(["doctor", "--probe"]) == 0
    out = capsys.readouterr().out
    assert "protection: needs-probe" in out
    assert "to confirm on a real host" in out


def test_cli_doctor_not_installed(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(tmp_path / "empty"))
    code = cli_main(["doctor", "--scope", "user"])
    assert code == 1
    assert "not installed" in capsys.readouterr().err
