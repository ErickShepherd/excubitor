"""Top-level entry point embedded in the standalone Excubitor zipapp.

The ordinary CLI remains available without special interpreter flags. Native hooks use the separate
``hook <host>`` route, which refuses to run unless Python isolated startup and ``-S`` are active and
the archive path is absolute. The native registration is responsible for naming a verified absolute
interpreter; this entry point checks the properties visible from inside the process and fails loudly
when the registration omits its isolation contract.
"""
from __future__ import annotations

import os
import sys


def _usage_error(message: str) -> int:
    print(f"excubitor hook: {message}", file=sys.stderr)
    return 2


def _run_hook(argv: "list[str]") -> int:
    if len(argv) != 1:
        return _usage_error("expected exactly one host: hook <host>")
    if not sys.flags.isolated or not sys.flags.no_site:
        return _usage_error("native hooks require Python isolated startup: -I -S")
    if not os.path.isabs(sys.argv[0]) or not os.path.isabs(sys.executable):
        return _usage_error("native hooks require absolute interpreter and archive paths")

    host = argv[0]
    if host == "codex":
        from excubitor.adapters import codex

        codex.main()
        return 0
    return _usage_error(f"unsupported host {host!r}")


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["hook"]:
        return _run_hook(args[1:])

    from excubitor import cli

    return cli.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
