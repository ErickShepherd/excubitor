# Vendor-agnostic enforcement plan

Status: active

This checklist moves Excubitor from a Claude Code distribution with a neutral policy core to native,
testable enforcement adapters for Codex and Antigravity. Each checked item is one Ralph-loop unit and
one focused commit. A runtime is not called supported until a harmless real-host denial probe proves
that the host invoked the hook and honored its veto.

## Key decisions

- The model-blind core remains the only policy authority. Runtime adapters translate native events,
  call the shared dispatcher, and translate the result back; they do not copy deny sets.
- Codex is implemented before Antigravity because its current native hook schema is documented and
  locally available for a real probe. Claude Code behavior remains byte-compatible while adapters are
  added.
- A passing decision is silence, meaning Excubitor has no objection. It must never become a native
  auto-approval that bypasses the host's normal permission flow.
- A recognized mutation event is denied when the adapter cannot enumerate every target. Unknown or
  malformed outer envelopes remain fail-open so a broken hook cannot wedge the host.
- Neutral `EXCUBITOR_*` configuration is primary. Existing Claude variables remain compatibility
  aliases during migration and must be reported honestly as legacy inputs.
- Code, installation, trust, and support claims are separate gates. A green fixture suite does not
  prove that a live host loaded or honored the hook.

## Checklist

- [x] Add a Codex `PreToolUse` adapter for Bash and `apply_patch`, including complete patch-target
  extraction, all four shared policies, Codex-native veto rendering, and Windows-safe golden fixtures.
- [x] Add transactional Codex project and user registration, receipts, rollback, self-integrity
  coverage for active registrations, and a trust-review handoff.
- [x] Run harmless Codex allow/deny probes under the installed registration and record the observed
  native fixtures and support status without overstating specialized-tool coverage.
- [x] Add explicit Codex MCP mutation profiles so configured write-capable MCP tools supply every
  target while unknown MCP tools continue to preserve the host's normal permission flow.
- [ ] Add an Antigravity `PreToolUse` adapter from observed native fixtures, covering command execution
  and every documented file-mutation surface through the same dispatcher.
- [ ] Add transactional Antigravity registration, receipts, rollback, self-integrity coverage, and
  harmless real-host allow/deny probes.
- [ ] Update installation documentation, support matrices, skills, environment examples, and known
  bypasses so Claude Code, Codex, and Antigravity have explicit, evidence-backed capability status.
