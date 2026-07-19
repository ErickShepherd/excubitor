"""Per-runtime adapters: translate a host's native pre-tool event to/from the model-blind core.

An adapter is the ONLY host-specific layer. It normalizes a native envelope, invokes the core policy /
dispatcher, and renders the core's `Decision` back into the host's veto shape — it never reimplements a
deny set. Unlike `excubitor.core`, adapter modules ARE allowed to name their host (its tool names, event
shape, control paths); the neutrality invariant applies to the core, not here.
"""
from __future__ import annotations

__all__ = ["claude_code"]
