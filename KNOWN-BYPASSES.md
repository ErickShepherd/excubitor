# Known bypasses

These guards are **seatbelts for the default path, not sandboxes** — their own docstrings say so, and
this file is where we mean it in the open. Every entry below is a way to get past a guard that we
**know about and have chosen not to close.** They are enumerated (and, where practical, pinned by an
executable test) rather than quietly hoped-away, because for a project whose thesis is *an agent
cannot forge its own proof of safety*, a hidden limit is itself a forged claim.

The discipline is deliberate: **document the limit, don't chase it.** The only closures worth making
are the ones that protect a guard's **own integrity** (a judge the model can rewrite is not a judge).
Everything else — completeness against the full git surface, against every shell expansion — is a
losing race whose "fix" (reimplement the shell; deny every metacharacter) costs more than the gap it
closes. So we write it down instead.

Each bypass is classed:

- **ACCEPTED** — a residual we will not close; pinned by a bidirectional test (the pin fails if the
  behavior changes in *either* direction, so a silent scope change is impossible).
- **CLOSED** — listed for the record because it *used* to work; a regression test now proves it
  doesn't.

## How the guards parse (why these exist)

Since the C1 model-blind extraction, this parsing logic lives in the **shared core** —
`excubitor/core/policies/loop_vc.py` and `excubitor/core/policies/self_integrity.py` — and the shipped
`hooks/guard-loop-vc.py` / `guard-self-integrity.py` are thin Claude Code adapters over it (the generic
`runtime/spec_adapter.py` reaches the same core). So **every residual below is a property of the core
and travels with every adapter**, not just the Claude Code hook — the seatbelt-not-sandbox nature of the
parse is host-independent. The guard filenames below name the shipped entry points; the behavior they
describe is the core's.

`guard-loop-vc.py` and `guard-self-integrity.py` both read the `Bash` tool's command **string**. They
split it into segments on shell separators (`;`, `|`, `&`, newline) **and** on subshell /
command-substitution boundaries (`(`, `)`, backtick) — honoring those boundaries **only outside
quotes** (a separator inside single/double quotes is literal text, so a dangerous token quoted in an
argument is not falsely promoted to its own command) — then `shlex.split` each segment and inspect the
resulting **literal tokens** — a git subcommand, or a path's basename. They do **not** run a shell, so
any construct that only resolves to the dangerous token *after* bash expands it is invisible to them.

`guard-loop-vc.py` additionally steps over an **enumerated set of exec-prefix launchers** (`env`,
`command`, `exec`, `nohup`, `setsid`, `sudo`, `doas`, `nice`, `ionice`, `stdbuf`, `timeout`, `time`,
`unbuffer`, `eatmydata`, `catchsegv`, `torsocks`): these run their argument list
as a new command, so it resolves the *delegated* executable (recursing for a chain like
`sudo nice git push`) instead of anchoring on the launcher's own basename. A shell running a simple
`-c`/`+c` command string (`bash`/`sh`/`dash`/`zsh`/`ksh -c "git push"`) is re-scanned as the command
line it is. Every token is still literal — this is executable resolution, not shell expansion — so the
shell-expansion residuals below apply unchanged on top of it. The set holds launchers whose
separate-value option grammar is **small, stable, and confidently complete** (so a value token is
never misread as the command); it is **enumerated, not exhaustive** — an exec-prefix outside it,
including a launcher with a large or version-growing option grammar, is an accepted residual (below).

## ACCEPTED — shell word-expansion evades literal-token matching

Both guards match a *literal* token. A word expansion that mutates the token before bash resolves it
is not the token the guard sees, so it defers. These are real disarms at the shell and out of scope
here — closing them means reimplementing bash expansion or denying every metacharacter (which would
break ordinary globbing and lose more than it gains).

`guard-loop-vc.py` — the dangerous git subcommand is hidden from `_classify`
(pinned: `hooks/tests/test_guard_loop_vc.py::TestGuardLoopVC::test_accepted_residuals_still_allow`):

