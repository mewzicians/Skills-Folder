# Compatibility

Recorded on 2026-10-20 for version 1.1.0. This page separates what was run
on a real machine from what rests only on each host's documentation. It is a
point-in-time record: the workflow badge in the README shows the current
automated result.

## Verified On A Real Machine

One Windows 11 machine with Python 3.13, before the 1.1.0 tag:

| Check | Result |
| --- | --- |
| `install.py` install, status, and uninstall for every target (`codex`, `codex-legacy`, `codex-project`, `claude`, `claude-project`, and `--dest`), in temporary home folders | Pass |
| Every installer decision and refusal; rollback after a failure injected at the first, second, fifth, and ninth of nine swap renames, at the ledger write, and in staging; recovery of an interrupted run; Ctrl+C during the swap, the rollback, a recovery, and the cleanup; a second run refused while the first holds the lock; ledger names and journal paths outside a run's folders refused; operating-system errors reported without a traceback; and backups outside every skills folder (`tests/install/test_install.py`) | Pass |
| The installer opens no socket, in process and in a real run | Pass |
| The real skill folders, state folders, and checkout are unchanged after the installer tests | Pass |
| A Windows junction inside a skill, or as an installed copy, is refused | Pass |
| A symbolic link inside a skill is refused | Not Run on Windows, which needs extra privileges to create one; CI is configured to run it on macOS and Linux (not yet run on this branch) |
| Removing and recovering folders without read or search permission (the POSIX-only installer tests) | Not Run on Windows; CI is configured to run them on macOS and Linux (not yet run on this branch) |
| `tools/verify_package.py`, `tools/validate_skill.py`, the strict auditor on all 12 skills, every test under `tests/`, and both bundled self-tests | Pass |
| The portable `plugin.json` against the Agent Plugins 1.0.0 schema, with the `jsonschema` package | Pass |
| The Python 3.11 floor, checked statically with `vermin` | Pass; no 3.11 interpreter was run |

## Documented But Not Verified

These routes follow each vendor's documentation as read in October 2026. None
was run, because no host CLI or model ran on the test machine.

| Route | Status |
| --- | --- |
| Claude Code plugin marketplace: `/plugin marketplace add` and `/plugin install`, and `claude plugin validate` on the manifests | Not Run |
| Claude Code loading the skills that `install.py` copies into `~/.claude/skills` or `.claude/skills`, and listing them with `/skills` | Not Run |
| Codex loading the skills that `install.py` copies into `~/.agents/skills`, `$CODEX_HOME/skills`, or `.agents/skills` | Not Run |
| Codex installing the plugin after `codex plugin marketplace add mewzicians/Skills-Folder` and `/plugins`, from `.agents/plugins/marketplace.json` and the portable `plugin.json` | Not Run |
| ChatGPT: standalone skills in the ChatGPT desktop app, as in Codex CLI and the IDE extension; the desktop app reading `$REPO_ROOT/.agents/plugins/marketplace.json`, the legacy `$REPO_ROOT/.claude-plugin/marketplace.json`, and a personal `~/.agents/plugins/marketplace.json`; `codex plugin marketplace add owner/repo`; and a workspace admin importing the repository for an organization | Not Run |
| Codex honoring `policy.allow_implicit_invocation: false` for the three explicit-only skills | Not Run; no model runs were made |
| macOS and Linux, and Python 3.11, 3.14, and 3.15 | Not Run until the GitHub Actions workflow runs on a push |

## What The Suite Assumes About Each Host

From each host's documentation and, where marked, its source, as read in
October 2026:

- **Codex** reads personal skills from `$HOME/.agents/skills` and project
  skills from `.agents/skills`. Its source also reads `$CODEX_HOME/skills`
  (by default `~/.codex/skills`), where version 1.0 installed, and marks that
  location deprecated, kept for backward compatibility
  ([`host_roots.rs`](https://github.com/openai/codex/blob/cb00a67569450aea2fdb1b1f31fc042fc0b5416f/codex-rs/ext/skills/src/host_roots.rs)). Move skills from there to
  `$HOME/.agents/skills`; the README's
  [Upgrading from 1.0.x](../README.md#upgrading-from-10x) gives the
  commands. Until then the installer treats that folder as a second Codex
  folder when it checks for duplicate names. Codex's source names a skill by
  its frontmatter `name`, or else its folder's name, and finds every
  `SKILL.md` at most six levels down outside hidden folders
  ([`loader/`](https://github.com/openai/codex/tree/cb00a67569450aea2fdb1b1f31fc042fc0b5416f/codex-rs/ext/skills/src/loader)), so the installer's duplicate check for a Codex
  target does the same. Its source resolves `CODEX_HOME` with no `~`
  expansion and requires the folder to exist.
- **Claude Code** reads personal skills from `~/.claude/skills` (or
  `$CLAUDE_CONFIG_DIR/skills`), project skills from `.claude/skills`, and
  plugin skills from a plugin's `skills/` folder. It does not read
  `.agents/skills`.
- **ChatGPT** (documented, not verified): the ChatGPT desktop app uses
  standalone skills, as Codex CLI and the IDE extension do. Its plugin
  directory reads a repository's `$REPO_ROOT/.agents/plugins/marketplace.json`
  and the legacy `$REPO_ROOT/.claude-plugin/marketplace.json`, and a personal
  `~/.agents/plugins/marketplace.json`. Opened on this repository, the app
  may therefore see both of its marketplaces, which share the name
  `skills-folder`; how it handles two marketplaces with one name is not
  verified. `codex plugin marketplace add owner/repo` adds a marketplace from
  the command line, and for an organization a workspace admin can import a
  repository.
- **Plugins.** The repository root is one plugin, `game-dev-skills`, in the
  `skills-folder` marketplace. Claude Code reads `.claude-plugin/`; Codex
  and other Agent Plugins clients read the portable `plugin.json`, whose
  Codex-specific data sits under `extensions.com.openai`, and Codex reads
  `.agents/plugins/marketplace.json`. The plugin has no `agents/` folder.

## Known Limits

- The duplicate-name check covers the personal folders of the target's host
  and, for a project target, that project. It cannot know every project you
  will open, so a project-level copy elsewhere can still shadow a personal
  one.
- `--dest` installs skip the duplicate-name check, because the installer
  cannot tell which host reads that folder.
- One install or uninstall runs at a time per user state folder, through an
  operating-system file lock. A network file system may not honor that
  lock, and recovery's check for a still-running process sees only
  processes on the same machine.
- Explicit-only skills are documented as enforced only in Codex (not
  verified). Claude Code may still offer one when a request matches its
  description.
