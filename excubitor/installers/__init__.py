"""The transactional installer foundation for Excubitor's runtime integrations.

Campaign 2 builds the *installer transaction*, not the native marketplace plugins (those are later
campaigns). The pieces:

* :mod:`excubitor.installers.runtime` — runtime profiles (Claude Code only, today), deterministic
  discovery of a runtime's concrete config/hook targets per scope, and the artifact/registration set an
  install owns.
* :mod:`excubitor.installers.plan` — a deterministic, side-effect-free install plan (the ``--dry-run``
  output): exactly which directories, files, and settings-registrations an install would create,
  computed by *reading* only.

The state machine follows ``docs/design/installable-multi-runtime-distribution.md`` (Discover →
Validate → Plan → Stage → Register → Trust → Probe → Receipt → Rollback). Discovery and Plan write
nothing; staging/registration/rollback (with a receipt of exact, hash-bound ownership) land in later
plan items, and installation is not "protected" until a real harmless-denial host probe succeeds.

Only Claude Code is a supported runtime. No claim is made here that any other host is supported.
"""
from __future__ import annotations
