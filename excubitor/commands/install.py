"""Read-only previews of the legacy hook installer during Ralph-only remediation.

Legacy hooks can affect ordinary tasks in either scope. This command cannot install
them as a substitute for the unfinished explicit-job installer. The transaction
library remains available for isolated tests and existing-installation maintenance.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from excubitor import config
from excubitor.installers import plan as plan_mod
from excubitor.installers import runtime as rt
from excubitor.installers import validate

__all__ = ["register", "run"]

_SUPPORTED = ["claude-code", "codex"]


def register(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "install",
        help="inspect a legacy install plan (--dry-run); new registrations are unavailable",
        description=("Preview the legacy hook layout without writing. New registrations are disabled "
                     "until the explicit-job Ralph installer is ready; ordinary tasks must stay unaffected."),
    )
    parser.add_argument(
        "--runtime", default="auto",
        help="legacy runtime layout to inspect: 'auto' (detected only) or one of: " + ", ".join(_SUPPORTED),
    )
    parser.add_argument("--scope", choices=[s.value for s in rt.Scope], default=rt.Scope.USER.value)
    parser.add_argument("--home", type=Path, default=None,
                        help="home directory for USER scope (default: the current user's home)")
    parser.add_argument("--project-root", type=Path, default=None,
                        help="project root for PROJECT scope (default: current directory)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the exact plan and write nothing")
    parser.add_argument("--allow-downgrade", action="store_true",
                        help="legacy compatibility option; cannot enable registration writes")
    parser.set_defaults(_handler=run)


def _selected_profiles(runtime: str, targets: "list[rt.RuntimeTarget]") -> "list[rt.RuntimeProfile]":
    if runtime == "auto":
        return [rt.profile_for(t.runtime) for t in targets if t.detected]
    return [rt.profile_for(runtime)]


def run(args: argparse.Namespace) -> int:
    """Handle ``excubitor install``. Returns a process exit code."""
    if not args.dry_run:
        print(
            "excubitor install: the legacy hooks also enforce rules on ordinary tasks, so new "
            "registrations are disabled in this Ralph-only development branch. No settings were "
            "changed. The explicit-job installer is not ready. Use --dry-run only to inspect the "
            "old layout; status, doctor and uninstall remain available for existing installations.",
            file=sys.stderr,
        )
        return 2
    scope = rt.Scope(args.scope)
    home = args.home if args.home is not None else Path.home()
    project_root = args.project_root if args.project_root is not None else Path.cwd()

    # Validate the neutral policy before any mutation — an unknown version stops the install.
    try:
        policy, _policy_path = config.load_policy_file(
            project_root if scope is rt.Scope.PROJECT else home, strict=True
        )
    except config.PolicyFileError as exc:
        print(f"excubitor install: policy error: {exc}", file=sys.stderr)
        return 2
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
        print("Legacy hook preview only: this layout affects ordinary tasks and cannot be applied here.")
        sys.stdout.write(plan_mod.render_plan(plan))
    return exit_code
