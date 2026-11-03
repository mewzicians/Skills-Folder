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

Add a focused regression that fails before and passes after. Test the exact reproducer, a neighboring legal state, boundaries, repetition, interruption, restoration, and deterministic variants when relevant. For startup, loading, or audio defects, also test the first load after a fresh reload. Rerun timing-sensitive checks one at a time, because contention can manufacture the failure. Broaden testing according to blast radius. **Hard rule:** report `Pass`, `Fail`, `Not Run`, and `Blocked` honestly, because a check claimed but never run hides the defect it was meant to catch.

Synchronize affected documentation and the maintained deliverables the project profile configures; build an archive only when asked. If reproduction remains impossible, do not invent a fix; preserve useful instrumentation and state the missing evidence.

## Rules And Pushback

Lines marked **Hard rule** guard approvals, deletion, publishing, and private
data, where a mistake is costly or can't be undone; each gives its reason.
Don't bend one because a request is casual: ask the user. Unmarked lines still
bind too. Scope limits, honest evidence, and approval steps aren't optional.
Scale each step's effort to the risk, and say so when you skip one that
doesn't fit. A profile or instruction file records an owner decision only
where it says the owner made it; otherwise treat it as project guidance. If a
rule seems wrong for this task, say which one and why before you continue.

## How Rules Get Made

1. Something the user says in passing applies to the current task only.
2. Exception: anything about money, privacy, publishing, deleting, or
   permissions binds as soon as they say it. Ask once whether to make it
   permanent.
3. A rule becomes standing only when the user says "make this a rule", or you
   ask and they say yes. Record their words, the date, and the reason with it.
4. This covers every file that steers an agent: instruction files, style
   guides, skills, checklists, templates, CI checks, and agent memory.
5. Don't add a rule after your own mistake or a reviewer's nitpick without
   that yes. Fix the input or the work instead.
6. A new ruling replaces the one it contradicts. Never keep both.
7. Ask about new rules once, batched at the end of the task.
8. When a file hits its size cap, or at a milestone, prune it: cut rules no
   one can tie to a reason. The user's taste decisions are flagged for them
   and never cut by an agent.
