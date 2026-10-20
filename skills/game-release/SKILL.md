---
name: game-release
description: Synchronize and byte-verify a game's maintained release deliverables, such as a public repository mirror, and build an archive only on request. Use when preparing, refreshing, validating, or handing off a public game repository, release archive, upload bundle, or Pages-ready package.
---

# Game Release

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify the authoritative root, the maintained deliverables, the tested candidate version, and the public allowlist. Preserve unrelated work and stop on unexplained implementation-document drift.

Keep two kinds of output apart. Maintained deliverables, such as the public repository mirror or a store, jam, or Pages upload the project keeps current, are synchronized and verified on every release. On-demand derived copies, such as a ZIP archive, are point-in-time copies built only when the user asks for one; never keep, synchronize, or check one in as if it were maintained.

Treat a mirror as an allowlist: synchronize only mapped root files, byte-for-byte, keep required hidden repository files, and keep launchers separate from game logic. Exclude credentials, private archives, local profiles, caches, editor and vault state, stale archives, and accidental personal paths. Run project QA checks and required change-focused tests before release.

When the user asks for an archive, build it with `scripts/build_repository_zip.py`. It fails closed: risky files are default excludes that only `--include` overrides, git-ignored files and symbolic links are never packaged, and `--git-tracked` or `--allowlist FILE` limits the inventory. Review its packaged and excluded lists. Its `contentDigest` covers names and bytes only; the archive's own SHA-256 is reproducible across Python builds only with `--stored`.

Report the deliverables and any archive, synchronized files, checks as `Pass`, `Fail`, `Not Run`, or `Blocked`, candidate and archive digests, file count, and remaining blockers. Never call a release ready when a required check failed or did not run.
