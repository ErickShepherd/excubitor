"""Host-owned Ralph lifecycle storage, independent of model and native hook syntax.

This module belongs in the trusted host controller, outside the worker's writable
filesystem. It is NOT an authentication service: callers must authenticate owner
starts and collect candidate/check/review/worker facts independently. There is no
worker-facing activation CLI or JSON endpoint. An ordinary prompt, policy file,
environment variable, or worker-authored result is never read here as authority.

The caller must prove storage isolation and event provenance for its native mode
before wiring this into a hook. Merely placing SQLite outside a project is not a
portable security guarantee. Verification must execute untrusted candidate code
inside a sandbox, never with this controller's authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TERMINAL = ("complete", "cancelled")


class RunError(RuntimeError):
    """The controller must surface this error, never translate it into inactive."""


class Conflict(RunError):
    """A consumed authorization, overlapping run, or stale worker result."""


class NotReady(RunError):
    """A prerequisite is missing. Reload: observing expiry can latch blocked."""


def _text(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError("expected bounded nonempty text")


def _fingerprint(value: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError("expected a SHA-256 fingerprint")


def _canonical(project: str) -> str:
    path = Path(project)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("project must be an existing absolute directory")
    return os.path.normcase(str(path.resolve(strict=True)))


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Binding:
    runtime: str
    session: str
    project: str
    project_identity: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        _text(self.runtime)
        _text(self.session)
        object.__setattr__(self, "project", _canonical(self.project))
        info = Path(self.project).stat()
        identity = (info.st_dev, info.st_ino)
        if not info.st_ino or self.project_identity is not None and tuple(self.project_identity) != identity:
            raise ValueError("project directory identity changed or is unavailable")
        object.__setattr__(self, "project_identity", identity)

    @classmethod
    def _from_record(cls, raw: dict) -> Binding:
        """Decode history without requiring an ended run's directory to exist."""
        if set(raw) != {"runtime", "session", "project", "project_identity"}:
            raise ValueError("invalid stored binding")
        for name in ("runtime", "session", "project"):
            _text(raw[name])
        project = raw["project"]
        if not Path(project).is_absolute() or os.path.normcase(os.path.normpath(project)) != project:
            raise ValueError("invalid stored project path")
        identity = raw["project_identity"]
        if (
            not isinstance(identity, list)
            or len(identity) != 2
            or any(type(value) is not int for value in identity)
            or identity[1] <= 0
        ):
            raise ValueError("invalid stored directory identity")
        binding = object.__new__(cls)
        for name in ("runtime", "session", "project"):
            object.__setattr__(binding, name, raw[name])
        object.__setattr__(binding, "project_identity", tuple(identity))
        return binding

    @property
    def key(self) -> str:
        # Look up the original scope even if its directory has been replaced.
        # _read then rejects the changed identity instead of reporting inactive.
        scope = {"runtime": self.runtime, "session": self.session, "project": self.project}
        return hashlib.sha256(_json(scope).encode()).hexdigest()


@dataclass(frozen=True)
class Check:
    name: str
    oracle_digest: str

    def __post_init__(self) -> None:
        _text(self.name)
        _fingerprint(self.oracle_digest)


@dataclass(frozen=True)
class Contract:
    binding: Binding
    goal: str
    units: tuple[str, ...]
    checks: tuple[Check, ...]
    max_attempts: int
    deadline: int
    completion: str = "retain-branch"

    def __post_init__(self) -> None:
        _text(self.goal)
        if not isinstance(self.binding, Binding):
            raise ValueError("expected a canonical host binding")
        if not isinstance(self.units, tuple) or not self.units or len(set(self.units)) != len(self.units):
            raise ValueError("units must be a nonempty unique tuple")
        for unit in self.units:
            _text(unit)
        if not isinstance(self.checks, tuple) or not self.checks:
            raise ValueError("at least one frozen acceptance check is required")
        if any(not isinstance(check, Check) for check in self.checks):
            raise ValueError("invalid acceptance check")
        if len({check.name for check in self.checks}) != len(self.checks):
            raise ValueError("duplicate acceptance check")
        if type(self.max_attempts) is not int or self.max_attempts < len(self.units):
            raise ValueError("attempt budget must cover all work units")
        if type(self.deadline) is not int or self.deadline <= 0:
            raise ValueError("deadline must be a positive UTC timestamp")
        if self.completion != "retain-branch":
            raise ValueError("automatic merge, publication, and deployment are not implemented")

    @property
    def digest(self) -> str:
        return hashlib.sha256(_json(asdict(self)).encode()).hexdigest()


