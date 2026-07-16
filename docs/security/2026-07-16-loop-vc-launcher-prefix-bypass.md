# Security advisory: loop-VC guard exec-prefix launcher bypass

- **Date:** 2026-07-16
- **Component:** `hooks/guard-loop-vc.py`
- **Class:** false safety claim / guard bypass (SECURITY.md category 2)
- **Fixed in:** commit `17d568d` (merge of `fix/loop-vc-launcher-prefix-bypass`)
- **Affected:** every revision before that commit
- **Severity:** high **for the workflow that opts into the guard** (an armed autonomous loop);
  none for anyone not using `CLAUDE_LOOP_GUARD`, which is off by default.

## Summary

`guard-loop-vc.py` is the seatbelt that stops an autonomous loop (`CLAUDE_LOOP_GUARD` set) from
performing an irreversible version-control act — `git push`, `git merge`, `git branch -d/-D`,
`git reset --hard`, non-dry-run `git clean`, `git worktree remove`, `gh pr merge`. It classified a
`Bash` command by checking whether the command's **executable** was literally `git` or `gh`.

Because of that, **any exec-prefix launcher hid the fenced verb one token deeper and the guard
deferred** — allowing the very acts it exists to block:

```
env git push origin main         # allowed (should deny)
sudo git branch -D main          # allowed
bash -c "git push"               # allowed
```

`env` is POSIX and needs no privilege, so a single prefix word defeated the **entire** deny set. This
falsified the guard's headline claim (telos `TELOS-001`, "the conservative loop fence denies the whole
irreversible VC set"). It was **not** one of the accepted residuals in
[`KNOWN-BYPASSES.md`](../../KNOWN-BYPASSES.md): those are shell-*expansion* evasions (`git pus{h,}`,
`$VAR`), whereas this was a failure to resolve the real executable — every token was literal.

The sibling guard `guard-self-integrity.py` was **not** affected: it scans every token of a command
for kill-switch paths, so a launcher prefix never hid anything from it.

## Impact

An armed loop — or anything running under the guard — could push, merge, delete branches, hard-reset,
`git clean`, remove worktrees, or merge a PR by prefixing the command with `env`/`sudo`/`nice`/
`timeout`/`bash -c`/etc. In the branch-first, stop-and-surface workflow the guard underpins, that is
the unattended-bad-merge / unintended-publish failure the guard is meant to prevent.

This is a **capability** gap in an opt-in safety fence, not a data-exfiltration or
remote-code-execution bug: exploiting it requires already running commands in the guarded environment.
The concern is that an oversight control silently did less than it claimed.

## The fix

`_classify` now steps over an **enumerated set of exec-prefix launchers** and re-classifies the
command they delegate to (recursing for chains like `sudo nice git push`), and re-scans a simple
shell `-c`/`+c` command string (`bash -c "git push"`) as the command line it is. Short-option
**clusters** are walked letter-by-letter, so a value option clustered behind other flags
(`env -vu FOO git push`) still consumes its value instead of being mistaken for the command.

The design is **soundness-first**: a launcher is recognized (and its bypass therefore closed) only
when its separate-value option grammar is small, stable, and confidently complete — so a value token
is never misread as the command. Recognized: `env`, `command`, `exec`, `nohup`, `setsid`, `sudo`,
`doas`, `nice`, `ionice`, `stdbuf`, `timeout`, `time`, `unbuffer`, `eatmydata`, `catchsegv`,
`torsocks`, and the plain shells' simple `-c`.

The change is executable resolution over literal tokens — **not** a shell reimplementation. It was
verified end-to-end and hardened across eight independent adversarial review passes, each of which
found and fixed a further real gap (culminating in the clustered-short-option parser). The full guard
test suite passes; the closed bypass is recorded in `KNOWN-BYPASSES.md` (CLOSED table) and pinned by
`hooks/tests/test_guard_loop_vc.py::TestLauncherPrefix`.

## Residual posture (what is still deliberately open)

Consistent with this project's thesis — *document the limit, don't forge a claim* — a set of related
bypasses remain **accepted residuals**, enumerated and test-pinned as *allowed* in
[`KNOWN-BYPASSES.md`](../../KNOWN-BYPASSES.md). They are **not** closed, and a command using one will
still get past `guard-loop-vc.py`:

- launchers whose option grammar cannot be confidently/completely modeled — `unshare`, `numactl`,
  `cpulimit`, `xargs`, `strace`, `ltrace`, `proot`, `firejail`;
- launchers with a leading positional of their own — `taskset <mask>`, `chrt <prio>`, `flock <file>`;
- privileged shell strings with a different arg grammar — `su -c`, `runuser -c`, `sg -c`;
- a shell `-c` whose option vector carries a value-consuming `-o`/`-O` or `--rcfile`/`--init-file`
  (`bash -o monitor -c "git push"`), and `env -S 'git push'`;
- a launcher chain deeper than the recursion cap;
- the pre-existing shell-expansion evasions (brace/glob/`$VAR`, live command substitution inside
  double quotes, wrapper scripts, aliases).

**Why they are left open:** closing the class fully means recognizing every launcher on every host and
parsing each one's option/positional grammar (and, for the expansion cases, running the shell) — the
completeness race the project explicitly refuses. Each remaining residual requires *deliberate*
evasion; the paths a drifting loop would actually take (`git push`, `env git push`) are now fenced.

**The honest bound:** `guard-loop-vc.py` is a **seatbelt for the default path, not a sandbox**. A
command-string parser cannot be airtight, and the residual list above is enumerated from review, not
proven exhaustive — seven of the eight review passes each surfaced a form not previously anticipated.
A workflow that needs a hard, adversary-proof guarantee needs an OS-level sandbox beneath the agent
(the Tier-3 control named in [`THREAT-MODEL.md`](../../THREAT-MODEL.md)), which excubitor's hooks do
not provide.

## Remediation

Update your excubitor checkout to `17d568d` or later:

```bash
cd <your excubitor clone>
git pull
```

The installed hooks are symlinks into the clone (`scripts/install.sh`), so a pull updates the live
guard with no reinstall. If you vendored a copy of `hooks/guard-loop-vc.py`, replace it. No settings
or configuration change is required.

## Credit

The underlying issue was surfaced by an external LLM review of the repository. The fix, the residual
enumeration, and the eight-pass adversarial hardening were done with Claude (Fable 5).
