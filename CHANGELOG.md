# Changelog

Every notable change to this suite is recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The root `VERSION`
file, both plugin manifests, and the newest entry below always name the same
version.

## [Unreleased]

### Changed

- **Breaking:** `game-context-continuity` is renamed to `context-continuity`,
  and `game-skill-auditor` to `skill-auditor`. Neither depends on a game, so
  their names, descriptions, and Codex display names no longer say so. Call
  them as `$context-continuity` and `$skill-auditor`. `install.py` offers to
  move the old folders to backups; see the README's
  [Upgrading from 1.1.x](README.md#upgrading-from-11x).
- When `install.py` moves a renamed or removed skill to backups, it also
  removes that skill's install record, and its messages name the skill that
  replaced it.

## [1.1.0] - 2026-10-20

Items marked **Breaking** change how you install or invoke the suite. To
upgrade from 1.0.x, follow the README's
[Upgrading from 1.0.x](README.md#upgrading-from-10x).

### Added

- `install.py`, a standard-library installer with `install`, `status`, and
  `uninstall`, for Codex, Claude Code, project folders, or any folder. It
  shows a plan and asks first; upgrades older copies and refuses newer,
  unaccounted-for, or duplicate-name copies unless told otherwise; detects
  the three retired 1.0 skills and offers to back them up; stages, swaps,
  and rolls back changes together; finishes or rolls back an interrupted
  run on the next run without deleting any backup; runs one change at a
  time under a lock;
  keeps backups and its install record in the user state folder, outside
  every skills folder; and never uses the network.
- One root plugin, `game-dev-skills`, in the `skills-folder` marketplace:
  `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` for
  Claude Code, a portable Agent Plugins 1.0.0 `plugin.json`, and
  `.agents/plugins/marketplace.json` for Codex.
- `tools/verify_package.py`, a standard-library verifier that reports every
  problem in one run: skill structure, portable frontmatter, the text policy,
  private project names, generated debris, dangling symbolic links, generated-copy and
  identical-file drift, the explicit-only policy and wording, the plugin
  manifests and their documented Codex values, one version across `VERSION`,
  both manifests, and the newest changelog entry, relative links and images
  in the README, changelog, and `docs/` (also `--metadata`), description and
  body budgets, and a neutrality lint (also `--lint`) for self-granted
  permissions, author-specific names, personal paths and addresses, private
  vault names, and committed continuity ledgers.
- `tools/validate_skill.py` and `tools/lib/skill_frontmatter.py`, a
  standard-library frontmatter validator with portable and spec levels and a
  generated test corpus. It expands glob patterns itself, so the same
  command works in PowerShell, cmd, and POSIX shells.
- A bundled structural validator inside `game-skill-auditor`, so the auditor
  needs neither PyYAML nor Codex. It fails on everything Codex's validator
  rejects.
- `docs/SKILL_SCHEMA.md`, `docs/SPECIALIZE.md`, `docs/COMPATIBILITY.md`, a
  root `VERSION` file, and this changelog.
- Tests for the frontmatter schema, the package verifier, the skill scripts,
  the archive builder, and the installer, and a CI workflow on Windows,
  macOS, and Linux with Python 3.11 and 3.15, plus 3.14 on Linux.

### Changed

- **Breaking:** Renamed `game-github-package` to `game-release`. Invoke it as
  `$game-release` in Codex or `/game-release` in Claude Code.
- **Breaking:** The installer's default Codex folder is `~/.agents/skills`,
  where Codex documents personal skills, instead of `$CODEX_HOME/skills`.
  The old folder is still available as `--target codex-legacy`.
- **Breaking:** Every `SKILL.md` follows a new portable frontmatter schema
  ([docs/SKILL_SCHEMA.md](docs/SKILL_SCHEMA.md)): only `name`, `description`,
  `license`, and one-level string `metadata`; UTF-8 with LF and no BOM; no
  tabs, block scalars, or multi-line values; and descriptions of at most 300
  characters. Claude Code-only keys, `compatibility`, and `allowed-tools` are
  rejected.
- **Breaking:** Every script needs Python 3.11 or later.
- **Breaking:** `game-release`, `game-qa-cleanup`, and
  `game-full-verification` are explicit-only: they set Codex's switch for
  running only when named, and their descriptions tell Claude Code to wait
  for an explicit request.
- The README is rewritten for first-time builders, with install steps for
  Claude Code and Codex and a Validation section that lists only what CI
  runs.
- Every description is host-neutral and trigger-accurate, and each skill
  body has an estimated-token cap.
- The project profile template holds only pointers: repository-relative
  paths, labels, commands, and yes-or-no answers. Eleven skills read it
  through identical `references/project-profile.md` routers;
  `game-skill-auditor` does not.
- `game-skill-auditor`'s method detail moved into on-demand references, and
  it audits explicit-only skills by named invocation.
- `music-composer` is a lean core with routed references. It classifies a
  request before reading any project file and changes the status of an
  audition only with the user's approval.
- `game-release` separates maintained deliverables from on-demand archives,
  runs identity, secret, path, private-folder, and license checks before
  anything is published, and then stops until the user says to publish.
- `game-qa-cleanup` proposes every move, retag, or removal and performs only
  the action the user approved; `game-full-verification` gained read-only
  consistency checks; `game-implement` does not publish.
- `game-balance-lab` shows as "Balance Sim Lab" in Codex.
- `.gitattributes` pins LF line endings for every text file.

### Removed

- **Breaking:** Removed `game-skill-creator` and `game-skill-installer`,
  which were adapted from OpenAI Codex system skills. Use your agent host's
  own skill-creator; [docs/SPECIALIZE.md](docs/SPECIALIZE.md) explains how to
  specialize the suite. The `v1.0.0` tag still holds both.
- **Breaking:** Removed `install-skills.ps1`, `verify-package.ps1`, and
  `MANIFEST.sha256`. `install.py` and `tools/verify_package.py` replace the
  scripts. The manifest pinned CRLF bytes that failed on LF checkouts and on
  GitHub's Download ZIP; git's own object hashes now identify the bytes.

### Fixed

- Scripts name their text encoding, write files atomically, and reconfigure
  stdout and stderr, so they no longer misread files in a non-UTF-8 locale
  or crash on non-ASCII output.
- The archive builder refuses to build when git cannot answer for a git work
  tree, treats Windows junctions as links, and refuses files that resolve
  outside the source.
- The 1.0.0 README's list of release checks included checks that no
  committed file performed; it is kept below as history.

### Security

- A standing approval counts only when it points to the user's own written
  grant; a grant that an agent wrote or edited is void.
- `game-release` checks author, committer, tagger, and co-author addresses
  before publishing.
- The archive builder excludes common secrets and signing material by
  default, says plainly that its excludes are a denylist, and offers
  `--allowlist`, its only fully fail-closed mode.
- The auditor's evidence assessor no longer runs a script that an evidence
  manifest names before trusting it: it replays only its own pinned bundled
  validator, Codex's validator under `CODEX_HOME`, or the bundled audit beside
  it, and replays its own scripts isolated with `-I`.
- CI pins its actions by commit, reads repository contents only, and
  installs its one test dependency, PyYAML, by hash. Dependabot
  (`.github/dependabot.yml`) proposes weekly updates to the pinned actions
  and to that requirement.

## [1.0.0] - 2026-08-18

### Added

- Fourteen skills: `game-plan`, `game-balance-lab`, `game-playtest-analysis`,
  `game-implement`, `game-debug`, `game-ux-audit`, `music-composer`,
  `game-qa-cleanup`, `game-full-verification`, `game-github-package`,
  `game-context-continuity`, `game-skill-auditor`, `game-skill-creator`, and
  `game-skill-installer`.
- `install-skills.ps1`, which copied every skill into `$CODEX_HOME\skills`
  or `~\.codex\skills` and backed up replaced folders inside that folder.
- `verify-package.ps1` and `MANIFEST.sha256`, and a GitHub workflow on
  Windows.
- `templates/GAME_PROJECT_PROFILE.template.md`.

Recorded as history: the 1.0.0 README said the release package was checked
for:

- valid skill structure and matching metadata;
- project-neutral language and portable paths;
- strict static-audit findings;
- continuity and auditor adversarial self-tests;
- manifest completeness and SHA-256 byte integrity;
- backup-preserving installation;
- deterministic archive inventory; and
- extraction and clean installation from the archive.

It also said the GitHub workflow ran the package verifier, the official
skill validator, the strict auditor, and both bundled self-test suites on
Windows. These describe that release and were not re-run for this record.
Version 1.1 found no committed test for the installation or archive checks,
and found that the manifest failed on LF checkouts.

The version links below resolve once the `v1.0.0` and `v1.1.0` tags are
pushed to GitHub.

[1.1.0]: https://github.com/mewzicians/Skills-Folder/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/mewzicians/Skills-Folder/releases/tag/v1.0.0
