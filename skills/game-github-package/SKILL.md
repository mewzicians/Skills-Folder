---
name: game-github-package
description: Synchronize, build, and byte-verify a GitHub-ready game repository mirror and ZIP. Use when preparing, refreshing, validating, or handing off a public game repository, release archive, upload bundle, or Pages-ready package.
---

# Game GitHub Package

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify the authoritative root, configured public mirror, package output, tested candidate version, and public allowlist. Preserve unrelated work and stop on unexplained implementation-document drift.

Build a repository-root inventory containing the game, launchers, public documentation, licenses, contribution and agent guidance, repository metadata, required assets, public skills, test runners, and current evidence. Exclude credentials, private archives, local profiles, caches, editor state, stale archives, and accidental personal paths.

Synchronize mapped root files byte-for-byte. Preserve hidden repository files and keep launchers separate from game logic. Run project QA checks and required change-focused tests before packaging.

Use `scripts/build_repository_zip.py` to produce a deterministic archive whose paths begin at repository-root contents. Verify safe unique paths, exact folder/ZIP inventory, byte equality, hidden files, links, candidate hash, exclusions, and final SHA-256.

Report the mirror and ZIP paths, synchronized files, checks as `Pass`, `Fail`, `Not Run`, or `Blocked`, candidate and archive hashes, size, file count, and remaining blockers. Never call an archive ready when a required check failed or did not run.
