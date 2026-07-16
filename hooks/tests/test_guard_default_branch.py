#!/usr/bin/env python3
"""Tests for the guard-default-branch.py PreToolUse hook.

Drives the hook as a subprocess with a crafted PreToolUse stdin payload against a real temp git repo,
asserting the deny/defer contract: deny = exit 0 + JSON permissionDecision=deny on stdout; defer = exit 0
with no decision. Pins the security-load-bearing properties: main/master stay protected even when
origin/HEAD points elsewhere (the union, not replace), git-failure fails OPEN (never a non-zero crash),
the marker must be a real file, and a relative file_path resolves against the payload cwd.

Stdlib unittest only; every test uses a temp repo. Run:
  python3 hooks/tests/test_guard_default_branch.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "guard-default-branch.py"
INSTALL_SH = Path(__file__).resolve().parents[2] / "scripts" / "install.sh"


def _git(args: list[str], cwd: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _repo(td: str, branch: str = "main", origin_head: "str | None" = None) -> str:
    """Init a repo with one commit on `branch`; optionally point refs/remotes/origin/HEAD somewhere."""
    _git(["init", "-q", "-b", branch], td)
    _git(["config", "user.email", "t@t"], td)
    _git(["config", "user.name", "t"], td)
    Path(td, "seed.txt").write_text("x")
    _git(["add", "-A"], td)
    _git(["commit", "-qm", "seed"], td)
    if origin_head:
        _git(["symbolic-ref", f"refs/remotes/origin/HEAD", f"refs/remotes/origin/{origin_head}"], td)
    return td


def _run(payload: dict, env: "dict | None" = None) -> "tuple[int, str]":
    env = dict(os.environ) if env is None else dict(env)
    # Keep test denies out of the real telemetry log (every deny appends — see hooks/_denial_log.py).
    env.setdefault("EXCUBITOR_DENIAL_LOG", os.devnull)
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout


def _denied(stdout: str) -> bool:
    try:
        return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    except (ValueError, KeyError):
        return False


class TestGuardDefaultBranch(unittest.TestCase):
    def test_main_still_protected_when_origin_head_is_custom(self):
        # The regression: origin/HEAD -> develop must NOT un-protect main (union, not replace).
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="main", origin_head="develop")
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertEqual(rc, 0)
            self.assertTrue(_denied(out), "main must stay protected even when origin/HEAD points at develop")

    def test_custom_default_also_protected(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="develop", origin_head="develop")
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertTrue(_denied(out), "the resolved custom default (develop) is protected too")

    def test_slash_containing_default_protected(self):
        # A slash-containing default branch (release/2.0, team/main) must stay protected — rsplit("/")
        # used to yield "2.0" and silently un-fence the real default. removeprefix keeps the full name.
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="release/2.0", origin_head="release/2.0")
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertEqual(rc, 0)
            self.assertTrue(_denied(out), "editing on the slash-named default branch must be denied")

    def test_feature_branch_defers(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="main")
            _git(["switch", "-qc", "feature/x"], td)
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertEqual((rc, out.strip()), (0, ""))  # not on default → defer (no decision)

    def test_marker_must_be_a_regular_file(self):
        # A DIRECTORY named like the marker must NOT disable the guard (old os.path.exists said yes).
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="main")
            (Path(td, ".claude", "allow-default-branch")).mkdir(parents=True)  # a dir, not a file
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertTrue(_denied(out), "a directory marker must not bless the default branch")

    def test_relative_target_resolves_against_payload_cwd(self):
        # A relative file_path must resolve against the payload cwd (not the process cwd / a fallback),
        # so repo detection lands on the intended sibling — here a feature-branch repo → defer.
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td, "a"), Path(td, "b")
            a.mkdir(); b.mkdir()
            _repo(str(a), branch="main")
            _repo(str(b), branch="main")
            _git(["switch", "-qc", "feature/y"], str(b))
            rc, out = _run({"tool_input": {"file_path": "../b/f.py"}, "cwd": str(a)})
            self.assertEqual((rc, out.strip()), (0, ""))  # resolves to repo b (feature) → defer, not repo a (main)

    def test_git_missing_fails_open_not_crash(self):
        # git unreachable at hook runtime (empty PATH) must fail OPEN (exit 0, no decision), never crash
        # non-zero. Old code let FileNotFoundError escape; now _git swallows it → caller defers.
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="main")
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ALLOW_DEFAULT_BRANCH"}
            env["PATH"] = "/nonexistent"  # git not findable from inside the hook
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td}, env=env)
            self.assertEqual(rc, 0)              # never non-zero
            self.assertFalse(_denied(out))      # fails open (defer), does not crash

    def test_non_object_json_fails_open(self):
        # valid JSON that is not an object must fail open, not crash on payload.get(...).
        for payload in (5, [], None, "x"):
            rc, out = _run(payload)  # _run json.dumps() the value; a bare scalar/array is valid JSON
            self.assertEqual((rc, out.strip()), (0, ""), f"non-object payload must defer: {payload!r}")


class TestGuardSymlinkLaundering(unittest.TestCase):
    """R-03: a symlink must not launder an Edit/Write into a protected repo. The guard evaluates BOTH
    the logical target's container and the realpath-resolved container; a protected hit in EITHER denies."""

    def _two_repos(self, td: str) -> "tuple[Path, Path]":
        """A feature-branch repo and a separate protected (main) repo under `td`."""
        feat = Path(td, "feature")
        prot = Path(td, "protected")
        feat.mkdir()
        prot.mkdir()
        _repo(str(feat), branch="main")
        _git(["switch", "-qc", "feature/x"], str(feat))
        _repo(str(prot), branch="main")
        return feat, prot

    def test_file_symlink_into_protected_repo_denied(self):
        # /feature/link.txt -> /protected/victim.txt; /feature is on a feature branch, /protected on main.
        # Pre-fix the logical container (/feature) was the only thing inspected → ALLOWED. The realpath
        # lands in /protected (default branch) → must DENY.
        with tempfile.TemporaryDirectory() as td:
            feat, prot = self._two_repos(td)
            victim = Path(prot, "victim.txt")
            victim.write_text("x")
            link = Path(feat, "link.txt")
            os.symlink(victim, link)
            rc, out = _run({"tool_input": {"file_path": str(link)}, "cwd": str(feat)})
            self.assertEqual(rc, 0)
            self.assertTrue(_denied(out), "a symlink resolving into a protected repo must be denied")

    def test_symlinked_dir_new_file_into_protected_denied(self):
        # A Write creating a NEW file through a symlinked directory: /feature/dir -> /protected/sub.
        # realpath resolves the existing symlink component even though the leaf file does not exist yet.
        with tempfile.TemporaryDirectory() as td:
            feat, prot = self._two_repos(td)
            sub = Path(prot, "sub")
            sub.mkdir()
            linkdir = Path(feat, "dir")
            os.symlink(sub, linkdir)
            newfile = Path(linkdir, "new.txt")  # not created yet
            rc, out = _run({"tool_input": {"file_path": str(newfile)}, "cwd": str(feat)})
            self.assertEqual(rc, 0)
            self.assertTrue(_denied(out), "a new file through a symlinked dir into a protected repo must deny")

    def test_ordinary_feature_file_still_defers(self):
        # No symlink: an ordinary edit on a feature branch must still DEFER (the common path is unchanged).
        with tempfile.TemporaryDirectory() as td:
            feat, _ = self._two_repos(td)
            rc, out = _run({"tool_input": {"file_path": str(Path(feat, "real.py"))}, "cwd": str(feat)})
            self.assertEqual((rc, out.strip()), (0, ""), "an ordinary feature-branch edit must defer")

    def test_dangling_symlink_fails_open(self):
        # A symlink whose target does not exist must not crash and must not false-deny (feature branch).
        with tempfile.TemporaryDirectory() as td:
            feat, _ = self._two_repos(td)
            link = Path(feat, "dangling")
            os.symlink(Path(td, "nonexistent", "x"), link)
            rc, out = _run({"tool_input": {"file_path": str(link)}, "cwd": str(feat)})
            self.assertEqual(rc, 0, "a dangling symlink must not crash the guard")
            self.assertFalse(_denied(out))

    def test_nul_in_target_fails_open(self):
        # An embedded NUL makes os.stat/realpath raise ValueError; the guard must fail OPEN, never crash —
        # even though the (malformed) path points under the protected repo.
        with tempfile.TemporaryDirectory() as td:
            feat, prot = self._two_repos(td)
            rc, out = _run({"tool_input": {"file_path": str(prot) + "/\x00bad"}, "cwd": str(feat)})
            self.assertEqual(rc, 0, "malformed NUL target must fail open, not crash")
            self.assertFalse(_denied(out))


