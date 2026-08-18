---
name: game-plan
description: Continue game design, systems, progression, economy, content, pacing, and balance planning from a project's durable sources of truth. Use when the user asks to brainstorm, critique, compare, resume, or lock game-design decisions without implementing them.
---

# Game Plan

## Establish Project Truth

1. Read repository guidance and `GAME_PROJECT_PROFILE.md` when present.
2. Use [references/project-profile.md](references/project-profile.md) to map implementation, stable design, decision ledger, status, handoff, archives, and test evidence.
3. Inspect implementation only when a claim depends on current behavior.
4. Keep implemented, approved, draft, open, rejected, and superseded states distinct.

## Plan

1. State the requested topic, relevant approved constraints, and unresolved decisions.
2. Evaluate proposals rather than automatically endorsing them.
3. Check interactions with the game's core loop, resources, progression, difficulty, content availability, accessibility, and technical constraints.
4. Recommend a concrete direction with benefits, costs, risks, and the smallest useful experiment.
5. Ask at most three questions when subjective intent cannot be recovered from evidence.

## Preserve Decisions

- Lock only the exact choice the user explicitly approves.
- Leave unanswered questions open and never apply a default silently.
- Record approved decisions in the configured decision ledger when edits are permitted.
- Move only useful superseded reasoning to the configured archive.
- Do not edit implementation during planning.

## Stop

Finish when the user has a clear recommendation or decision, exact status is recorded, and implementation work is either explicitly requested or left separate.
