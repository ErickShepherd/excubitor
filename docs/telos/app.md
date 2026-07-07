# agent-harness — telos record

The living intent record for this repo: the **motive** (why it exists), the **telos** (the purpose
it must keep fulfilling), and the falsifiable **claims** the `audit-telos` audit checks the code
against. This repo ships the tooling that reads this record — the record below is audited by
`skills/audit-telos/telos_check.py` in this same tree, witnesses and all (see
`.github/workflows/ci.yml`).

> **Evidence model.** A claim's `state: DISCHARGED` is honest only when *backed*: the parser
> demotes any `DISCHARGED` with no executable `verified-by` witness to **SUSPECT** at read time,
> and the audit runs each witness and trusts its exit code over any LLM judgment. Every claim
> below carries a witness for exactly that reason. See `docs/design/telos-evidence-tier.md`.

## Motive

An unattended agent loop ends in an irreversible act, and an LLM cannot be trusted to bless its
own "done" — self-preference bias means a loop that authors its own completion evidence produces
plausible-but-forged proof. The fences in this repo exist so that the irreversible tail of an
agent workflow is gated by things the model cannot forge: denied tool calls, frozen oracles, and
mechanically demoted overclaims. If these guards silently weakened, the failure would be quiet —
an unattended bad merge nobody watched happen — which is the dangerous kind.

## Telos

Be a small, portable, test-backed harness whose guards deny the irreversible acts of an
autonomous loop by default, permit autonomous integration only under an unforgeable done-signal
within a reversible blast radius, fail deny on ambiguity about that radius, fail open only in the
never-wedge-the-tool process sense, and mechanically refuse to represent unproven completion
claims as proven.

## Claims

### TELOS-001 — the conservative loop fence denies the whole irreversible VC set
- state: DISCHARGED
- intent: stop-and-surface is only real if every irreversible escape hatch is closed; one missed subcommand (a push, a branch delete) is the whole unattended-bad-merge failure back again
- discharged-by: hooks/guard-loop-vc.py::_classify
- contract: with CLAUDE_LOOP_GUARD set, _classify returns a deny reason for git merge, git push, git branch -d/-D, git reset --hard, non-dry-run git clean, git worktree remove, and gh pr merge
- verified-by: hooks/tests/test_guard_loop_vc.py::TestGuardLoopVC::test_deny_set
- last-grilled: 2026-07-07
- anchor: none

### TELOS-002 — YOLO integration is fenced to a revertable merge into a non-default branch
- state: DISCHARGED
- intent: verifiable autonomy is only safe inside the reversible/internal blast radius; a fast-forward merge leaves nothing to revert and a default-branch merge is the irreversible act the whole harness exists to prevent
- discharged-by: hooks/guard-loop-vc.py::_yolo_merge_reason
- contract: in yolo mode a git merge is allowed only when it carries --no-ff and the current branch is confirmed non-default; a missing --no-ff, a default or protected-name branch, or any inability to determine the current or default branch yields a deny reason
- verified-by: hooks/tests/test_guard_loop_vc.py::TestGuardYoloMode::test_denies_merge_when_default_ambiguous
- last-grilled: 2026-07-07
- anchor: none

### TELOS-003 — a guard defect never wedges the tool
- state: DISCHARGED
- intent: a safety hook that can crash the tool it guards will get disabled by its operator; the process contract must be fail-open (no decision) on unparseable input so the guard is trustworthy enough to stay installed
- discharged-by: hooks/guard-loop-vc.py::main
- contract: main exits 0 and emits no deny decision when stdin is not parseable JSON
- verified-by: hooks/tests/test_guard_loop_vc.py::TestGuardLoopVC::test_unparseable_stdin_fails_open
- last-grilled: 2026-07-07
- anchor: none

### TELOS-004 — an unproven completion claim is never represented as proven
- state: DISCHARGED
- intent: the record-as-read must not overclaim; a DISCHARGED with no executable witness is an author assertion, and representing it as proven is exactly the self-blessed "done" the harness distrusts
- discharged-by: skills/audit-telos/telos_check.py::parse_record
- contract: parse_record rewrites a claim whose state is DISCHARGED and whose verified-by is absent or blank to state SUSPECT in the parsed representation, leaving witness-backed claims untouched
- verified-by: skills/audit-telos/tests/test_telos_check.py::TestParserDemotion::test_unbacked_discharged_demotes_to_suspect
- last-grilled: 2026-07-07
- anchor: none

### TELOS-005 — the oracle-freeze check fails deny, not open
- state: DISCHARGED
- intent: YOLO mode's permit-to-act is keyed to a loop-immutable oracle; if the freeze check cannot positively confirm the oracle untouched, answering "frozen" would hand the loop a permit its safety case no longer supports
- discharged-by: skills/ralph-loop/scripts/check_oracle_frozen.py::main
- contract: main exits non-zero whenever the oracle file cannot be positively confirmed untouched since the baseline, including when the oracle path does not exist in the baseline
- verified-by: skills/ralph-loop/tests/test_check_oracle_frozen.py::TestCheckOracleFrozen::test_fail_deny_when_no_oracle_file
- last-grilled: 2026-07-07
- anchor: none

### TELOS-006 — the default branch is protected even when it is not named main or master
- state: DISCHARGED
- intent: branch-first enforcement that only pattern-matches the literal names main/master silently unprotects repos with a custom trunk, which is where an unnoticed default-branch edit would land
- discharged-by: hooks/guard-default-branch.py::main
- contract: main denies Edit/Write/NotebookEdit on the repo's resolved default branch even when origin/HEAD names a branch other than main or master
- verified-by: hooks/tests/test_guard_default_branch.py::TestGuardDefaultBranch::test_custom_default_also_protected
- last-grilled: 2026-07-07
- anchor: none
