---
name: game-balance-lab
description: Analyze game balance with rules-faithful simulation, legal policy audits, telemetry, ablations, uncertainty, and human evidence. Use for difficulty, win rates, economies, progression curves, builds, content power, encounters, rewards, or whether a mechanic is too strong or weak.
---

# Balance Sim Lab

Read repository guidance, [references/project-profile.md](references/project-profile.md), current implementation, decision status, and relevant playtest evidence. Record the exact candidate version and label proposed values as experiments.

## Validate The Instrument

Before trusting telemetry, prove automated policies obey legal information, actions, costs, limits, exclusions, timing, randomness, and resolution order, and can actually use every compared strategy. Treat policy-rule mismatch as a blocker, because a policy that breaks the rules measures a different game.

## Experiment

Define the question, hypothesis, population, metrics, decision threshold, baseline, and controlled ablations. Prefer paired fixed seeds. Report sample size and uncertainty. Keep human evidence separate from scripted-policy evidence.

Measure the whole curve: success/failure by stage, resources, pacing, recovery, economy, exposure, availability, selection, conversion, survivorship, overkill, remaining power, action burden, and outliers. Find the first decisive deficit or excess, not only the final result.

Guard against rare exposure, policy blindness, survivorship bias, conditional samples, and averaging away exciting high-rolls. Protect distinct option identities and viable tradeoffs.

Report evidence, policy legality, confidence, structural problems, watchpoints, competing explanations, and smallest next experiments. **Hard rule:** recommendations remain draft until explicitly approved; do not edit values during analysis, because tuned numbers that slip in during analysis get treated as decided.

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
