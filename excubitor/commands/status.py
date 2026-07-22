"""``excubitor status`` — report installed state, versions, compatibility, and protection verdict.

Human text by default; ``--json`` emits the stable, schema-tagged inventory for tooling. The protection
verdict is deliberately conservative: it comes from a recorded host probe, never from file presence, so
this command can never claim "protected" for an install that has not passed a real harmless-denial
probe.
"""
from __future__ import annotations

import argparse
import json
import sys

from excubitor.installers import status as status_mod

__all__ = ["register", "run"]


def register(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "status",
        help="report Excubitor versions, installed runtimes, and the honest protection verdict",
        description="Report installed state and compatibility. Never infers protection from file "
                    "presence — only a recorded host probe earns 'protected'.",
    )
    parser.add_argument("--json", action="store_true", help="emit the stable machine-readable JSON")
    parser.set_defaults(_handler=run)


def run(args: argparse.Namespace) -> int:
    data = status_mod.gather_status()
    if args.json:
        json.dump(data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    print(f"excubitor {data['excubitor_version']}  (core protocol {data['core_protocol']})")
    print(f"verified enforcement:  {', '.join(data['supported_runtimes']) or 'none'}")
    print(f"adapter foundations:   {', '.join(data['available_adapters'])}")
    print(f"designed, not built:   {', '.join(data['designed_not_supported'])}")
    if not data["installations"]:
        print("installations:         none")
        return 0
    print("installations:")
    for inst in data["installations"]:
        files = inst["files"]
        print(f"  {inst['runtime']}/{inst['scope']}  (installed by {inst['installed_version']} "
              f"at {inst['installed_at']})")
        print(f"    files: {files['present']} present"
              + (f", {len(files['drifted'])} drifted" if files["drifted"] else "")
              + (f", {len(files['missing'])} missing" if files["missing"] else ""))
        print(f"    registrations: {inst['registrations']}")
        print(f"    protection: {inst['protection']}"
              + (f" — {inst['probe']['detail']}" if inst["probe"].get("detail") else ""))
    return 0