@dataclass(frozen=True)
class Candidate:
    """Facts collected by the trusted host about an immutable candidate snapshot.

    digest binds the tested bytes; commit identifies the retained Git result.
    The host must actually inspect isolation, cleanliness, and current candidate
    identity. Booleans from a worker's completion message are not these facts.
    """

    digest: str
    commit: str
    clean: bool
    isolated: bool

    def __post_init__(self) -> None:
        _fingerprint(self.digest)
        if not isinstance(self.commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.commit):
            raise ValueError("expected a complete Git object identity")
        if type(self.clean) is not bool or type(self.isolated) is not bool:
            raise ValueError("candidate facts must be booleans")


@dataclass(frozen=True)
class Run:
    id: str
    contract: Contract
    revision: int
    state: str
    attempts: int
    completed_units: int
    candidate: Candidate | None
    check_results: tuple[tuple[str, bool], ...]
    reviewed: bool

    @property
    def enforces(self) -> bool:
        # A blocked or stopping run retains its boundary until workers are drained.
        return self.state not in _TERMINAL


class RunStore:
    """Private host store with atomic, revision-checked lifecycle operations.

    create=True is provisioning, not activation. No record means inactive only
    after a successful read of an intact store; a missing/broken store raises.
    Access control is supplied by the native host/OS, not by a writable marker.
    """

    def __init__(self, directory: Path, *, create: bool = False, clock: Callable[[], float] = time.time):
        self.directory = Path(directory)
        if not self.directory.is_absolute():
            raise ValueError("authority directory must be absolute")
        for path in (self.directory, *self.directory.parents):
            if path.exists() and (
                path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400
            ):
                raise RunError("authority path traverses a link or reparse point")
        self.path = self.directory / "runs.sqlite3"
        self.clock = clock
        if create:
            self.directory.mkdir(parents=True, exist_ok=True)
            # Create-only provisioning cannot silently replace lost or prior state.
            with self.path.open("xb"):
                pass
            with self._connect(initializing=True) as db:
                db.executescript(
                    "CREATE TABLE metadata (version INTEGER NOT NULL); INSERT INTO metadata VALUES (1);"
                    "CREATE TABLE runs (id TEXT PRIMARY KEY, authorization TEXT UNIQUE NOT NULL, "
                    "binding TEXT NOT NULL, contract TEXT NOT NULL, digest TEXT NOT NULL, "
                    "revision INTEGER NOT NULL, state TEXT NOT NULL, progress TEXT NOT NULL);"
                    "CREATE UNIQUE INDEX active_binding ON runs(binding) "
                    "WHERE state NOT IN ('complete','cancelled');"
                )

    @contextmanager
    def _connect(self, *, initializing: bool = False) -> Iterator[sqlite3.Connection]:
        if not self.path.is_file() or self.path.is_symlink():
            raise RunError("authority store is missing or redirected; activation is unknown")
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)) as db, db:
                db.row_factory = sqlite3.Row
                if not initializing and [
                    tuple(row) for row in db.execute("SELECT version FROM metadata")
                ] != [(1,)]:
                    raise RunError("unsupported or damaged authority store")
                yield db
        except sqlite3.IntegrityError as exc:
            raise Conflict("authorization replay or overlapping run") from exc
        except sqlite3.Error as exc:
            raise RunError("authority store unavailable; do not disarm an active run") from exc

    @staticmethod
    def _read(row: sqlite3.Row) -> Run:
        try:
            raw = json.loads(row["contract"])
            raw["binding"] = Binding._from_record(raw["binding"])
            raw["units"] = tuple(raw["units"])
            raw["checks"] = tuple(Check(**check) for check in raw["checks"])
            contract = Contract(**raw)
            if contract.digest != row["digest"] or contract.binding.key != row["binding"]:
                raise ValueError("contract binding mismatch")
            progress = json.loads(row["progress"])
            candidate = Candidate(**progress["candidate"]) if progress["candidate"] else None
            if (
                set(progress) != {"attempts", "completed_units", "candidate", "checks", "reviewed", "drained"}
                or type(progress["attempts"]) is not int
                or not 0 <= progress["attempts"] <= contract.max_attempts
                or type(progress["completed_units"]) is not int
                or not 0 <= progress["completed_units"] <= len(contract.units)
                or type(progress["reviewed"]) is not bool
                or type(progress["drained"]) is not bool
                or not isinstance(progress["checks"], dict)
                or not set(progress["checks"]).issubset({check.name for check in contract.checks})
                or any(type(value) is not bool for value in progress["checks"].values())
                or row["state"]
                not in ("running", "interrupted", "blocked", "stopping", "complete", "cancelled")
                or type(row["revision"]) is not int
                or row["revision"] < 0
            ):
                raise ValueError("invalid progress record")
            if progress["drained"] != (row["state"] in _TERMINAL):
                raise ValueError("terminal state and worker shutdown record disagree")
            if row["state"] not in _TERMINAL and Binding(**asdict(contract.binding)) != contract.binding:
                raise ValueError("active project identity changed")
            if candidate is None and (progress["checks"] or progress["reviewed"]):
                raise ValueError("evidence without a candidate")
            if row["state"] == "complete" and (
                candidate is None
                or not candidate.clean
                or not candidate.isolated
                or progress["completed_units"] != len(contract.units)
                or not progress["reviewed"]
                or progress["checks"] != {check.name: True for check in contract.checks}
            ):
                raise ValueError("incomplete completion record")
            return Run(
                row["id"],
                contract,
                row["revision"],
                row["state"],
                progress["attempts"],
                progress["completed_units"],
                candidate,
                tuple(sorted(progress["checks"].items())),
                progress["reviewed"],
            )
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise RunError("invalid authority record; do not treat it as inactive") from exc

    def start(self, contract: Contract, authorization: str) -> Run:
        """Called only for independently authenticated, explicit owner approval."""
        _text(authorization)
        if contract.deadline <= self.clock():
            raise NotReady("authorization has already expired")
        if self.directory.resolve().is_relative_to(Path(contract.binding.project)):
            raise RunError("authority storage must be outside the worker project")
        run_id = str(uuid.uuid4())
        progress = {
            "attempts": 0,
            "completed_units": 0,
            "candidate": None,
            "checks": {},
            "reviewed": False,
            "drained": False,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, 0, 'running', ?)",
                (
                    run_id,
                    authorization,
                    contract.binding.key,
                    _json(asdict(contract)),
                    contract.digest,
                    _json(progress),
                ),
            )
            return self._read(db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())

    def lookup(self, binding: Binding) -> Run | None:
        with self._connect() as db:
            records = [
                self._read(row) for row in db.execute("SELECT * FROM runs WHERE binding = ?", (binding.key,))
            ]
            return next((run for run in records if run.enforces), None)

    def get(self, run_id: str) -> Run:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise RunError("unknown run")
            return self._read(row)

    def latest(self, binding: Binding) -> Run | None:
        """Read the last accepted job in this exact task, including terminal history.

        Insertion order is database-owned; revisions, clocks, and UUID ordering
        do not tell which of several successive jobs was accepted last.
        Historical completion is not permission to start or reactivate a job.
        """
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM runs WHERE binding = ? ORDER BY rowid DESC LIMIT 1", (binding.key,)
            ).fetchone()
            return self._read(row) if row is not None else None

    def _change(self, run: Run, operation: Callable[[dict, Run], str], *, working: bool = False) -> Run:
        expired = False
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM runs WHERE id = ?", (run.id,)).fetchone()
            if row is None or row["revision"] != run.revision:
                raise Conflict("stale run revision")
            current = self._read(row)
            if current.contract != run.contract or not current.enforces:
                raise Conflict("contract changed or run is terminal")
            if working:
                if current.state != "running" or current.attempts == 0:
                    raise NotReady("run is not working within its original limits")
                expired = self.clock() >= current.contract.deadline
            progress = json.loads(row["progress"])
            state = "blocked" if expired else operation(progress, current)
            db.execute(
                "UPDATE runs SET revision = revision + 1, state = ?, progress = ? WHERE id = ?",
                (state, _json(progress), run.id),
            )
            updated = self._read(db.execute("SELECT * FROM runs WHERE id = ?", (run.id,)).fetchone())
        # Commit the observed expiry before reporting failure. A later wall-clock
        # correction must not make the same failed completion attempt eligible.
        if expired:
            raise NotReady("run expired; progress and protections are retained")
        return updated

    def begin_attempt(self, run: Run) -> Run:
        def change(progress: dict, current: Run) -> str:
            if current.state != "running":
                raise NotReady("blocked or cancelling runs cannot start another worker")
            if current.attempts >= current.contract.max_attempts or self.clock() >= current.contract.deadline:
                return "blocked"
            progress.update(attempts=current.attempts + 1, candidate=None, checks={}, reviewed=False)
            return "running"

        return self._change(run, change)

    def checkpoint(self, run: Run, candidate: Candidate, *, unit: str | None = None) -> Run:
        def change(progress: dict, current: Run) -> str:
            if unit is not None:
                units = current.contract.units
                if current.completed_units >= len(units) or units[current.completed_units] != unit:
                    raise Conflict("checkpoint does not match the next agreed work unit")
                progress["completed_units"] += 1
            progress.update(candidate=asdict(candidate), checks={}, reviewed=False)
            return "running"

        return self._change(run, change, working=True)

    def record_check(self, run: Run, candidate: Candidate, check: Check, *, passed: bool) -> Run:
        """Accept the host verifier's result, never a worker's claimed test summary."""

        def change(progress: dict, current: Run) -> str:
            if (
                candidate != current.candidate
                or check not in current.contract.checks
                or type(passed) is not bool
            ):
                raise Conflict("verification is not bound to this candidate and frozen check")
            progress["checks"][check.name] = passed
            progress["reviewed"] = False
            return "running"

        return self._change(run, change, working=True)

    def record_review(self, run: Run, candidate: Candidate, *, passed: bool) -> Run:
        def change(progress: dict, current: Run) -> str:
            if candidate != current.candidate or type(passed) is not bool:
                raise Conflict("review is not bound to this candidate")
            progress["reviewed"] = passed
            return "running"

        return self._change(run, change, working=True)

    def finish(self, run: Run, current_candidate: Candidate, *, workers_idle: bool) -> Run:
        def change(progress: dict, current: Run) -> str:
            expected = {check.name: True for check in current.contract.checks}
            if (
                current.completed_units != len(current.contract.units)
                or current_candidate != current.candidate
                or not current_candidate.clean
                or not current_candidate.isolated
                or dict(current.check_results) != expected
                or not current.reviewed
                or workers_idle is not True
            ):
                raise NotReady(
                    "completion needs all units, frozen checks, review, a committed clean isolated "
                    "candidate, and confirmed worker shutdown"
                )
            progress["drained"] = True
            return "complete"

        return self._change(run, change, working=True)

    def cancel(self, run: Run) -> Run:
        return self._change(run, lambda progress, current: "stopping")

    def interrupt(self, run: Run) -> Run:
        """Preserve the boundary when the host observes interrupted execution."""

        def change(progress: dict, current: Run) -> str:
            if current.state != "running":
                raise NotReady("only a running job can be interrupted")
            return "interrupted"

        return self._change(run, change)

    def resume(self, run: Run, binding: Binding, *, workers_idle: bool) -> Run:
        """Resume the same native task within its original, unextended authority."""

        def change(progress: dict, current: Run) -> str:
            if (
                current.state != "interrupted"
                or binding != current.contract.binding
                or workers_idle is not True
            ):
                raise NotReady("resumption needs the original task and confirmed old-worker shutdown")
            if self.clock() >= current.contract.deadline:
                return "blocked"
            return "running"

        return self._change(run, change)

    def acknowledge_cancel(self, run: Run, *, workers_idle: bool) -> Run:
        def change(progress: dict, current: Run) -> str:
            if current.state != "stopping" or workers_idle is not True:
                raise NotReady("cancellation must drain workers before releasing the boundary")
            progress["drained"] = True
            return "cancelled"

        return self._change(run, change)
