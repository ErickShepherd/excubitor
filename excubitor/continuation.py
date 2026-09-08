"""Durable host observations for fresh workers, never completion authority.

Kept outside rotating watchdog journals and candidate workspaces. SQLite commits
feedback and its observation together, so controller loss cannot leave half a
handoff. Missing legacy history starts empty; damaged history stops the caller.
The host's RunStore alone owns progress, acceptance, and resource limits.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager

from excubitor.processes import ProcessResult
from excubitor.runs import Run, RunError, RunStore

_FEEDBACK_LIMIT = 16384


class Continuation:
    def __init__(self, store: RunStore):
        self.store = store
        self.path = store.directory / "continuation.sqlite3"

    @contextmanager
    def _connect(self, run: Run):
        if self.path.is_symlink():
            raise RunError("continuation history is redirected")
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
                db.row_factory = sqlite3.Row
                db.execute(
                    "CREATE TABLE IF NOT EXISTS handoffs ("
                    "run TEXT PRIMARY KEY, contract TEXT NOT NULL, "
                    "completed_units INTEGER NOT NULL, feedback TEXT NOT NULL)"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS observations ("
                    "id INTEGER PRIMARY KEY, run TEXT NOT NULL, attempt INTEGER NOT NULL, "
                    "completed_units INTEGER NOT NULL, phase TEXT NOT NULL, outcome TEXT NOT NULL, "
                    "observed_at REAL NOT NULL, facts TEXT NOT NULL)"
                )
                db.execute("CREATE INDEX IF NOT EXISTS observations_by_run ON observations (run, id)")
                db.execute(
                    "INSERT OR IGNORE INTO handoffs VALUES (?, ?, ?, '')",
                    (run.id, run.contract.digest, run.completed_units),
                )
                row = db.execute("SELECT contract FROM handoffs WHERE run = ?", (run.id,)).fetchone()
                if row["contract"] != run.contract.digest:
                    raise RunError("continuation history does not match the original agreement")
                yield db
        except sqlite3.Error as exc:
            raise RunError("continuation history is unavailable or damaged") from exc

    def feedback(self, run: Run) -> str:
        with self._connect(run) as db:
            row = db.execute("SELECT * FROM handoffs WHERE run = ?", (run.id,)).fetchone()
            # A crash after checkpointing but before clearing feedback must not
            # attach the previous unit's repair to the next unit.
            return row["feedback"] if row["completed_units"] == run.completed_units else ""

    def note(
        self,
        run: Run,
        phase: str,
        outcome: str,
        *,
        result: ProcessResult | None = None,
        feedback: str | None = None,
        check: str | None = None,
    ) -> None:
        facts = {}
        if check is not None:
            facts["check"] = check
        if result is not None:
            execution = result.execution
            facts.update(
                elapsed_seconds=execution.elapsed_seconds,
                exit_code=execution.exit_code,
                timed_out=execution.timed_out,
                output_limited=execution.output_limited,
                cancelled=result.cancelled,
                drained=result.drained,
                processes=result.processes,
                retryable_error=result.retryable_error,
            )
        # Never persist worker prose as host instructions or parse it as success.
        with self._connect(run) as db:
            db.execute(
                "INSERT INTO observations "
                "(run, attempt, completed_units, phase, outcome, observed_at, facts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run.id,
                    run.attempts,
                    run.completed_units,
                    phase,
                    outcome,
                    self.store.clock(),
                    json.dumps(facts, allow_nan=False),
                ),
            )
            if feedback is not None:
                db.execute(
                    "UPDATE handoffs SET completed_units = ?, feedback = ? WHERE run = ?",
                    (run.completed_units, feedback[:_FEEDBACK_LIMIT], run.id),
                )

    def handoff(self, run: Run) -> dict:
        with self._connect(run) as db:
            rows = db.execute(
                "SELECT attempt, phase, outcome, observed_at, facts FROM observations "
                "WHERE run = ? ORDER BY id DESC LIMIT 6",
                (run.id,),
            ).fetchall()
        recent = []
        for row in reversed(rows):
            try:
                facts = json.loads(row["facts"])
            except (TypeError, ValueError) as exc:
                raise RunError("continuation observation is damaged") from exc
            recent.append({key: row[key] for key in ("attempt", "phase", "outcome", "observed_at")} | facts)
        return {
            "checkpointed_units": run.completed_units,
            "total_units": len(run.contract.units),
            "pending_units": len(run.contract.units) - run.completed_units,
            "attempt": run.attempts,
            "remaining_attempts_after_this_one": max(0, run.contract.max_attempts - run.attempts),
            "seconds_remaining": max(0, run.contract.deadline - self.store.clock()),
            "recent_host_observations": recent,
        }
