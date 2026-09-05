"""Tests for the stdlib-only reproducible zipapp (`.pyz`) artifact (C2.10).

The `.pyz` must be built from the SAME source inputs as the wheel and sdist, be byte-reproducible,
contain only the stdlib-only `excubitor` package (plus its reviewed `__main__` source) and no tests,
and actually run — `python excubitor.pyz --version` prints the version while native hooks use the
isolated `python -I -S excubitor.pyz hook <host>` route.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import venv
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


def _codex_self_integrity_payload(cwd: Path) -> str:
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "apply_patch",
            "tool_input": {
                "command": (
                    "*** Begin Patch\n*** Update File: .codex/hooks.json\n"
                    "@@\n-old\n+new\n*** End Patch"
                )
            },
            "cwd": str(cwd),
            "session_id": "isolated-pyz-test",
        }
    )


def _plant_python_shadow(root: Path, marker: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    marker_literal = repr(str(marker))
    payload = f"from pathlib import Path\nPath({marker_literal}).write_text('loaded')\n"
    (root / "sitecustomize.py").write_text(payload, encoding="utf-8")
    (root / "json.py").write_text(payload + "raise RuntimeError('shadow json loaded')\n", encoding="utf-8")
    package = root / "excubitor"
    package.mkdir()
    (package / "__init__.py").write_text(
        payload + "raise RuntimeError('shadow excubitor loaded')\n", encoding="utf-8"
    )


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


def test_pyz_bundles_canonical_guard_bytes(tmp_path: Path) -> None:
    pyz = builder.build_pyz(tmp_path)
    with zipfile.ZipFile(pyz) as zf:
        for name in builder.GUARD_NAMES:
            expected = (builder.PROJECT_ROOT / "hooks" / name).read_bytes()
            assert zf.read(f"excubitor/_artifacts/{name}") == expected


def test_pyz_is_stdlib_only_and_excludes_tests(tmp_path: Path) -> None:
    pyz = builder.build_pyz(tmp_path)
    members = _pyz_members(pyz)
    assert "__main__.py" in members
    # Every other entry is part of the excubitor package — no vendored third-party code.
    non_pkg = {n for n in members if n != "__main__.py" and not n.startswith("excubitor/")}
    assert non_pkg == set(), f"unexpected non-package entries in pyz: {non_pkg}"
    assert not any("/tests/" in n or n.endswith(".pyc") for n in members)
    with zipfile.ZipFile(pyz) as zf:
        assert zf.read("__main__.py") == builder.PYZ_MAIN.read_bytes()


@pytest.mark.slow
def test_pyz_runs(tmp_path: Path) -> None:
    pyz = builder.build_pyz(tmp_path)
    result = subprocess.run([sys.executable, str(pyz), "--version"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert VERSION in result.stdout


@pytest.mark.slow
def test_pyz_hook_refuses_nonisolated_startup(tmp_path: Path) -> None:
    pyz = builder.build_pyz(tmp_path)
    result = subprocess.run(
        [sys.executable, str(pyz), "hook", "codex"],
        input=_codex_self_integrity_payload(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert "require Python isolated startup: -I -S" in result.stderr
    assert result.stdout == ""


@pytest.mark.slow
def test_pyz_hook_refuses_relative_archive_path(tmp_path: Path) -> None:
    pyz = builder.build_pyz(tmp_path)
    result = subprocess.run(
        [sys.executable, "-I", "-S", pyz.name, "hook", "codex"],
        cwd=tmp_path,
        input=_codex_self_integrity_payload(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 2
    assert "require absolute interpreter and archive paths" in result.stderr
    assert result.stdout == ""


@pytest.mark.slow
def test_pyz_hook_isolated_from_hostile_python_state_and_paths(tmp_path: Path) -> None:
    # A Windows venv path cannot contain ';' because it is the platform path-list separator. Keep
    # that shell metacharacter on the archive path while the venv still exercises the others.
    special = tmp_path / "runtime with spaces &()[]'$!"
    pyz = builder.build_pyz(special / "artifact output ;")
    workdir = special / "ordinary working directory"
    python_path = special / "hostile PYTHONPATH"
    virtual_env = special / "hostile virtual environment"
    workdir.mkdir(parents=True)
    venv.EnvBuilder(with_pip=False).create(virtual_env)

    if os.name == "nt":
        interpreter = virtual_env / "Scripts" / "python.exe"
        site_packages = virtual_env / "Lib" / "site-packages"
    else:
        interpreter = virtual_env / "bin" / "python"
        site_packages = (
            virtual_env
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
        )

    markers = [special / f"shadow-{index}.loaded" for index in range(3)]
    for root, marker in zip((workdir, python_path, site_packages), markers, strict=True):
        _plant_python_shadow(root, marker)
    startup_marker = special / "python-startup.loaded"
    startup = special / "hostile-startup.py"
    startup.write_text(
        f"from pathlib import Path\nPath({str(startup_marker)!r}).write_text('loaded')\n",
        encoding="utf-8",
    )

    env = {
        **os.environ,
        "PYTHONHOME": str(special / "nonexistent-python-home"),
        "PYTHONPATH": str(python_path),
        "PYTHONSTARTUP": str(startup),
        "PYTHONUSERBASE": str(special / "hostile-user-base"),
        "VIRTUAL_ENV": str(virtual_env),
    }
    result = subprocess.run(
        [str(interpreter.resolve()), "-I", "-S", str(pyz.resolve()), "hook", "codex"],
        cwd=workdir,
        env=env,
        input=_codex_self_integrity_payload(workdir),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert output["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert not any(marker.exists() for marker in [*markers, startup_marker])


@pytest.mark.slow
def test_pyz_carries_the_full_cli(tmp_path: Path) -> None:
    """The zipapp carries the full CLI — a real subcommand (status --json) runs from it end to end.

    (`install` additionally needs the guard artifacts, which the Campaign-2 pyz does not bundle — that
    is Campaign 3's plugin job — so the stdlib-only smoke exercises a command with no artifact needs.)
    """
    pyz = builder.build_pyz(tmp_path)
    import json
    import os

    env = {**os.environ, "EXCUBITOR_STATE_HOME": str(tmp_path / "state")}
    result = subprocess.run([sys.executable, str(pyz), "status", "--json"],
                            capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["schema"] == "excubitor.status.v2"
    assert data["supported_runtimes"] == ["codex"]
    assert data["enforcement_coverage"]["codex"]["verified_tools"] == ["Bash", "apply_patch"]
    assert data["available_adapters"] == ["claude-code", "codex"]


@pytest.mark.slow
def test_pyz_installer_lifecycle(tmp_path: Path) -> None:
    pyz = builder.build_pyz(tmp_path / "dist")
    import json
    import os

    home, state = tmp_path / "home", tmp_path / "state"
    home.mkdir()
    env = {**os.environ, "EXCUBITOR_STATE_HOME": str(state)}
    base = [sys.executable, str(pyz), "install", "--runtime", "claude-code", "--home", str(home)]
    dry = subprocess.run([*base, "--dry-run"], env=env, capture_output=True, text=True, timeout=60)
    assert dry.returncode == 0, dry.stderr
    assert not (home / ".claude").exists()
    applied = subprocess.run(base, env=env, capture_output=True, text=True, timeout=60)
    assert applied.returncode == 0, applied.stderr
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    registered = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    exact = subprocess.run(
        registered, shell=True, input="{}\n", text=True, capture_output=True, timeout=30
    )
    assert exact.returncode == 0, exact.stderr
    doctor = subprocess.run(
        [sys.executable, str(pyz), "doctor", "--runtime", "claude-code", "--scope", "user",
         "--probe", "--json"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert doctor.returncode == 0, doctor.stderr
    assert json.loads(doctor.stdout)["protection"] == "needs-probe"
    removed = subprocess.run(
        [sys.executable, str(pyz), "uninstall", "--runtime", "claude-code", "--scope", "user",
         "--home", str(home)],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert removed.returncode == 0, removed.stderr
    assert not (home / ".claude" / "settings.json").exists()
