---
name: game-release
description: Synchronize and byte-verify maintained game release deliverables, such as a repository mirror or Pages site; run pre-publish checks; build archives or upload bundles on request. Use when the user explicitly asks to prepare, refresh, check, or hand off a public release or upload, not ship readiness.
---

# Game Release

Run only when the user asked for this workflow; otherwise offer it.

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify the authoritative root, the maintained deliverables, the tested candidate version, and the public allowlist. Preserve unrelated work and stop on unexplained implementation-document drift.

Keep two kinds of output apart. Maintained deliverables, such as the public repository mirror or a store, jam, or Pages upload the project keeps current, are synchronized and verified on every release. On-demand derived copies, such as a ZIP archive, are point-in-time copies built only when the user asks for one; never keep, synchronize, or check one in as if it were maintained. A live upload, such as to Pages, a store, or a jam, is publishing.

Treat a mirror as an allowlist: synchronize only mapped root files, byte-for-byte, keep required hidden repository files, and keep launchers separate from game logic. Exclude credentials, private archives, local profiles, caches, editor and vault state, stale archives, and accidental personal paths. Run project QA checks and required change-focused tests before release. Never delete a stale mirror file that no mapping covers: report it, and only with the user's approval naming the path and the action, move it to a dated quarantine folder with a manifest of original paths and hashes.

When the user asks for an archive, build it with `scripts/build_repository_zip.py`. Git-ignored files, symbolic links, and junctions are never packaged, and risky files are default excludes that only `--include` overrides. Those excludes are a denylist of common names, so the default walk and `--git-tracked` package any secret they do not name; `--allowlist FILE` is the only fully fail-closed mode, so use it for a public release. The `.git*` exclude also drops `.github/`, `.gitattributes`, and `.gitignore` unless they are `--include`d, and `--git-tracked` refuses tracked files that differ from HEAD unless `--allow-dirty` is passed. Review the packaged and excluded lists. Its `contentDigest` covers names and bytes only; the archive's own SHA-256 is reproducible across Python builds only with `--stored`.

Before anything is published, check and report:

- identity: every author, committer, tagger, and `Co-authored-by` trailer being published uses a noreply or project address, never a personal one. Check every branch and tag being pushed, not only the current one. When the remote already has history, check what it lacks: `git log --branches --tags --not --remotes=origin --format="%h %ae %ce %(trailers:key=Co-authored-by,valueonly,separator=%x20)"`. For a first publication, check the whole history: `git log --branches --tags --format="%h %ae %ce %(trailers:key=Co-authored-by,valueonly,separator=%x20)"`. Check taggers with `git for-each-ref refs/tags --format="%(refname:short) %(taggeremail)"`;
- secrets: no tokens, private keys, credentials, or `.env` files in the files or the history being published;
- paths: no absolute local paths, such as a user's home folder;
- private folders: nothing outside the allowlist, such as notes, vaults, continuity ledgers, or local profiles;
- licenses: every bundled asset, font, sound, and library permits redistribution, with its required notices included.

Report the checks first: the deliverables and any archive, synchronized files, each check as `Pass`, `Fail`, `Not Run`, or `Blocked`, candidate and archive digests, file count, and remaining blockers. Never call a release ready when a required check failed or did not run.

Then stop. Publish only on the user's explicit instruction for this candidate, given after that report, and never while a required check failed or did not run. Without that instruction the agent never pushes, tags, uploads, or publishes.
