"""Tests for the stdlib-only reproducible builder (`packaging/build.py`).

Covers the C2.1 acceptance surface: reproducible wheel/sdist bytes, a spec-valid wheel whose RECORD
hashes verify, tests excluded from the distribution, the console entry point present, and a real
offline install smoke test (fresh venv, `--no-index` install, run the installed `excubitor`).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

# Import the builder from the repo's packaging/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build as builder  # noqa: E402

import excubitor  # noqa: E402

VERSION = excubitor.__version__


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wheel_reproducible(tmp_path: Path) -> None:
    """Two independent wheel builds produce byte-identical archives (same SHA-256)."""
    first = builder.build_wheel(tmp_path / "a")
    second = builder.build_wheel(tmp_path / "b")
    assert first.name == second.name == f"excubitor-{VERSION}-py3-none-any.whl"
    assert _sha256(first) == _sha256(second)


def test_sdist_reproducible(tmp_path: Path) -> None:
    """Two independent sdist builds produce byte-identical archives (same SHA-256)."""
    first = builder.build_sdist(tmp_path / "a")
    second = builder.build_sdist(tmp_path / "b")
    assert first.name == second.name == f"excubitor-{VERSION}.tar.gz"
    assert _sha256(first) == _sha256(second)


def test_wheel_is_valid_and_record_verifies(tmp_path: Path) -> None:
    """The wheel is a valid zip; every RECORD row's SHA-256 matches the stored bytes."""
    wheel = builder.build_wheel(tmp_path)
    dist_info = f"excubitor-{VERSION}.dist-info"
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        for required in ("METADATA", "WHEEL", "RECORD", "entry_points.txt"):
            assert f"{dist_info}/{required}" in names

        record = zf.read(f"{dist_info}/RECORD").decode("utf-8")
        rows = [line for line in record.splitlines() if line]
        for row in rows:
            name, digest, _size = row.rsplit(",", 2)
            if name == f"{dist_info}/RECORD":
                assert digest == ""  # RECORD's own row is hashless, per the wheel spec.
                continue
            import base64

            data = zf.read(name)
            expected = "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(data).digest()
            ).rstrip(b"=").decode("ascii")
            assert digest == expected, f"RECORD hash mismatch for {name}"


def test_entry_point_declared(tmp_path: Path) -> None:
    """The wheel declares the `excubitor` console script bound to `excubitor.cli:main`."""
    wheel = builder.build_wheel(tmp_path)
    dist_info = f"excubitor-{VERSION}.dist-info"
    with zipfile.ZipFile(wheel) as zf:
        entry_points = zf.read(f"{dist_info}/entry_points.txt").decode("utf-8")
    assert "[console_scripts]" in entry_points
    assert "excubitor = excubitor.cli:main" in entry_points


def test_metadata_has_name_and_version(tmp_path: Path) -> None:
    wheel = builder.build_wheel(tmp_path)
    dist_info = f"excubitor-{VERSION}.dist-info"
    with zipfile.ZipFile(wheel) as zf:
        metadata = zf.read(f"{dist_info}/METADATA").decode("utf-8")
    assert "Name: excubitor" in metadata
    assert f"Version: {VERSION}" in metadata
    assert "License: MIT" in metadata


def test_wheel_excludes_tests_and_bytecode(tmp_path: Path) -> None:
    """The distribution never ships the package's own tests or compiled bytecode."""
    wheel = builder.build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    assert not any("/tests/" in n or n.endswith(".pyc") for n in names)
    # But it does ship the core it is meant to distribute.
    assert "excubitor/__init__.py" in names
    assert "excubitor/core/dispatch.py" in names


def test_wheel_bundles_canonical_guard_bytes(tmp_path: Path) -> None:
    wheel = builder.build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        for name in builder.GUARD_NAMES:
            expected = (builder.PROJECT_ROOT / "hooks" / name).read_bytes()
            assert zf.read(f"excubitor/_artifacts/{name}") == expected


def test_sdist_contains_sources_and_pyproject(tmp_path: Path) -> None:
    sdist = builder.build_sdist(tmp_path)
    prefix = f"excubitor-{VERSION}"
    with tarfile.open(sdist) as tar:
        names = set(tar.getnames())
    for required in ("pyproject.toml", "PKG-INFO", "README.md", "LICENSE", "excubitor/__init__.py"):
        assert f"{prefix}/{required}" in names
    assert not any("/tests/" in n for n in names)


