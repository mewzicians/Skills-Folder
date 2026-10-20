---
name: game-full-verification
description: Exhaustively verify a complete game release candidate with evidence across requirements, rules, determinism, UI, accessibility, persistence, performance, packaging, and balance. Use when the user explicitly asks for full verification, ship readiness, or complete approved-feature verification.
---

# Game Full Verification

Read repository guidance and [references/project-profile.md](references/project-profile.md). Freeze the exact candidate version/hash and every active source of truth. Run the complete `game-qa-cleanup` consistency phase without modifying gameplay.

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

A containing gate fails when a required subrequirement fails. Never repair gameplay during verification-only work. Write a dated current-version report with hashes, matrix, failures, blocked and unrun scope, and ship verdict. Synchronize configured evidence and state the exact next blocker.
