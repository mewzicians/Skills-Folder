---
name: game-release
description: Synchronize and byte-verify a game's maintained release deliverables, such as a public repository mirror, run pre-publish checks, and build an archive only on request. Use when the user explicitly asks to prepare, refresh, validate, or hand off a public release or upload.
---

# Game Release

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify the authoritative root, the maintained deliverables, the tested candidate version, and the public allowlist. Preserve unrelated work and stop on unexplained implementation-document drift.

Keep two kinds of output apart. Maintained deliverables, such as the public repository mirror or a store, jam, or Pages upload the project keeps current, are synchronized and verified on every release. On-demand derived copies, such as a ZIP archive, are point-in-time copies built only when the user asks for one; never keep, synchronize, or check one in as if it were maintained.

Treat a mirror as an allowlist: synchronize only mapped root files, byte-for-byte, keep required hidden repository files, and keep launchers separate from game logic. Exclude credentials, private archives, local profiles, caches, editor and vault state, stale archives, and accidental personal paths. Run project QA checks and required change-focused tests before release.

When the user asks for an archive, build it with `scripts/build_repository_zip.py`. Git-ignored files, symbolic links, and junctions are never packaged, and risky files are default excludes that only `--include` overrides. Those excludes are a denylist of common names, so the default walk and `--git-tracked` package any secret they do not name; `--allowlist FILE` is the only fully fail-closed mode, so use it for a public release. Review the packaged and excluded lists. Its `contentDigest` covers names and bytes only; the archive's own SHA-256 is reproducible across Python builds only with `--stored`.

Before anything is published, check and report:

- identity: every commit to publish has a noreply or project author and committer address, never a personal one (for example `git log --format="%h %ae %ce" origin/main..HEAD`);
- secrets: no tokens, private keys, credentials, or `.env` files in the files or the history being published;
- paths: no absolute local paths, such as a user's home folder;
- private folders: nothing outside the allowlist, such as notes, vaults, continuity ledgers, or local profiles;
- licenses: every bundled asset, font, sound, and library permits redistribution, with its required notices included.

Report the deliverables and any archive, synchronized files, checks as `Pass`, `Fail`, `Not Run`, or `Blocked`, candidate and archive digests, file count, and remaining blockers. Never call a release ready when a required check failed or did not run.

Stop before publishing. The agent never pushes, tags, uploads, or publishes without the user's explicit instruction to do so.
