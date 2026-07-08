---
name: leak-guard
description: >-
  Before content generated or derived from a private source crosses into a public/outward artifact (a
  résumé, a website, a public doc, an outbound message), scan it for leaked secrets, PII, or
  NDA/confidential material and block on a hit. Use when generating or publishing outward-facing
  content from private data, or reviewing an artifact before it ships.
argument-hint: "<the artifact or content to guard>"
allowed-tools: [Read, Grep, Glob, Bash]
metadata:
  version: 1.1.0
---

# leak-guard

Private data must not cross an outward boundary. Before content generated or derived from a private
source-of-truth goes out — a résumé, a website, a public doc, an outbound message — guard it: scan for
leaked secrets, PII, and NDA/confidential material, and **block on a hit**. A leak is asymmetric: once
published it's cached, indexed, and effectively irreversible; the re-check that prevents it is cheap.

## When to use

- Generating or publishing outward-facing content from private data.
- Reviewing an artifact before it leaves the private boundary — the source content *and* the built
  output.
- Adding or maintaining the guard itself.

## What counts as a leak

- **Secrets / credentials** — keys, tokens, passwords, connection strings.
- **PII** — beyond what's intentionally public.
- **NDA / confidential** — client names, proprietary systems, internal processes, embargoed material.
- **Project-specific must-never-ship rules** — required corrections, banned phrasings, etc., sourced
  from the project's own canon.

## How

1. **Identify the boundary.** What's the private source-of-truth, and what's the public artifact? The
   guard runs at the crossing — and scans *both* the source content and the built output (a leak can
   appear only after rendering).
2. **Run the deterministic scanner** — [`leak_check.py`](leak_check.py), a stdlib tool shipped with
   this skill: it scans the artifact (file or directory) for built-in structured secrets (private
   keys, AWS/GitHub/token shapes, URL credentials) **and** the must-never-ship tokens you supply, exits
   non-zero on a finding (so it gates a build), fails closed, and prints findings **masked** (it never
   re-prints the secret). Deterministic + tested beats a model eyeballing it.

   ```bash
   # scan a built artifact against the project's private canon, whitelisting intentional exceptions
   python3 leak_check.py ./public-site/ --private-tokens .private-tokens --allow "IntentionallyPublicName"
   ```

   `--private-tokens` is a file of literals or `re:<regex>` (the names/systems/numbers from your private
   source-of-truth — the guard can't know these, you tell it). See `leak_check.py --help`; its LIMITS
   docstring is honest about what pattern-matching misses.
3. **Block on a hit.** A finding stops the publish. Report `where — what leaked`; the human redacts, or
   **explicitly** whitelists an intentional exception — never silently.
4. **Fail closed.** If you can't verify it's clean, treat it as not-clean.

## Discipline

- **Whitelist intentionally-public data explicitly** so the guard doesn't cry wolf and get ignored — a
  noisy guard is a disabled guard.
- **Guard strength tracks sensitivity** (`threat-model`) — NDA/secret material is a hard block, not a
  warning.
- **Make it deterministic and CI-gating** where possible (pairs with `automated-testing`): a guard
  wired into the build pipeline can't be forgotten.

## Related

Same "private data must not cross an outward boundary" family as `logging` (never log secrets/PII) and
`handoff` (redaction) — leak-guard applies it to *published/generated* artifacts. `threat-model` is the
reasoning for how hard to guard.