@pytest.mark.slow
def test_installed_wheel_preserves_legacy_registration_refusal(tmp_path: Path) -> None:
    wheel = builder.build_wheel(tmp_path / "dist")
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, timeout=120)
    bindir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    pip = bindir / ("pip.exe" if sys.platform == "win32" else "pip")
    exe = bindir / ("excubitor.exe" if sys.platform == "win32" else "excubitor")
    subprocess.run([str(pip), "install", "--no-index", "--no-deps", str(wheel)], check=True, timeout=180)
    home, state = tmp_path / "home", tmp_path / "state"
    home.mkdir()
    env = {**os.environ, "EXCUBITOR_STATE_HOME": str(state)}
    dry = subprocess.run(
        [str(exe), "install", "--runtime", "claude-code", "--home", str(home), "--dry-run"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert dry.returncode == 0, dry.stderr
    assert not (home / ".claude").exists()
    install = subprocess.run(
        [str(exe), "install", "--runtime", "claude-code", "--home", str(home)],
        env=env, capture_output=True, text=True, timeout=60,
    )
    # The current product deliberately refuses broad hook registration. Package
    # installation must not re-enable the retired ordinary-task behavior.
    assert install.returncode == 2, install.stderr
    assert "new registrations are disabled" in install.stderr
    assert not (home / ".claude").exists()
    assert not (state / "receipts" / "claude-code-user.json").exists()


@pytest.mark.slow
def test_offline_install_smoke(tmp_path: Path) -> None:
    """Build the wheel, install it into a fresh venv with `--no-index`, run the installed command.

    This is the offline install smoke test the plan requires: no network (`--no-index`), no build
    backend (a pre-built wheel), no dependencies (the runtime is stdlib-only). It proves the console
    entry point the wheel declares actually resolves and runs after a real install.
    """
    wheel = builder.build_wheel(tmp_path / "dist")
    venv_dir = tmp_path / "venv"
    try:
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True,
                       capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:  # pragma: no cover
        pytest.fail(f"required isolated installation environment could not be created: {exc}")

    bindir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    pip = bindir / ("pip.exe" if sys.platform == "win32" else "pip")
    install = subprocess.run(
        [str(pip), "install", "--no-index", "--no-deps", str(wheel)],
        capture_output=True, text=True, timeout=180,
    )
    assert install.returncode == 0, f"offline install failed:\n{install.stdout}\n{install.stderr}"

    exe = bindir / ("excubitor.exe" if sys.platform == "win32" else "excubitor")
    assert exe.exists(), "console entry point was not installed"
    result = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert VERSION in result.stdout

    # Exercise the installed launcher outside the source tree and remove import
    # redirects so an editable checkout cannot accidentally satisfy the smoke.
    environment = {k: v for k, v in os.environ.items()
                   if k.upper() not in ("PYTHONPATH", "PYTHONHOME")}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for command in (("ralph", "--help"), ("ralph", "init", "--help"),
                    ("ralph", "resume", "--help")):
        launched = subprocess.run([str(exe), *command], cwd=tmp_path,
                                  env=environment, capture_output=True, text=True, timeout=60)
        assert launched.returncode == 0, launched.stderr
    installed_python = bindir / ("python.exe" if sys.platform == "win32" else "python")
    imported = subprocess.run(
        [str(installed_python), "-I", "-B", "-c",
         "import excubitor; print(excubitor.__file__)"], cwd=tmp_path,
        env=environment, capture_output=True, text=True, timeout=60)
    assert imported.returncode == 0, imported.stderr
    assert Path(imported.stdout.strip()).is_relative_to(venv_dir)
    replaced = subprocess.run(
        [str(pip), "install", "--no-index", "--no-deps", "--upgrade", "--force-reinstall", str(wheel)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=180)
    assert replaced.returncode == 0, replaced.stderr
    relaunched = subprocess.run([str(exe), "ralph", "--help"], cwd=tmp_path,
                               env=environment, capture_output=True, text=True, timeout=60)
    assert relaunched.returncode == 0, relaunched.stderr
    removed = subprocess.run([str(pip), "uninstall", "-y", "excubitor"], cwd=tmp_path,
                             env=environment, capture_output=True, text=True, timeout=180)
    assert removed.returncode == 0, removed.stderr
    assert not exe.exists(), "uninstall left the console entry point installed"
    absent = subprocess.run([str(installed_python), "-I", "-B", "-c", "import excubitor"],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60)
    assert absent.returncode != 0, "uninstall left an importable package"
