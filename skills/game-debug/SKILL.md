---
name: game-debug
description: Reproduce, diagnose, narrowly fix, and regression-test defects in game logic, UI, persistence, determinism, simulation, audio, networking, tooling, or packaging. Use when game behavior is broken, inconsistent, stuck, duplicated, missing, corrupted, or incorrect.
---

# Game Debug

## Establish Truth

Read repository guidance and the project profile described in [references/project-profile.md](references/project-profile.md). Identify the exact build, intended behavior, affected implementation, and current evidence. Separate defects from design preferences, stale documentation, invalid test policy, unsupported state, or corrupted input.

## Reproduce

Capture the smallest relevant state: version/hash, platform, seed or random state, save/schema version, scene/phase, resources, selected content, input sequence, logs, screenshots, and timing. Prefer a deterministic reproducer. Instrument intermittent boundaries without changing outcomes.

## Diagnose And Repair

1. Trace state mutation, rendering, persistence, scheduling, ordering, and cleanup.
2. Check repeated invocation, stale callbacks, canonical IDs, rollback, transitions, race conditions, and shared helpers.
3. Name the earliest root cause before editing.
4. Apply the smallest complete fix across all affected entry points.
5. Preserve unrelated behavior, ordering, randomness, saves, and user changes.

## Prove

Add a focused regression that fails before and passes after. Test the exact reproducer, a neighboring legal state, boundaries, repetition, interruption, restoration, and deterministic variants when relevant. Broaden testing according to blast radius. Report `Pass`, `Fail`, `Not Run`, and `Blocked` honestly.

Synchronize affected documentation and release artifacts configured by the project profile. If reproduction remains impossible, do not invent a fix; preserve useful instrumentation and state the missing evidence.