| Bypass | What bash runs | Why it slips |
|---|---|---|
| `git pus{h,} origin main` | `git push origin main` | brace expansion; token seen is `pus{h,}` |
| `git merge{,} --no-ff topic` | `git merge merge --no-ff topic` | brace expansion; token seen is `merge{,}` |
| `git pus*h origin main` | (glob) | token seen is `pus*h`, never `push` |
| `G=push; git $G origin main` | `git push origin main` | subcommand in a variable; token seen is `$G` |
| `git commit -m "$(git push)"` | `git push` | live command substitution **inside double quotes** (see below) |

`guard-self-integrity.py` — the kill-switch **basename** is hidden from the matcher
(pinned: `hooks/tests/test_guard_self_integrity.py::TestAcceptedResiduals::test_documented_bypasses_still_allow`):

| Bypass | What bash touches | Why it slips |
|---|---|---|
| `rm hooks/guard-loop-vc.p*` | the real guard script | glob; basename seen is `guard-loop-vc.p*` |
| `rm hooks/guard-loop-vc.p?` | the real guard script | single-char glob |
| `rm .claude/settings.jso{n,}` | `.claude/settings.json` | brace expansion → `settings.json settings.jso` |
| `rm .claude/allow-default-branch{,}` | the disarm marker | brace expansion |
| `B=allow-default-branch; rm .claude/$B` | the disarm marker | **basename** in a variable |
| `python3 -c "open('.claude/allow-default-branch','w')"` | the disarm marker | interpreter builds the path at runtime |
| `echo "$(rm hooks/guard-loop-vc.py)"` | the real guard script | live command substitution **inside double quotes** (segments split only outside quotes — see below) |

> **Near-miss, for the record:** `F=.claude/allow-default-branch; rm $F` is **DENIED**, not allowed —
> the *assignment* token's own basename is `allow-default-branch`, which the guard catches even though
> `rm $F` alone would slip. Only hiding the **basename** in the variable evades it.

### A note on the quote-aware split (why the two "inside double quotes" rows exist)

