"""Tests for runtime discovery and the deterministic, write-nothing install plan (C2.3).

The load-bearing proof: building and rendering a plan against an isolated home leaves the filesystem
byte-for-byte unchanged. Also covers discovery determinism, per-scope path resolution, artifact hashing
against the real guard scripts, exact-tuple registrations, and the CLI `install --dry-run` wiring.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from excubitor.cli import main as cli_main
from excubitor.installers import plan as plan_mod
from excubitor.installers import runtime as rt

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "hooks"


def _snapshot(root: Path) -> "dict[str, str]":
    """Map every file under ``root`` to its SHA-256 — a byte-for-byte filesystem fingerprint."""
    out: "dict[str, str]" = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


# --- discovery -------------------------------------------------------------------------------------

def test_discovery_is_deterministic_and_reads_only(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    before = _snapshot(tmp_path)
    first = rt.discover(home=home, scope=rt.Scope.USER)
    second = rt.discover(home=home, scope=rt.Scope.USER)
    assert [t.runtime for t in first] == [t.runtime for t in second] == ["claude-code"]
    assert all(not t.detected for t in first)  # nothing there yet
    assert _snapshot(tmp_path) == before  # discovery created nothing


def test_user_scope_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home=home, project_root=None)
    assert target.control_dir == home / ".claude"
    assert target.settings_path == home / ".claude" / "settings.json"
    assert target.hooks_dir == home / ".claude" / "hooks"


def test_project_scope_uses_local_settings(tmp_path: Path) -> None:
    proj = tmp_path / "repo"
    target = rt.CLAUDE_CODE.target(rt.Scope.PROJECT, home=tmp_path, project_root=proj)
    assert target.settings_path == proj / ".claude" / "settings.local.json"


def test_detection_flips_when_control_dir_exists(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    assert rt.CLAUDE_CODE.target(rt.Scope.USER, home=home, project_root=None).detected is True


def test_unsupported_runtime_is_refused_not_faked() -> None:
    with pytest.raises(KeyError):
        rt.profile_for("codex")


# --- artifacts and registrations -------------------------------------------------------------------

def test_artifacts_match_real_guard_scripts() -> None:
    artifacts = {a.basename: a for a in rt.CLAUDE_CODE.artifacts()}
    for name in ("guard-loop-vc.py", "guard-default-branch.py", "guard-one-unit.py",
                 "guard-self-integrity.py", "_denial_log.py"):
        assert name in artifacts
        expected = hashlib.sha256((HOOKS_DIR / name).read_bytes()).hexdigest()
        assert artifacts[name].sha256 == expected


def test_registrations_are_exact_tuples(tmp_path: Path) -> None:
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home=tmp_path, project_root=None)
    regs = {r.script: r for r in rt.CLAUDE_CODE.registrations(target)}
    assert regs["guard-default-branch.py"].matcher == "Edit|Write|NotebookEdit"
    assert regs["guard-loop-vc.py"].matcher == "Bash"
    assert regs["guard-one-unit.py"].matcher == "*"
    assert regs["guard-self-integrity.py"].matcher == "Bash|Edit|Write|NotebookEdit"
    for reg in regs.values():
        assert reg.timeout == rt.CANON_TIMEOUT
        assert reg.event == "PreToolUse"
        assert str(target.hooks_dir) in reg.command


def test_missing_artifact_source_is_a_precise_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EXCUBITOR_ARTIFACTS_DIR", str(tmp_path / "nonexistent"))
    with pytest.raises(FileNotFoundError):
        rt.CLAUDE_CODE.artifacts()


# --- the plan writes nothing (the C2.3 proof) ------------------------------------------------------

def test_build_plan_writes_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    before = _snapshot(tmp_path)
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home=home, project_root=None)
    plan = plan_mod.build_install_plan(rt.CLAUDE_CODE, target)
    text = plan_mod.render_plan(plan)
    assert "dry-run" in text
    assert _snapshot(tmp_path) == before  # not one byte written


def test_plan_content_is_complete_and_deterministic(tmp_path: Path) -> None:
    home = tmp_path / "home"
    target = rt.CLAUDE_CODE.target(rt.Scope.USER, home=home, project_root=None)
    plan_a = plan_mod.build_install_plan(rt.CLAUDE_CODE, target)
    plan_b = plan_mod.build_install_plan(rt.CLAUDE_CODE, target)
    assert plan_a == plan_b  # deterministic
    # Every guard is both staged and registered; the telemetry helper is staged but not registered.
    staged = {a.basename for a in plan_a.staged_files}
    assert {"guard-loop-vc.py", "_denial_log.py"} <= staged
    registered = {a.basename for a in plan_a.registrations}
    assert "_denial_log.py" not in registered
    assert len(plan_a.registrations) == 4
    # ensure-dir precedes stage precedes register.
    kinds = [a.kind for a in plan_a.actions]
    assert kinds.index("ensure_dir") < kinds.index("stage_file") < kinds.index("register_hook")


# --- CLI dry-run wiring ----------------------------------------------------------------------------

def test_cli_install_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    home = tmp_path / "home"
    home.mkdir()
    before = _snapshot(tmp_path)
    code = cli_main(["install", "--runtime", "claude-code", "--scope", "user",
                     "--home", str(home), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "install plan" in out
    assert "register" in out
    assert _snapshot(tmp_path) == before


def test_cli_install_without_dry_run_refuses(tmp_path: Path, capsys) -> None:
    home = tmp_path / "home"
    home.mkdir()
    code = cli_main(["install", "--runtime", "claude-code", "--home", str(home)])
    err = capsys.readouterr().err
    assert code == 2
    assert "dry-run" in err
    assert _snapshot(tmp_path / "home") == {}  # nothing created


def test_cli_install_auto_reports_no_runtime_when_absent(tmp_path: Path, capsys) -> None:
    home = tmp_path / "home"
    home.mkdir()
    code = cli_main(["install", "--runtime", "auto", "--home", str(home), "--dry-run"])
    err = capsys.readouterr().err
    assert code == 1
    assert "no supported runtime detected" in err
