---
name: game-ux-audit
description: Audit a game's usability, onboarding, information architecture, readability, responsive behavior, interaction feedback, accessibility, and player decision clarity. Use when the user asks whether a game is understandable, navigable, readable, accessible, mobile-friendly, or visually clear.
---

# Game UX Audit

Read repository guidance, the project profile in [references/project-profile.md](references/project-profile.md), relevant design/status sources, and the implemented product. Audit the complete player journey rather than screenshots alone.

For every surface and transition, check:

- objective, next action, selection rules, consequences, timing, costs, targets, exclusions, and recovery paths;
- ordinary and exceptional modes, tutorial, menus, HUD, gameplay, upgrades, results, settings, save/restore, and error recovery;
- desktop and supported device viewports, text zoom, long labels, overflow, layout stability, and touch targets;
- keyboard order, focus, modal behavior, semantic names, live feedback, screen-reader order, contrast, reduced motion, and non-color cues.

Separate usability defects from visual taste, balance, and implementation bugs. Inspect rendered screenshots visually; geometry alone does not prove clarity.

Rank findings as `Blocker`, `High`, `Medium`, or `Low`. For each, provide evidence, affected players and state, frequency, consequence, and a concrete lean recommendation. Do not implement changes unless requested. Report what passed, what was not run, accessibility limits, and the smallest high-value next pass.

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
