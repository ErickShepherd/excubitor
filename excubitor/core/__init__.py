"""The model-blind Excubitor policy core: canonical types plus pure, host-free policy functions.

Everything under ``excubitor.core`` is stdlib-only and free of host I/O — no stdin/stdout, process
exit, environment reads, native tool names, or model/provider identity. Those belong to the adapters.
This is what makes one decision table provably equivalent across runtimes.

The canonical value types are re-exported here for ergonomic imports
(``from excubitor.core import PreToolEvent, Decision``). Policy functions (loop-vc, default-branch,
one-unit, self-integrity) and the dispatcher land in later modules as the extraction proceeds.
"""
from __future__ import annotations

from . import git_state
from .events import (
    SCHEMA,
    Capability,
    Decision,
    LoopMode,
    Outcome,
    PreToolEvent,
)

__all__ = [
    "SCHEMA",
    "Capability",
    "LoopMode",
    "Outcome",
    "Decision",
    "PreToolEvent",
    "git_state",
]
