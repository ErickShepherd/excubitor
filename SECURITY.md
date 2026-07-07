# Security policy

Excubitor is a set of **safety fences for autonomous coding agents**. Its whole value is that its
guards do what they claim — so in this project, **a bypass of a guard is a security bug**, and an
overstated safety claim is too. This document says what counts as a vulnerability, what explicitly
does not, and how to report one.

## Threat model in one paragraph

The adversary is an **autonomous agent loop** — at worst a capable model optimizing to finish a task,
which may route around a check that stands between it and "done". The design docs under
`docs/design/` carry the full reasoning (start with `loop-yolo-verifiable-autonomy.md`). The guards are
**seatbelts for the default path, not a sandbox**: they intercept tool calls and parse command
strings, which is not an airtight boundary. That limit is stated openly, and the known ways past each
guard are enumerated in [`KNOWN-BYPASSES.md`](KNOWN-BYPASSES.md). This policy is about the gap between
what a guard *claims* and what it *does*.

## What is a vulnerability here

Report it if you find any of these:

1. **A self-integrity break** — a way for an armed loop (`CLAUDE_LOOP_GUARD` set) to **disarm a guard
   that constrains it**: write or repoint a kill-switch (`.claude/allow-default-branch`, a guard hook
   script, the `settings.json` hooks block) despite `guard-self-integrity.py`, or rewrite the
   `origin/HEAD` trust anchor despite the `remote set-head` / `symbolic-ref` denials. *A judge the
   model can rewrite is not a judge* — this is the one class we always treat as a bug to fix.
2. **A false safety claim** — a guard, a `telos` claim's `contract:`, the README, or `ARCHITECTURE.md`
   asserts a protection the code does not actually deliver (e.g. an "always denied" act that a plain,
   non-exotic invocation gets past, and that is *not* already listed in `KNOWN-BYPASSES.md`). A hidden
   limit is itself a forged claim, which is exactly what this repo exists to refuse.
3. **A fail-*closed* process bug** — a crafted tool payload that makes a guard **crash or exit
   non-zero** (wedging the tool it guards), violating the fail-open process contract. (Fail-*open* on
   unparseable input is intended; a crash is not.)
4. **A telos-audit forgery** — a way to make `telos_check.py` report a claim as DISCHARGED at the
   `witness` tier when its witness did not actually pass, or to make the strict parser silently accept
   a malformed record (a "never-silent-pass" violation).

## What is NOT a vulnerability (already-documented limits)

These are **known, accepted residuals** — please don't file them as new; the shell/git ones are
catalogued, with the reasoning, in [`KNOWN-BYPASSES.md`](KNOWN-BYPASSES.md), and the telos-witness one
is pinned in the audit's adversarial tests
(`skills/audit-telos/tests/test_adversarial_records.py`):

- **Shell-expansion evasions** of the command parsers — glob (`git pus{h,}`, `rm x.p*`), brace
  expansion, `$VAR` indirection, a live command substitution inside double quotes, an interpreter
  one-liner, a parent-directory rename. The guards match *literal tokens*; closing this class means
  reimplementing the shell.
- **Dangerous git verbs outside the fenced set** — `update-ref -d`, `reflog expire`, `stash drop`,
  `tag -d`, `filter-branch`, `rebase`, `gc --prune`, `checkout -- ` / `restore`. The fence covers the
  *integration/publication* set a loop reaches on its normal path, not every destructive verb.
- **Out-of-band side effects** the hook never sees — a `post-commit` git hook, a filesystem watcher, a
  git wrapper/alias, a different VCS binary.
- **Default-branch heuristic** on a local-only repo with a non-standard trunk (bounded: `main`/`master`
  are always protected, YOLO fails deny on ambiguity, only a revertable `--no-ff` merge is ever
  permitted).
- **A backed-but-weak witness** — the telos audit trusts a `verified-by` witness's exit code; it does
  not judge witness *quality*. An always-pass witness (`verified-by: true`) yields a DISCHARGED. This
  is by design (an in-record check the author controls can't grade the author's own witness); catching
  it is the job of an out-of-loop reviewer or a frozen oracle.

If you find a *new* member of one of these classes, a note (or a PR adding it to `KNOWN-BYPASSES.md`
with a pinning test) is welcome — but it is a documentation improvement, not a security fix.

## How to report

This is a small, single-maintainer project extracted from a private library; it has no dedicated
security inbox yet. Until one is published here:

- Open a **GitHub issue** for anything already public or already in `KNOWN-BYPASSES.md`.
- For a **self-integrity break or a false safety claim** (categories 1–2 above), which a live disarm
  recipe could make abusable, prefer **GitHub's private vulnerability reporting** ("Report a
  vulnerability" on the Security tab) if enabled, or contact the maintainer via the address on their
  GitHub profile, rather than opening a public issue with a working recipe. We'll confirm, fix, and
  credit you.

There is no bounty. There is genuine gratitude: a found bypass is the difference between an *honest*
limit and a *hidden* one, and honesty about limits is the entire brand.

## Scope

In scope: the guard hooks (`hooks/`), the telos audit spine (`skills/audit-telos/telos_check.py`), the
loop-discipline scripts (`skills/ralph-loop/scripts/`), and the safety claims made about them in the
docs and the telos record. Out of scope: the host agent runtime itself (Claude Code or any other), the
model, and anything the guards openly say they do not cover.
