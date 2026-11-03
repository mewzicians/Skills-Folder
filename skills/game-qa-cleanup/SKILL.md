---
name: game-qa-cleanup
description: Audit and reconcile a game's active documentation, guidance, handoff documents, mirrors, manifests, and skill metadata without changing gameplay or removing files on its own. Use when the user explicitly asks to run QA cleanup, reconcile project truth, or repair documentation drift.
---

# Game QA Cleanup

Run only when the user asked for this workflow; otherwise offer it.

Read repository guidance and [references/project-profile.md](references/project-profile.md). Inventory active instructions, design and decision sources, status/handoff files, skills, verification evidence, mirrors, manifests, metadata, and packages. Treat mirrors as copies, never independent truth.

Compare implementation claims with current code or exact-version evidence. Preserve the project's status vocabulary and distinguish former baseline, approved, draft, open, rejected, and superseded material. Report implementation-document mismatches before changing either.

Rewrite stale active sections in place. Consolidate duplicates, repair dates, hashes, paths, links, statuses, and completed instructions. Keep useful history in the configured archive; keep transient audit narration out of active design. **Hard rule:** never promote an unapproved decision or edit gameplay, because cleanup that changes decisions or behavior passes unreviewed.

**Hard rule:** never delete, move, demote, retag, or retire a file or status on your own judgment, because a removal made on a guess can lose the only copy. Propose each item with its path and reason, and act only on the user's approval naming the path and the action. Carry out an approved removal of a git-tracked file as its own commit only when its current bytes are already committed; never commit other pending edits just to get that backup, since they may hold private or unrelated work. Otherwise, and for untracked files, move the file to a dated quarantine folder with collision-safe names and a list of original paths. An approved removal never permits publishing the backup.

Synchronize mapped files to configured mirrors and refresh manifests and hashes of maintained deliverables; build an on-demand archive only when the user asks. Preserve hidden files and historical evidence that still truthfully names its version; a hash in a historical record describes the bytes of its time and is not drift.

Validate references, UTF-8, unintended debris, decision consistency, source-to-mirror equality, skill metadata, manifest completeness, package inventory, and byte equality. Report changed files, corrected mismatches, checks as `Pass`, `Fail`, `Not Run`, or `Blocked`, and work requiring design, implementation, or human testing.

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
