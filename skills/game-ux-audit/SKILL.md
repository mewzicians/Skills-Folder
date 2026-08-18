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
