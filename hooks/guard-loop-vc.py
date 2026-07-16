#!/usr/bin/env python3
"""PreToolUse guard: fence the version-control actions of an autonomous loop.

A self-paced `/loop` runs unattended across many iterations; the global VC norm auto-merges
(`--no-ff`) and DELETES the branch on review SIGN-OFF. If a loop self-blesses a false "done",
that chain can fire an unattended bad merge — the exact failure this guard exists to prevent.

TWO MODES, selected by the value of CLAUDE_LOOP_GUARD (see docs/design/loop-yolo-verifiable-autonomy.md):

  CLAUDE_LOOP_GUARD=1 (conservative — "stop-and-surface, never stop-and-act").
    The loop may keep working and committing on its own branch, but may NOT merge, delete
    branches, push, hard-reset, remove worktrees, `gh pr merge`, or `git clean`. Every
    irreversible act is reserved for an out-of-loop reviewer / human. This is the default posture
    and the safe one for *judgment* claims: a loop that writes its own telos witnesses produces
    *backed* DISCHARGED claims, so telos's SUSPECT-demotion (which only catches *unbacked*
    discharges) is routed around by construction — we can't trust the loop's self-judgment to gate
    the irreversible step, so we sever its ability to *act* on it.

  CLAUDE_LOOP_GUARD=yolo (verifiable autonomy).
    For loops whose Definition of Done is a frozen, loop-immutable oracle (an exit code trusted
    over the LLM), the self-judgment objection above evaporates — "done" is unforgeable, not
    self-blessed. So the loop may *act* to completion, but ONLY within the reversible/internal
    blast radius: it may integrate via a `--no-ff` merge into a NON-default local branch. It still
    may NOT push, force-push, hard-reset, `git clean`, delete a branch, remove a worktree,
    `gh pr merge`, merge into the default branch, or fast-forward merge (excluded so every merge is
    revertable via `git revert -m 1`). Default-branch detection FAILS DENY: if the current or
    default branch can't be determined, the merge is blocked.

`git clean` (without a dry-run flag) is denied in BOTH modes — it deletes untracked files with no
reflog, strictly worse than `reset --hard`.

Also denied in BOTH modes: `git remote set-head` and the write/delete forms of `git symbolic-ref`.
They repoint refs/remotes/origin/HEAD — the trust anchor this guard (and guard-default-branch.py)
reads for default-branch detection — so denying them protects the guard's OWN integrity. The read
form of `symbolic-ref` stays allowed. (main/master are hardcode-protected regardless, so this only
ever mattered for a non-standard trunk. This is deliberately NOT a complete deny-set over the git
surface — other rarely-dangerous verbs like `update-ref -d` / `reflog expire` are left open by
design; chasing full git-verb completeness is a losing race the SCOPE / LIMITS section documents
rather than pretends to win.)

ACTIVATION (opt-in). Does nothing unless CLAUDE_LOOP_GUARD is set. `/loop` is a built-in skill that
sets no marker of its own and there is no reliable way to auto-detect loop context, so the guard is
deliberately opt-in: zero friction for ordinary interactive work, protection when you explicitly
say "I'm looping."

It also steps over an enumerated set of exec-prefix LAUNCHERS (`env git push`,
`sudo git branch -D main`, `nice`/`nohup`/`setsid`/`stdbuf`/`ionice`/`timeout`/`time`/`command`/
`exec`/`doas`/`unbuffer`/`eatmydata`/`catchsegv`/`torsocks`) — these run their
argument list as a new command, so the fenced verb hides one token deeper; `_classify` resolves the
real executable (recursing for a chain like `sudo nice git push`) rather than anchoring on the
launcher basename. A shell running a simple `-c`/`+c` command string
(`bash`/`sh`/`dash`/`zsh`/`ksh -c "git push"`) is re-scanned as the command line it is. This is
executable resolution, not shell expansion (every token is literal), and it closes what was a
trivial no-privilege disarm of the whole deny set. The set holds launchers whose separate-value
option grammar is small, stable, and confidently complete — so a value is never misread as the
command. It is *enumerated, not exhaustive*: any exec-prefix NOT in it (an unlisted or
large-option-grammar launcher — `unshare`/`numactl`/`strace`/…, a leading-positional launcher, a
value-consuming `-o` shell form) is an accepted residual (see SCOPE / LIMITS), the same class as a
wrapper script — the guard recognizes a set, it does not model every launcher on the system.

SCOPE / LIMITS (honest). It parses the dangerous git/gh subcommands out of the Bash command string
as *literal* tokens — it does not expand the shell. String-parsing is NOT airtight, and these are
ACCEPTED residuals (documented, not chased — closing them would mean reimplementing the shell):
  * a script that calls git indirectly, or a shell alias;
  * a **word expansion that mutates the subcommand token** before bash resolves it — a brace
    (`git pus{h,} origin main` runs a real push; `git merge{,} --no-ff topic` a real merge), a glob,
    or a `$VAR` — the token the guard sees (`pus{h,}`, `$G`) is not `push`/`merge`, so `_classify`
    does not recognize it. Pinned as accepted-residual fixtures in
    hooks/tests/test_guard_loop_vc.py::TestAcceptedResiduals;
  * a **live command substitution inside double quotes** (`git commit -m "$(git push)"`) — segments
    split only outside quotes (so a verb literally quoted in a commit message is not a false deny);
    the unquoted `$(git push)` / `` `git push` `` forms stay caught;
  * an **exec-prefix OUTSIDE the recognized launcher set** — the set is enumerated, not exhaustive,
    so any other prefix that runs its arguments as a command is an accepted residual, the same class
    as an indirect wrapper script: a launcher with a leading positional of its own (`taskset <mask>`,
    `chrt <prio>`, `flock <file>` — the guard lands on the mask/priority/lock file, not `git`), a
    large or version-growing separate-value option grammar not confidently modeled (`unshare`,
    `numactl`, `cpulimit`, `strace`, `ltrace`, `proot`), or an optional-arg option grammar that the
    consume-next-token model cannot represent (`xargs -i`/`--replace`), a privileged shell string with a different
    arg order (`su -c`, `runuser -c`, `sg -c`), a shell `-c` whose vector has a value-consuming
    `-o`/`-O` or a `--rcfile`/`--init-file` (shifting the command position — `bash -o monitor -c
    "git push"`), a string-splitting option (`env -S 'git push'`), or a launcher chain deeper than
    the recursion cap. Pinned in
    hooks/tests/test_guard_loop_vc.py::TestLauncherPrefix::test_launcher_residuals_still_allow;
  * a `post-commit`/`post-merge` git hook or a filesystem watcher firing an external side effect the
    guard never sees (YOLO presumes a hook-clean working copy).
This is a seatbelt for the default path, not a sandbox; where possible, also simply don't hand the
loop a merge capability.

Registered in settings.json for the Bash tool.

Contract (docs/en/hooks): deny = exit 0 + JSON on stdout with
hookSpecificOutput.permissionDecision="deny"; emitting no decision defers to the normal flow.
We never exit non-zero — a guard bug must fail OPEN, never wedge the tool. (Note: "fail open" is the
*process* contract — never crash/wedge the tool. The merge-allow *decision* in YOLO mode fails
DENY: an undeterminable branch yields a normal deny, not a crash.)

Every deny is also appended, strictly best-effort AFTER the decision is on stdout, to a local
JSONL telemetry log (see hooks/_denial_log.py) — a telemetry fault never changes the decision.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

# Characters that, OUTSIDE quotes, separate independent commands within one Bash invocation:
# the command separators `;` `|` `&` newline, and the subshell / command-substitution boundaries
# `(` `)` backtick (so a dangerous verb glued inside `(git push)` / `$(git push)` / `` `git push` ``
# becomes its own segment instead of hiding behind the `(`/backtick in one shlex token). `&&`/`||`
# fall out of the single-char `&`/`|` split (an empty middle segment is harmless).
_SEPARATORS = frozenset(";|&\n()`")
# git global options that consume the *following* token as their value (so the real subcommand is
# one token further on): e.g. `git -C /path merge`, `git --config-env sec.key=ENV merge`. Verified
# against git 2.47.3 with a subcommand-shift discriminator (`git <opt> <val> zzzcmd` => git reports
# `zzzcmd` is unknown, proving <val> was consumed). `--exec-path` is deliberately NOT here: bare it
# is a query-terminal (prints the path and exits, never runs a following subcommand), and its only
# value form is the attached `--exec-path=<path>` (a single `-`-prefixed token already skipped).
_GIT_VALUE_OPTS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--attr-source",
}
# Environment variables that SELECT THE REPOSITORY out-of-band of the argv scan (`GIT_DIR=/p/.git
# git merge --no-ff t` targets /p while branch detection would read the payload cwd). P0.14 posture:
# they are not modeled — their presence marks the segment's repo selection UNMODELED, which
# _yolo_merge_reason turns into a fail-deny. (GIT_NAMESPACE etc. don't move HEAD; not selectors.)
_GIT_ENV_SELECTORS = {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"}
# Shell builtins that CHANGE THE WORKING DIRECTORY of every LATER segment (`cd /p && git merge
# --no-ff t` merges in /p while branch detection would read the payload cwd) — the cross-segment
# sibling of the launcher chdir options above. Same posture: not modeled; a preceding segment headed
# by one of these marks later segments' repo selection UNMODELED → YOLO merge fail-deny.
_DIR_BUILTINS = {"cd", "pushd", "popd"}
# Builtins that can EXPORT a GIT_DIR-family variable into every later segment
# (`export GIT_DIR=/p/.git; git merge --no-ff t`) — the cross-segment sibling of the same-segment
# `GIT_DIR=x git merge` prefix _classify already flags.
_EXPORT_BUILTINS = {"export", "declare", "typeset", "local"}
# gh options that consume the following token as their value and may precede the subcommand
# path, so a flag value isn't mistaken for `pr`/`merge`: e.g. `gh -R owner/repo pr merge`.
_GH_VALUE_OPTS = {"-R", "--repo", "--hostname"}
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Exec-prefix launchers: commands that run their argument list as a NEW command, so a fenced
# git/gh verb hides one token deeper (`env git push`, `nice git merge`, `sudo git branch -D main`).
# Without stepping over them the guard anchors on the launcher basename (`env`), sees no `git`
# executable, and defers — a trivial, no-privilege disarm of the ENTIRE deny set. `_classify`
# steps over the launcher (and its own options/values) and re-classifies the delegated command;
# recursion handles a chain (`sudo nice git push`). This is NOT shell expansion — every token is
# literal; the guard simply resolves the real executable, the same way it already steps over git's
# global options. The set is the common, well-behaved `[options] command` launchers whose grammar
# has no required leading positional (except `timeout`'s DURATION, handled below). Niche launchers
# with a leading positional of their own (`taskset <mask> cmd`, `chrt <prio> cmd`, `flock <file>
# cmd`) are the documented residual in KNOWN-BYPASSES.md — same class as an indirect wrapper script.
# The recognized launchers are those whose separate-value option grammar is SMALL, STABLE, and
# confidently complete — so a `<launcher> <value-opt> <val> git push` cannot MISS by mis-reading the
# value as the command. Launchers with a large or version-growing separate-value option set
# (`unshare`, `numactl`, `cpulimit`, `strace`, `ltrace`, `proot`), or an OPTIONAL-arg option that
# cannot be modeled in the consume-next-token framework at all (`xargs -i`/`--replace` are
# attached-only, and `--process-slot-var` grows the set), are the documented residual instead: a
# half-modeled launcher whose option slips is exactly the "claimed catch that slips" failure this
# fence must not have. (`unbuffer`/`eatmydata`/`catchsegv` are optionless; `torsocks`/`doas`/`time`
# have tiny fixed value sets. `firejail` is NOT here: its option surface is large enough that a
# separate-value option can't be confidently ruled out, so it is a documented residual.)
_LAUNCHERS = {
    "env", "command", "exec", "nohup", "setsid", "sudo", "doas",
    "nice", "ionice", "stdbuf", "timeout", "time",
    "unbuffer", "eatmydata", "catchsegv", "torsocks",
}
# Shells that run a command STRING passed to `-c` (`bash -c "git push"`). The string is itself a
# command line, so `_classify` re-scans it with the full segment splitter (catching `sh -c 'env git
# push'` too). `_shell_c_command` models the SIMPLE `-c`/`+c` flag-cluster forms and bails to the
# residual on the value-consuming `-o`/`-O` forms rather than guess the command position. Privileged
# positional-arg shell forms (`su -c`, `runuser -c`, `sg -c`) are the documented residual.
_SHELL_LAUNCHERS = {"bash", "sh", "dash", "zsh", "ksh", "ash", "mksh"}
# Long shell options that take a SEPARATE value token; their presence shifts the command position, so
# `_shell_c_command` bails to the residual rather than mis-locate it.
_SHELL_LONG_VALUE_OPTS = {"--rcfile", "--init-file"}
# Per-launcher options that consume the FOLLOWING token as their value, so a value (e.g. the `git`
# in `sudo -u git ...`, a nice adjustment, a timeout signal) is never mistaken for the delegated
# command. Only the common value-taking options are enumerated; an unknown value-option whose value
# is non-git and precedes a real git verb is the same literal-token residual the module documents.
_LAUNCHER_VALUE_OPTS = {
    "env": {"-u", "--unset", "-C", "--chdir", "-a", "--argv0"},  # -a/--argv0 <name> still execs the
                                                #  command (coreutils 9.x); NOT -S/--split-string,
                                                #  which re-splits one string arg (an expansion) →
                                                #  documented residual
    "sudo": {"-u", "--user", "-g", "--group", "-C", "--close-from", "-h", "--host", "-p",
             "--prompt", "-r", "--role", "-t", "--type", "-T", "--command-timeout", "-U",
             "--other-user", "-R", "--chroot", "-D", "--chdir"},
    "doas": {"-u", "-C", "-a"},  # doas [-a style] [-C config] [-u user] command
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "--class", "-n", "--classdata", "-p", "--pid"},
    "stdbuf": {"-i", "--input", "-o", "--output", "-e", "--error"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "exec": {"-a"},
    "time": {"-o", "--output", "-f", "--format"},  # GNU /usr/bin/time (the bash keyword ignores these)
    "torsocks": {"-a", "--address", "-p", "--port", "-P", "--pass", "-u", "--user"},
}
# Launcher options that CHANGE THE WORKING DIRECTORY of the delegated command (`env -C /p git merge`
# runs the merge in /p while branch detection would read the payload cwd) — another repo-selector
# spelling. P0.14 posture: not modeled (composing the new cwd faithfully buys little); their presence
# marks the delegated command's repo selection UNMODELED → fail-deny for a YOLO merge. sudo's `-C`
# is --close-from (an fd number), NOT chdir — its chdir short is `-D`; env's chdir short IS `-C`.
_LAUNCHER_CHDIR_OPTS = {
    "env": {"-C", "--chdir"},
    "sudo": {"-D", "--chdir"},
}
# Launchers whose grammar puts N bare positionals BEFORE the delegated command (`timeout DURATION
# command`). Skipped after the option scan so the DURATION is not misread as the command.
_LAUNCHER_POSITIONAL_SKIP = {"timeout": 1}
_MAX_LAUNCHER_DEPTH = 10  # backstop against a pathological launcher chain (each hop shrinks tokens)


def _after_launcher(launcher: str, args: list[str]) -> tuple[list[str] | None, bool]:
    """(Tokens of the command a launcher delegates to or None, saw-a-chdir-option).

    Steps over the launcher's own options (consuming the values of `_LAUNCHER_VALUE_OPTS`) and any
    leading positionals it takes (`_LAUNCHER_POSITIONAL_SKIP`), landing on the delegated command.
    The caller re-runs `_classify` on the result, so a `VAR=val` prefix (env's assignments) and a
    nested launcher are handled by that recursion, not here.

    The second element is True iff a `_LAUNCHER_CHDIR_OPTS` option was seen (in long, `--chdir=`
    attached, clustered-short, or `-C<path>` attached-short form): the delegated command then runs
    in a directory the guard did not model, so a YOLO merge behind it must fail-deny (P0.14).
    """
    value_opts = _LAUNCHER_VALUE_OPTS.get(launcher, frozenset())
    chdir_opts = _LAUNCHER_CHDIR_OPTS.get(launcher, frozenset())
    chdir_letters = {opt[1] for opt in chdir_opts if len(opt) == 2 and opt[0] == "-"}
    chdir_longs = {opt for opt in chdir_opts if opt.startswith("--")}
    saw_chdir = False
    # The value-taking SHORT letters, so a value option CLUSTERED behind other short flags
    # (`env -vu FOO ...`, `sudo -knu user ...`, `ionice -tc 2 ...`) still consumes its value token
    # instead of being read as a valueless flag — the same clustered-short walk `_has_delete_flag`
    # and `_clean_is_dry_run` already do. Without it a modeled value option's value is mis-read as
    # the command (a 3-char cluster reopens the whole bypass). Long `--opt` forms stay exact-match.
    value_letters = {opt[1] for opt in value_opts if len(opt) == 2 and opt[0] == "-"}
    j = 0
    while j < len(args):
        a = args[j]
        if a == "--" or a == "--end-of-options":
            j += 1  # option terminator — the very next token is the command
            break
        if a.startswith("--"):
            if a in chdir_longs or a.partition("=")[0] in chdir_longs:
                saw_chdir = True  # --chdir <dir> / --chdir=<dir>
            j += 2 if a in value_opts else 1  # long value-opt consumes its token; else a flag
            continue
        if a.startswith("-") and len(a) > 1:
            # a short cluster: a value letter consumes the cluster remainder as an attached value
            # (`-n5`, `-oL`) or, if it is the cluster's LAST letter, the next separate token.
            consumes_next = False
            for idx, ch in enumerate(a[1:]):
                if ch in value_letters:
                    if ch in chdir_letters:
                        saw_chdir = True  # -C <dir>, -C<dir>, or clustered (-vC <dir>)
                    consumes_next = idx == len(a) - 2  # value letter is the cluster's last char
                    break
            j += 2 if consumes_next else 1
            continue
        if a == "-":
            j += 1  # a bare `-` (env "clear environment") is never the command
            continue
        break  # first non-option token
    for _ in range(_LAUNCHER_POSITIONAL_SKIP.get(launcher, 0)):
        if j < len(args):
            j += 1
    return (args[j:] if j < len(args) else None), saw_chdir


def _shell_c_command(args: list[str]) -> str | None:
    """The command STRING a shell's `-c` runs, or None if it can't be located SOUNDLY.

    `c` is bash/sh/dash/zsh/ksh's only 'c' short option and, when command mode is set, the command
    string is the first operand after the option vector. This models the simple, unambiguous forms:
    a `-`/`+` flag cluster that contains `c` and NO value-consuming letter (`-c`, `-cx`, `-xc`,
    `+c`, `bash --norc -c`) → the command is the token right after the cluster. It deliberately does
    NOT model the value-consuming forms: a `-o`/`-O`/`+o`/`+O` letter (which eats a SEPARATE token,
    shifting the command position — `bash -co monitor "git push"`) or a `--rcfile`/`--init-file`
    long value option makes the command position ambiguous without faithfully parsing the shell's
    option vector, so it bails to None (the documented residual) rather than mis-locate the command
    and either miss the verb or false-deny an option value. Same posture as the leading-positional
    launchers: model the clean case, document the rest."""
    j = 0
    while j < len(args):
        a = args[j]
        if a == "--":
            return None  # end of options with no command-mode operand seen → not a `-c` invocation
        if a.startswith("--"):
            if a in _SHELL_LONG_VALUE_OPTS:
                return None  # a separate-value long option shifts the command position → residual
            j += 1
            continue
        if a and a[0] in "-+" and len(a) > 1:
            letters = a[1:]
            if "o" in letters or "O" in letters:
                return None  # value-consuming letter → command position ambiguous → residual
            if "c" in letters:
                return args[j + 1] if j + 1 < len(args) else None
            j += 1
            continue
        return None  # an operand before any `-c` → a script/interactive shell, not `-c` mode
    return None


def _subcommand_path(args: list[str], value_opts: set[str], depth: int) -> list[str]:
    """First `depth` positional tokens, stepping over flags and the values of `value_opts`.

    Lets `git -C /p merge` and `gh -R o/r pr merge` resolve to their real subcommand path
    instead of mistaking an option's value for the subcommand.
    """
    path: list[str] = []
    j = 0
    while j < len(args) and len(path) < depth:
        a = args[j]
        if a in value_opts:
            j += 2
            continue
        if a.startswith("-"):
            j += 1
            continue
        path.append(a)
        j += 1
    return path


def _allow() -> None:
    """Emit no decision → defer to the normal permission flow. Always exit 0."""
    sys.exit(0)


def _record_denial(reason: str, payload: dict) -> None:
    """Best-effort denial telemetry via the sibling hooks/_denial_log.py (loaded by resolved
    path, the runtime/spec_adapter.py pattern, so the ~/.claude symlink layout finds it). ANY
    fault — module missing (a copied guard with no sibling), unwritable log, anything — is
    swallowed: the deny already flushed to stdout must never be affected."""
    try:
        import importlib.util

        mod_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "_denial_log.py")
        spec = importlib.util.spec_from_file_location("_denial_log", mod_path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.record("guard-loop-vc", reason, payload)
    except Exception:
        pass


def _deny(reason: str, payload: dict) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    # Decision first, telemetry second: flush the deny to the harness BEFORE any telemetry I/O.
    # Flushing alone is necessary but not sufficient — a hung write would still hold this process
    # past the hook timeout (which fails OPEN and lets the fenced call run) — so record() also
    # time-bounds the filesystem I/O in an abandonable daemon thread (see hooks/_denial_log.py).
    sys.stdout.flush()
    _record_denial(reason, payload)
    sys.exit(0)


def _git(selectors: list[str], *args: str) -> tuple[bool, str]:
    """Run a read-only `git` query; return (ok, stdout). Never raises (fail toward not-ok).

    `selectors` are the repository-selecting global options (`-C <dir>`, `--git-dir <dir>`,
    `--work-tree <dir>`) reconstructed from the guarded command, so the query interrogates the SAME
    repository the guarded command would mutate (P0.14) — not the payload cwd. The `-C` entry is
    placed first by the caller, so a relative `--git-dir`/`--work-tree` resolves against the `-C`
    base exactly as git itself resolves them (git chdirs for `-C` during option parsing and resolves
    GIT_DIR/GIT_WORK_TREE at repository setup, i.e. after every chdir, regardless of option order).
    """
    try:
        p = subprocess.run(["git", *selectors, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if p.returncode != 0:
        return False, ""
    return True, p.stdout.strip()


def _current_branch(selectors: list[str]) -> str | None:
    """The checked-out branch name, or None if undeterminable. Detached HEAD reads as 'HEAD'."""
    ok, out = _git(selectors, "rev-parse", "--abbrev-ref", "HEAD")
    return out if ok else None


def _default_branch(selectors: list[str]) -> str | None:
    """The repo's default branch, or None if it can't be determined unambiguously (→ fail-deny).

    Mirrors pre-merge-review's base resolution: prefer `origin/HEAD`; else, for local-only repos
    (the common case here), the sole of `main`/`master`. If BOTH exist, disambiguate only via an
    explicit `init.defaultBranch` naming one of them; otherwise it is genuinely ambiguous → None.

    HONEST LIMIT: a local-only repo has no authoritative "default branch", so the main/master
    fallback is a *best-effort heuristic*, not the fail-deny guarantee. A repo whose real trunk is
    a non-standard name (e.g. `develop`) with no `origin/HEAD` and no `init.defaultBranch` would be
    mis-resolved. `_yolo_merge_reason` compensates by *also* always protecting the literal `main`/
    `master` names; the residual (a non-standard trunk) is bounded — the only allowed act is a
    revertable `--no-ff` merge, and push stays denied. Set `origin/HEAD`/`init.defaultBranch` to be safe.
    """
    ok, out = _git(selectors, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if ok and out.startswith("refs/remotes/origin/"):
        # Strip the fixed ref prefix, NOT rsplit("/") — a branch name can itself contain slashes
        # (release/2.0, team/main), and rsplit would keep only the last segment ("2.0", "main"),
        # resolving a DIFFERENT default than the one checked out and letting a YOLO merge into the
        # real default slip through. removeprefix keeps the full name. (This mirrors the sibling
        # fix in guard-default-branch.py, which resolves the same trust anchor.)
        return out.removeprefix("refs/remotes/origin/")
    has_main = _git(selectors, "show-ref", "--verify", "--quiet", "refs/heads/main")[0]
    has_master = _git(selectors, "show-ref", "--verify", "--quiet", "refs/heads/master")[0]
    if has_main and not has_master:
        return "main"
    if has_master and not has_main:
        return "master"
    if has_main and has_master:
        ok, cfg = _git(selectors, "config", "init.defaultBranch")
        if ok and cfg in ("main", "master"):
            return cfg
    return None


def _yolo_merge_reason(selectors: list[str], rest: list[str], unmodeled_selector: bool) -> str | None:
    """In YOLO mode, return a deny reason for this `git merge`, or None if the merge is allowed.

    Allowed iff it is a `--no-ff` merge (so it is revertable via `git revert -m 1`) into a
    confirmed NON-default branch. Any uncertainty about the current/default branch fails DENY —
    including `unmodeled_selector`: the command carries a repository/directory selector spelling the
    guard did not model (attached `-C<path>`, a `GIT_DIR`/`GIT_WORK_TREE`/`GIT_COMMON_DIR` env
    assignment, a launcher chdir option, or a preceding `cd`/`pushd`/`export` segment), so branch
    detection would interrogate the WRONG repo (P0.14).
    """
    if "--no-ff" not in rest:
        return "fast-forward merge in YOLO (only --no-ff merges are allowed, so the merge is revertable)"
    if unmodeled_selector:
        return (
            "merge behind a repository/directory selector the guard does not model "
            "(attached -C, GIT_DIR-family environment variable, launcher chdir option, or a "
            "preceding cd/pushd/export segment) — branch detection can't be trusted (fail-deny)"
        )
    current = _current_branch(selectors)
    if not current or current == "HEAD":
        return "merge while the current branch can't be confirmed non-default (fail-deny)"
    default = _default_branch(selectors)
    if default is None:
        return "merge while the repo's default branch can't be determined (fail-deny)"
    # Protect the resolved default AND the literal main/master names — so a main/master mix-up, or a
    # local-only repo whose heuristic default is the wrong one of the two, can never wave a
    # default-branch merge through. (A non-standard trunk name is the documented residual.)
    if current == default or current in ("main", "master"):
        return f"merge into a default/protected branch '{current}' (YOLO integrates only into non-default branches)"
    return None


def _clean_is_dry_run(rest: list[str]) -> bool:
    """True iff `git clean` carries a genuine dry-run flag (`-n` / `--dry-run`).

    The subtle part is `-e<pattern>` (exclude): it consumes the rest of its short cluster — and, if
    nothing follows in-token, the *next* argument — as a literal pattern. Letters inside that pattern
    (e.g. the `n` in `git clean -fenode_modules`) must NOT be mistaken for the `-n` dry-run flag, or a
    real force-delete is waved through. We parse the cluster, stop scanning at `-e`, and skip its value.
    Anything not positively recognized as dry-run returns False → deny (fail-deny posture).
    """
    i = 0
    while i < len(rest):
        t = rest[i]
        if t == "--" or t == "--end-of-options":
            break  # both are option terminators — everything after is a pathspec, never a flag;
            # an `-n`/`--dry-run` there is a filename, not the dry-run option
        if t == "--dry-run":
            return True
        if t == "-e" or t == "--exclude":
            i += 2  # `-e <pattern>` — the value is the next token; never a flag
            continue
        if t.startswith("--"):
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            consumes_next = False
            for idx, ch in enumerate(t[1:]):
                if ch == "n":
                    return True  # a real -n in this cluster (before any -e) → dry-run
                if ch == "e":
                    # -e takes the cluster remainder as its value; if it's the last char, the
                    # value is the NEXT argument, which must then be skipped (not read as a flag).
                    consumes_next = idx == len(t) - 2
                    break
            if consumes_next:
                i += 2
                continue
        i += 1
    return False


def _has_delete_flag(
    rest: list[str],
    delete_letters: tuple[str, ...],
    value_taking: tuple[str, ...],
    long_forms: tuple[str, ...] = ("--delete",),
) -> bool:
    """True iff `rest` carries a DELETE flag, honoring CLUSTERED short options.

    Git accepts clustered shorts, so `-d`/`-D` hide in ordinary forms — `git branch -vd feature`,
    `-rd origin/feature`, `git symbolic-ref -qd ...`. A bare `"-d" in rest` membership test misses
    every one of those and waves a real delete through. Scan each short cluster left-to-right;
    a `delete_letter` anywhere in it (before a value-taking option) is a delete. A `value_taking`
    short consumes the cluster remainder — and, if it is the cluster's last letter, the NEXT token —
    as its value, so letters/tokens after it are NOT flags (mirrors `_clean_is_dry_run`'s `-e`
    handling). Stop at the `--`/`--end-of-options` terminator; long forms match as whole tokens.
    """
    i = 0
    while i < len(rest):
        t = rest[i]
        if t == "--" or t == "--end-of-options":
            break  # everything after is a positional (a ref/pathspec), never a flag
        if t in long_forms:
            return True
        if t.startswith("--"):
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            consumes_next = False
            for idx, ch in enumerate(t[1:]):
                if ch in delete_letters:
                    return True
                if ch in value_taking:
                    consumes_next = idx == len(t) - 2  # value-taking short is the cluster's last char
                    break
            if consumes_next:
                i += 2  # the next token is this option's value — skip it, never read it as a flag
                continue
        i += 1
    return False


def _symbolic_ref_write_reason(rest: list[str]) -> str | None:
    """Deny reason for a WRITE-form `git symbolic-ref`, or None for the read form.

    The read form (one positional: `git symbolic-ref [--quiet|--short] <name>`) is how scripts —
    including this guard itself — *query* refs, and must stay allowed. The write form
    (`git symbolic-ref <name> <ref>`, two positionals) and the delete form (`-d`/`--delete`)
    mutate the ref — that is how refs/remotes/origin/HEAD gets repointed. `-m <reason>` consumes
    the following token as its value, so a reason string is never counted as a positional.
    """
    # `-d`/`--delete`, including clustered forms (`-qd`). symbolic-ref's only value-taking short is
    # `-m <reason>`, so a `-md`/`-qm` cluster's trailing letters are the reason value, not a delete.
    if _has_delete_flag(rest, ("d",), ("m",)):
        return "delete a symbolic ref (git symbolic-ref -d)"
    positionals = 0
    j = 0
    while j < len(rest):
        t = rest[j]
        if t == "-m":
            j += 2  # -m <reason>: the value is the next token, never a positional
            continue
        if t.startswith("-"):
            j += 1
            continue
        positionals += 1
        j += 1
    if positionals >= 2:
        return "rewrite a symbolic ref (git symbolic-ref <name> <ref>)"
    return None


def _classify(
    tokens: list[str], yolo: bool, cwd: str | None, _depth: int = 0, _unmodeled_sel: bool = False
) -> str | None:
    """Return a short reason if `tokens` (one command segment) is a forbidden VC mutation.

    `yolo` selects the destructive-only deny set; `cwd` is the fallback repo dir used for branch
    detection when the command carries no repo selector. `_depth` bounds launcher-prefix recursion.
    `_unmodeled_sel` carries a repo/directory-selector sighting the guard did not model (a launcher
    chdir option, a GIT_DIR-family env assignment) down the recursion — it fail-denies a YOLO merge
    (P0.14) and is ignored everywhere else (the rest of the deny set never consults the repo).
    """
    # Skip leading `VAR=value` env assignments to reach the executable. GIT_DIR-family assignments
    # select the repository out-of-band of the argv scan → mark the selection unmodeled (P0.14).
    i = 0
    while i < len(tokens) and _ENV_ASSIGN.match(tokens[i]):
        if tokens[i].partition("=")[0] in _GIT_ENV_SELECTORS:
            _unmodeled_sel = True
        i += 1
    if i >= len(tokens):
        return None
    exe = os.path.basename(tokens[i])
    args = tokens[i + 1 :]

    # Exec-prefix launcher (`env`/`sudo`/`nice`/`timeout`/…): the real command hides in its args.
    # Step over the launcher and re-classify the delegated command so `env git push` is seen as the
    # `git push` it runs. Recursion (bounded) handles a chain like `sudo nice git push`; the fenced
    # git/gh verb is a literal token, so this is executable resolution, not shell expansion.
    if exe in _LAUNCHERS and _depth < _MAX_LAUNCHER_DEPTH:
        delegated, saw_chdir = _after_launcher(exe, args)
        if delegated is None:
            return None
        return _classify(delegated, yolo, cwd, _depth + 1, _unmodeled_sel or saw_chdir)

    # A shell running a `-c` command string: the string is another command line, so re-scan it with
    # the full segment splitter (`bash -c "git push"`, `sh -c 'env git push'`). No `-c` → a script or
    # interactive shell whose body the guard does not read (the wrapper-script residual).
    if exe in _SHELL_LAUNCHERS and _depth < _MAX_LAUNCHER_DEPTH:
        inner = _shell_c_command(args)
        return _dangerous(inner, yolo, cwd, _depth + 1, _unmodeled_sel) if inner is not None else None

    if exe == "gh":
        # Only `gh pr merge` performs the merge server-side (denied in both modes). Resolve the
        # subcommand path while stepping over value-taking flags (so `gh -R o/r pr merge` /
        # `gh pr --repo o/r merge` are still caught), and so reads like `gh pr view`,
        # `gh pr list --label merge`, or `gh pr checkout some-merge-branch` are allowed.
        if _subcommand_path(args, _GH_VALUE_OPTS, 2) == ["pr", "merge"]:
            return "merge a PR (gh pr merge)"
        return None

    if exe != "git":
        return None

    # Find the git subcommand, stepping over global options (and their values). Capture every
    # REPOSITORY SELECTOR the command carries — `-C` (repeated relatives compose, each against the
    # preceding base, per git), `--git-dir`/`--work-tree` in both the separate and the `=`-attached
    # spelling — so branch detection interrogates the repo the command TARGETS, not the payload cwd
    # (P0.14). The one git-selector spelling NOT modeled is the attached `-C<path>`: git 2.47.3
    # rejects it ("unknown option"), so today it can't run — marking it unmodeled (→ YOLO fail-deny)
    # is hardening in case a future git accepts it, not a live-bypass closure.
    repo_dir = cwd
    git_dir: str | None = None
    work_tree: str | None = None
    unmodeled_sel = _unmodeled_sel
    sub = None
    rest: list[str] = []
    j = 0
    while j < len(args):
        a = args[j]
        if a in _GIT_VALUE_OPTS:
            if j + 1 < len(args):
                val = args[j + 1]
                if a == "-C":
                    repo_dir = val if os.path.isabs(val) else os.path.join(repo_dir or ".", val)
                elif a == "--git-dir":
                    git_dir = val
                elif a == "--work-tree":
                    work_tree = val
            j += 2
            continue
        if a.startswith("--git-dir="):
            git_dir = a.partition("=")[2]
            j += 1
            continue
        if a.startswith("--work-tree="):
            work_tree = a.partition("=")[2]
            j += 1
            continue
        if a.startswith("-C") and len(a) > 2:
            unmodeled_sel = True  # attached -C<path>: git-rejected today; fail-deny hardening
            j += 1
            continue
        if a.startswith("-"):
            j += 1
            continue
        sub = a
        rest = args[j + 1 :]
        break
    if sub is None:
        return None
    # Reconstruct the selectors for the read-only detection queries. `-C` first: git resolves a
    # relative GIT_DIR/GIT_WORK_TREE at repository setup — after every `-C` chdir — so this
    # reproduces the guarded command's resolution for any option order (see _git's docstring).
    selectors: list[str] = []
    if repo_dir:
        selectors += ["-C", repo_dir]
    if git_dir is not None:
        selectors += ["--git-dir", git_dir]
    if work_tree is not None:
        selectors += ["--work-tree", work_tree]

    # `merge` but not the read-only plumbing `merge-base` / `merge-tree` / `merge-file`.
    if sub == "merge":
        return _yolo_merge_reason(selectors, rest, unmodeled_sel) if yolo else "merge a branch (git merge)"
    if sub == "push":
        return "push to a remote (git push)"
    if sub == "reset" and "--hard" in rest:
        return "hard-reset the working tree (git reset --hard)"
    if sub == "clean" and not _clean_is_dry_run(rest):
        return "delete untracked files (git clean)"
    # `-d`/`-D`/`--delete`, including clustered forms (`-vd`, `-rd`, `-qD`). branch's value-taking
    # short is `-u <upstream>`, so an `-ud` cluster's `d` is the upstream name, not a delete.
    if sub == "branch" and _has_delete_flag(rest, ("d", "D"), ("u",)):
        return "delete a branch (git branch -d/-D)"
    # position-aware (like `remote set-head` / `gh pr merge` below), NOT a bare `"remove" in rest`
    # membership — else `git worktree add ../wt remove` (a branch/path literally named `remove`) would
    # be a false deny. Only the `remove` SUBCOMMAND (first positional) is the destructive one.
    if sub == "worktree" and _subcommand_path(rest, set(), 1) == ["remove"]:
        return "remove a worktree (git worktree remove)"
    # Both `remote set-head` and the write form of `symbolic-ref` rewrite refs/remotes/origin/HEAD —
    # the trust anchor _default_branch() (and guard-default-branch.py) reads for default-branch
    # detection. A loop that can repoint it can re-aim what "default branch" means, so denying these
    # protects the guard's OWN integrity (not deny-set completeness — other rarely-dangerous verbs
    # are left open by design; see the module docstring's SCOPE / LIMITS). Residual: main/master
    # stay hardcode-protected regardless, so this only ever mattered for a non-standard trunk.
    if sub == "remote" and _subcommand_path(rest, set(), 1) == ["set-head"]:
        return "repoint a remote's HEAD (git remote set-head)"
    if sub == "symbolic-ref":
        return _symbolic_ref_write_reason(rest)
    # `git pull` is deliberately NOT denied: it advances the *current* branch from upstream
    # (reflog-recoverable, no push / branch-delete / remote mutation) — within the seatbelt scope.
    return None


def split_segments(command: str) -> list[str]:
    """Split a Bash command into segments at _SEPARATORS, honoring them ONLY outside quotes.

    A separator inside single or double quotes is literal text, not a command boundary — so a
    dangerous verb quoted in an argument (`git commit -m "document the (git push) bypass"`) stays
    inside its segment and is NOT promoted to its own command (which would be a false deny; this
    repo's own commit messages are full of such strings). The tradeoff is that a LIVE command
    substitution inside double quotes (`"... $(git push)"`, which bash WOULD execute) is likewise
    not segmented — an accepted under-block residual, consistent with the word-expansion limits in
    SCOPE / LIMITS. Backslash escapes the next char (outside single quotes) so an escaped separator
    is literal too. Quote characters are preserved in the segment for the downstream shlex.split."""
    segments: list[str] = []
    buf: list[str] = []
    in_single = in_double = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
        elif in_double:
            if ch == "\\" and i + 1 < n:
                buf.append(ch); buf.append(command[i + 1]); i += 2; continue
            buf.append(ch)
            if ch == '"':
                in_double = False
        elif ch == "'":
            in_single = True; buf.append(ch)
        elif ch == '"':
            in_double = True; buf.append(ch)
        elif ch == "\\" and i + 1 < n:
            buf.append(ch); buf.append(command[i + 1]); i += 2; continue
        elif ch in _SEPARATORS:
            segments.append("".join(buf)); buf = []
        else:
            buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [s for s in (seg.strip() for seg in segments) if s]


def _segment_changes_repo_context(tokens: list[str]) -> bool:
    """True iff this segment relocates the repo context of LATER segments (P0.14, cross-segment).

    Three shapes, all fail-deny-marked rather than modeled: a directory-changing builtin (`cd`,
    `pushd`, `popd` — also behind the `builtin`/`command` prefixes bash accepts); an export-style
    builtin naming a GIT_DIR-family variable (`export GIT_DIR=/p/.git`, `declare -x GIT_DIR=…`,
    bare `export GIT_DIR` promoting an earlier assignment); and an assignments-only segment that
    assigns one (`GIT_DIR=/p/.git; git merge …` — only live if exported earlier/later, but the
    conservative flag costs nothing real). Marking is one-directional: segments BEFORE this one are
    unaffected (`git merge …; cd /p` merges in the payload cwd, so it stays modeled).
    """
    if not tokens:
        return False
    head = tokens[0]
    if head in ("builtin", "command") and len(tokens) > 1:
        head = tokens[1]
    if head in _DIR_BUILTINS:
        return True
    if tokens[0] in _EXPORT_BUILTINS and any(
        t.partition("=")[0] in _GIT_ENV_SELECTORS for t in tokens[1:]
    ):
        return True
    if all(_ENV_ASSIGN.match(t) for t in tokens) and any(
        t.partition("=")[0] in _GIT_ENV_SELECTORS for t in tokens
    ):
        return True
    return False


def _dangerous(
    command: str, yolo: bool, cwd: str | None, _depth: int = 0, _unmodeled_sel: bool = False
) -> str | None:
    """Scan a full Bash command (possibly compound) for a forbidden VC mutation.

    `_depth` and `_unmodeled_sel` are threaded from a shell `-c` re-scan (`bash -c "git push"`) so a
    nested-shell chain shares the launcher recursion cap, and an unmodeled directory selector seen
    OUTSIDE the shell (`env -C /p bash -c "git merge --no-ff t"`) still fail-denies the inner merge.

    Segments are scanned IN ORDER, carrying the unmodeled-selector flag forward: a segment that
    relocates the repo context (`cd /p`, `export GIT_DIR=…`) marks every LATER segment, so
    `cd /p && git merge --no-ff t` fail-denies the merge in YOLO instead of evaluating the payload
    cwd's branches (P0.14, cross-segment)."""
    unmodeled_sel = _unmodeled_sel
    for segment in split_segments(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()  # unbalanced quotes etc. → best-effort
        reason = _classify(tokens, yolo, cwd, _depth, unmodeled_sel)
        if reason:
            return reason
        if not unmodeled_sel and _segment_changes_repo_context(tokens):
            unmodeled_sel = True
    return None


def _deny_message(reason: str, yolo: bool) -> str:
    if yolo:
        return (
            f"Blocked: even in YOLO mode (CLAUDE_LOOP_GUARD=yolo) a loop may not {reason}. "
            f"YOLO permits autonomous acts only within the reversible/internal blast radius (commit, "
            f"and `--no-ff` merges into NON-default branches) gated by a verifiable Definition of Done; "
            f"it does NOT permit destructive, irreversible, or external acts — push/force-push, "
            f"hard-reset, git clean, branch-delete, worktree-remove, gh pr merge, a merge into the "
            f"default branch, or a fast-forward merge. Keep working on your own non-default branch and "
            f"integrate only via `--no-ff` merges into non-default branches. "
            f"See docs/design/loop-yolo-verifiable-autonomy.md."
        )
    return (
        f"Blocked: an autonomous loop (CLAUDE_LOOP_GUARD set) may not {reason}. "
        f"Loops are stop-and-surface, never stop-and-act: keep working and committing on "
        f"your own branch, then STOP and surface the branch for an out-of-loop reviewer "
        f"(e.g. pre-merge-review) or a human to merge. A self-paced loop cannot bless its "
        f"own completion — telos discharge is surface-not-correctness and a loop that writes "
        f"its own witnesses routes around the SUSPECT guard. To allow autonomous integration of "
        f"verifiable work, set CLAUDE_LOOP_GUARD=yolo instead (reversible/internal acts only); to "
        f"lift the guard entirely, unset it (accepting unattended irreversible VC actions)."
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:  # JSONDecodeError is a ValueError subclass — one catch suffices
        _allow()  # unparseable input → fail open, never wedge the tool
    if not isinstance(payload, dict):
        _allow()  # valid-JSON-but-not-an-object (5, "x", [], null) → fail open; the never-exit-non-zero
        # contract is unconditional, so payload.get(...) must never see a non-dict and raise AttributeError

    # Inactive unless explicitly in a guarded loop (opt-in marker). The value selects the mode.
    marker = os.environ.get("CLAUDE_LOOP_GUARD")
    if not marker:
        _allow()
    yolo = marker.strip().lower() == "yolo"

    if payload.get("tool_name") != "Bash":
        _allow()  # matcher should restrict to Bash, but never assume

    # Same P0.16 posture as guard-default-branch.py: a truthy NON-string command/cwd (a crafted or
    # buggy payload) must fail OPEN, not TypeError inside split_segments/os.path.join and exit 1
    # against the never-exit-non-zero contract.
    tool_input = payload.get("tool_input")
    command = (tool_input if isinstance(tool_input, dict) else {}).get("command")
    if not isinstance(command, str):
        _allow()  # absent or malformed command → nothing parseable to fence
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    reason = _dangerous(command, yolo, cwd)
    if reason:
        _deny(_deny_message(reason, yolo), payload)
    _allow()


if __name__ == "__main__":
    main()
