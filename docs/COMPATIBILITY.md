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
| Every installer decision and refusal, rollback after a failure injected at each swap step, the ledger write, and staging, recovery of an interrupted run, and backups outside every skills folder (`tests/install/test_install.py`) | Pass |
| The installer opens no socket, in process and in a real run | Pass |
| The real skill folders, state folders, and checkout are unchanged after the installer tests | Pass |
| A Windows junction inside a skill, or as an installed copy, is refused | Pass |
| A symbolic link inside a skill is refused | Not Run on Windows, which needs extra privileges to create one; CI runs it on macOS and Linux |
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
| Codex installing the plugin from `.agents/plugins/marketplace.json` and the portable `plugin.json` | Not Run |
| A ChatGPT workspace admin importing this repository's marketplace, and Codex in the ChatGPT desktop app reading a project's primary folder | Not Run |
| Codex honoring `policy.allow_implicit_invocation: false` for the three explicit-only skills | Not Run; no model runs were made |
| macOS and Linux, and Python 3.11, 3.14, and 3.15 | Not Run until the GitHub Actions workflow runs on a push |

## What The Suite Assumes About Each Host

From the hosts' documentation, as read in October 2026:

- **Codex** reads personal skills from `$HOME/.agents/skills` and project
  skills from `.agents/skills`. It still reads the older `$CODEX_HOME/skills`
  (by default `~/.codex/skills`), where version 1.0 installed, so the
  installer treats that folder as a second Codex folder when it checks for
  duplicate names. Codex resolves `CODEX_HOME` with no `~` expansion and
  requires the folder to exist.
- **Claude Code** reads personal skills from `~/.claude/skills` (or
  `$CLAUDE_CONFIG_DIR/skills`), project skills from `.claude/skills`, and
  plugin skills from a plugin's `skills/` folder. It does not read
  `.agents/skills`.
- **ChatGPT** reaches these skills only through a workspace admin's plugin
  marketplace import or through Codex in the desktop app. It documents no
  way for an individual to upload a `SKILL.md`.
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
- Explicit-only skills are enforced only in Codex. Claude Code may still
  offer one when a request matches its description.
