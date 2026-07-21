"""Tests for status, print-config, compatibility reporting, and stable JSON (C2.7).

The load-bearing honesty check: a freshly installed runtime with all files present but no host probe
reports protection == 'needs-probe', never 'protected'. Also covers drift/missing reporting, the
supported-vs-designed compatibility split, config provenance, and JSON stability.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from excubitor.cli import main as cli_main
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


# --- status: protection is never inferred from file presence ---------------------------------------

def test_installed_but_unprobed_is_needs_probe(installed) -> None:
    data = status_mod.gather_status()
    inst = data["installations"][0]
    assert inst["runtime"] == "claude-code"
    assert inst["files"]["present"] == 5
    assert inst["registrations"] == 4
    # All files present, all registrations intact — but no probe → NOT protected.
    assert inst["protection"] == "needs-probe"
    assert inst["probe"]["state"] == "needs-probe"


def test_recorded_probe_flips_protection(installed) -> None:
    _home, state = installed
    ppath = status_mod.probe_path("claude-code", "user")
    ppath.parent.mkdir(parents=True, exist_ok=True)
    ppath.write_text(json.dumps({"schema": status_mod.PROBE_SCHEMA, "state": "protected",
                                 "at": "2026-07-21T00:00:00Z", "detail": "denied + no marker"}))
    inst = status_mod.gather_status()["installations"][0]
    assert inst["protection"] == "protected"


def test_drift_and_missing_reported(installed) -> None:
    home, _state = installed
    (home / ".claude" / "hooks" / "guard-loop-vc.py").write_text("# tampered\n")
    (home / ".claude" / "hooks" / "guard-one-unit.py").unlink()
    inst = status_mod.gather_status()["installations"][0]
    assert any("guard-loop-vc.py" in p for p in inst["files"]["drifted"])
    assert any("guard-one-unit.py" in p for p in inst["files"]["missing"])


def test_compatibility_split_is_honest() -> None:
    data = status_mod.gather_status()
    assert data["supported_runtimes"] == ["claude-code"]
    assert "codex" in data["designed_not_supported"]
    assert "claude-code" not in data["designed_not_supported"]
    assert data["core_protocol"] == "excubitor.pre_tool.v1"


def test_no_installations_is_clean(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EXCUBITOR_STATE_HOME", str(tmp_path / "empty"))
    data = status_mod.gather_status()
    assert data["installations"] == []


# --- status CLI + JSON stability -------------------------------------------------------------------

def test_status_json_is_stable_and_schema_tagged(installed, capsys) -> None:
    assert cli_main(["status", "--json"]) == 0
    first = capsys.readouterr().out
    assert cli_main(["status", "--json"]) == 0
    second = capsys.readouterr().out
    assert first == second  # deterministic
    parsed = json.loads(first)
    assert parsed["schema"] == "excubitor.status.v1"
    assert parsed["installations"][0]["protection"] == "needs-probe"


def test_status_text_reports_needs_probe(installed, capsys) -> None:
    assert cli_main(["status"]) == 0
    out = capsys.readouterr().out
    assert "claude-code/user" in out
    assert "needs-probe" in out
    assert "supported runtimes:" in out


# --- print-config ----------------------------------------------------------------------------------

def test_print_config_json_shows_provenance(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("EXCUBITOR_LOOP_GUARD", "conservative")
    monkeypatch.chdir(tmp_path)
    assert cli_main(["print-config", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["schema"] == "excubitor.effective-config.v1"
    assert data["settings"]["loop_mode"]["value"] == "conservative"
    assert data["settings"]["loop_mode"]["source"] == "env:EXCUBITOR_LOOP_GUARD"
    assert data["settings"]["opt_out_marker"]["source"] == "default"


def test_print_config_surfaces_legacy_warning(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("EXCUBITOR_LOOP_GUARD", raising=False)
    monkeypatch.setenv("CLAUDE_LOOP_GUARD", "1")
    monkeypatch.chdir(tmp_path)
    assert cli_main(["print-config", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["settings"]["loop_mode"]["value"] == "conservative"
    assert "(legacy)" in data["settings"]["loop_mode"]["source"]
    assert any("legacy" in w for w in data["warnings"])


def test_print_config_text(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli_main(["print-config"]) == 0
    out = capsys.readouterr().out
    assert "effective configuration" in out
    assert "loop_mode" in out
