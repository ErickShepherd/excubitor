"""Tests for the stdlib-only reproducible zipapp (`.pyz`) artifact (C2.10).

The `.pyz` must be built from the SAME source inputs as the wheel and sdist, be byte-reproducible,
contain only the stdlib-only `excubitor` package (plus a `__main__` shim) and no tests, and actually
run — `python excubitor.pyz --version` prints the version.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build as builder  # noqa: E402

import excubitor  # noqa: E402

VERSION = excubitor.__version__


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pyz_members(pyz: Path) -> set:
    # A .pyz is a shebang line followed by a zip archive; zipfile reads it directly.
    with zipfile.ZipFile(pyz) as zf:
        return set(zf.namelist())


def test_pyz_reproducible(tmp_path: Path) -> None:
    first = builder.build_pyz(tmp_path / "a")
    second = builder.build_pyz(tmp_path / "b")
    assert first.name == second.name == f"excubitor-{VERSION}.pyz"
    assert _sha256(first) == _sha256(second)


def test_pyz_built_from_same_source_as_wheel(tmp_path: Path) -> None:
    pyz = builder.build_pyz(tmp_path / "pyz")
    wheel = builder.build_wheel(tmp_path / "whl")
    pyz_pkg = {n for n in _pyz_members(pyz) if n.startswith("excubitor/")}
    with zipfile.ZipFile(wheel) as zf:
        wheel_pkg = {n for n in zf.namelist() if n.startswith("excubitor/")}
    assert pyz_pkg == wheel_pkg  # identical package source in both artifacts


def test_pyz_is_stdlib_only_and_excludes_tests(tmp_path: Path) -> None:
    members = _pyz_members(builder.build_pyz(tmp_path))
    assert "__main__.py" in members
    # Every other entry is part of the excubitor package — no vendored third-party code.
    non_pkg = {n for n in members if n != "__main__.py" and not n.startswith("excubitor/")}
    assert non_pkg == set(), f"unexpected non-package entries in pyz: {non_pkg}"
    assert not any("/tests/" in n or n.endswith(".pyc") for n in members)


@pytest.mark.slow
def test_pyz_runs(tmp_path: Path) -> None:
    pyz = builder.build_pyz(tmp_path)
    result = subprocess.run([sys.executable, str(pyz), "--version"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert VERSION in result.stdout


@pytest.mark.slow
def test_pyz_carries_the_full_cli(tmp_path: Path) -> None:
    """The zipapp carries the full CLI — a real subcommand (status --json) runs from it end to end.

    (`install` additionally needs the guard artifacts, which the Campaign-2 pyz does not bundle — that
    is Campaign 3's plugin job — so the stdlib-only smoke exercises a command with no artifact needs.)
    """
    pyz = builder.build_pyz(tmp_path)
    import json

    env = {"EXCUBITOR_STATE_HOME": str(tmp_path / "state"), "PATH": "/usr/bin:/bin"}
    result = subprocess.run([sys.executable, str(pyz), "status", "--json"],
                            capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["schema"] == "excubitor.status.v1"
    assert data["supported_runtimes"] == ["claude-code"]
