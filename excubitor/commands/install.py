"""``excubitor install`` — deterministic install planning (dry-run) for a runtime integration.

Campaign 2 lands this in two steps: this item (C2.3) implements ``--dry-run``, which computes and prints
the exact plan while writing nothing; the transaction that *applies* a plan (atomic stage/register with
a hash-bound receipt and rollback) lands in a later item. Until then a non-dry-run invocation refuses
with a precise message rather than silently no-op an apply the user asked for.

``--runtime auto`` plans only for *detected* runtimes; an explicit ``--runtime`` plans even when the
runtime's control dir is absent (it would be created). Only Claude Code is supported.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from excubitor.installers import plan as plan_mod
from excubitor.installers import runtime as rt

__all__ = ["register", "run"]

_SUPPORTED = ["claude-code"]


def register(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "install",
        help="plan (and, later, apply) an Excubitor install into a coding-agent runtime",
        description="Plan an Excubitor install. Only --dry-run is available in this build.",
    )
    parser.add_argument(
        "--runtime", default="auto",
        help="runtime to install into: 'auto' (detected only) or one of: " + ", ".join(_SUPPORTED),
    )
    parser.add_argument("--scope", choices=[s.value for s in rt.Scope], default=rt.Scope.USER.value)
    parser.add_argument("--home", type=Path, default=None,
                        help="home directory for USER scope (default: the current user's home)")
    parser.add_argument("--project-root", type=Path, default=None,
                        help="project root for PROJECT scope (default: current directory)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the exact plan and write nothing (required in this build)")
    parser.set_defaults(_handler=run)


def _selected_profiles(runtime: str, targets: "list[rt.RuntimeTarget]") -> "list[rt.RuntimeProfile]":
    if runtime == "auto":
        return [rt.profile_for(t.runtime) for t in targets if t.detected]
    return [rt.profile_for(runtime)]


def run(args: argparse.Namespace) -> int:
    """Handle ``excubitor install``. Returns a process exit code."""
    scope = rt.Scope(args.scope)
    home = args.home if args.home is not None else Path.home()
    project_root = args.project_root if args.project_root is not None else Path.cwd()

    if not args.dry_run:
        print(
            "excubitor install: only --dry-run is available in this build; the apply transaction "
            "lands in a later Campaign 2 item. Re-run with --dry-run to preview the plan.",
            file=sys.stderr,
        )
        return 2

    try:
        targets = rt.discover(home=home, project_root=project_root, scope=scope)
    except ValueError as exc:
        print(f"excubitor install: {exc}", file=sys.stderr)
        return 2

    if args.runtime == "auto":
        profiles = _selected_profiles("auto", targets)
        if not profiles:
            print("excubitor install: no supported runtime detected (use --runtime to force a plan).",
                  file=sys.stderr)
            return 1
    else:
        try:
            profiles = _selected_profiles(args.runtime, targets)
        except KeyError as exc:
            print(f"excubitor install: {exc}", file=sys.stderr)
            return 2

    exit_code = 0
    for profile in profiles:
        target = profile.target(scope, home, project_root)
        try:
            plan = plan_mod.build_install_plan(profile, target)
        except FileNotFoundError as exc:
            print(f"excubitor install: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        sys.stdout.write(plan_mod.render_plan(plan))
    return exit_code
