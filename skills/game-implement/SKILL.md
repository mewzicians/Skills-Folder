---
name: game-implement
description: Implement approved game features and fixes end to end across logic, UI, content, persistence, tests, documentation, and maintained deliverables. Use when the user asks to build, wire up, apply, or finish an approved game change.
---

# Game Implement

## Confirm The Contract

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify implemented truth, stable design, decision status, and the smallest relevant code. Implement only the behavior the user approved or directly requested. Report conflicts before editing; do not silently choose among open alternatives.

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

Run syntax/static checks, the changed path, neighboring interactions, boundaries, repeated invocation, persistence, deterministic variants, and representative viewports as relevant, including the first load after a fresh reload. Broaden by blast radius. Record exact evidence and never claim an unrun suite passed.

When a rule changes, update every affected description, tooltip, legend, forecast, comment, and help entry in the same change. Update only affected design, decision, status, handoff, verification, mirror, and manifest records; byte-check maintained deliverables, and build an archive only when asked. Finish when behavior, player-facing explanations, tests, and maintained deliverables agree. Do not publish; publishing goes through `game-release` when the user invokes it.
