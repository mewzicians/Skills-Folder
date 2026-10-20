---
name: game-full-verification
description: Exhaustively verify a complete game release candidate with evidence across requirements, rules, determinism, UI, accessibility, persistence, performance, packaging, and balance. Use when the user explicitly asks for full verification, a ship-readiness verdict, or complete approved-feature checks.
---

# Game Full Verification

Run only when the user asked for this workflow; otherwise offer it.

Read repository guidance and [references/project-profile.md](references/project-profile.md). Freeze the exact candidate version/hash and every active source of truth. Run the read-only consistency checks verification needs: references and links, encoding and debris, decision-status consistency, and mirror and manifest equality. Verification never edits gameplay or documents; when a check finds drift, report it, and clean up only if the user separately asks for cleanup.

Reconstruct a bidirectional requirement matrix: every approved requirement must map to implementation, player-facing explanation, and current-version evidence; every material implementation branch must map back to status, exposure, and tests. Mark each row `Pass`, `Fail`, `Not Run`, or `Blocked`.

Verify proportionally across:

- static integrity, data registries, assets, dependencies, and startup;
- ordinary and exceptional gameplay, ordering, boundaries, termination, and error recovery;
- deterministic/replay/network parity and random-state integrity where applicable;
- saves, migrations, checkpoints, refresh, resume, corruption, and incompatibility;
- UI, viewports, text zoom, keyboard, semantics, contrast, motion, and screenshots;
- performance, memory, long sessions, cleanup, and platform constraints;
- maintained deliverables, metadata, hidden files, manifests, launchers, and byte equality, with on-demand archives checked only when the user asks for one;
- legal simulation policy and balance evidence, kept distinct from human testing.

Run timing-sensitive browser or audio suites one at a time, because contention can manufacture the failure. When the project defines rigor levels, state the level used and never silently downgrade it. A hash in a historical record describes the bytes of its time and is not drift.

A containing gate fails when a required subrequirement fails. Never repair gameplay during verification-only work. Write a dated current-version report with hashes, matrix, failures, blocked and unrun scope, and ship verdict where the project keeps verification evidence, plus any configured mirror copy of that report, or give it in the response; change no other file. State the exact next blocker.
