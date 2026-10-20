---
name: game-plan
description: Continue game design, systems, progression, economy, content, pacing, and balance planning from a project's durable sources of truth. Use to brainstorm, critique, compare, resume, or lock design decisions without implementing them; for simulation or telemetry evidence, use game-balance-lab.
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

- Lock only the exact choice the user explicitly approves. Approval is an explicit statement naming the choice; silence, enthusiasm, questions, "continue", or "use your judgment" approve nothing.
- Leave unanswered questions open and never apply a default silently.
- Never infer rejection from silence or nonselection, and never quietly revive a rejected idea; reopen it only by proposing it again.
- Record approved decisions in the configured decision ledger when edits are permitted; otherwise report the exact pending ledger entry.
- Move only useful superseded reasoning to the configured archive.
- Do not edit implementation during planning.

## Stop

Finish when the user has a clear recommendation or decision, exact status is recorded or reported as a pending update, and implementation work is either explicitly requested or left separate.
