# Ralph completion cycle

Excubitor should make it easy to launch a persistent coding loop with a selected
LLM. It breaks agreed work into cohesive steps, gives fresh workers current code
and durable feedback, verifies results, and continues until checked completion or
a concrete external blocker or agreed resource limit. A worker ending its answer
is not a reason for the controller to abandon pending work.

The owner authorized completion in this session, using the Ralph skill as a
template. Existing host controls and publication permissions remain separate.
Keep task storage on D:. Preserve the existing dirty development worktree.

## Context policy

Research found degradation in multi-turn underspecified tasks, including early
wrong assumptions, but did not establish a universal safe number of coding turns.
Sources: https://arxiv.org/abs/2505.06120 and https://arxiv.org/abs/2602.07338.
Anthropic reports both useful resets and a model for which compaction sufficed:
https://www.anthropic.com/engineering/harness-design-long-running-apps.

Use fresh model calls at bounded step boundaries now. Preserve original goals,
current facts, progress, and recent host feedback outside conversation history.
Record outcomes and timings for later calibration; a few failed attempts are not
statistically proven context degradation. A context refresh never increases
limits. Claude and Codex calls already start fresh each attempt. Development of
this cycle uses fresh implementation sessions for bounded steps as well.

## Completion checklist

- [x] Persist feedback across controller loss, supply compact handoff context,
  and record attempt outcomes and timings. Verify fresh workers recover prior
  failed-check and review feedback without replaying a chat.
- [x] Add generic command model transport and vendor-independent execution.
  Keep explicit executor selection. Trusted local execution is not a sandbox;
  it is never fallback for a native denial. Test transport and cancellation.
- [x] Provide profile generation/preflight and a complete quickstart, including
  custom/local model bridges. Preserve plan review and original limits; require
  no per-step owner restart. Add a small common HTTP bridge where appropriate.
- [x] Verify combined regressions, a native loop, fresh-context recovery and
  cancellation. Check unchanged original/tests and obtain a fresh independent
  review. Consolidate the dirty work for the authorized broker commit.

Validation passed: 253 regression tests and two subtests, three packaging/install
checks, native Claude and generic-bridge completion and crash recovery. Earlier
native comparison also verified Codex. Independent review reproduced and cleared
malformed-response recovery and saved-cancellation defects. HTTP is tested with
local protocol fixtures only; native launch support is Windows. The broker commit
outcome is recorded in the external completion-cycle evidence after this snapshot.

## Carry-forward facts

The existing candidate already shares planning, edits, checks, review and
background recovery between Claude and Codex. Both native comparison runs passed.
A first over-fragmented Claude plan exhausted its limit and remains preserved;
the planner now reserves retry capacity.

The owner explicitly authorized the single outdated Python-pin repair in the
commit broker. Root applied it after verifying the installed runtime signature
and bytes, preserving the exact broker preimage for rollback. No other broker
policy or host configuration was changed.

Private evidence: D:/Projects/Internal/excubitor-remediation/windows-pathfinding-astra
Worktree: D:/Projects/Repositories/excubitor-worktrees/vendor-agnostic-enforcement
