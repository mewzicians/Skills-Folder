---
name: game-release
description: Synchronize and byte-verify maintained game release deliverables, such as a repository mirror or Pages site; run pre-publish checks; build archives or upload bundles on request. Use when the user explicitly asks to prepare, refresh, check, or hand off a public release or upload, not ship readiness.
---

# Game Release

Run only when the user asked for this workflow; otherwise offer it.

Read repository guidance and [references/project-profile.md](references/project-profile.md). Identify the authoritative root, the maintained deliverables, the tested candidate version, and the public allowlist. Preserve unrelated work and stop on unexplained implementation-document drift.

Keep two kinds of output apart. Maintained deliverables, such as the public repository mirror or a store, jam, or Pages upload the project keeps current, are synchronized and verified on every release. On-demand copies, such as a ZIP archive, are built only when the user asks, and never kept, synchronized, or checked in: a kept archive drifts on every documentation edit, while every check it carries already holds against the folder it came from. A live upload, such as to Pages, a store, or a jam, is publishing.

Treat a mirror as an allowlist: synchronize only mapped root files, byte-for-byte, keep required hidden repository files, and keep launchers separate from game logic. Exclude credentials, private archives, local profiles, caches, editor and vault state, stale archives, and accidental personal paths. Run project QA checks and required change-focused tests before release.

**Hard rule:** never delete a stale mirror file that no mapping covers, because the mirror may hold the only copy. Report it, and act only on the user's approval naming the path and the action. In a git mirror, remove it as its own commit only when its current bytes are already committed; never commit other pending edits to get that backup. Otherwise move it to a dated quarantine folder with collision-safe names and a list of original paths. An approved removal never permits publishing the backup.

When the user asks for an archive, run `python scripts/build_repository_zip.py --help`, then build with it. Use `--allowlist FILE` for anything public: it is the only mode that refuses an unlisted file, while the default excludes are a denylist of common names and can miss a secret. Include required hidden files deliberately; the `.git*` exclude also drops `.github/`, `.gitattributes`, and `.gitignore` unless they are `--include`d. Review the packaged and excluded lists. Report `contentDigest` (names and bytes) apart from the archive's own SHA-256, which is reproducible across Python builds only with `--stored`.

**Hard rule:** before anything is published, check and report each item below. Anything pushed to a public remote can be copied before you notice.

- identity: every author, committer, tagger, and `Co-authored-by` trailer being published uses a noreply or project address, never a personal one, on every branch and tag being pushed. When the remote already has history, check what it lacks: `git log --branches --tags --not --remotes=origin --format="%h %ae %ce %(trailers:key=Co-authored-by,valueonly,separator=%x20)"`. For a first publication, drop `--not --remotes=origin`. Check taggers with `git for-each-ref refs/tags --format="%(refname:short) %(taggeremail)"`;
- secrets: no tokens, private keys, credentials, or `.env` files in the files or the history being published;
- paths: no absolute local paths, such as a user's home folder;
- private folders: nothing outside the allowlist, such as notes, vaults, continuity ledgers, or local profiles;
- licenses: every bundled asset, font, sound, and library permits redistribution, with its required notices included.

Report the checks first: the deliverables and any archive, synchronized files, each check as `Pass`, `Fail`, `Not Run`, or `Blocked`, candidate and archive digests, file count, and remaining blockers. **Hard rule:** never call a release ready when a required check failed or did not run.

Then stop. **Hard rule:** publish only on the user's explicit instruction for this candidate, given after that report, and never while a required check failed or did not run. Without that instruction the agent never pushes, tags, uploads, or publishes. Publishing, deleted untracked files, and other external side effects can't be undone with git.

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
