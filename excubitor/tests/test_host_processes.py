"""Platform dispatch tests are not native OS or provider evidence."""

import os
import sys
from types import SimpleNamespace

import pytest

from excubitor import development_adapters as adapters
from excubitor.host_processes import background_options, host_backend, process_tree
from excubitor.runs import RunError


def settings():
    return {
        "llm": {"adapter": "command-json", "command": [sys.executable, "-V"], "model": "fixture"},
        "executor": {"adapter": "local-process"},
    }


def test_convenience_descriptor_freezes_host_backend():
    original = settings()
    resolved = adapters.normalize(original)
    assert resolved["executor"] == {"adapter": host_backend()}
    assert original["executor"] == {"adapter": "local-process"}
    assert adapters.normalize(resolved) == resolved
    adapters.preflight(resolved)


def test_unavailable_backend_is_refused_without_fallback():
    value = settings()
    value["executor"] = {"adapter": "posix-process" if os.name == "nt" else "windows-process"}
    with pytest.raises(RunError, match="unavailable"):
        adapters.preflight(value)


def test_unavailable_executor_refuses_before_paid_planning_or_disk_creation(tmp_path, monkeypatch):
    from excubitor import development_plan

    value = settings()
    value["executor"] = {"adapter": "posix-process" if os.name == "nt" else "windows-process"}
    monkeypatch.setattr(development_plan, "make_runtime", lambda *_: pytest.fail("no paid planning"))
    root = tmp_path / "plan"
    with pytest.raises(RunError, match="unavailable"):
        development_plan.prepare(value, tmp_path, root, "Do the work")
    assert not root.exists()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_posix_dispatch_only(monkeypatch, platform):
    from excubitor import host_processes
    from excubitor.posix_processes import PosixProcessTree

    # Patch the seam, never execute a fake platform's backend.
    monkeypatch.setattr(host_processes, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(host_processes, "sys", SimpleNamespace(platform=platform))
    assert host_backend() == "posix-process"
    assert isinstance(process_tree(), PosixProcessTree)
    assert background_options() == {"start_new_session": True}
