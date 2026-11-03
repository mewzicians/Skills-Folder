---
name: game-full-verification
description: Exhaustively verify a complete game release candidate with evidence across requirements, rules, determinism, UI, accessibility, persistence, performance, packaging, and balance. Use when the user explicitly asks for full verification, a ship-readiness verdict, or complete approved-feature checks.
---

# Game Full Verification

Run only when the user asked for this workflow; otherwise offer it.

Read repository guidance and [references/project-profile.md](references/project-profile.md). Freeze the exact candidate version/hash and every active source of truth. Run the read-only consistency checks verification needs: references and links, encoding and debris, decision-status consistency, and mirror and manifest equality. **Hard rule:** verification never edits gameplay or documents, because a verdict on a candidate you changed describes a build nobody tested; when a check finds drift, report it, and clean up only if the user separately asks for cleanup.

Reconstruct a bidirectional requirement matrix: every approved requirement must map to implementation, player-facing explanation, and current-version evidence; every material implementation branch must map back to status, exposure, and tests. Mark each row `Pass`, `Fail`, `Not Run`, or `Blocked`.

Verify proportionally across:

- static integrity, data registries, assets, dependencies, and startup;
- ordinary and exceptional gameplay, ordering, boundaries, termination, and error recovery;
- deterministic/replay/network parity and random-state integrity where applicable;
- saves, migrations, checkpoints, refresh, resume, corruption, and incompatibility;
- UI, viewports, text zoom, keyboard, semantics, contrast, motion, and screenshots;
- performance, memory, long sessions, cleanup, and platform constraints;
- maintained deliverables, metadata, hidden files, manifests, launchers, and byte equality, with on-demand archives checked only when the user asks for one;
- legal simulation policy and balance evidence, kept distinct from human testing.

Run timing-sensitive browser or audio suites one at a time, because contention can manufacture the failure. **Hard rule:** when the project defines rigor levels, state the level used and never silently downgrade it, because a quiet downgrade makes a weaker verdict look like the full one. A hash in a historical record describes the bytes of its time and is not drift.

A containing gate fails when a required subrequirement fails. Never repair gameplay during verification-only work. Write a dated current-version report with hashes, matrix, failures, blocked and unrun scope, and ship verdict where the project keeps verification evidence, plus any configured mirror copy of that report, or give it in the response; change no other file. State the exact next blocker.

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
