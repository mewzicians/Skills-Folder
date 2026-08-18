---
name: game-qa-cleanup
description: Audit, rewrite, and synchronize a game's active documentation, guidance, handoffs, mirrors, manifests, skills, and release packages without changing gameplay. Use to remove stale material, reconcile project truth, repair documentation drift, or prepare consistent handoffs.
---

# Game QA Cleanup

Read repository guidance and [references/project-profile.md](references/project-profile.md). Inventory active instructions, design and decision sources, status/handoff files, skills, verification evidence, mirrors, manifests, metadata, and packages. Treat mirrors as copies, never independent truth.

Compare implementation claims with current code or exact-version evidence. Preserve the project's status vocabulary and distinguish former baseline, approved, draft, open, rejected, and superseded material. Report implementation-document mismatches before changing either.

Rewrite stale active sections in place. Consolidate duplicates, repair dates, hashes, paths, links, statuses, and completed instructions. Keep useful history in the configured archive; keep transient audit narration out of active design. Never promote an unapproved decision or edit gameplay.

Synchronize mapped files to configured mirrors, refresh manifests and hashes, and rebuild configured packages only when the package boundary is known. Preserve hidden files and historical evidence that still truthfully names its version.

Validate references, UTF-8, unintended debris, decision consistency, source-to-mirror equality, skill metadata, manifest completeness, package inventory, and byte equality. Report changed files, corrected mismatches, checks as `Pass`, `Fail`, `Not Run`, or `Blocked`, and work requiring design, implementation, or human testing.
