"""The loop-VC policy: classify whether a Bash command is a fenced version-control mutation.

This is the model-blind core of the shipped `hooks/guard-loop-vc.py` — the segment splitter, the
launcher/shell/eval step-over, the git/gh subcommand classifier, and the two-mode (conservative /
YOLO) deny set. It was extracted VERBATIM from that hook (which is now a thin host adapter that parses
the native pre-tool envelope, checks the arming marker, calls `_dangerous`, and renders the veto).
`runtime/spec_adapter.py` drives the SAME `_dangerous` from a generic envelope, so the "one core,
many adapters" portability claim is a running, tested fact.

The policy is stdlib + git-boundary only: it never reads stdin/stdout, the environment, or a model
identity. Branch detection for the YOLO merge check goes through `excubitor.core.git_state` (the
read-only git boundary). The `hooks/tests/` and `runtime/tests/` suites are the differential oracle —
a decision change here is a regression, never a fixture update.

SCOPE / LIMITS are unchanged from the shipped guard and documented there and in KNOWN-BYPASSES.md:
this parses dangerous git/gh verbs out of the command string as literal tokens; it does not expand
the shell. It is a seatbelt for the default path, not a sandbox.
"""
from __future__ import annotations

import os
import re
import shlex

from excubitor.core import git_state
from excubitor.core.shell import split_segments

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
    "env", "command", "builtin", "exec", "nohup", "setsid", "sudo", "doas",
    "nice", "ionice", "stdbuf", "timeout", "time",
    "unbuffer", "eatmydata", "catchsegv", "torsocks",
}  # `builtin`/`command` are the shell twins that run a following builtin/command (`builtin eval git
   #  push`); both optionless-for-our-purposes → the launcher step-over lands on the real command.
# Shells that run a command STRING passed to `-c` (`bash -c "git push"`). The string is itself a
# command line, so `_classify` re-scans it with the full segment splitter (catching `sh -c 'env git
# push'` too). `_shell_c_command` models the SIMPLE `-c`/`+c` flag-cluster forms and bails to the
# residual on the value-consuming `-o`/`-O` forms rather than guess the command position. Privileged
# positional-arg shell forms (`su -c`, `runuser -c`, `sg -c`) are the documented residual.
_SHELL_LAUNCHERS = {"bash", "sh", "dash", "zsh", "ksh", "ash", "mksh"}
# Shell RESERVED WORDS / grouping tokens that can prefix a *literal* command within one segment and
# still run it: `! git push` (negation), `{ git push; }` (group), `if git push; then …`,
# `while git push; do …`, `until git push; …`. These are shell keywords, not external binaries, so
# they never reach `_LAUNCHERS`; without stepping over them `_classify` anchors `exe` on `!`/`{`/`if`/
# … , matches nothing, and defers — a no-privilege disarm of the WHOLE deny set, the exact class
# already closed for `env`/`sudo`/`bash -c`. They carry no option grammar, so a leading run of them
# is skipped unconditionally. `time` is deliberately NOT here — it takes options (`time -p git push`)
# and is handled as a `_LAUNCHERS` binary instead. Body keywords that head their own post-`;` segment
# (`then`/`do`/`else git push`) are skipped the same way when that segment is scanned.
_SHELL_KEYWORD_PREFIXES = {
    "!", "{", "}", "if", "then", "elif", "else", "fi",
    "while", "until", "do", "done", "for", "case", "esac", "select", "in", "coproc",
}
# A shell NAME/identifier — the optional coprocess name in `coproc NAME <compound-command>`, which
# sits between the (skipped) `coproc` keyword and a compound-command opener (`{`/`if`/…). Skipped so
# `coproc worker { git push; }` lands on the real `git`, not the name. (`[[`, `function` are
# deferred/non-command constructs; a function BODY runs only when the function is later called — the
# documented indirect-wrapper residual.)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# `eval` concatenates its arguments and re-parses the result as a command line, so a fenced verb hides
# inside them whether quoted (`eval "git push"`) or not (`eval git push`). It is re-scanned via the
# JOINED args (a plain step-over fails: the quoted form is one token whose basename isn't `git`).
_EVAL_BUILTINS = {"eval"}
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
    current = git_state.current_branch(selectors)
    if not current or current == "HEAD":
        return "merge while the current branch can't be confirmed non-default (fail-deny)"
    default = git_state.default_branch(selectors)
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


