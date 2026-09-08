"""Internal subprocess entry for the native development watchdog."""

import argparse
from pathlib import Path
from types import SimpleNamespace

from excubitor.commands.ralph import _controller, _resume


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("watch", "controller"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    operation = _controller if args.mode == "controller" else _resume
    return operation(SimpleNamespace(root=args.root, background=False))


if __name__ == "__main__":
    raise SystemExit(main())
