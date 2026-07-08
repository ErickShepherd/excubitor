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

`guard-loop-vc.py` and `guard-self-integrity.py` both read the `Bash` tool's command **string**. They
split it into segments on shell separators (`;`, `|`, `&`, newline) **and** on subshell /
command-substitution boundaries (`(`, `)`, backtick) — honoring those boundaries **only outside
quotes** (a separator inside single/double quotes is literal text, so a dangerous token quoted in an
argument is not falsely promoted to its own command) — then `shlex.split` each segment and inspect the
resulting **literal tokens** — a git subcommand, or a path's basename. They do **not** run a shell, so
any construct that only resolves to the dangerous token *after* bash expands it is invisible to them.

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
`worktree remove`, `gh pr merge`, and (because they repoint the default-branch trust anchor)
`remote set-head` / `symbolic-ref` writes. It is **not** a complete deny-set over the git surface, and
does not try to be — that is the deny-set-completeness race the crux refuses. The following verbs are
destructive-or-history-rewriting and **left open by design**, documented here and pinned ALLOW in
`hooks/tests/test_guard_loop_vc.py::TestUnhandledGitVerbs`:

| Verb | What it can do | Why it's left open |
|---|---|---|
| `git update-ref -d <ref>` | delete a ref (incl. a branch) via plumbing | plumbing; not on the loop's normal path; parking it invites chasing every plumbing verb |
| `git reflog expire --expire=now --all` | drop the reflog (the recovery net others rely on) | rare; only matters combined with another destructive act |
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

## CLOSED — self-integrity holes (fixed because they protect a guard's own judge)

These *did* work and no longer do — they are the closures the crux does call for, because each let the
loop rewrite the judge that constrains it.

| Was | Now | Fixed by |
|---|---|---|
| An armed loop could `touch .claude/allow-default-branch`, or edit/delete the guard scripts or the `.claude/settings.json` hooks block, to disarm the fence | Denied while `CLAUDE_LOOP_GUARD` is set (file tools **and** Bash) | `guard-self-integrity.py` (TELOS-007/008) |
| `git remote set-head` / `git symbolic-ref <name> <ref>` / `-d` could repoint `refs/remotes/origin/HEAD`, the trust anchor both guards read | Denied in both modes; the read form of `symbolic-ref` stays allowed | `guard-loop-vc.py::_classify` (TELOS-009) |
| A dangerous verb or kill-switch glued inside an *unquoted* subshell / command substitution — `(git push)`, `$(rm PATH)`, `` `rm PATH` `` — slipped past the segment splitter | Denied; segments now split (quote-aware) on `(`, `)`, and backtick | both guards' `split_segments()` |

## Reporting a bypass

Finding a bypass **not** listed here is a genuine contribution — it is the difference between an honest
limit and a hidden one. Treat it as a security report (see [`SECURITY.md`](SECURITY.md) for what counts
and how to report): if it lets a loop **disarm a guard's own integrity** it is a bug we will close; if
it is one more instance of the enumerated seatbelt limits above, we will add it here (and pin it)
rather than pretend to have closed the class.
