"""Tests for the neutral policy configuration layer (`excubitor.config`).

Covers the C2.2 surface: `EXCUBITOR_*` precedence over the legacy `CLAUDE_*` aliases (with a
deprecation warning), the runtime-only arming rule (no `policy.toml` key can arm the loop),
`.excubitor/policy.toml` discovery and value resolution, honest provenance, and fail-soft handling of
a missing/malformed policy file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from excubitor import config
from excubitor.core.events import LoopMode

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- loop-mode arming (env only) -------------------------------------------------------------------

def test_neutral_loop_guard_arms_conservative() -> None:
    mode, source, warnings = config.resolve_loop_mode({"EXCUBITOR_LOOP_GUARD": "conservative"})
    assert mode is LoopMode.CONSERVATIVE
    assert source == "env:EXCUBITOR_LOOP_GUARD"
    assert warnings == ()


def test_neutral_accepts_legacy_raw_values() -> None:
    assert config.resolve_loop_mode({"EXCUBITOR_LOOP_GUARD": "1"})[0] is LoopMode.CONSERVATIVE
    assert config.resolve_loop_mode({"EXCUBITOR_LOOP_GUARD": "yolo"})[0] is LoopMode.VERIFIABLE
    assert config.resolve_loop_mode({"EXCUBITOR_LOOP_GUARD": "verifiable"})[0] is LoopMode.VERIFIABLE


def test_legacy_loop_guard_honored_with_warning() -> None:
    mode, source, warnings = config.resolve_loop_mode({"CLAUDE_LOOP_GUARD": "yolo"})
    assert mode is LoopMode.VERIFIABLE
    assert source == "env:CLAUDE_LOOP_GUARD (legacy)"
    assert warnings and "legacy" in warnings[0]


def test_neutral_wins_over_legacy_and_suppresses_warning() -> None:
    mode, source, warnings = config.resolve_loop_mode(
        {"EXCUBITOR_LOOP_GUARD": "conservative", "CLAUDE_LOOP_GUARD": "yolo"}
    )
    assert mode is LoopMode.CONSERVATIVE
    assert source == "env:EXCUBITOR_LOOP_GUARD"
    assert warnings == ()  # neutral present → legacy is not consulted, no deprecation noise


def test_unset_and_empty_and_unknown_are_unarmed() -> None:
    assert config.resolve_loop_mode({})[0] is None
    assert config.resolve_loop_mode({"EXCUBITOR_LOOP_GUARD": ""})[0] is None  # empty does not arm
    assert config.resolve_loop_mode({"EXCUBITOR_LOOP_GUARD": "banana"})[0] is None


# --- allow-default-branch off-switch ---------------------------------------------------------------

def test_allow_default_branch_precedence(tmp_path: Path) -> None:
    neutral = config.resolve_config(tmp_path, {"EXCUBITOR_ALLOW_DEFAULT_BRANCH": "1"})
    assert neutral.allow_default_branch.value is True
    assert neutral.allow_default_branch.source == "env:EXCUBITOR_ALLOW_DEFAULT_BRANCH"
    assert neutral.warnings == ()

    legacy = config.resolve_config(tmp_path, {"CLAUDE_ALLOW_DEFAULT_BRANCH": "1"})
    assert legacy.allow_default_branch.value is True
    assert "(legacy)" in legacy.allow_default_branch.source
    assert any("legacy" in w for w in legacy.warnings)

    off = config.resolve_config(tmp_path, {})
    assert off.allow_default_branch.value is False
    assert off.allow_default_branch.source == "default"


# --- policy.toml discovery and resolution ----------------------------------------------------------

def _write_policy(root: Path, body: str) -> None:
    (root / ".excubitor").mkdir(parents=True, exist_ok=True)
    (root / ".excubitor" / "policy.toml").write_text(body, encoding="utf-8")


def test_policy_file_found_by_upward_search(tmp_path: Path) -> None:
    _write_policy(tmp_path, '[default_branch]\nopt_out_marker = ".custom/marker"\n')
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    cfg = config.resolve_config(nested, {})
    assert cfg.policy_path is not None and cfg.policy_path.endswith("policy.toml")
    assert cfg.opt_out_marker.value == ".custom/marker"
    assert cfg.opt_out_marker.source == "policy.toml"


def test_defaults_when_no_policy_file(tmp_path: Path) -> None:
    cfg = config.resolve_config(tmp_path, {})
    assert cfg.policy_path is None
    assert cfg.opt_out_marker.value == config.DEFAULT_OPT_OUT_MARKER
    assert cfg.opt_out_marker.source == "default"
    assert cfg.one_unit_enabled.value is True
    assert cfg.protected_roots.value == ()


def test_one_unit_and_protected_roots_from_policy(tmp_path: Path) -> None:
    _write_policy(
        tmp_path,
        "[one_unit]\nenabled = false\n\n[self_integrity]\nprotected_roots = ['scripts/ci', 'x.py']\n",
    )
    cfg = config.resolve_config(tmp_path, {})
    assert cfg.one_unit_enabled.value is False
    assert cfg.one_unit_enabled.source == "policy.toml"
    assert cfg.protected_roots.value == ("scripts/ci", "x.py")


def test_malformed_policy_file_degrades_to_defaults(tmp_path: Path) -> None:
    _write_policy(tmp_path, "this is not valid = = toml [[[")
    cfg = config.resolve_config(tmp_path, {})
    assert cfg.policy_path is not None  # discovered-invalid stays distinguishable from absent
    assert cfg.opt_out_marker.value == config.DEFAULT_OPT_OUT_MARKER


def test_malformed_policy_file_strict_mode_fails_closed(tmp_path: Path) -> None:
    _write_policy(tmp_path, "this is not valid = = toml [[[")
    with pytest.raises(config.PolicyFileError, match="invalid policy file"):
        config.load_policy_file(tmp_path, strict=True)


def test_state_home_resolution(tmp_path: Path) -> None:
    assert config.resolve_config(tmp_path, {}).state_home.value is None
    cfg = config.resolve_config(tmp_path, {"EXCUBITOR_STATE_HOME": "/var/lib/excubitor"})
    assert cfg.state_home.value == "/var/lib/excubitor"
    assert cfg.state_home.source == "env:EXCUBITOR_STATE_HOME"


# --- committed example loads -----------------------------------------------------------------------

def test_committed_example_policy_parses(tmp_path: Path) -> None:
    example = (REPO_ROOT / "docs" / "examples" / "policy.toml").read_text(encoding="utf-8")
    _write_policy(tmp_path, example)
    cfg = config.resolve_config(tmp_path, {})
    assert cfg.opt_out_marker.value == ".excubitor/allow-default-branch"
    assert cfg.one_unit_enabled.value is True


def test_marker_recognition_lists_neutral_first() -> None:
    assert config.ALLOW_DEFAULT_BRANCH_MARKERS[0] == ".excubitor/allow-default-branch"
    assert config.ALLOW_DEFAULT_BRANCH_MARKERS[1] == ".claude/allow-default-branch"
