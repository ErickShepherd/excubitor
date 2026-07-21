"""The ``excubitor`` CLI subcommands.

Each subcommand lives in its own module and exposes ``register(subparsers)``, which adds its parser and
sets ``_handler`` (the function the top-level dispatcher in :mod:`excubitor.cli` calls). Keeping one
module per command lets each plan item add a command without touching the others.

:func:`register_all` wires every implemented command; it is the single place :mod:`excubitor.cli` calls,
so the parser and the dispatch stay in lockstep.
"""
from __future__ import annotations

import argparse

from excubitor.commands import doctor as _doctor
from excubitor.commands import install as _install
from excubitor.commands import print_config as _print_config
from excubitor.commands import status as _status
from excubitor.commands import uninstall as _uninstall

__all__ = ["register_all"]


def register_all(subparsers: "argparse._SubParsersAction") -> None:
    """Register every implemented subcommand onto ``subparsers``."""
    _install.register(subparsers)
    _uninstall.register(subparsers)
    _status.register(subparsers)
    _print_config.register(subparsers)
    _doctor.register(subparsers)
