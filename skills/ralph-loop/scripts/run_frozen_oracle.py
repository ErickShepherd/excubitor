#!/usr/bin/env python3
"""The R-04 atomic frozen-oracle runner — the YOLO permit-to-act gate.

check_oracle_frozen.py is a point-in-time diagnostic: it can prove the oracle surface matched the
base tree at the instant it looked, but the recipe then ran the witness as a SECOND command, and the
loop could edit the oracle between the two (the check/run race). A point-in-time diff is therefore
not proof that the code which produced the trusted exit code is the frozen code.

This runner closes that gap by binding the checked bytes to the verdict in ONE operation, and — the
2026-07-16 independent-review hardening — by binding WHAT RUNS to state the loop cannot author:

    0. BASE PIN — `--base` must resolve to the repo's default branch (origin/HEAD, else the sole
       main/master, else an explicit init.defaultBranch naming one). A caller-chosen base (e.g.
       `--base HEAD` on the loop's own branch) would let the loop anchor the gate to its own
       commits, making every check below vacuous — REFUSED.
    1. ANCHOR BINDING — the witness command must appear verbatim in the BASE-TREE blob of a tracked
       anchor file (`--anchor`, e.g. the telos ledger or plan file). The command is read against
       baseline-authored state, so a caller-supplied replacement command (`/bin/true <tracked
       file>`) is REFUSED no matter which frozen files it happens to name: naming a frozen file
       earns nothing — only a command the baseline author wrote can produce a permit.
    2. EXECUTABLE BINDING — argv[0] is resolved (bare names against the fixed trusted PATH
       /usr/bin:/bin, never the caller's PATH) and must itself be trustworthy: an executable inside
       the repo must be tracked at base and joins the frozen surface (the untracked, agent-writable
       `.venv/bin/python` is REFUSED — replacing the interpreter forges any verdict); an executable
       outside the repo must not be writable by the invoking user (file, dir, resolved target, its
       dir). An unresolvable executable is REFUSED, not RED — trust cannot be bound.
    3. VERDICT-SURFACE BINDING — known verdict-affecting companions are bound too: every
       `conftest.py` from the repo root down to each oracle file, root runner configuration
       (pytest.ini, pyproject.toml, setup.cfg, tox.ini), and — for a `-m <module>` witness — a
       repo-root module/package that would shadow it on sys.path. Tracked → frozen with the
       surface; present-but-untracked → REFUSED (cannot be bound to the baseline).
    4. PRECHECK — evaluate the complete oracle surface against the baseline
       (check_oracle_frozen.evaluate: lexical paths, symlink hops — file AND directory — resolved
       targets, path types, link targets, regular-file content vs the base blob, and the committed
       diff — every ambiguity refuses);
    5. SNAPSHOT — record each surface path's type, link target, and content hash (sha256);
    6. EXECUTE — run the witness WITHOUT a shell (shlex-split argv, shell=False: no substitution,
       no redirection, no chaining — a metacharacter in verified-by is a literal argument) and
       under a SANITIZED environment (fixed PATH=/usr/bin:/bin, no PYTHONPATH/PYTHONSTARTUP or
       other inherited injection vectors, user site-packages disabled) so the caller's environment
       cannot swap what the trusted executable loads;
    7. RECHECK — re-evaluate the surface and re-snapshot; the verdict is returned ONLY when the
       recheck is frozen and byte/topology-identical to the snapshot.

HONEST LIMITS. Snapshot equality proves the surface was identical before and after execution — it
cannot prove the surface never changed DURING execution (a witness that mutates an oracle file and
restores it before exiting defeats the recheck; OS-level atomicity does not exist here). The
executable/environment binding narrows, not perfects, trusted execution: a baseline-AUTHORED command
is trusted author intent, so a DoD author who writes `/bin/true x` or delegates through a launcher
(`env …`) owns that Goodhart risk; the content of a trusted interpreter's system site-packages, and
sys.path shadowing from a SCRIPT's own directory (direct-script witnesses), remain outside the
frozen surface; a gate run as root refuses (everything is root-writable) — the safe direction. See
KNOWN-BYPASSES.md ("the frozen-oracle gate binds authorship and bytes, not semantics").

FAIL-DENY. Refusal (exit 10) on any binding/precheck/recheck failure or snapshot mismatch. A
witness that executes but fails, or times out, is RED (exit 1) — never green, never a refusal
masquerading as a pass.

Exit codes:
    0  = fully bound + frozen through the whole run AND witness exited 0 (GREEN — the permit to act)
    1  = bound + frozen but the witness failed or timed out (RED)
    10 = REFUSED — a binding failed, surface not frozen, unverifiable, or changed across execution
    2  = usage error

Usage:
    run_frozen_oracle.py --repo <path> --base <default-branch> --anchor <tracked ledger/plan file> \
        --verified-by "<command>" [--timeout 600]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shlex
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_oracle_frozen as cof  # noqa: E402  (the shared surface model + evaluate)

EXIT_GREEN = 0
EXIT_RED = 1
EXIT_REFUSED = 10
EXIT_USAGE = 2

# The ONLY executable search path the gate resolves against, and the ONLY PATH the witness runs
# under. Fixed and system-owned: the caller's PATH is an agent-controlled injection vector.
_TRUSTED_PATH = "/usr/bin:/bin"
# Root-of-repo files that can silently change a test runner's verdict for any file it collects.
_ROOT_RUNNER_CONFIGS = ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "conftest.py")


def _git_text(repo: str, *args: str) -> tuple[bool, str]:
    """Read-only git query, decoding output tolerantly (a binary blob must not crash the gate)."""
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                           errors="replace", timeout=10, env=cof._git_env())
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if p.returncode != 0:
        return False, ""
    return True, p.stdout


def _toplevel(repo: str) -> str | None:
    ok, out = _git_text(repo, "rev-parse", "--show-toplevel")
    return os.path.realpath(out.strip()) if ok and out.strip() else None


def _default_branch_oid(repo: str) -> tuple[str | None, str | None]:
    """(default-branch name, its commit OID) — mirrors the guards' resolution; None on ambiguity."""
    ok, out = _git_text(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    name: str | None = None
    candidates: list[str] = []
    if ok and out.strip().startswith("refs/remotes/origin/"):
        name = out.strip().removeprefix("refs/remotes/origin/")
        candidates = [name, f"origin/{name}"]
    else:
        has_main = _git_text(repo, "show-ref", "--verify", "--quiet", "refs/heads/main")[0]
        has_master = _git_text(repo, "show-ref", "--verify", "--quiet", "refs/heads/master")[0]
        if has_main and not has_master:
            name = "main"
        elif has_master and not has_main:
            name = "master"
        elif has_main and has_master:
            ok2, cfg = _git_text(repo, "config", "init.defaultBranch")
            if ok2 and cfg.strip() in ("main", "master"):
                name = cfg.strip()
        candidates = [name] if name else []
    for c in candidates:
        ok, oid = _git_text(repo, "rev-parse", "--verify", f"{c}^{{commit}}")
        if ok and oid.strip():
            return name, oid.strip()
    return None, None


def _base_pin_refusal(repo: str, base: str) -> str | None:
    """REFUSE unless `base` resolves to the repo's default branch tip — the one line the loop
    cannot move (guard-loop-vc denies merges into it and direct ref moves). A loop-chosen base
    (`HEAD`, its own branch, a raw commit) would anchor the gate to loop-authored state."""
    name, want = _default_branch_oid(repo)
    if want is None:
        return ("the repo's default branch cannot be determined, so --base cannot be verified as "
                "loop-immutable (fail-deny)")
    ok, got = _git_text(repo, "rev-parse", "--verify", f"{base}^{{commit}}")
    if not ok or got.strip() != want:
        return (f"--base {base!r} does not resolve to the default branch "
                f"{name!r} — the permit gate only anchors to the baseline the loop cannot author "
                f"(fail-deny)")
    return None


def _anchor_authored(blob: str, verified_by: str) -> bool:
    """True iff `verified_by` appears in the anchor blob as a WHOLE authored unit.

    A unit is a whole (stripped) line, or the complete `verify:`-suffix of a line — the two shapes
    a ledger/plan authors a command in. NOT a substring test (independent review, round 2): a
    substring match accepts any contiguous slice of an authored command, so a loop could drop a
    trailing `--strict`/`&& second-check` (or a leading `first-check &&`) and run a WEAKER witness
    than the author wrote while still earning the permit.
    """
    cmd = verified_by.strip()
    for line in blob.splitlines():
        line = line.strip()
        if line == cmd:
            return True
        _, marker, tail = line.partition("verify:")
        if marker and tail.strip() == cmd:
            return True
    return False


def _anchor_refusal(repo: str, toplevel: str, base: str, anchor: str, verified_by: str) -> str | None:
    """REFUSE unless the witness command is a whole authored unit in the BASE blob of the anchor.

    The blob is read from the base tree, never the worktree, so editing the ledger/plan on the loop
    branch (committed or not) changes nothing — the command must be baseline-authored, and it must
    match a whole authored line / `verify:` suffix (see _anchor_authored), not a substring of one."""
    abs_anchor = anchor if os.path.isabs(anchor) else os.path.join(repo, anchor)
    rel = os.path.normpath(os.path.relpath(os.path.abspath(abs_anchor), toplevel))
    if rel.startswith(".."):
        return f"--anchor {anchor!r} is outside the repository (fail-deny)"
    ok, blob = _git_text(repo, "cat-file", "blob", f"{base}:{rel}")
    if not ok:
        return f"--anchor {rel!r} is not a tracked blob at {base} (fail-deny)"
    if not _anchor_authored(blob, verified_by):
        return (f"the witness command is not baseline-authored: it does not appear in "
                f"{base}:{rel} as a whole authored line or `verify:` suffix — a caller-supplied "
                f"replacement or a TRUNCATION of an authored command earns no permit, no matter "
                f"which frozen files it names (fail-deny)")
    return None


def _under(toplevel: str, path: str) -> bool:
    try:
        return os.path.commonpath([toplevel, path]) == toplevel
    except ValueError:
        return False


def _bind_executable(repo: str, toplevel: str, argv0: str) -> tuple[str | None, str | None, list[str]]:
    """Resolve and trust-check the witness executable.

    Returns (refusal, resolved_absolute_path, extra_required_paths). An in-repo executable joins
    the frozen surface via extra_required (so an untracked `.venv/bin/python` refuses and a tracked
    script is content-bound to base); an out-of-repo executable must not be user-writable at the
    file, its directory, its resolved target, or the target's directory."""
    if os.sep in argv0:
        lex = argv0 if os.path.isabs(argv0) else os.path.normpath(os.path.join(repo, argv0))
        lex = os.path.abspath(lex)
    else:
        found = shutil.which(argv0, path=_TRUSTED_PATH)
        if found is None:
            return (f"witness executable {argv0!r} does not resolve on the trusted PATH "
                    f"({_TRUSTED_PATH}); trust cannot be bound (fail-deny)"), None, []
        lex = os.path.abspath(found)
    real = os.path.realpath(lex)
    if not os.path.isfile(real):
        return (f"witness executable {lex!r} does not resolve to a regular file (fail-deny)"), None, []
    # Trust each component (the lexical path AND the resolved target) by WHERE it lands. An in-repo
    # component is frozen to base via extra_required (tracked → content/type/hops bound; untracked,
    # e.g. .venv/bin/python, refuses in evaluate). An out-of-repo component is NOT covered by the
    # frozen surface, so it must be non-user-writable — otherwise it can be swapped between snapshot
    # and exec. This closes an in-repo SYMLINK whose resolved target is an external writable binary
    # (round-3 review, finding 3): the earlier code short-circuited on the in-repo link and never
    # writability-checked the external target, freezing only the link identity, not the target bytes.
    in_repo: list[str] = []
    for p in dict.fromkeys([lex, real]):
        if _under(toplevel, p):
            in_repo.append(p)
            continue
        for q in (p, os.path.dirname(p)):
            if os.access(q, os.W_OK):
                return (f"witness executable path {q!r} is writable by the invoking user — a "
                        f"replaceable executable cannot produce a trusted verdict (fail-deny)"), None, []
    # Freeze whichever components ARE in-repo (an in-repo link's own _collect_surface already binds
    # its hops+target; listing `real` too is harmless dedup). Fully out-of-repo → [] (writability
    # gate above is the whole guarantee).
    return None, lex, in_repo


# python options that consume a value (attached to the same token, or the next token) — so a `m`
# appearing in their value (`-Wm`, `-Xm`) is NOT the module switch. Mirrors install_settings.py.
_PY_M_VALUE_SHORTS = frozenset("WX")


def _module_arg(argv: list[str]) -> "str | None":
    """The module name a python `-m` witness runs, across EVERY spelling, or None if it is not a
    `-m` run. Sound against the real interpreter grammar (verified vs CPython):

      -m pytest         separate value            -mpytest      attached to the -m token
      -Bm pytest        -m last in a cluster      -Bmpytest     -m mid-cluster, rest is the module

    `-m`/`-c` terminate option processing and take the REST of their own token as the argument, or —
    if they are the token's last char — the NEXT token. `-W`/`-X` consume a value first, so a `m` in
    `-Wm` is that value, not the switch (the earlier `"-m" not in argv` test missed the attached and
    clustered forms entirely — a live permit-forge: a repo-root `pytest.py`/`pytest/` shadowing a
    `-mpytest` witness was never frozen). A non-option token is the script operand → no `-m`."""
    j = 1  # argv[0] is the interpreter
    while j < len(argv):
        t = argv[j]
        if t == "--" or t == "-" or not t.startswith("-"):
            return None  # end-of-options / script operand reached before any -m
        if t.startswith("--"):
            j += 1  # python's long options don't introduce a module; step over
            continue
        for idx, ch in enumerate(t[1:]):
            if ch == "c":
                return None  # -c code mode: no module (rest of token/next token is code)
            if ch == "m":
                rest = t[1 + idx + 1:]
                if rest:
                    return rest  # attached / mid-cluster: -mpytest, -Bmpytest
                return argv[j + 1] if j + 1 < len(argv) else None  # -m last char → next token
            if ch in _PY_M_VALUE_SHORTS:
                # value-consuming short: the rest of THIS token is its value (`-Wm` → value 'm'); if
                # it is the token's last char, the value is the next token (skip it). Either way no
                # -m lives past it in this token.
                if idx == len(t[1:]) - 1:
                    j += 1
                break
        j += 1
    return None


def _module_shadow(toplevel: str, argv: list[str]) -> tuple[str | None, list[str]]:
    """For a `-m <module>` witness (any spelling — see `_module_arg`), bind the repo-root path that
    would shadow the module.

    `python -m` puts the cwd (the repo) first on sys.path, so a repo-root `<module>.py` or
    `<module>/` package replaces the intended module wholesale. A shadowing package directory
    cannot be frozen as a blob → refuse; a shadowing file joins the required surface (tracked →
    frozen, untracked → evaluate refuses)."""
    mod = _module_arg(argv)
    if mod is None:
        return None, []
    top_mod = mod.split(".")[0]
    if not top_mod:
        return None, []
    pkg = os.path.join(toplevel, top_mod)
    if os.path.isdir(pkg):
        return (f"repo-root package {top_mod}/ would shadow the -m module on sys.path and cannot "
                f"be frozen as a blob (fail-deny)"), []
    mod_py = pkg + ".py"
    if os.path.isfile(mod_py) or os.path.islink(mod_py):
        return None, [mod_py]
    return None, []


def _config_surface(repo: str, base: str, toplevel: str, verified_by: str) -> list[str]:
    """Known verdict-affecting companions of the named oracle files: every conftest.py from the
    repo root down to each oracle file's directory, plus root runner configuration. Absent paths
    are harmless (evaluate skips never-existed ones); present-untracked or deleted-since-base ones
    make evaluate refuse."""
    out: list[str] = [os.path.join(toplevel, n) for n in _ROOT_RUNNER_CONFIGS]
    files, _ = cof._oracle_files(repo, base, verified_by)
    for rel in files:
        cur = toplevel
        for part in os.path.dirname(rel).split(os.sep):
            if part in ("", "."):
                continue
            cur = os.path.join(cur, part)
            out.append(os.path.join(cur, "conftest.py"))
    return list(dict.fromkeys(out))


def _witness_env() -> dict[str, str]:
    """The sanitized environment the witness runs under: a fixed system PATH and no inherited
    interpreter injection vectors (PYTHONPATH, PYTHONSTARTUP, user site-packages, GIT_* redirects
    — all absent because nothing is inherited)."""
    env = {"PATH": _TRUSTED_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    home = os.environ.get("HOME")
    if home:
        env["HOME"] = home
    return env


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


def run(repo: str, base: str, anchor: str, verified_by: str, timeout: float) -> int:
    toplevel = _toplevel(repo)
    if toplevel is None:
        print(f"REFUSED: {repo} is not a git repo (fail-deny)", file=sys.stderr)
        return EXIT_REFUSED

    # 0. BASE PIN — the baseline must be the default branch, the one line the loop cannot author.
    reason = _base_pin_refusal(repo, base)
    if reason is not None:
        print(f"REFUSED (base): {reason}", file=sys.stderr)
        return EXIT_REFUSED

    # 1. ANCHOR BINDING — the command itself must be baseline-authored, not caller-supplied.
    reason = _anchor_refusal(repo, toplevel, base, anchor, verified_by)
    if reason is not None:
        print(f"REFUSED (anchor): {reason}", file=sys.stderr)
        return EXIT_REFUSED

    try:
        argv = shlex.split(verified_by)
    except ValueError as e:
        print(f"usage: unparseable verified-by: {e}", file=sys.stderr)
        return EXIT_USAGE
    if not argv:
        print("usage: empty verified-by", file=sys.stderr)
        return EXIT_USAGE

    # 2. EXECUTABLE BINDING — resolve argv[0] against trusted state, never the caller's PATH.
    reason, resolved_exe, extra = _bind_executable(repo, toplevel, argv[0])
    if reason is not None:
        print(f"REFUSED (executable): {reason}", file=sys.stderr)
        return EXIT_REFUSED

    # 3. VERDICT-SURFACE BINDING — module shadowing + runner config/conftest companions.
    reason, shadow_extra = _module_shadow(toplevel, argv)
    if reason is not None:
        print(f"REFUSED (module shadow): {reason}", file=sys.stderr)
        return EXIT_REFUSED
    extra = extra + shadow_extra + _config_surface(repo, base, toplevel, verified_by)

    # 4. PRECHECK
    reason, surface = cof.evaluate(repo, base, verified_by, extra_required=extra)
    if reason is not None:
        print(f"REFUSED (precheck): {reason}", file=sys.stderr)
        return EXIT_REFUSED

    # 5. SNAPSHOT
    reason, before = _snapshot(surface)
    if reason is not None:
        print(f"REFUSED (snapshot): {reason}", file=sys.stderr)
        return EXIT_REFUSED

    # 6. EXECUTE — no shell, resolved executable, sanitized environment. Metacharacters stay
    # literal; the caller's PATH/PYTHONPATH cannot redirect what the trusted executable loads.
    try:
        witness = subprocess.run([resolved_exe, *argv[1:]], cwd=repo, shell=False, timeout=timeout,
                                 capture_output=True, text=True, errors="replace",
                                 env=_witness_env())
        witness_code: int | None = witness.returncode
        witness_tail = (witness.stdout + witness.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        witness_code, witness_tail = None, f"witness timed out after {timeout}s"
    except OSError as e:
        witness_code, witness_tail = None, f"witness could not execute: {e}"

    # 7. RECHECK — the surface must still be frozen AND byte/topology-identical to the snapshot.
    reason, surface_after = cof.evaluate(repo, base, verified_by, extra_required=extra)
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
        print("GREEN: witness exited 0 under a frozen, baseline-bound oracle surface — "
              + ", ".join(sorted(surface)))
        return EXIT_GREEN
    detail = f"exit {witness_code}" if witness_code is not None else "no verdict"
    print(f"RED: witness failed ({detail}) under a frozen oracle surface.\n{witness_tail}",
          file=sys.stderr)
    return EXIT_RED


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Atomically run a baseline-anchored verified-by witness under a frozen-oracle "
                    "guarantee.")
    ap.add_argument("--repo", required=True, help="path to the repo (the loop's working copy)")
    ap.add_argument("--base", required=True,
                    help="the loop branch's base; must resolve to the repo's default branch")
    ap.add_argument("--anchor", required=True,
                    help="tracked file whose BASE-tree blob authored the verified-by command "
                         "(the telos ledger / plan file)")
    ap.add_argument("--verified-by", required=True, help="the claim's verified-by command string")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="witness timeout in seconds (default 600; a hung witness is RED)")
    args = ap.parse_args()
    return run(args.repo, args.base, args.anchor, args.verified_by, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
