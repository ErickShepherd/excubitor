#!/usr/bin/env python3
"""The R-04 atomic frozen-oracle runner — the YOLO permit-to-act gate.

check_oracle_frozen.py is a point-in-time diagnostic: it can prove the oracle surface matched the
base tree at the instant it looked, but the recipe then ran the witness as a SECOND command, and the
loop could edit the oracle between the two (the check/run race). A point-in-time diff is therefore
not proof that the code which produced the trusted exit code is the frozen code.

This runner closes that gap by binding the checked bytes to the verdict in ONE operation:

    1. PRECHECK — evaluate the complete oracle surface against the baseline
       (check_oracle_frozen.evaluate: lexical paths, symlink-chain hops, resolved targets, path
       types, link targets, and the committed diff — every ambiguity refuses);
    2. SNAPSHOT — record each surface path's type, link target, and content hash (sha256);
    3. EXECUTE — run the witness WITHOUT a shell (shlex-split argv, shell=False: no substitution,
       no redirection, no chaining — a metacharacter in verified-by is a literal argument);
    4. RECHECK — re-evaluate the surface and re-snapshot; the verdict is returned ONLY when the
       recheck is frozen and byte/topology-identical to the snapshot.

HONEST LIMIT. Snapshot equality proves the surface was identical before and after execution — it
cannot prove the surface never changed DURING execution (a witness that mutates an oracle file and
restores it before exiting defeats the recheck; OS-level atomicity does not exist here). What the
runner guarantees is: the verdict it returns was produced by a run whose start and end state both
matched the frozen baseline. That is the strongest binding available without an immutable
filesystem, and it removes the between-commands window entirely.

FAIL-DENY. Refusal (exit 10) on any precheck/recheck failure or snapshot mismatch. A witness that
cannot execute, times out, or exits non-zero is RED (exit 1) — never green, never a refusal
masquerading as a pass.

Exit codes:
    0  = surface frozen through the whole run AND witness exited 0 (GREEN — the permit to act)
    1  = surface frozen but the witness failed / could not run / timed out (RED)
    10 = REFUSED — surface not frozen, unverifiable, or changed across execution (fail-deny)
    2  = usage error

Usage:
    run_frozen_oracle.py --repo <path> --base <branch> --verified-by "<command>" [--timeout 600]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_oracle_frozen as cof  # noqa: E402  (the shared surface model + evaluate)

EXIT_GREEN = 0
EXIT_RED = 1
EXIT_REFUSED = 10
EXIT_USAGE = 2


def _snapshot(surface: dict[str, str]) -> tuple[str | None, dict[str, tuple[str, str]]]:
    """Record each surface path's (kind, identity): a symlink's identity is its literal target, a
    regular file's is its sha256. Returns (refusal_reason, snapshot) — a path that is neither
    (vanished mid-flight, special file) is a refusal, never a guess."""
    snap: dict[str, tuple[str, str]] = {}
    for rel, p in sorted(surface.items()):
        if os.path.islink(p):
            snap[rel] = ("link", os.readlink(p))
        elif os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    snap[rel] = ("file", hashlib.sha256(f.read()).hexdigest())
            except OSError as e:
                return f"cannot hash oracle file {rel}: {e} (fail-deny)", {}
        else:
            return f"oracle surface path {rel} is neither file nor symlink (fail-deny)", {}
    return None, snap


def run(repo: str, base: str, verified_by: str, timeout: float) -> int:
    # 1. PRECHECK
    reason, surface = cof.evaluate(repo, base, verified_by)
    if reason is not None:
        print(f"REFUSED (precheck): {reason}", file=sys.stderr)
        return EXIT_REFUSED

    # 2. SNAPSHOT
    reason, before = _snapshot(surface)
    if reason is not None:
        print(f"REFUSED (snapshot): {reason}", file=sys.stderr)
        return EXIT_REFUSED

    # 3. EXECUTE — no shell: the command is an argv, not a script. Metacharacters stay literal.
    try:
        argv = shlex.split(verified_by)
    except ValueError as e:
        print(f"usage: unparseable verified-by: {e}", file=sys.stderr)
        return EXIT_USAGE
    if not argv:
        print("usage: empty verified-by", file=sys.stderr)
        return EXIT_USAGE
    try:
        witness = subprocess.run(argv, cwd=repo, shell=False, timeout=timeout,
                                 capture_output=True, text=True)
        witness_code: int | None = witness.returncode
        witness_tail = (witness.stdout + witness.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        witness_code, witness_tail = None, f"witness timed out after {timeout}s"
    except OSError as e:
        witness_code, witness_tail = None, f"witness could not execute: {e}"

    # 4. RECHECK — the surface must still be frozen AND byte/topology-identical to the snapshot.
    reason, surface_after = cof.evaluate(repo, base, verified_by)
    if reason is not None:
        print(f"REFUSED (recheck): {reason}", file=sys.stderr)
        return EXIT_REFUSED
    reason, after = _snapshot(surface_after)
    if reason is not None:
        print(f"REFUSED (recheck snapshot): {reason}", file=sys.stderr)
        return EXIT_REFUSED
    if after != before:
        drifted = sorted(k for k in (set(before) | set(after)) if before.get(k) != after.get(k))
        print("REFUSED: oracle surface changed across witness execution — the verdict was not "
              "produced by the frozen bytes: " + ", ".join(drifted), file=sys.stderr)
        return EXIT_REFUSED

    # Only now is the witness verdict trustworthy enough to report.
    if witness_code == 0:
        print("GREEN: witness exited 0 under a frozen oracle surface — "
              + ", ".join(sorted(surface)))
        return EXIT_GREEN
    detail = f"exit {witness_code}" if witness_code is not None else "no verdict"
    print(f"RED: witness failed ({detail}) under a frozen oracle surface.\n{witness_tail}",
          file=sys.stderr)
    return EXIT_RED


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Atomically run a verified-by witness under a frozen-oracle guarantee.")
    ap.add_argument("--repo", required=True, help="path to the repo (the loop's working copy)")
    ap.add_argument("--base", required=True, help="the loop branch's base (the repo's default branch)")
    ap.add_argument("--verified-by", required=True, help="the claim's verified-by command string")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="witness timeout in seconds (default 600; a hung witness is RED)")
    args = ap.parse_args()
    return run(args.repo, args.base, args.verified_by, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
