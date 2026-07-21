"""``excubitor install`` — plan or apply an Excubitor install for a runtime integration.

``--dry-run`` computes and prints the exact plan while writing nothing (C2.3). Without it, the plan is
applied transactionally (C2.5): the neutral policy is validated first (an unknown version stops), then
the artifacts are staged atomically, the exact-tuple hooks registered, and a hash-bound receipt
committed — any failure rolls back the exact prior state. Installation is reported as *not protected
yet*: only a real harmless-denial host probe (``excubitor doctor --probe``) earns that.

``--runtime auto`` acts only on *detected* runtimes; an explicit ``--runtime`` acts even when the
runtime's control dir is absent (it would be created). Only Claude Code is supported.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from excubitor import config
from excubitor.installers import plan as plan_mod
from excubitor.installers import runtime as rt
from excubitor.installers import transaction, validate

__all__ = ["register", "run"]

_SUPPORTED = ["claude-code"]


def register(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "install",
        help="plan (--dry-run) or apply an Excubitor install into a coding-agent runtime",
        description="Plan or apply an Excubitor install transactionally.",
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
                        help="print the exact plan and write nothing")
    parser.add_argument("--allow-downgrade", action="store_true",
                        help="allow installing over a receipt from a newer Excubitor (default: refuse)")
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

    # Validate the neutral policy before any mutation — an unknown version stops the install.
    policy, _policy_path = config.load_policy_file(project_root if scope is rt.Scope.PROJECT else home)
    policy_result = validate.validate_policy(policy)
    if not policy_result.ok:
        for problem in policy_result.problems:
            print(f"excubitor install: policy error: {problem}", file=sys.stderr)
        return 2

    try:
        targets = rt.discover(home=home, project_root=project_root, scope=scope)
    except ValueError as exc:
        print(f"excubitor install: {exc}", file=sys.stderr)
        return 2

    if args.runtime == "auto":
        profiles = _selected_profiles("auto", targets)
        if not profiles:
            print("excubitor install: no supported runtime detected (use --runtime to force it).",
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
        if args.dry_run:
            sys.stdout.write(plan_mod.render_plan(plan))
            continue
        try:
            result = transaction.apply_install(
                profile, target, plan, allow_downgrade=args.allow_downgrade
            )
        except (ValueError, transaction.TransactionError) as exc:
            print(f"excubitor install: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        status = "changed" if result.changed else "already current"
        print(f"installed {target.runtime}/{target.scope.value}: {status} "
              f"({', '.join(result.messages)})")
        print("  NOT protected yet — run `excubitor doctor --probe` for a real harmless-denial "
              "host probe (installation earns 'protected' only after that probe succeeds).")
    return exit_code