def _cluster_denies(token: str, deny: str, value_stop: str) -> bool:
    """True iff a short-option token carries a denied letter, parsed the way git parse-options does.

    git clusters short booleans and lets the FIRST VALUE-TAKING letter consume the token's
    remainder as its attached value (`git switch -fCmain` = `-f` + `-C main`; `git switch -cnew` =
    `-c new`). So a left-to-right scan is the only correct reading: a letter in `deny` before any
    value-consumer denies; a letter in `value_stop` ends the scan (everything after is that option's
    VALUE — so a branch NAME glued to `switch -c`/`checkout -b`/`branch -u`, e.g. `-cFooCase`, can't
    false-deny); a non-alphabetic char means this isn't a pure option cluster (`-u=x`) and the token
    is left to the exact-match checks. `value_stop` is per-subcommand: verified against git 2.47.3,
    `git branch -c/-C` take POSITIONAL names (so `c` is NOT a value-stop for branch — only
    `u`=--set-upstream-to), whereas `switch -c`/`checkout -b`/`-t` and `worktree add -b` take
    attached values. Long options are matched by `_long_opt_matches`, not here."""
    if len(token) < 2 or not token.startswith("-") or token.startswith("--"):
        return False
    for ch in token[1:]:
        if ch in deny:
            return True
        if ch in value_stop:
            return False
        if not ch.isalpha():
            return False
    return False