The segment splitter honors `(`, `)`, and backtick **only outside quotes**. That is a deliberate
trade: it eliminates a *false deny* (a dangerous verb or a kill-switch path quoted in an ordinary
commit message — `git commit -m "document the (git push) bypass"` — must not be blocked, and this
repo's own history is full of such strings), at the cost of *under-blocking* a live command
substitution that sits **inside double quotes** (`"$(git push)"`), which bash would actually execute.
The unquoted forms — `(git push)`, `$(git push)`, `` `git push` `` — stay caught. We took the
under-block over the false deny: a false deny trips ordinary work and gets the guard uninstalled,
while the quoted-substitution under-block is one more instance of the "resolves only after the shell
runs" residual this whole file documents. Pinned in both suites' `TestAcceptedResiduals` /
`ACCEPTED_RESIDUALS`.

## ACCEPTED — an exec-prefix outside the recognized launcher set

`guard-loop-vc.py` steps over an **enumerated** set of exec-prefix launchers (see *How the guards
parse*), so `env git push`, `sudo git branch -D main`, `nice -n 5 git merge`, `timeout 60 git push`,
`unbuffer git push`, and `bash -c "git push"` are all caught — as are leading shell reserved
words/grouping tokens (`! git push`, `{ git push; }`, `if git push; then …`, `while git push; do …`,
`coproc git push`) and the `eval`/`builtin` builtins (`eval git push`, `builtin eval git push`),
which are stepped over / re-scanned the same way (CLOSED table). The set is a curated list of launchers
whose invocation grammar is **small, stable, and confidently modeled** — it is **not a claim to
recognize every launcher on the system, nor to fully parse a launcher with a large or version-growing
option set.** An exec-prefix *outside* the set still runs the fenced verb one token deeper and defers;
this is the same residual class as an indirect wrapper script, pinned ALLOW in
`hooks/tests/test_guard_loop_vc.py::TestLauncherPrefix::test_launcher_residuals_still_allow`:

| Bypass | Why it's outside the set |
|---|---|
| `taskset 0x3 git push` / `chrt 10 git push` / `flock /tmp/lock git push` | a **leading positional of the launcher's own** (cpu mask / RT priority / lock file) sits before the command; the guard lands on it, not `git` |
| `unshare git push` / `numactl -N 0 git push` / `cpulimit -l 50 git push` / `strace git push` / `ltrace git push` / `proot -r / git push` | a **large or version-growing separate-value option grammar**: modeling it half-way lets the newest option slip and mis-read its value as the command — the exact "claimed catch that slips" failure this fence must avoid — so it is documented, not claimed. (Enumerating every value-option of every such tool completely is the per-tool-grammar chase the crux refuses.) |
| `xargs git push` / `xargs -i git push` / `xargs --process-slot-var V git push` | **an optional-arg option grammar** the consume-next-token model cannot represent: `-i`/`-e`/`-l`/`--replace` take an *attached-only optional* value (so the next token is NOT their value), while `--process-slot-var` *is* separate-value and grows the set — no single "consume next token or not" rule is correct for both, so `xargs` is documented, not modeled |
| `firejail git push` / `firejail --whitelist /x git push` | firejail's option surface is **large enough that a separate-value option cannot be confidently ruled out** (most are attached `--opt=val`, but the set is big and grows); rather than half-model it and risk a slip, it is documented, not claimed |
| `su -c 'git push'` / `runuser -c 'git push'` / `sg grp -c 'git push'` | a **privileged shell running a `-c` string** with a different arg grammar than the plain `bash`/`sh -c` that *is* re-scanned; also needs privilege |
| `bash -o monitor -c 'git push'` / `bash -co monitor 'git push'` / `bash --rcfile f -c 'git push'` | a shell `-c` whose option vector carries a **value-consuming `-o`/`-O`** (or a `--rcfile`/`--init-file`) that eats a separate token and shifts the command position; the simple `-c`/`+c` flag-cluster forms *are* caught, this interleaved form is not |
| `env -S 'git push origin main'` | `env -S` **re-splits one string arg** — an expansion, like the `$VAR`/brace cases above |
| `sudo … ×N git push` (N > recursion cap) | a launcher **chain deeper than `_MAX_LAUNCHER_DEPTH`** (absurd to type; bounded backstop against pathological input) |

Closing the whole class means either recognizing every launcher binary on every host, or parsing each
one's positional/option grammar (and, for `-S` and the interleaved `-c` strings, expanding) — the
deny-set / shell-reimplementation race the crux refuses. The recognized set covers the common,
no-privilege prefixes; the rest is enumerated here, not chased. **Adding a launcher to the recognized
set is the right move when its separate-value option grammar is small, stable, and confidently
complete** — do that and move its row to `TestLauncherPrefix.LAUNCHER_DENY`, rather than growing this
table or half-modeling a launcher whose newest option would then slip.

## ACCEPTED — the guards see only what the runtime hands them

Both guards run as `PreToolUse` hooks on specific tools. They see nothing outside that surface:

- A `post-commit` / `post-merge` git hook, or a filesystem watcher, can fire an external side effect
  the guard never intercepts (YOLO mode presumes a hook-clean working copy).
- `guard-loop-vc.py` classifies `git`/`gh` invocations. A different VCS binary, a wrapper script, or
  a shell **alias** that ultimately calls git is not recognized.
- `guard-self-integrity.py` fences the file tools and `Bash`. It does **not** fence the `Read` tool —
  by design: reads of a kill-switch are harmless, and leaving reads open is what keeps the seatbelt
  wearable (you can still inspect a guard you cannot rewrite).
- A rename of a **parent directory** of a kill-switch, or a `find ~/.claude -delete`, reaches the file
  without ever naming its basename as a token.

## ACCEPTED — dangerous git verbs outside the fenced set

`guard-loop-vc.py` fences the irreversible VC set an unattended loop actually reaches on the
stop-and-surface / YOLO paths: `merge`, `push`, `branch -d/-D`, `reset --hard`, non-dry-run `clean`,
`worktree remove`, `gh pr merge`, and — because they repoint/rename/overwrite a ref (the
default-branch trust anchor that guard-default-branch.py and the ralph-loop frozen-oracle base pin
read) **without** the porcelain verbs above — the direct ref moves `branch -f/-m/-M/-C`, `update-ref`,
`switch -C`, `checkout -B`, `worktree add -B`, `remote set-head`, and `symbolic-ref` writes. It is
**not** a complete deny-set over the git surface, and does not try to be — that is the
deny-set-completeness race the crux refuses. The following verbs are destructive-or-history-rewriting
and **left open by design**, documented here and pinned ALLOW in
`hooks/tests/test_guard_loop_vc.py::TestUnhandledGitVerbs`:

| Verb | What it can do | Why it's left open |
|---|---|---|
| `git reflog expire --expire=now --all` | drop the reflog (the recovery net others rely on) | rare; only matters combined with another destructive act |
| `git fetch <path> +<src>:<ref>` (incl. `refs/remotes/*`) | move a ref — even a remote-tracking one — via a local-path refspec, no network/credentials | a fetch refspec retargets a ref without a fenced verb, and a direct `.git/refs` write goes below any Bash-parsing hook entirely; both are the irreducible "a loop with repo write access can move any ref" residual. The real backstop is DRIVER ISOLATION (run the loop in a worktree/container with no write access to the real refs) or an out-of-band base OID, NOT a per-verb fence |
| `git stash drop` / `git stash clear` | discard stashed work | stashes are not the loop's committed line of work |
| `git tag -d <tag>` | delete a tag | local tag; recreatable; not an integration act |
| `git filter-branch …` / `git rebase …` | rewrite history on the current branch | rewrites the *current* branch only — like `reset`, within the "own branch" seatbelt scope until a push (which IS denied) would publish it |
| `git gc --prune=now` | prune unreachable objects | housekeeping; only destructive after something already unlinked the objects |
| `git checkout -- <path>` / `git restore <path>` | discard *uncommitted* changes to tracked files | discards only un-committed work, like `reset --soft`'s neighbor; the loop's *committed* line stays intact |

The honest framing: these lose *local, mostly-recoverable, not-yet-integrated* state. The acts the
harness exists to prevent — an unattended **integration** or **publication** (merge into a shared
branch, push, branch delete) — are the ones fenced. If a specific loop genuinely needs one of these
verbs fenced, add it to `_classify`; the general posture is *don't hand the loop a capability it
doesn't need*, not *enumerate every git verb*.

The same is true of **`gh`**: only `gh pr merge` (a server-side integration) is fenced. Other
write-capable `gh` verbs — `gh repo sync` (can fast-forward a remote branch), `gh release create`,
`gh api` with a mutating method — are **not** fenced, for the same reason: the loop shouldn't be
handed a `gh` capability it doesn't need. Documented here so the residual is enumerated, not implied.

## ACCEPTED — leak_check trusts its owner-authored `--private-tokens` regexes

`skills/leak-guard/leak_check.py` runs each `re:` rule from the `--private-tokens` file against the
(untrusted) scanned content. That file is **owner-authored, trusted input** — as trusted as the code it
guards. A *pathological* caller regex (catastrophic backtracking, e.g. `re:(a+)+$`) can therefore be
driven to hang by crafted content — a **self-inflicted ReDoS**. The built-in secret patterns are all
linear and ReDoS-safe; the residual is solely the owner's own `re:` rules. A stdlib scanner cannot
interrupt a Python regex mid-backtrack without a per-match subprocess sandbox — out of proportion for
trusted input — so the boundary is *documented* (keep your `re:` rules linear; see the module LIMITS)
rather than sandboxed. See `skills/leak-guard/leak_check.py::load_private_patterns`.

## ACCEPTED — default-branch detection on a local-only, non-standard trunk

On a local-only repo with a trunk that is neither `main` nor `master` and no `origin/HEAD`, the
default-branch heuristic is best-effort. This is bounded, not open: `main`/`master` are
hardcode-protected regardless, YOLO mode fails **deny** on ambiguity, and the only act ever permitted
into the mis-resolved branch is a revertable `--no-ff` merge (push stays denied). See
`hooks/guard-loop-vc.py::_default_branch` and `TELOS-006`.

## ACCEPTED — guard-default-branch fences the direct file-edit tools, not Bash (R-06)

`guard-default-branch.py` is registered for `Edit|Write|NotebookEdit` only. Its enforceable claim is
therefore **"blocks the runtime's direct file-edit tools on the default branch"** — NOT "no file
mutations": a shell redirection, `sed -i`, a formatter, a generator, or `git apply` runs under the
`Bash` tool, which the registration never routes to this guard, and mutates the default branch
unimpeded. This is a *registration* boundary, not a parsing gap — the guard, handed a Bash payload,
would deny **every** command whose `cwd` is a protected repo (it falls back to `cwd` when there is no
file path), which is why registering it for `Bash` is not the fix: the honest alternatives are the
disruptive all-shell-deny or an OS-level sandbox, both declined (decision recorded 2026-07-16 in
`the build checklist`, R-06). A Bash-string *mutation parser* is not a
credible complete solution (see the expansion residuals above). Pinned bidirectionally in
`hooks/tests/test_guard_default_branch.py::TestR06RegistrationBoundary` — the matcher excludes
`Bash`, a shell mutation on the default branch succeeds (the residual, so the docs must change if the
boundary ever strengthens), and a direct `Edit` stays denied (the claim).

## ACCEPTED — guard-default-branch resolves symlinks but not hard links

`guard-default-branch.py` checks **both** the logical edit target's container and its
`realpath`-resolved container, so a **symlink** — a symlinked file, or a new file created through a
symlinked directory — can no longer launder an `Edit`/`Write` from a feature-branch repo into a
*different* repo checked out on its default branch (this was a real bypass, closed by R-03; pinned in
`hooks/tests/test_guard_default_branch.py::TestGuardSymlinkLaundering`). A **hard link**, however, is
indistinguishable from an ordinary file at the path layer — there is no link for `realpath` to
resolve — so a hard link whose inode is a tracked file in a protected repo is **not** caught. Closing
it means stat-ing inode/nlink and cross-referencing repositories on every edit, out of proportion for
a stdlib seatbelt. Likewise a **bind mount** or other kernel-level redirection that `realpath` does
not see is out of scope. Documented, not chased. See `guard-default-branch.py::_candidate_dirs`.

## ACCEPTED — the frozen-oracle gate binds authorship and bytes, not semantics

`run_frozen_oracle.py` (the YOLO permit-to-act gate) refuses a caller-supplied witness command (it
must appear in the anchor file's **base-tree blob** as a **whole authored unit** — a whole line or a
complete `verify:` suffix, so a *truncation* of an authored command earns no permit either — with
`--base` pinned to the **remote-tracking** default `refs/remotes/origin/<name>`), refuses an untrusted
executable (untracked in-repo — the `.venv/bin/python` class — or user-writable outside the repo,
including a resolved symlink target that lands outside the repo), and binds
conftest/runner-config/module-shadow companions into the frozen surface, executing under a sanitized
environment. What it deliberately does **not** verify:

- **A baseline-authored command's semantics.** A DoD author who writes `/bin/true <file>` (vacuous),
  or a launcher/delegating prefix (`env …`, a trusted wrapper), authored that oracle — the gate binds
  *who authored the command* and *what bytes ran*, not whether the oracle is adequate. Same class as
  the `verified-by: true` weak-witness residual above. Pinned bidirectionally in
  `skills/ralph-loop/tests/test_run_frozen_oracle.py::TestPermitBinding::test_baseline_authored_bin_true_is_green_accepted_residual`.
- **The content of a trusted interpreter's environment beyond the repo:** system site-packages of a
  root-owned interpreter, and sys.path shadowing from a directly-executed script's own directory,
  are outside the frozen surface (the `-m` repo-root shadow *is* checked, across every `-m` spelling —
  spaced, attached, or clustered).
- **The base OID's ultimate immutability — the DRIVER's job, not the gate's.** The pin resolves the
  remote-tracking default (`refs/remotes/origin/HEAD` → `refs/remotes/origin/<name>`), which RAISES
  THE BAR: the trivial local ref moves (`branch -f/-M/-C`, `update-ref`, `switch -C`, `checkout -B`,
  `checkout <default> && reset --soft`) are fenced or don't touch it, and a local-only default (no
  remote-tracking anchor at all) **fail-denies** rather than pin to a trivially-movable local ref. It
  is **not** absolute immutability, and the gate does not claim to be: a `git fetch <path>
  +<src>:refs/remotes/origin/<name>` (local-path, no credentials — verified ALLOWED by the guard) and,
  below any Bash-parsing hook, a direct `.git/refs` write can still retarget even the remote-tracking
  ref. Chasing those is the completeness race the guard refuses; the real guarantee is **driver
  isolation** — run the loop in a worktree/container with no write access to the real refs, or capture
  the default-branch OID out of band before launch and pass it as `--base <sha>`. This gate is
  defense-in-depth over that isolation, not a replacement for it. Pinned in
  `skills/ralph-loop/tests/test_run_frozen_oracle.py::TestBasePinRequiresPushProtectedAnchor`.
