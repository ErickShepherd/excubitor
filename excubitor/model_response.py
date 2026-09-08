"""Recoverable model formatting failures, separate from host admission refusals."""

from dataclasses import replace

from excubitor.runs import RunError


class InvalidModelResponse(RunError):
    """A completed model response has the wrong shape, not an authority violation."""


def failed_response(result, message):
    # Called only after a completed, drained native call. Preserve its process
    # evidence while supplying a bounded host diagnosis for the next fresh call.
    return replace(
        result,
        execution=replace(result.execution, exit_code=1, stdout=b"", stderr=message.encode()[:1024]),
        retryable_error="model-output",
    )