def _long_opt_matches(token: str, dangerous: tuple[str, ...], safe_exact: tuple[str, ...] = ()) -> bool:
    """True iff a `--long` token is (an unambiguous abbreviation of) a dangerous long option.

    git accepts any UNAMBIGUOUS PREFIX of a long option and an attached `--opt=value`, so exact
    full-spelling matching (`"--force" in rest`) misses `--forc`/`--del`/`--force-create=x` — all of
    which really act (git 2.47.3). Strip a `=value` suffix and treat the token as dangerous when its
    name is a non-empty prefix of a dangerous name. An AMBIGUOUS prefix errors out in git (a no-op),
    so denying it costs nothing; a prefix that resolves to a SAFE option isn't a prefix of any
    dangerous name, so it stays allowed. `safe_exact` carves out a COMPLETE safe option that is
    itself a prefix of a dangerous one — `switch --force` (discard-changes) is a prefix of
    `--force-create`, and git binds an exact full match to the shorter option, so `--force` must
    stay allowed while `--force-create`/`--force-cr`/`--force-create=x` deny."""
    if not token.startswith("--"):
        return False
    name = token[2:].split("=", 1)[0]
    if not name or name in safe_exact:
        return False
    return any(d.startswith(name) for d in dangerous)


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
    # Step over leading shell reserved words / grouping tokens (`!`, `{`, `if`, `while`, `coproc`, …):
    # they run the following literal command in the same segment, so a fenced verb hides one token
    # past them (`! git push`, `{ git push; }`, `if git push; then …`, `coproc git push`). They are
    # keywords, not launchers, and carry no options, so a leading run is skipped before `exe` is
    # anchored. The one exception is the `coproc NAME <compound>` name: skip an identifier that sits
    # between a just-skipped `coproc` and a compound-command opener (`coproc worker { git push; }`),
    # so the name is not mistaken for the executable.
    while i < len(tokens):
        if tokens[i] in _SHELL_KEYWORD_PREFIXES:
            i += 1
            continue
        if (i > 0 and tokens[i - 1] == "coproc" and _IDENT.match(tokens[i])
                and i + 1 < len(tokens) and tokens[i + 1] in _SHELL_KEYWORD_PREFIXES):
            i += 1  # the coprocess NAME before its compound command
            continue
        break
    if i >= len(tokens):
        return None
    exe = os.path.basename(tokens[i])
    args = tokens[i + 1 :]

    # `eval` re-parses its concatenated args as a command line — re-scan the JOINED args (not a token
    # step-over: `eval "git push"` is a single token whose basename isn't `git`). Same disarm class
    # as `bash -c "git push"`, which is already re-scanned.
    if exe in _EVAL_BUILTINS and _depth < _MAX_LAUNCHER_DEPTH:
        return _dangerous(" ".join(args), yolo, cwd, _depth + 1, _unmodeled_sel) if args else None

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
    # Direct ref MOVES that repoint/rename/overwrite an existing ref WITHOUT the porcelain verbs
    # above — the same trust-anchor-integrity rationale as `symbolic-ref`/`remote set-head` below,
    # and the specific forge the P0.13 base-pin depends on being closed: `git branch -f main <sha>`
    # / `update-ref refs/heads/main <sha>` / `switch -C main` move the default branch the frozen-
    # oracle gate reads as its loop-immutable baseline. Denied UNCONDITIONALLY (any branch, like the
    # branch-delete above): a loop integrates only via `--no-ff` merges into non-default branches, so
    # force-moving/renaming/overwriting ANY ref is outside its model. `-m`/`-M` rename (old name
    # vanishes), `-C` force-copies over an existing ref; `u` (--set-upstream-to) is branch's only
    # value-consumer, so it is the cluster value-stop. Long forms match by unambiguous prefix.
    if sub == "branch" and (
        any(_long_opt_matches(t, ("force", "move")) for t in rest)
        or any(_cluster_denies(t, "fmMC", "u") for t in rest)
    ):
        return "force-move, rename, or overwrite a branch ref (git branch -f/-m/-M/-C)"
    if sub == "update-ref":
        # No read form exists — update-ref is pure ref-mutation plumbing (incl. -d and --stdin).
        return "move or delete a ref directly (git update-ref)"
    # switch/checkout force-(re)create a branch at an arbitrary commit (`-C main`/`-B main` clobber
    # an existing ref). `-C`/`-B` take an ATTACHED value (`-Cmain`) and cluster after booleans
    # (`-fCmain`); the lowercase creators `-c`/`-b` and `-t` consume the remainder as a value, so a
    # capital in `-cFooCase`/`-bFix` must not false-deny. `switch --force` (discard-changes) is a
    # complete safe option that is a prefix of the dangerous `--force-create`, so it is carved out;
    # `checkout` has no `--force-create` long option (git 2.47.3: "unknown option force-create").
    if sub == "switch" and (
        any(_long_opt_matches(t, ("force-create",), ("force",)) for t in rest)
        or any(_cluster_denies(t, "C", "ct") for t in rest)
    ):
        return "force-recreate a branch at an arbitrary commit (git switch -C)"
    if sub == "checkout" and any(_cluster_denies(t, "B", "bt") for t in rest):
        return "force-recreate a branch at an arbitrary commit (git checkout -B)"
    # position-aware (like `remote set-head` / `gh pr merge` below), NOT a bare `"remove" in rest`
    # membership — else `git worktree add ../wt remove` (a branch/path literally named `remove`) would
    # be a false deny. Only the `remove` SUBCOMMAND (first positional) is the destructive one.
    if sub == "worktree" and _subcommand_path(rest, set(), 1) == ["remove"]:
        return "remove a worktree (git worktree remove)"
    # `git worktree add -B <branch>` force-resets an existing branch ref (git 2.47.3 verified) — the
    # same ref clobber as `branch -f`, spelled through worktree. `-b` only CREATES (fails if the
    # branch exists), so it stays allowed; `b` is the value-stop (consumes the new-branch name), `B`
    # denies even attached (`-Bmain`) or clustered after `-f` (`-fB`).
    if sub == "worktree" and "add" in rest and any(_cluster_denies(t, "B", "b") for t in rest):
        return "force-reset a branch ref via worktree (git worktree add -B)"
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
