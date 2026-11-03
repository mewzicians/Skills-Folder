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

- **Hard rule:** lock only the exact choice the user explicitly approves, because work built on a decision the user never made is costly to unwind. Approval is an explicit statement naming the choice; silence, enthusiasm, questions, or "continue" approve nothing.
- When the user delegates a specific choice ("use your judgment on this", "you pick"), make it within that scope, label it agent-chosen under that delegation rather than approved, and list it in your report so it is easy to overturn. Delegation never authorizes publishing, deleting files, or changing a previously approved value.
- **Hard rule:** leave unanswered questions open and never apply a default silently. Never infer rejection from silence or nonselection, and never quietly revive a rejected idea; reopen it only by proposing it again.
- Record approved decisions in the configured decision ledger when edits are permitted; otherwise report the exact pending ledger entry.
- Move only useful superseded reasoning to the configured archive.
- Do not edit implementation during planning.

## Stop

Finish when the user has a clear recommendation or decision, exact status is recorded or reported as a pending update, and implementation work is either explicitly requested or left separate.

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