class TestR06RegistrationBoundary(unittest.TestCase):
    """R-06: the guard's enforceable claim is its REGISTRATION — it fences the runtime's direct
    file-edit tools (`Edit|Write|NotebookEdit`) and nothing else. A Bash mutation never reaches it.
    These pin BOTH sides of that boundary end-to-end, so the honest-narrow claim in README /
    THREAT-MODEL / KNOWN-BYPASSES stays true: if the residual test ever fails (a shell mutation got
    blocked), the boundary strengthened and those documents must be rewritten first."""

    def _registered_matcher(self) -> str:
        text = INSTALL_SH.read_text(encoding="utf-8")
        m = re.search(r'\("guard-default-branch\.py",\s*"([^"]+)"\)', text)
        assert m is not None, "install.sh must register guard-default-branch.py"
        return m.group(1)

    def test_registered_matcher_is_direct_file_edit_tools_only(self):
        # The claim side: the installer registers exactly the direct file-edit tools — and the
        # matcher must NOT capture Bash, or the guard (which falls back to the payload cwd when
        # there is no file path) would deny every shell command run from a protected repo.
        matcher = self._registered_matcher()
        self.assertEqual(matcher, "Edit|Write|NotebookEdit")
        for tool in ("Edit", "Write", "NotebookEdit"):
            self.assertIsNotNone(re.fullmatch(matcher, tool), f"{tool} must route to the guard")
        self.assertIsNone(re.fullmatch(matcher, "Bash"), "Bash must NOT route to this guard")

    def test_bash_mutation_bypasses_the_guard_end_to_end(self):
        # The residual side, pinned honestly: a shell mutation on the default branch is dispatched
        # under tool_name=Bash, the matcher misses, the hook is never invoked, the mutation lands.
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(td)  # checked out on main — maximally protected state
            dispatched_to_guard = re.fullmatch(self._registered_matcher(), "Bash") is not None
            self.assertFalse(dispatched_to_guard)
            # host dispatch semantics: matcher missed → the command runs unguarded
            target = Path(repo, "seed.txt")
            subprocess.run(["bash", "-c", f"echo mutated >> '{target}'"], check=True)
            self.assertIn("mutated", target.read_text(),
                          "the documented R-06 residual: Bash mutates the default branch unimpeded")

    def test_direct_edit_tool_still_denied_control(self):
        # The control: the claim the docs DO make keeps holding — a direct Edit on main is denied.
        with tempfile.TemporaryDirectory() as td:
            repo = _repo(td)
            code, out = _run({"tool_name": "Edit", "cwd": repo,
                              "tool_input": {"file_path": str(Path(repo, "seed.txt"))}})
            self.assertEqual(code, 0)
            self.assertTrue(_denied(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
