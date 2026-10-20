---
name: game-qa-cleanup
description: Audit, rewrite, and synchronize a game's active documentation, guidance, handoffs, mirrors, manifests, skills, and release packages without changing gameplay. Use to remove stale material, reconcile project truth, repair documentation drift, or prepare consistent handoffs.
---

# Game QA Cleanup

Read repository guidance and [references/project-profile.md](references/project-profile.md). Inventory active instructions, design and decision sources, status/handoff files, skills, verification evidence, mirrors, manifests, metadata, and packages. Treat mirrors as copies, never independent truth.

Compare implementation claims with current code or exact-version evidence. Preserve the project's status vocabulary and distinguish former baseline, approved, draft, open, rejected, and superseded material. Report implementation-document mismatches before changing either.

Rewrite stale active sections in place. Consolidate duplicates, repair dates, hashes, paths, links, statuses, and completed instructions. Keep useful history in the configured archive; keep transient audit narration out of active design. Never promote an unapproved decision or edit gameplay.

Never delete, move, demote, retag, or retire a file or status on your own judgment. Propose each item with its path and reason. Only with the user's approval naming the path and the action, move it to a dated quarantine folder with a manifest of original paths and hashes.

Synchronize mapped files to configured mirrors and refresh manifests and hashes of maintained deliverables; build an on-demand archive only when the user asks. Preserve hidden files and historical evidence that still truthfully names its version; a hash in a historical record describes the bytes of its time and is not drift.

Validate references, UTF-8, unintended debris, decision consistency, source-to-mirror equality, skill metadata, manifest completeness, package inventory, and byte equality. Report changed files, corrected mismatches, checks as `Pass`, `Fail`, `Not Run`, or `Blocked`, and work requiring design, implementation, or human testing.
