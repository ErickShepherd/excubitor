"""Excubitor — a model-blind, multi-runtime policy core and its runtime adapters.

This package is the neutral core extracted from the shipped Claude Code hooks (`hooks/guard-*.py`).
A *model* chooses which tool call to propose; an *agent runtime* names the call, dispatches it, and
decides whether a pre-execution hook may veto it. Excubitor lives at that second boundary: it makes
deterministic Python/Git decisions that must be identical whether the proposed call came from Claude,
GPT, Gemini, an open-weight model, or a human-authored automation.

Layering (see `docs/design/model-agnostic-runtime.md`):

    excubitor.core       — canonical event/decision types + pure, host-free policy functions
    excubitor.adapters   — per-runtime normalizers/serializers (translation only, never policy)

The core is deliberately **stdlib-only** and free of host I/O: no stdin/stdout, no process exit, no
environment reads, no native tool names, and no model/provider identity. Those concerns belong to the
adapters. Keeping the core pure is what lets one decision table be proven equivalent across runtimes.

Extraction is behavior-preserving: the shipped `hooks/tests/` and `runtime/tests/` suites remain the
differential oracle, so a decision change during extraction is a regression, not a new baseline.
"""
from __future__ import annotations

#: Single source of truth for the distribution version. `pyproject.toml` reads this attribute
#: dynamically (`[tool.setuptools.dynamic]`), and the stdlib reproducible builder
#: (`packaging/build.py`) imports it directly, so the wheel/sdist/pyz names can never drift from
#: the package. A consistency test pins the two together.
__version__ = "0.2.0"

__all__ = ["__version__", "core"]
