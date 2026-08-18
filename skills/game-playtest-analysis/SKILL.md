---
name: game-playtest-analysis
description: Turn game playtest notes, recordings, saves, screenshots, surveys, interviews, and telemetry into prioritized findings and discriminating experiments. Use when the user asks what player feedback means, why players succeeded or failed, or what to test next.
---

# Game Playtest Analysis

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify the exact tested build and current rules; never merge evidence from different builds without labels.

Normalize each session when available: player profile, build/version, platform, inputs, seed/save, choices, resources, progression, session length, failure or success cause, exact quote or observation, and supporting artifact. Keep observation, player explanation, analyst hypothesis, and telemetry separate.

Classify findings as `Bug`, `Comprehension`, `Decision quality`, `Balance`, `Pacing`, `Feedback`, `Accessibility`, or `Taste`. Assess frequency, severity, reproducibility, reach, learning effects, telemetry support, confidence, and competing explanations.

Look for decision bottlenecks, automatic choices, unused systems, first irreversible deficits, build availability versus execution, pacing fatigue, tutorial drop-off, feedback delays, and exceptional-mode confusion.

Rank findings by player harm and evidence strength. For each important hypothesis, propose the smallest discriminating reproduction, prototype, instrumentation event, ablation, seed set, cohort comparison, or interview question, including what outcome would support or reject it.

Keep recommendations draft until approved. Route confirmed defects, balance questions, UX issues, and approved implementation to the appropriate specialized workflow.
