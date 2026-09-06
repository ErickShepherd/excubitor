---
name: ralph
description: Start or resume an explicitly requested Excubitor Ralph job through the connected native Ralph tools. Ordinary development and questions about Ralph do not invoke this workflow.
---

Use the existing coding task. This skill requires the admitted Excubitor native
Ralph tools; it does not install them or provide enforcement itself. If the tools
are unavailable, identify that missing connection and stop the launch attempt.
Do not substitute a manual loop or change runtime permissions or registration.

Call `ralph_status` first. For an active or interrupted job, call `ralph_start` with no arguments
to reconnect under its original agreement. A blocked job needs its reported
blocker resolved; do not submit a replacement plan or extend its limits.
Completed or cancelled jobs in the status history are inactive. Start a new one
only for the owner's explicit new Ralph request.

For a new job, use the owner's request and existing project context to propose
the goal, manageable work units, and concrete input/output acceptance checks.
Use only the verification runners advertised in the tool schema. Check that the
proposed checks distinguish the requested behavior from plausible wrong results.
Ask only for missing requirements that materially affect the job; do not make
the owner hand-write a plan or repeat preferences already captured by the host.

Call `ralph_start` with `job` containing `goal`, `units`, and `checks`. Each check
has a short `name`, an advertised `runner`, and exact `stdin` and `stdout` strings;
`stderr`, `exit_code`, and a shorter `timeout_seconds` are optional. Omit `attempts`
and `seconds` to use the displayed host defaults unless the owner requested
different limits within the advertised bounds. The first supported check format
is input/output behavior; report a missing verifier capability for other work.

The native form presents the actual agreement for owner confirmation. A chat
message, this skill, and a tool argument cannot answer that form. A declined or
cancelled form ends the launch attempt. Editing a proposal requires a fresh form;
an accepted job cannot be replaced by resubmitting these fields.

After Start reports acceptance, the host controller owns iterations, checks,
repair, and separate review. Report that the job started; do not implement its
units in the initiating conversation or request a restart after each unit.
Use status when asked, and report completion only from the host's completion
evidence. Default completion retains reviewed, verified work on an isolated
committed branch. Merge, publishing, and deployment are unavailable in this mode.