- **The gate's own invocation.** A misbehaving loop can still skip the gate or run it through a
  forged interpreter — the recipe-level honest limit that has always applied (the guard hooks cannot
  know which files are "the oracle"). YOLO narrows the trust placed in the loop; it does not
  eliminate it.
- A gate run **as root** refuses (every executable is then writable by the invoking user) — the safe
  direction, documented rather than special-cased.

## CLOSED — the frozen-oracle permit could be forged by a caller-supplied command or interpreter

Before the 2026-07-16 independent review, `run_frozen_oracle.py --verified-by '/bin/true
<tracked-test>'` returned GREEN without executing the frozen file (any tracked file argument was
collected as the frozen surface; the executable was silently dropped), and the real checklist
commands ran through the untracked, agent-writable `.venv/bin/python` — replacing the interpreter
forged the permit. Closed by the authorship/executable/surface/environment bindings above; the
reproductions are pinned in
`skills/ralph-loop/tests/test_run_frozen_oracle.py::TestPermitBinding`.

## ACCEPTED — the denial-telemetry log is editable by the agent it records

Every guard deny is appended to a local JSONL log (`hooks/_denial_log.py`; default
`~/.claude/excubitor/denials.jsonl`). That log is **observability, not evidence**: it lives on the
same disk the agent writes, and `guard-self-integrity.py` deliberately does **not** fence it — an
armed loop can edit or delete its own denial history. Fencing it would not protect the guards'
integrity (they deny identically whether the log exists or not, and the decision is flushed to the
harness *before* the log write), it would only add false-deny surface for a file nothing
load-bearing reads. Nothing in the trust story leans on the log; a consumer that needs
tamper-evident denial records needs a sink outside the agent's write reach, which is out of scope
for a stdlib guard set. Pinned bidirectionally in
`hooks/tests/test_denial_log.py::TestLogIsNotAKillSwitch` (armed loop touching the log is allowed;
the same command shape against a real kill-switch still denies).

