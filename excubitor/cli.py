#!/usr/bin/env python3
"""The ``excubitor`` console entry point.

This is the single user-facing command the packaged distribution installs (``[project.scripts]`` in
``pyproject.toml`` maps ``excubitor`` → :func:`main`). Campaign 2 grows it one subcommand per plan
item — ``install``, ``uninstall``, ``status``, ``print-config``, ``doctor`` — behind the transactional
installer contract in ``docs/design/installable-multi-runtime-distribution.md``. This foundational
version wires the dispatcher, ``--version``, and ``--help`` only; subcommands register themselves as
they are implemented so the offline install smoke test has a real entry point to exercise.

The command is intentionally thin: it parses arguments and delegates. All policy and mutation logic
lives in the importable package (``excubitor.core``, ``excubitor.installers``, …) so the same behavior
is reachable without the console script — a runtime that embeds Excubitor never needs the CLI.
"""
from __future__ import annotations

import argparse
import sys

from excubitor import __version__

_PROG = "excubitor"


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser.

    Subcommands are added to the returned ``subparsers`` by later plan items; keeping construction in
    one function lets the tests build the parser without invoking :func:`main`.
    """
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description=(
            "Installable, model-blind safety policy for coding-agent runtimes. "
            "Only Claude Code is a supported runtime today; other hosts are designed, not built."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{_PROG} {__version__}",
        help="print the installed Excubitor version and exit",
    )
    parser.set_defaults(_handler=None)
    parser.add_subparsers(dest="command", metavar="<command>")
    return parser


def main(argv: "list[str] | None" = None) -> int:
    """Parse ``argv`` (defaulting to ``sys.argv[1:]``) and dispatch to the selected subcommand.

    With no subcommand, prints help and returns 2 (the conventional "usage" exit) so a bare
    ``excubitor`` invocation is a usage error rather than a silent success.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
