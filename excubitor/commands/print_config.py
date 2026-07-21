"""``excubitor print-config`` — show the effective neutral policy with per-value precedence/provenance.

Shows every resolved setting, where its value came from (env / policy.toml / default), and any legacy
(`CLAUDE_*`) deprecation warnings — so a user can see exactly what policy is in effect and why. Human
text by default; ``--json`` emits a stable, schema-tagged object.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from excubitor import config
from excubitor.core.events import LoopMode

__all__ = ["register", "run"]

CONFIG_SCHEMA = "excubitor.effective-config.v1"


def register(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "print-config",
        help="show the effective neutral policy and every override, with precedence",
        description="Resolve and print the effective neutral configuration with per-value provenance.",
    )
    parser.add_argument("--project-root", type=Path, default=None,
                        help="directory to resolve .excubitor/policy.toml from (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit the stable machine-readable JSON")
    parser.set_defaults(_handler=run)


def _loop_mode_value(mode: "LoopMode | None") -> "str | None":
    return mode.value if isinstance(mode, LoopMode) else None


def _to_json(cfg: config.Config) -> dict:
    return {
        "schema": CONFIG_SCHEMA,
        "policy_path": cfg.policy_path,
        "settings": {
            "loop_mode": {"value": _loop_mode_value(cfg.loop_mode.value),
                          "source": cfg.loop_mode.source},
            "allow_default_branch": {"value": cfg.allow_default_branch.value,
                                     "source": cfg.allow_default_branch.source},
            "state_home": {"value": cfg.state_home.value, "source": cfg.state_home.source},
            "opt_out_marker": {"value": cfg.opt_out_marker.value, "source": cfg.opt_out_marker.source},
            "one_unit_enabled": {"value": cfg.one_unit_enabled.value,
                                 "source": cfg.one_unit_enabled.source},
            "protected_roots": {"value": list(cfg.protected_roots.value),
                                "source": cfg.protected_roots.source},
        },
        "warnings": list(cfg.warnings),
    }


def run(args: argparse.Namespace) -> int:
    cfg = config.resolve_config(start_dir=args.project_root)
    payload = _to_json(cfg)
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    print(f"policy file: {cfg.policy_path or '(none — built-in defaults)'}")
    print("effective configuration (value <- source):")
    for key, entry in payload["settings"].items():
        print(f"  {key:<22} {entry['value']!r:<28} <- {entry['source']}")
    for warning in cfg.warnings:
        print(f"  warning: {warning}", file=sys.stderr)
    return 0
