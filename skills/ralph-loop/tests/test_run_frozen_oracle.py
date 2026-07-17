#!/usr/bin/env python3
"""Tests for run_frozen_oracle.py — the R-04 atomic permit-to-act gate.

Builds throwaway local git repos (no remote): a `main` base carrying witness scripts AND a tracked
anchor file (PLAN.md) that baseline-authors every witness command, then a loop branch. Pins the
envelope contract: binding refusals (base pin, anchor, executable, verdict surface), precheck
refusal (10), GREEN (0) / RED (1) verdicts only under a frozen surface, the recheck refusal when
the witness mutates its own oracle mid-run, shell-less execution, sanitized environment, and the
timeout → RED path.

The 2026-07-16 independent-review regressions live in TestPermitBinding: a caller-supplied
`/bin/true <tracked-file>` earns no permit (the command must be baseline-authored), and an
untracked in-repo interpreter (`.venv/bin/python`) refuses even when baseline-authored (the
executable is part of the trusted surface).

Stdlib unittest only. Run:
  python3 skills/ralph-loop/tests/test_run_frozen_oracle.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_frozen_oracle.py"

GREEN = 0
RED = 1
REFUSED = 10
USAGE = 2

ANCHOR = "PLAN.md"


def _run(repo: str, base: str, verified_by: str, timeout: str | None = None,
         anchor: str | None = ANCHOR, env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), "--repo", repo, "--base", base, "--verified-by", verified_by]
    if anchor is not None:
        cmd += ["--anchor", anchor]
    if timeout is not None:
        cmd += ["--timeout", timeout]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


class _RepoCase(unittest.TestCase):
    """A base repo whose PLAN.md baseline-authors every command the tests run."""

    def setUp(self) -> None:
        self.d = tempfile.mkdtemp(prefix="frozenrun-")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        # an OUTSIDE-repo, user-writable directory for the writable-executable refusal case
        self.ext = tempfile.mkdtemp(prefix="frozenrun-ext-")
        self.addCleanup(shutil.rmtree, self.ext, ignore_errors=True)
        self.ext_exe = os.path.join(self.ext, "fake-witness")
        Path(self.ext_exe).write_text("#!/bin/sh\nexit 0\n")
        os.chmod(self.ext_exe, 0o755)

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", self.d, *args], check=True, capture_output=True, text=True)

        self.g = g
        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        tests = Path(self.d) / "tests"
        tests.mkdir()
        (tests / "witness_ok.py").write_text("import sys\nsys.exit(0)\n")
        (tests / "witness_fail.py").write_text("import sys\nsys.exit(3)\n")
        (tests / "witness_slow.py").write_text("import time\ntime.sleep(30)\n")
        # a witness that MUTATES its own oracle file mid-run, then exits 0 — the check/run race
        (tests / "witness_selfmut.py").write_text(
            "import pathlib\n"
            "p = pathlib.Path(__file__)\n"
            "p.write_text(p.read_text() + '\\n# mutated during run\\n')\n"
        )
        # a witness that proves the sanitized environment: fixed PATH, no inherited PYTHONPATH
        (tests / "witness_env.py").write_text(
            "import os, sys\n"
            "ok = (os.environ.get('PATH') == '/usr/bin:/bin'\n"
            "      and 'PYTHONPATH' not in os.environ\n"
            "      and os.environ.get('PYTHONNOUSERSITE') == '1')\n"
            "sys.exit(0 if ok else 5)\n"
        )
        # a tracked in-repo executable witness (the positive control for executable binding)
        runner = Path(self.d) / "tests" / "runner.sh"
        runner.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(runner, 0o755)
        # a tracked IN-REPO symlink whose target is the EXTERNAL, user-writable executable — the
        # round-3 finding-3 shape: the frozen surface covers the link identity, not the target bytes.
        os.symlink(self.ext_exe, Path(self.d) / "tests" / "link-exe")
        (Path(self.d) / "feature.py").write_text("x = 1\n")
        # The anchor: every command a test runs must be BASELINE-AUTHORED here (base-tree blob).
        (Path(self.d) / ANCHOR).write_text(
            "verify: python3 tests/witness_ok.py\n"
            "verify: python3 tests/witness_fail.py\n"
            "verify: python3 tests/witness_slow.py\n"
            "verify: python3 tests/witness_selfmut.py\n"
            "verify: python3 tests/witness_env.py\n"
            "verify: python3 tests/witness_link.py\n"
            "verify: python3 tests/witness_ok.py $(touch pwned)\n"
            "verify: python3 tests/witness_ok.py ; python3 tests/witness_fail.py\n"
            "verify: no-such-interpreter tests/orphan.py\n"
            "verify: echo done\n"
            "verify: /bin/true tests/witness_ok.py\n"
            "verify: .venv/bin/python tests/witness_ok.py\n"
            "verify: tests/runner.sh\n"
            "verify: python3 -m pytest tests/witness_ok.py\n"
            "verify: python3 -mpytest tests/witness_ok.py\n"     # attached -m spelling
            "verify: python3 -Bmpytest tests/witness_ok.py\n"    # -m mid-cluster, module attached
            "verify: python3 -Bm pytest tests/witness_ok.py\n"   # -m last in cluster, module next tok
            "verify: python3 --check-hash-based-pycs always -m pytest tests/witness_ok.py\n"  # sep-value long opt
            f"verify: {self.ext_exe} tests/witness_ok.py\n"
            "verify: tests/link-exe tests/witness_ok.py\n"       # in-repo link → external writable exe
        )
        g("add", "-A")
        g("commit", "-m", "base")
        # A PUSH-PROTECTED default anchor: mirror the base commit into refs/remotes/origin/main and
        # point origin/HEAD at it (no real remote needed). The gate pins --base to this remote ref
        # (round-5 fix), which a loop cannot move without a push; a local-only default with no such
        # anchor fail-denies (see TestBasePinRequiresPushProtectedAnchor).
        sha = subprocess.run(["git", "-C", self.d, "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        g("update-ref", "refs/remotes/origin/main", sha)
        g("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        g("checkout", "-b", "loop/telos")


class TestRunFrozenOracle(_RepoCase):
    def test_green_when_witness_passes_and_surface_frozen(self):
        p = _run(self.d, "main", "python3 tests/witness_ok.py")
        self.assertEqual(p.returncode, GREEN, p.stderr)
        self.assertIn("GREEN", p.stdout)

    def test_red_when_witness_fails(self):
        p = _run(self.d, "main", "python3 tests/witness_fail.py")
        self.assertEqual(p.returncode, RED)
        self.assertIn("RED", p.stderr)

    def test_refused_on_precheck_when_oracle_edited(self):
        # the loop committed an edit to its own witness → precheck refuses before anything runs
        (Path(self.d) / "tests" / "witness_ok.py").write_text("import sys\nsys.exit(0)  # weakened\n")
        self.g("add", "-A")
        self.g("commit", "-m", "edit witness")
        p = _run(self.d, "main", "python3 tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED)
        self.assertIn("precheck", p.stderr)

    def test_refused_on_precheck_uncommitted_content_weakening(self):
        # R-04 finding #1 at the permit-to-act gate: the loop weakens a regular witness IN THE
        # WORKTREE without committing (here a would-fail witness rewritten to exit 0). Pre-fix the
        # precheck reported FROZEN (three-dot diff blind to worktree edits) and the runner then ran
        # the now-passing witness and returned GREEN — a false permit. Precheck must REFUSE.
        (Path(self.d) / "tests" / "witness_fail.py").write_text("import sys\nsys.exit(0)  # weakened, UNCOMMITTED\n")
        p = _run(self.d, "main", "python3 tests/witness_fail.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("precheck", p.stderr)

    def test_refused_on_recheck_when_witness_mutates_its_oracle(self):
        # THE RACE: precheck passes (surface pristine), the witness itself rewrites the oracle during
        # execution and exits 0 — the runner must NOT return that green. The recheck refuses: since
        # R-04 #1, the post-execution evaluate() also compares each oracle's content to base, so a
        # non-restored mutation is caught there; the snapshot before/after diff remains as an
        # independent, git-free backstop (defense in depth). Either way the mutation cannot pass.
        p = _run(self.d, "main", "python3 tests/witness_selfmut.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("recheck", p.stderr)

    def test_refused_on_uncommitted_retarget(self):
        # symlinked oracle repointed in the worktree (uncommitted) → precheck's state comparison refuses
        tests = Path(self.d) / "tests"
        os.symlink("witness_ok.py", tests / "witness_link.py")
        self.g("add", "-A")
        self.g("commit", "-m", "add link")
        self.g("checkout", "main")
        self.g("merge", "--ff-only", "loop/telos")
        self.g("checkout", "loop/telos")
        os.remove(tests / "witness_link.py")
        os.symlink("witness_fail.py", tests / "witness_link.py")  # uncommitted retarget
        p = _run(self.d, "main", "python3 tests/witness_link.py")
        self.assertEqual(p.returncode, REFUSED)

    def test_no_shell_metacharacters_stay_literal(self):
        # `$(touch pwned)` must reach the witness as literal argv, not execute: no shell, no side file
        p = _run(self.d, "main", "python3 tests/witness_ok.py $(touch pwned)")
        self.assertEqual(p.returncode, GREEN, p.stderr)
        self.assertFalse((Path(self.d) / "pwned").exists(), "command substitution must not execute")

    def test_shell_chain_does_not_chain(self):
        # `a; b` under a shell would run b and report ITS exit code; without a shell the `;` glues
        # into a literal filename argument. Witness scripts ignore argv → still the FIRST script's
        # verdict, and the chained command never runs.
        p = _run(self.d, "main", "python3 tests/witness_ok.py ; python3 tests/witness_fail.py")
        self.assertEqual(p.returncode, GREEN,
                         f"`;` must not chain a second command (stderr={p.stderr})")

    def test_timeout_is_red_not_green(self):
        p = _run(self.d, "main", "python3 tests/witness_slow.py", timeout="1")
        self.assertEqual(p.returncode, RED)
        self.assertIn("timed out", p.stderr)

    def test_unresolvable_witness_executable_is_refused(self):
        # 2026-07-16 hardening: an executable that does not resolve on the trusted PATH cannot have
        # its trust bound — REFUSED (was RED when the runner trusted any argv[0] the caller named).
        # A resolution failure is a binding failure, not a witness verdict.
        (Path(self.d) / "tests" / "orphan.py").write_text("import sys\nsys.exit(0)\n")
        self.g("add", "-A")
        self.g("commit", "-m", "add orphan oracle")
        self.g("checkout", "main")
        self.g("merge", "--ff-only", "loop/telos")
        # advance the PUSH-PROTECTED anchor too, so --base (origin/main) tracks the file and the base
        # pin passes — leaving the EXECUTABLE binding as the refusal under test, not the base pin.
        sha = subprocess.run(["git", "-C", self.d, "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        self.g("update-ref", "refs/remotes/origin/main", sha)
        self.g("checkout", "loop/telos")
        p = _run(self.d, "main", "no-such-interpreter tests/orphan.py")
        self.assertEqual(p.returncode, REFUSED)
        self.assertIn("executable", p.stderr)

    def test_refused_when_no_oracle_file(self):
        p = _run(self.d, "main", "echo done")
        self.assertEqual(p.returncode, REFUSED)

    def test_witness_runs_under_sanitized_environment(self):
        # The caller's environment is an injection vector (PYTHONPATH swaps what a trusted
        # interpreter loads). The witness must see the fixed PATH and none of the inherited vars.
        env = dict(os.environ)
        env["PYTHONPATH"] = "/evil"
        p = _run(self.d, "main", "python3 tests/witness_env.py", env=env)
        self.assertEqual(p.returncode, GREEN, f"stdout={p.stdout} stderr={p.stderr}")


class TestPermitBinding(_RepoCase):
    """The 2026-07-16 independent-review regressions: the permit must be bound to
    baseline-authored, trusted state — not to whatever command/executable the caller supplies."""

    def test_review_repro_no_anchor_is_never_green(self):
        # The literal review reproduction shape: no --anchor. The gate must not produce a permit —
        # an unanchored invocation is a usage error, never GREEN.
        p = _run(self.d, "main", "/bin/true tests/witness_ok.py", anchor=None)
        self.assertEqual(p.returncode, USAGE, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertNotIn("GREEN", p.stdout)

    def test_truncated_authored_command_refused(self):
        # Independent review (round 2): the anchor binding must match a WHOLE authored unit — a
        # whole line or a complete `verify:` suffix — never a substring. A substring match accepts
        # any contiguous slice of an authored command, so a loop could drop the tail (or head) of
        # what the author wrote and run a WEAKER witness while still earning the permit. Each of
        # these is a proper substring of an authored anchor line but not itself a whole unit.
        for cmd in (
            "python3 tests/witness_ok.py ; python3",   # tail dropped from the authored compound line
            "pytest tests/witness_ok.py",              # head dropped from the `-m pytest` line
            "python3 -m pytest tests/witness_ok",      # tail characters dropped mid-token
        ):
            p = _run(self.d, "main", cmd)
            self.assertEqual(p.returncode, REFUSED, f"{cmd!r}: stdout={p.stdout} stderr={p.stderr}")
            self.assertIn("baseline-authored", p.stderr, f"{cmd!r} must refuse at the anchor binding")

    def test_caller_supplied_replacement_command_refused(self):
        # `/bin/true <tracked-file>` names a frozen file but was never baseline-authored: naming an
        # unrelated frozen file must earn nothing. (witness_fail.py IS tracked and frozen here.)
        p = _run(self.d, "main", "/bin/true tests/witness_fail.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("baseline-authored", p.stderr)

    def test_edited_anchor_cannot_author_a_command(self):
        # The loop appends its own command to the anchor ON ITS BRANCH (committed) — the anchor is
        # read from the BASE blob, so the loop-authored line changes nothing.
        plan = Path(self.d) / ANCHOR
        plan.write_text(plan.read_text() + "verify: /bin/true tests/witness_fail.py\n")
        self.g("add", "-A")
        self.g("commit", "-m", "loop tries to author its own witness command")
        p = _run(self.d, "main", "/bin/true tests/witness_fail.py")
        self.assertEqual(p.returncode, REFUSED)
        self.assertIn("baseline-authored", p.stderr)

    def test_untracked_in_repo_interpreter_refused_even_when_baseline_authored(self):
        # THE .venv TRUST PROBLEM: the command `.venv/bin/python tests/witness_ok.py` IS
        # baseline-authored in PLAN.md, but the interpreter is an untracked, agent-writable file
        # inside the repo — replacing it forges any verdict. The executable is part of the trusted
        # surface: untracked in-repo executable → REFUSED.
        venv_bin = Path(self.d) / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        fake = venv_bin / "python"
        fake.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(fake, 0o755)
        p = _run(self.d, "main", ".venv/bin/python tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn(".venv", p.stderr)

    def test_writable_outside_repo_executable_refused(self):
        # A baseline-authored command whose executable lives in a user-writable directory outside
        # the repo is equally replaceable → REFUSED.
        p = _run(self.d, "main", f"{self.ext_exe} tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("writable", p.stderr)

    def test_in_repo_symlink_to_external_writable_exe_refused(self):
        # Round-3 review finding 3: a TRACKED in-repo symlink resolving to a user-writable EXTERNAL
        # binary must refuse. The frozen surface binds the link's identity (its target string), but
        # the target's bytes live outside the repo and can be swapped between snapshot and exec — so
        # the external target must pass the same writability gate as a plain out-of-repo executable.
        # (The link + its command are baseline-authored in the fixture, so the executable binding is
        # what's under test, not authorship or the frozen surface.)
        p = _run(self.d, "main", "tests/link-exe tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("writable", p.stderr)

    def test_tracked_in_repo_executable_is_green_then_refused_on_edit(self):
        # Positive control: a TRACKED in-repo executable witness is fine — and it is now part of
        # the frozen surface, so an uncommitted edit to it refuses.
        p = _run(self.d, "main", "tests/runner.sh")
        self.assertEqual(p.returncode, GREEN, f"stdout={p.stdout} stderr={p.stderr}")
        runner = Path(self.d) / "tests" / "runner.sh"
        runner.write_text("#!/bin/sh\nexit 0  # weakened\n")
        p = _run(self.d, "main", "tests/runner.sh")
        self.assertEqual(p.returncode, REFUSED)

    def test_base_must_resolve_to_the_default_branch(self):
        # `--base HEAD` on the loop's own branch anchors the gate to loop-authored state → REFUSED.
        (Path(self.d) / "loopwork.py").write_text("y = 2\n")
        self.g("add", "-A")
        self.g("commit", "-m", "loop work")
        p = _run(self.d, "HEAD", "python3 tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("remote-tracking default", p.stderr)

    def test_untracked_conftest_refuses(self):
        # conftest.py is auto-collected by pytest and changes verdicts without appearing in the
        # command. Present-but-untracked → cannot be bound to the baseline → REFUSED.
        (Path(self.d) / "tests" / "conftest.py").write_text("import sys\nsys.exit(0)\n")
        p = _run(self.d, "main", "python3 tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("conftest.py", p.stderr)

    def test_module_shadow_file_refuses(self):
        # `python -m pytest` puts the repo root first on sys.path: an untracked repo-root pytest.py
        # replaces the runner wholesale → REFUSED before anything executes.
        (Path(self.d) / "pytest.py").write_text("import sys\nsys.exit(0)\n")
        p = _run(self.d, "main", "python3 -m pytest tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("pytest.py", p.stderr)

    def test_module_shadow_package_refuses(self):
        (Path(self.d) / "pytest").mkdir()
        (Path(self.d) / "pytest" / "__init__.py").write_text("")
        p = _run(self.d, "main", "python3 -m pytest tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("shadow", p.stderr)

    def test_attached_and_clustered_m_shadow_refuses(self):
        # Round-3 review finding 1: the shadow binding must catch EVERY `-m` spelling, not just the
        # spaced `python3 -m pytest`. CPython accepts `-mpytest`, `-Bmpytest`, and `-Bm pytest`, each
        # of which puts the repo root first on sys.path — so a repo-root pytest.py forges GREEN if the
        # shadow is not frozen. The pre-fix `"-m" not in argv` test missed all three. (These spellings
        # are baseline-authored in the anchor above so the binding is what's exercised, not authorship.)
        (Path(self.d) / "pytest.py").write_text("import sys\nsys.exit(0)\n")
        for cmd in (
            "python3 -mpytest tests/witness_ok.py",
            "python3 -Bmpytest tests/witness_ok.py",
            "python3 -Bm pytest tests/witness_ok.py",
        ):
            p = _run(self.d, "main", cmd)
            self.assertEqual(p.returncode, REFUSED, f"{cmd!r}: stdout={p.stdout} stderr={p.stderr}")
            self.assertIn("pytest.py", p.stderr, f"{cmd!r}: attached/clustered -m shadow must refuse")

    def test_separate_value_long_opt_before_m_shadow_refuses(self):
        # Round-4 review finding 2: a separate-value long option (`--check-hash-based-pycs always`)
        # before `-m` must not end the module scan early — its value token is consumed, not read as
        # the script operand, so the `-m pytest` shadow is still bound and a repo-root pytest.py
        # refuses. (Baseline-authored above.)
        (Path(self.d) / "pytest.py").write_text("import sys\nsys.exit(0)\n")
        p = _run(self.d, "main", "python3 --check-hash-based-pycs always -m pytest tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("pytest.py", p.stderr)

    def test_baseline_authored_bin_true_is_green_accepted_residual(self):
        # ACCEPTED residual, pinned bidirectionally: a command the BASELINE AUTHOR wrote is trusted
        # author intent — the gate binds authorship and bytes, not semantics. `/bin/true
        # tests/witness_ok.py` in the base-tree anchor is a vacuous oracle the DoD author owns
        # (same class as `verified-by: true` in the telos ledger — see KNOWN-BYPASSES.md). If this
        # test starts refusing, the boundary strengthened and the docs must be rewritten.
        p = _run(self.d, "main", "/bin/true tests/witness_ok.py")
        self.assertEqual(p.returncode, GREEN, f"stdout={p.stdout} stderr={p.stderr}")


class TestBasePinRequiresPushProtectedAnchor(unittest.TestCase):
    """Round-5 review: the base pin must anchor to a PUSH-PROTECTED ref (refs/remotes/origin/<name>),
    never a loop-movable local ref. A local-only default has no such anchor and fail-denies; and even
    with an anchor, a loop that moves LOCAL main (via a verb outside the porcelain fence — the exact
    `checkout <default> && reset --soft` forge) no longer forges GREEN, because --base is compared to
    the REMOTE ref, which the moved local ref no longer matches."""

    def setUp(self) -> None:
        self.d = tempfile.mkdtemp(prefix="frozenrun-basepin-")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

        def g(*args: str) -> str:
            return subprocess.run(["git", "-C", self.d, *args],
                                  check=True, capture_output=True, text=True).stdout.strip()

        self.g = g
        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        Path(self.d, "PLAN.md").write_text("verify: /bin/true PLAN.md\n")
        g("add", "-A")
        g("commit", "-m", "base")
        self.base_sha = g("rev-parse", "HEAD")
        g("checkout", "-b", "loop/x")

    def _add_origin(self) -> None:
        self.g("update-ref", "refs/remotes/origin/main", self.base_sha)
        self.g("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    def test_local_only_default_fail_denies(self):
        # No origin/HEAD: the default is backed only by a loop-movable local ref → REFUSED, never a
        # permit over an unprovable baseline.
        p = _run(self.d, "main", "/bin/true PLAN.md")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("remote-tracking anchor", p.stderr)

    def test_push_protected_default_is_green(self):
        # With origin/HEAD mirroring the base, --base main resolves to the remote-tracking anchor → the
        # baseline-authored vacuous oracle passes (authorship residual), proving the anchor path works.
        self._add_origin()
        p = _run(self.d, "main", "/bin/true PLAN.md")
        self.assertEqual(p.returncode, GREEN, f"stdout={p.stdout} stderr={p.stderr}")

    def test_loop_moved_local_main_no_longer_forges(self):
        # THE round-5 forge: the loop authors a weaker PLAN.md on its branch, then moves LOCAL main
        # onto it via `checkout main && reset --soft loop/x` (verbs OUTSIDE the porcelain fence). The
        # base pin compares --base main to the REMOTE ref (still at the honest base), so the moved
        # local ref mismatches → REFUSED, not the forged GREEN the local-first resolution once gave.
        self._add_origin()
        Path(self.d, "PLAN.md").write_text("verify: /bin/true loot.py\n")  # weaker, loop-authored
        Path(self.d, "loot.py").write_text("x = 1\n")
        self.g("add", "-A")
        self.g("commit", "-m", "loop authors a weaker oracle")
        loop_sha = self.g("rev-parse", "HEAD")
        self.g("checkout", "main")
        self.g("reset", "--soft", loop_sha)  # local main now points at loop-authored state
        self.g("checkout", "loop/x")
        p = _run(self.d, "main", "/bin/true loot.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("remote-tracking default", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
