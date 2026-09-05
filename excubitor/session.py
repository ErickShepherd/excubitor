"""Host lifecycle reconciliation independent of MCP process cleanup."""

from __future__ import annotations

from excubitor.runs import Binding, Run, RunStore


def record_session_end(store: RunStore, binding: Binding) -> Run | None:
    """A trusted native SessionEnd observation interrupts this exact run only.

    Session exit is not proof that every worker has stopped, that acceptance
    passed, or that the job was cancelled. Retain the boundary and progress for
    explicit worker reconciliation and same-task resumption within original limits.
    """
    run = store.lookup(binding)
    if run is None or run.state != "running":
        return run
    return store.interrupt(run)
