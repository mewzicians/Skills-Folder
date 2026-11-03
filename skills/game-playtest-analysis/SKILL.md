---
name: game-playtest-analysis
description: Turn game playtest notes, recordings, saves, screenshots, surveys, interviews, and telemetry into prioritized findings and discriminating experiments. Use when the user asks what player feedback means, why players succeeded or failed, or what to test next.
---

# Game Playtest Analysis

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify the exact tested build and current rules; never merge evidence from different builds without labels.

Normalize each session when available: player profile, build/version, platform, inputs, seed/save, choices, resources, progression, session length, failure or success cause, exact quote or observation, and supporting artifact. Keep observation, player explanation, analyst hypothesis, and telemetry separate. **Hard rule:** label agent- or script-played sessions; they are not human evidence, because a call made on scripted play can look confirmed when no person ever played it. **Hard rule:** pseudonymize participants, keep only needed data, and keep participant data out of public files; published personal data can't be recalled.

Classify each finding:

- `Bug`: the build contradicts its rules or intent, shown by reproduction or source evidence, not a report alone.
- `Comprehension`: a player misread a rule, state, or goal.
- `Decision quality`: choices were automatic, empty, or unreadable.
- `Balance`: an option, strategy, or curve is too strong or weak.
- `Pacing`: length or repetition caused fatigue or drop-off.
- `Feedback`: a result was unclear, late, or missing.
- `Accessibility`: an input, display, or cognitive barrier blocked play.
- `Taste`: a preference, not a defect.

Assess frequency, severity, reproducibility, reach, learning effects, telemetry support, confidence, and competing explanations.

Look for decision bottlenecks, automatic choices, unused systems, first irreversible deficits, build availability versus execution, pacing fatigue, tutorial drop-off, feedback delays, and exceptional-mode confusion.

Rank findings by player harm and evidence strength. For each important hypothesis, propose the smallest discriminating reproduction, prototype, instrumentation event, ablation, seed set, cohort comparison, or interview question, including what outcome would support or reject it.

Keep recommendations draft until approved. Route confirmed defects, balance questions, UX issues, and approved implementation to the appropriate specialized workflow.

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
