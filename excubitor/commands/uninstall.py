"""``excubitor uninstall`` — remove exactly what a receipt owns, preserve everything else.

Uninstall is receipt-driven: it removes only the files and settings registrations the install's
hash-bound receipt records, and only when a file's bytes still match (a file the user edited after
install is preserved and reported as drifted). Unrelated configuration is never touched, so the
install→uninstall round trip is byte-for-byte for a canonical settings file. ``--dry-run`` previews the
disposition without writing.
"""
from __future__ import annotations

import argparse
import sys

from excubitor.installers import runtime as rt
from excubitor.installers import transaction

__all__ = ["register", "run"]


def register(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "uninstall",
        help="remove an Excubitor install, touching only receipt-owned bytes and entries",
        description="Remove exactly what the install receipt owns; preserve unrelated configuration.",
    )
    parser.add_argument("--runtime", default="claude-code")
    parser.add_argument("--scope", choices=[s.value for s in rt.Scope], default=rt.Scope.USER.value)
    parser.add_argument("--dry-run", action="store_true", help="preview what would be removed; write nothing")
    parser.set_defaults(_handler=run)


def run(args: argparse.Namespace) -> int:
    try:
        rt.profile_for(args.runtime)
    except KeyError as exc:
        print(f"excubitor uninstall: {exc}", file=sys.stderr)
        return 2

    try:
        result = transaction.apply_uninstall(args.runtime, args.scope, dry_run=args.dry_run)
    except transaction.TransactionError as exc:
        print(f"excubitor uninstall: {exc}", file=sys.stderr)
        return 1

    if not result.found:
        print(f"excubitor uninstall: no install receipt for {args.runtime}/{args.scope} — nothing to do.",
              file=sys.stderr)
        return 0

    verb = "would remove" if result.dry_run else "removed"
    print(f"{verb} {len(result.removed_files)} file(s), {result.removed_registrations} registration(s)"
          + (" and deleted the settings file" if result.settings_deleted else ""))
    for drifted in result.preserved_drifted:
        print(f"  preserved (edited since install, not ours to remove): {drifted}")
    return 0
