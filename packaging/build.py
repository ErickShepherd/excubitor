#!/usr/bin/env python3
"""Stdlib-only, byte-reproducible builder for the Excubitor wheel, sdist, and zipapp.

Why a hand-rolled builder instead of just calling `python -m build`? Two reasons, both load-bearing
for this repo:

1. **No build backend, no network.** The runtime is stdlib-only and the CI gate installs nothing but
   `pytest`. A reproducibility test and an offline-install smoke test must therefore run with zero
   extra dependencies. This module needs only the standard library, so those tests run everywhere the
   suite runs — including the stdlib-only gate.
2. **Determinism is the point.** Excubitor's whole thesis is *auditable, forgery-resistant artifacts*.
   A build that emits a different byte stream every run cannot be checksum-pinned. Every archive this
   module writes is deterministic: entries are emitted in sorted order, every timestamp is pinned to
   `SOURCE_DATE_EPOCH` (default 1980-01-01, the ZIP epoch floor), permissions are normalized, and the
   gzip/tar/zip headers carry no volatile machine state. Build twice, get identical bytes and identical
   SHA-256s.

The metadata is read from `pyproject.toml` (via `tomllib`) and the version from `excubitor.__version__`
so this producer can never drift from the standard setuptools path declared in `pyproject.toml`. The
distribution contains the importable package plus exact-byte guard resources generated from the
canonical `hooks/` entry points — never its tests.

CLI: `python packaging/build.py [wheel|sdist|pyz|all] [--outdir dist]`.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import os
import tarfile
import tomllib
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "excubitor"
GUARD_NAMES = (
    "_denial_log.py",
    "guard-default-branch.py",
    "guard-loop-vc.py",
    "guard-one-unit.py",
    "guard-self-integrity.py",
)

#: Default pinned timestamp: 1980-01-01T00:00:00Z, the earliest a ZIP local-file header can represent.
#: Overridable with the `SOURCE_DATE_EPOCH` environment variable (the reproducible-builds convention).
_DEFAULT_EPOCH = 315532800
#: The fixed ZIP date_time tuple derived from the epoch floor.
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
#: Normalized permissions: 0644 for regular files (no executable bit inside a distribution).
_FILE_MODE = 0o644


def source_date_epoch() -> int:
    """The pinned build timestamp: `SOURCE_DATE_EPOCH` if set and valid, else the ZIP epoch floor."""
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return _DEFAULT_EPOCH
    try:
        return max(int(raw), _DEFAULT_EPOCH)
    except ValueError:
        return _DEFAULT_EPOCH


def load_metadata() -> dict:
    """Read the `[project]` table from `pyproject.toml` and resolve the dynamic version.

    Returns a small normalized dict (name, version, and the fields needed to render METADATA/PKG-INFO)
    rather than the raw TOML, so the archive writers never re-parse.
    """
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    # The version is dynamic (attr = excubitor.__version__); read it from the package source without
    # importing the whole package, so the builder has no import side effects.
    version = _read_version()
    return {
        "name": project["name"],
        "version": version,
        "description": project.get("description", ""),
        "requires_python": project.get("requires-python", ""),
        "license": (project.get("license") or {}).get("text", ""),
        "authors": project.get("authors", []),
        "keywords": project.get("keywords", []),
        "classifiers": project.get("classifiers", []),
        "urls": project.get("urls", {}),
        "scripts": project.get("scripts", {}),
        "readme": project.get("readme", ""),
    }


def _read_version() -> str:
    """Extract `__version__` from `excubitor/__init__.py` by literal scan (no import side effects)."""
    text = (PROJECT_ROOT / PACKAGE / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("__version__"):
            # `__version__ = "0.1.0"` → strip to the quoted literal.
            _, _, rhs = stripped.partition("=")
            return rhs.strip().strip("\"'")
    raise RuntimeError("excubitor/__init__.py does not define __version__")


def _is_shippable(path: Path) -> bool:
    """True for a package file that belongs in the distribution: excludes tests, caches, and bytecode."""
    parts = path.relative_to(PROJECT_ROOT).parts
    if "tests" in parts or "__pycache__" in parts:
        return False
    return path.suffix != ".pyc"


def package_files() -> "list[Path]":
    """Every shippable file under the `excubitor` package, sorted by POSIX arcname for determinism."""
    root = PROJECT_ROOT / PACKAGE
    files = [p for p in root.rglob("*") if p.is_file() and _is_shippable(p)]
    return sorted(files, key=lambda p: p.relative_to(PROJECT_ROOT).as_posix())


def package_members() -> "list[tuple[str, bytes]]":
    """Canonical package sources plus exact-byte guard resources from the single ``hooks/`` source."""
    members = [(p.relative_to(PROJECT_ROOT).as_posix(), p.read_bytes()) for p in package_files()]
    for name in GUARD_NAMES:
        source = PROJECT_ROOT / "hooks" / name
        members.append((f"excubitor/_artifacts/{name}", source.read_bytes()))
    return sorted(members, key=lambda item: item[0])


def _metadata_body(meta: dict) -> str:
    """Render the RFC-822-style METADATA / PKG-INFO body from resolved metadata (Metadata-Version 2.1)."""
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {meta['name']}",
        f"Version: {meta['version']}",
    ]
    if meta["description"]:
        lines.append(f"Summary: {meta['description']}")
    for author in meta["authors"]:
        name, email = author.get("name"), author.get("email")
        if name and email:
            lines.append(f"Author-email: {name} <{email}>")
        elif email:
            lines.append(f"Author-email: {email}")
        elif name:
            lines.append(f"Author: {name}")
    if meta["license"]:
        lines.append(f"License: {meta['license']}")
    for label, url in meta["urls"].items():
        lines.append(f"Project-URL: {label}, {url}")
    if meta["keywords"]:
        lines.append("Keywords: " + ",".join(meta["keywords"]))
    for classifier in meta["classifiers"]:
        lines.append(f"Classifier: {classifier}")
    if meta["requires_python"]:
        lines.append(f"Requires-Python: {meta['requires_python']}")
    readme = meta.get("readme", "")
    body = ""
    if isinstance(readme, str) and readme.endswith(".md"):
        lines.append("Description-Content-Type: text/markdown")
        readme_path = PROJECT_ROOT / readme
        if readme_path.exists():
            body = readme_path.read_text(encoding="utf-8")
    header = "\n".join(lines) + "\n"
    return header + "\n" + body if body else header


def _wheel_metadata() -> str:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: excubitor-reproducible-builder\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )


def _entry_points_txt(meta: dict) -> str:
    lines = ["[console_scripts]"]
    for name, target in meta["scripts"].items():
        lines.append(f"{name} = {target}")
    return "\n".join(lines) + "\n"


def _record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _add_zip_entry(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    """Append one deterministic entry: pinned timestamp, normalized mode, DEFLATE."""
    info = zipfile.ZipInfo(arcname, date_time=_ZIP_DATE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = _FILE_MODE << 16
    zf.writestr(info, data)


def build_wheel(outdir: Path) -> Path:
    """Write a deterministic PEP 427 wheel and return its path.

    Layout: the `excubitor` package tree, then `<name>-<version>.dist-info/{METADATA, WHEEL,
    entry_points.txt, RECORD}`. RECORD lists every file with its SHA-256 and size (its own row is
    hashless per the spec). Entries are emitted in a fixed order so the byte stream is reproducible.
    """
    meta = load_metadata()
    dist_info = f"{meta['name']}-{meta['version']}.dist-info"
    outdir.mkdir(parents=True, exist_ok=True)
    wheel_path = outdir / f"{meta['name']}-{meta['version']}-py3-none-any.whl"

    # Collect (arcname, bytes) for every member except RECORD, in deterministic order.
    members: "list[tuple[str, bytes]]" = []
    members.extend(package_members())
    members.append((f"{dist_info}/METADATA", _metadata_body(meta).encode("utf-8")))
    members.append((f"{dist_info}/WHEEL", _wheel_metadata().encode("utf-8")))
    members.append((f"{dist_info}/entry_points.txt", _entry_points_txt(meta).encode("utf-8")))

    record_lines = [f"{arc},{_record_hash(data)},{len(data)}" for arc, data in members]
    record_lines.append(f"{dist_info}/RECORD,,")
    record = ("\n".join(record_lines) + "\n").encode("utf-8")

    tmp = wheel_path.with_suffix(".whl.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in members:
            _add_zip_entry(zf, arcname, data)
        _add_zip_entry(zf, f"{dist_info}/RECORD", record)
    os.replace(tmp, wheel_path)
    return wheel_path


def _tarinfo(name: str, size: int, epoch: int) -> tarfile.TarInfo:
    """A deterministic tar member header: pinned mtime, normalized mode, zeroed ownership."""
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = epoch
    info.mode = _FILE_MODE
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.type = tarfile.REGTYPE
    return info


def build_sdist(outdir: Path) -> Path:
    """Write a deterministic PEP 517 sdist (`<name>-<version>.tar.gz`) and return its path.

    Contents (under the `<name>-<version>/` prefix): `pyproject.toml`, `README.md`, `LICENSE`,
    `PKG-INFO`, and the `excubitor` package sources — enough to rebuild the wheel from source. The
    gzip header carries mtime 0 and no filename so the compressed stream is reproducible.
    """
    meta = load_metadata()
    epoch = source_date_epoch()
    prefix = f"{meta['name']}-{meta['version']}"
    outdir.mkdir(parents=True, exist_ok=True)
    sdist_path = outdir / f"{prefix}.tar.gz"

    members: "list[tuple[str, bytes]]" = []
    for rel in ("pyproject.toml", "README.md", "LICENSE"):
        source = PROJECT_ROOT / rel
        if source.exists():
            members.append((f"{prefix}/{rel}", source.read_bytes()))
    members.append((f"{prefix}/PKG-INFO", _metadata_body(meta).encode("utf-8")))
    for arcname, data in package_members():
        members.append((f"{prefix}/{arcname}", data))
    members.sort(key=lambda m: m[0])

    # Build the tar in memory, then gzip it with a pinned header (mtime=0, no name) for determinism.
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, data in members:
            tar.addfile(_tarinfo(name, len(data), epoch), io.BytesIO(data))

    tmp = sdist_path.with_suffix(".gz.tmp")
    with open(tmp, "wb") as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as gz:
            gz.write(raw.getvalue())
    os.replace(tmp, sdist_path)
    return sdist_path


def build_pyz(outdir: Path) -> Path:
    """Write a deterministic stdlib-only zipapp (`<name>-<version>.pyz`) and return its path.

    Built from the SAME package sources as the wheel and sdist. `zipapp` is used to lay out the
    archive with a `__main__.py` that invokes the CLI, then the archive is rewritten deterministically
    (pinned timestamps, sorted entries) so its bytes are reproducible.
    """
    meta = load_metadata()
    outdir.mkdir(parents=True, exist_ok=True)
    pyz_path = outdir / f"{meta['name']}-{meta['version']}.pyz"

    # Stage the package plus a __main__ shim into an in-memory source set, then write a deterministic
    # zip directly (zipapp.create_archive does not pin timestamps, so we assemble the zip ourselves and
    # only borrow zipapp's __main__ convention).
    main_shim = "import excubitor.cli\nimport sys\nsys.exit(excubitor.cli.main())\n"
    members: "list[tuple[str, bytes]]" = [("__main__.py", main_shim.encode("utf-8"))]
    members.extend(package_members())
    members.sort(key=lambda m: m[0])

    tmp = pyz_path.with_suffix(".pyz.tmp")
    shebang = b"#!/usr/bin/env python3\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in members:
            _add_zip_entry(zf, arcname, data)
    tmp.write_bytes(shebang + buffer.getvalue())
    os.replace(tmp, pyz_path)
    # Mark executable so the shebang is usable; the bit does not affect the archive bytes.
    pyz_path.chmod(0o755)
    return pyz_path


_BUILDERS = {"wheel": build_wheel, "sdist": build_sdist, "pyz": build_pyz}


def build_all(outdir: Path) -> "list[Path]":
    return [build_wheel(outdir), build_sdist(outdir), build_pyz(outdir)]


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Reproducibly build the Excubitor distribution artifacts.")
    parser.add_argument("target", nargs="?", default="all", choices=["all", *_BUILDERS])
    parser.add_argument("--outdir", type=Path, default=PROJECT_ROOT / "dist")
    args = parser.parse_args(argv)
    outputs = build_all(args.outdir) if args.target == "all" else [_BUILDERS[args.target](args.outdir)]
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
