---
name: game-implement
description: Implement approved game features and fixes end to end across logic, UI, content, persistence, tests, documentation, and maintained deliverables. Use when the user asks to build, wire up, apply, or finish an approved game change.
---

# Game Implement

## Confirm The Contract

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify implemented truth, stable design, decision status, and the smallest relevant code. **Hard rule:** implement only the behavior the user approved or directly requested. Report conflicts before editing; do not silently choose among open alternatives, because shipped code gets mistaken for a decision.

## Map Impact

Trace the change through:

- rules, state, content, AI, economy, progression, and resolution order;
- every input, replay, copy, speed, skip, pause, or synchronization path;
- save schema, restore checkpoints, migrations, reset, and compatibility;
- UI, accessibility, tutorial, feedback, tooltips, and help;
- tests, simulations, telemetry, documentation, mirrors, manifests, and packages.

## Implement

Reuse existing architecture and data-driven patterns. Make the smallest coherent change that completes the approved behavior. Preserve unrelated work, deterministic outcomes, transactional boundaries, and platform constraints. Keep decision-critical rules inspectable.

## Validate And Synchronize

Run syntax/static checks, the changed path, neighboring interactions, boundaries, repeated invocation, persistence, deterministic variants, and representative viewports as relevant, including the first load after a fresh reload. Broaden by blast radius. **Hard rule:** record exact evidence and never claim an unrun suite passed.

When a rule changes, update every affected description, tooltip, legend, forecast, comment, and help entry in the same change. Update only affected design, decision, status, handoff, verification, mirror, and manifest records; byte-check maintained deliverables, and build an archive only when asked. Finish when behavior, player-facing explanations, tests, and maintained deliverables agree. **Hard rule:** do not publish; publishing goes through `game-release` when the user invokes it, because a public push can't be recalled.

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
