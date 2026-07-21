"""``excubitor doctor`` — diagnose an install and (with ``--probe``) run a harmless-denial probe.

Reports versions, file integrity, and registration presence; ``--probe`` additionally runs the probe
framework. Because the CLI cannot drive the real runtime to dispatch the hook, ``--probe`` reports
``needs-probe`` (never ``protected``) and prints the manual verification command — the honest verdict
when no real host witness exists.
"""
from __future__ import annotations

import argparse
import json
import sys

from excubitor.installers import doctor as doctor_mod
from excubitor.installers import runtime as rt

__all__ = ["register", "run"]


def register(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "doctor",
        help="diagnose an install; with --probe, run a harmless-denial probe (reports needs-probe "
             "when no real host witness exists)",
        description="Diagnose an Excubitor install and optionally run the harmless-denial probe.",
    )
    parser.add_argument("--runtime", default="claude-code")
    parser.add_argument("--scope", choices=[s.value for s in rt.Scope], default=rt.Scope.USER.value)
    parser.add_argument("--probe", action="store_true",
                        help="attempt a harmless-denial probe and record its result")
    parser.add_argument("--json", action="store_true", help="emit the stable machine-readable JSON")
    parser.set_defaults(_handler=run)


def run(args: argparse.Namespace) -> int:
    try:
        rt.profile_for(args.runtime)
    except KeyError as exc:
        print(f"excubitor doctor: {exc}", file=sys.stderr)
        return 2

    report = doctor_mod.run_doctor(args.runtime, args.scope, do_probe=args.probe)
    if args.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if report.get("installed") else 1

    if not report["installed"]:
        print(f"excubitor doctor: {args.runtime}/{args.scope} is not installed.", file=sys.stderr)
        return 1

    print(f"doctor {report['runtime']}/{report['scope']}  "
          f"(installed by {report['installed_version']}, tool {report['excubitor_version']})")
    files = report["files"]
    print(f"  files: {files['present']} present"
          + (f", {len(files['drifted'])} drifted" if files["drifted"] else "")
          + (f", {len(files['missing'])} missing" if files["missing"] else ""))
    regs = report["registrations"]
    print(f"  registrations: {regs['expected']} expected"
          + (f", {len(regs['missing'])} MISSING from settings" if regs["missing"] else ", all present"))
    print(f"  protection: {report['protection']}")
    if "probe" in report and report["probe"].get("detail"):
        print(f"    probe: {report['probe']['detail']}")
    if "manual_verification" in report:
        print(f"    to confirm on a real host: {report['manual_verification']}")
    return 0