## CLOSED — self-integrity holes (fixed because they protect a guard's own judge)

These *did* work and no longer do — they are the closures the crux does call for, because each let the
loop rewrite the judge that constrains it.

| Was | Now | Fixed by |
|---|---|---|
| An armed loop could `touch .claude/allow-default-branch`, or edit/delete the guard scripts or the `.claude/settings.json` hooks block, to disarm the fence | Denied while `CLAUDE_LOOP_GUARD` is set (file tools **and** Bash) | `guard-self-integrity.py` (TELOS-007/008) |
| `git remote set-head` / `git symbolic-ref <name> <ref>` / `-d` could repoint `refs/remotes/origin/HEAD`, the trust anchor both guards read | Denied in both modes; the read form of `symbolic-ref` stays allowed | `guard-loop-vc.py::_classify` (TELOS-009) |
| A loop could move the **default branch** with a direct ref move — `git branch -f/-m/-M/-C main`, `git update-ref refs/heads/main`, `git switch -C main`, `git checkout -B main`, `git worktree add -B main` — none of which touched the fenced porcelain verbs, so the ralph-loop frozen-oracle **base pin** (`--base main`, the "loop-immutable" baseline the P0.13 permit reads) was forgeable: move local `main` onto loop-authored state, then the anchor/freeze all read the loop's own tree → forged GREEN | Denied in both modes (any branch, clustered/attached/abbreviated spellings); the base pin now rests on a fence that actually holds | `guard-loop-vc.py::_classify` / `_cluster_denies` / `_long_opt_matches` (round-4 review) |
| A dangerous verb or kill-switch glued inside an *unquoted* subshell / command substitution — `(git push)`, `$(rm PATH)`, `` `rm PATH` `` — slipped past the segment splitter | Denied; segments now split (quote-aware) on `(`, `)`, and backtick | both guards' `split_segments()` |
| An **exec-prefix launcher** hid the fenced verb one token deeper — `env git push`, `sudo git branch -D main`, `nice git merge`, `timeout 60 git push`, `env gh pr merge 5`, `unbuffer git push`, `bash -c "git push"` — so the guard anchored on the launcher basename (`env`) and deferred, a trivial no-privilege disarm of the **whole** loop-vc deny set | Denied; `_classify` steps over an enumerated launcher set (and re-scans a simple shell `-c` string) and re-classifies the delegated command (an exec-prefix outside the set remains the ACCEPTED residual above) | `guard-loop-vc.py::_classify` / `_after_launcher` / `_shell_c_command` (TELOS-001) |
| A **shell reserved word / grouping token**, the **`eval`/`builtin` builtins**, or **`coproc`** hid the fenced verb one token deeper in the SAME segment — `eval git push`, `eval "git push"`, `{ git push; }`, `! git push`, `if git push; then :; fi`, `while git push; do …`, `coproc git push`, `coproc worker { git push; }`, `builtin eval git push` — so the guard anchored `exe` on the keyword/builtin (not an external launcher binary, so the launcher step-over never fired), matched nothing, and deferred. Same no-privilege disarm class as the launchers above; worked in both `=1` and `=yolo`. Found by a fresh post-merge security audit + its pre-merge re-review, 2026-07-16 | Denied; `_classify` skips a leading run of `_SHELL_KEYWORD_PREFIXES` (`!`,`{`,`}`,`if`,`then`,`elif`,`else`,`fi`,`while`,`until`,`do`,`done`,`for`,`case`,`esac`,`select`,`in`,`coproc` — plus the `coproc NAME` identifier before a compound opener) and re-scans `eval`'s JOINED args before anchoring `exe`; `builtin` joins `_LAUNCHERS` alongside its twin `command` (`time` stays a `_LAUNCHERS` binary — it takes options). Pinned in `TestShellKeywordAndEvalPrefix` | `guard-loop-vc.py::_classify` (post-merge audit) |
| A **repository selector** divorced YOLO branch detection from the repo a merge actually targets: `git --git-dir=/protected/.git --work-tree=/protected merge --no-ff topic` (git-accepted) and composed relative `-C sub1 -C sub2` were evaluated against the payload cwd, so an innocent feature-branch cwd waved a merge into another repo's **default** branch through | Modeled spellings (repeated/composed `-C`, `--git-dir`/`--work-tree`, separate and `=`-attached) resolve detection against the **target** repo; unmodeled selector spellings — attached `-C<path>` (git-rejected today; hardening), `GIT_DIR`/`GIT_WORK_TREE`/`GIT_COMMON_DIR` env assignments (same-segment prefix, `export`/`declare` in a preceding segment, or an assignments-only segment), launcher chdir options (`env -C/--chdir`, `sudo -D/--chdir`), and a preceding directory-changing segment (`cd`/`pushd`/`popd`, incl. the `builtin`/`command` prefixes) — **fail-deny** the YOLO merge rather than guess (the known cost: a *legitimate* merge spelled through one of those is also denied) | `guard-loop-vc.py::_classify` / `_yolo_merge_reason` (P0.14) |

## Reporting a bypass

Finding a bypass **not** listed here is a genuine contribution — it is the difference between an honest
limit and a hidden one. Treat it as a security report (see [`SECURITY.md`](SECURITY.md) for what counts
and how to report): if it lets a loop **disarm a guard's own integrity** it is a bug we will close; if
it is one more instance of the enumerated seatbelt limits above, we will add it here (and pin it)
rather than pretend to have closed the class.
