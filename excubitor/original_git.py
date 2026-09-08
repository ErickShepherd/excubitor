"""Environment for read-only queries of the owner's selected repository."""

from __future__ import annotations

import os


def original_git_environment():
    """Keep effective Git configuration, never inherited repository redirects.

    Cleanliness depends on the owner's configuration (for example autocrlf).
    Preserve config-file selectors and command-scope configuration, including
    their numbered keys/values, while removing other Git-specific environment.
    Callers also disable fsmonitor explicitly. Normal Git-configured clean
    filters may run, just as they do for ordinary Git status.

    Candidate checkout and exact-byte inspection use their own isolated policy.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_") or key.upper().startswith("GIT_CONFIG")
    }
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
    return env
