# Install

How to get the skills onto a host, keep them current, and remove them. The
[README](../README.md#install) has the short version, and
[COMPATIBILITY.md](COMPATIBILITY.md) says which routes were run on a real
machine.

## Before you start

| Route | You need |
| --- | --- |
| Claude Code plugin (documented, not verified) | Claude Code. No Python. |
| Codex plugin (documented, not verified) | Codex CLI. No Python. |
| `install.py` (Codex or Claude Code) | Python 3.11 or later, and the files from [Get the files](#get-the-files). |
| Copy by hand | Nothing extra: copy each folder in `skills/` into your host's skills folder. You lose the upgrade checks and backups. |

`install.py` is a plain Python script, so it needs no PowerShell execution
policy change and no build step. Use the command for your system:

| System | Run it as | Watch out for |
| --- | --- | --- |
| Windows | `py -3 install.py ...` (the Python launcher), or `python install.py ...` | If `python` or `python3` opens the Microsoft Store or prints nothing, you are hitting an App Execution Alias, not Python. Install Python 3.11 or later from python.org, or turn the aliases off in Settings > Apps > Advanced app settings > App execution aliases. |
| macOS | `python3 install.py ...` | The `python3` that comes with Apple's Command Line Tools is often 3.9, which is too old. Install 3.11 or later from python.org or Homebrew. |
| Linux | `python3 install.py ...` | Debian 12 ships 3.11 and Ubuntu 24.04 ships 3.12. RHEL 9 and its rebuilds default to 3.9: install the `python3.11` package and run `python3.11 install.py ...`. |

Check your version with `py -3 --version` or `python3 --version`. The
examples below say `python`; use your system's command instead.

## Get the files

Cloning is best, because updating is then one command:

```text
git clone https://github.com/mewzicians/Skills-Folder.git
cd Skills-Folder
```

No git? On the repository page choose **Code**, then **Download ZIP**,
extract it, and open a terminal in the extracted folder. Everything below
works the same way; to update later, download a fresh ZIP.

## Install

### Claude Code

**Plugin marketplace (documented, not verified on a real install).** Inside
Claude Code, run:

```text
/plugin marketplace add mewzicians/Skills-Folder
/plugin install game-dev-skills@skills-folder
```

Plugin skills carry the plugin's name, so you invoke them as, for example,
`/game-dev-skills:game-release`.

**install.py (tested in temporary folders).** From the repository folder:

```text
python install.py install --target claude
```

This copies the skills to `~/.claude/skills`, or to
`$CLAUDE_CONFIG_DIR/skills` when you set `CLAUDE_CONFIG_DIR`. Use one route,
not both, so each skill appears once.

### Codex

```text
python install.py install
```

This copies the skills to `~/.agents/skills` (on Windows,
`%USERPROFILE%\.agents\skills`), where Codex looks for your personal skills.

**Plugin marketplace (documented, not verified).** In a terminal, run:

```text
codex plugin marketplace add mewzicians/Skills-Folder
```

Then start Codex, type `/plugins`, and install `game-dev-skills` from the
`skills-folder` marketplace. Plugin skills carry the plugin's name, so a
plugin install names them like `$game-dev-skills:game-release`; the names in
this guide and the README, such as `$game-release`, are for `install.py` installs. Use one
route, not both, so each skill appears once.

### What the installer does

`install.py` prints a plan and asks before it changes anything (add `--yes`
to skip the question). For each skill it installs a missing one, skips an
identical one, and upgrades an older one after backing it up. It refuses,
and changes nothing, when:

| It reports | Meaning | To go ahead anyway |
| --- | --- | --- |
| newer | The installed copy has a newer recorded version. | `--allow-downgrade` |
| unrecorded, modified, or same-version | The copy differs, and this installer did not put those bytes there: you edited it, another tool or version 1.0 installed it, or the skill changed without a new `VERSION`. | `--replace-modified` (the old copy is backed up first) |
| would share its name | Another skill with that name is in a folder the same host loads, such as `~/.codex/skills`. For Codex this includes a renamed folder whose `SKILL.md` has that name, and copies in subfolders. Both paths are printed. | Remove one copy, or `--allow-duplicate-names`. For version 1.0 copies, see [Upgrading from 1.0.x](#upgrading-from-10x). |
| link | The installed copy is a symbolic link or junction. | Replace the link by hand. |
| unreadable | The installed copy, or a folder in it, cannot be read. | Fix its permissions. |

It also offers to move three skills that version 1.0 installed and 1.1
retired (`game-github-package`, `game-skill-creator`, and
`game-skill-installer`) to backups, and asks separately before it does.
Changes are staged next to the skills folder and swapped in together; if
anything fails, or you press Ctrl+C, every change is rolled back. If it is
interrupted again during that rollback, or after every change is already
made, it says so, and the next run finishes the job without deleting any
backup; see
[If a run says "Recovery is incomplete"](#if-a-run-says-recovery-is-incomplete).
Only one install or uninstall runs at a time: a second one refuses until the
first finishes. It never uses the network.

Other places to install:

| Target | Skills folder | Loaded by |
| --- | --- | --- |
| `--target codex` (the default) | `~/.agents/skills` | Codex, in every project |
| `--target codex-legacy` | `$CODEX_HOME/skills`, or `~/.codex/skills` when `CODEX_HOME` is unset | Codex, from a personal folder that its source marks deprecated and still reads for backward compatibility. Version 1.0 installed here; prefer `--target codex`. |
| `--target codex-project --project DIR` | `DIR/.agents/skills` | Codex, in that project; also Codex in the ChatGPT desktop app when `DIR` is the project's primary folder (documented, not verified) |
| `--target claude` | `~/.claude/skills`, or `$CLAUDE_CONFIG_DIR/skills` | Claude Code, in every project |
| `--target claude-project --project DIR` | `DIR/.claude/skills` | Claude Code, in that project |
| `--dest DIR` | `DIR` | Any other tool that reads `SKILL.md` folders |

`CODEX_HOME` is read the way Codex reads it: an empty value counts as unset,
`~` is not expanded, and the folder must already exist.

### Check that it worked

Start a new agent session and type `/skills`, in Codex or Claude Code, to
see the list. On the command line, `python install.py status` shows what is
installed in each folder, which copies are current, and any duplicates.

## Update, uninstall, and backups

- **Update:** run `git pull` (or download a fresh ZIP), then run the same
  `python install.py install` command again. Current skills are skipped and
  older ones are upgraded with a backup. A skill whose files changed without
  a new `VERSION`, as between releases, is refused as `same-version`,
  because the installer cannot tell that change from your own edit. Check
  that you did not edit the installed copy, then run the command again with
  `--replace-modified`; the old copy is backed up first.
- **Uninstall:** `python install.py uninstall`, with the same `--target` you
  installed with. Skills move to a backup folder; nothing is deleted. It
  refuses copies you changed unless you add `--include-modified`.
- **Backups:** each run that replaces or removes a skill writes one dated
  folder with a `backup.json` list, outside every skills folder, so your
  agent never loads a backup:

  | System | Backup folder |
  | --- | --- |
  | Windows | `%LOCALAPPDATA%\skills-folder\backups` |
  | macOS | `~/Library/Application Support/skills-folder/backups` |
  | Linux | `$XDG_STATE_HOME/skills-folder/backups`, or `~/.local/state/skills-folder/backups` |

  To restore a skill, copy its folder from the backup into your skills
  folder. The install record, `install-ledger.json`, sits beside the
  `backups` folder.

### If a run says "Recovery is incomplete"

A run that is interrupted, by a crash, a closed terminal, or a second
Ctrl+C, leaves `journal.json` beside `install-ledger.json`. The next install
or uninstall offers to finish that run or roll it back. A rollback first
moves every skill back, then restores the install record, then cleans up,
so running the command again never repeats a step that already worked. A
recovery never deletes a backup; when it rolls a run back, it prints
`kept the backup` and the folder's path.

If a run prints `Recovery is incomplete` or `The rollback is incomplete`:

1. Read each `PROBLEM` line. Most often a program holds a file open, or a
   skill was edited after the interrupted run put it there, which the
   installer never overwrites.
2. Close the agent host or editor, or move the edited copy out of the
   skills folder, then run the same command again. Each run retries only
   what is left.
3. If the same problem stays, the journal no longer matches the folders,
   for example after it was restored from file history. Compare the skills
   folder with the backup named in the output, copy back what you need, then
   move `journal.json` away from `install-ledger.json` and run the command
   again.

## Upgrading from 1.1.x

After 1.1.x, two skills that work on any project, not only games, dropped
the `game-` prefix: `game-context-continuity` is now `context-continuity`,
and `game-skill-auditor` is now `skill-auditor`.

1. Run `python install.py install`. It installs the new names and offers to
   move the two old folders to backups, which also removes them from the
   install record. Add `--keep-retired` to leave the old folders in place.
2. If you call either skill by name, use `$context-continuity` and
   `$skill-auditor` in Codex, or `/context-continuity` and `/skill-auditor`
   in Claude Code.

## Upgrading from 1.0.x

Version 1.0 installed with `install-skills.ps1` into `$CODEX_HOME\skills` or
`~\.codex\skills` and kept no install record. Whenever it replaced a skill,
it left a `.game-skill-suite-backup-*` folder inside that skills folder.
Version 1.1 removed `game-skill-creator` and `game-skill-installer`, renamed
`game-github-package` to `game-release`, and replaced the PowerShell scripts
with Python: `install.py` and `tools/verify_package.py`.

1. See what you have: `python install.py status`.
2. Choose one:
   - **Move to the new default folder (recommended):**
     `python install.py uninstall --target codex-legacy --include-modified`,
     then `python install.py install`.
     [Codex's source](https://github.com/openai/codex/blob/cb00a67569450aea2fdb1b1f31fc042fc0b5416f/codex-rs/ext/skills/src/host_roots.rs)
     marks the old folder, `$CODEX_HOME/skills`, as deprecated and reads it
     only for backward compatibility.
   - **Keep the old folder:**
     `python install.py install --target codex-legacy --replace-modified`.
     The installer has no record of the 1.0 copies, so it needs
     `--replace-modified`. It backs up each old copy before replacing it and
     offers to move the retired skills to backups.
3. Installing into the new default while the 1.0 copies are still in the
   old folder is refused, because Codex would load both; the refusal prints
   both commands above.
4. The installer leaves the old `.game-skill-suite-backup-*` folders alone.
   Move them out of the skills folder yourself once you no longer need them.

[CHANGELOG.md](../CHANGELOG.md) lists every breaking change in 1.1.0.
