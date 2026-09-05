"""Disposable native SessionEnd binding. Does not grant or complete a Ralph run."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.runs import Binding, RunStore  # noqa: E402
from excubitor.session import record_session_end  # noqa: E402


def observe(payload: dict, store: RunStore, project: Path) -> dict:
    if payload.get("hook_event_name") != "SessionEnd":
        raise ValueError("this observer accepts only native SessionEnd")
    binding = Binding("codex-cli", payload["session_id"], payload["cwd"])
    if Path(binding.project) != project.resolve():
        return {"event": "SessionEnd", "result": "outside-selected-project"}
    run = record_session_end(store, binding)
    return {
        "event": "SessionEnd",
        "result": run.state if run else "inactive",
        "binding": binding.key,
        "run_id": run.id if run else None,
        "retains_protection": run.enforces if run else False,
        "workers_drained": False,
        "completion_claimed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not all(path.is_absolute() for path in (args.store, args.project, args.output)):
        parser.error("all paths must be absolute")
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"event": "SessionEnd", "result": "failed"}
    try:
        payload = json.loads(sys.stdin.read(65537))
        report = observe(payload, RunStore(args.store), args.project)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print("Excubitor test reconciliation failed; do not treat its run as inactive.", file=sys.stderr)
        raise
    finally:
        with (args.output / f"session-end-{uuid.uuid4()}.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)


if __name__ == "__main__":
    main()
