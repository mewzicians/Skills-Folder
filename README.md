<div align="center">

# Skills for Agent Game Development

Reusable Codex workflows for designing, building, testing, balancing,
documenting, composing for, and releasing games.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-0B7285.svg)](LICENSE)
![Skills](https://img.shields.io/badge/skills-14-2F9E44.svg)
![Validation](https://img.shields.io/badge/validation-passing-2F9E44.svg)

</div>

## Why This Exists

Game projects need agents that can retain decisions, respect implementation
boundaries, test the rules players actually face, and distinguish evidence
from confident guesses. This suite turns those needs into portable skills
without tying them to one engine, genre, repository layout, or game.

Each workflow has a reusable core. A single `GAME_PROJECT_PROFILE.md` can then
teach the suite about a particular game's sources of truth, status vocabulary,
tests, mirrors, constraints, and release gates.

## Included Skills

| Area | Skills |
| --- | --- |
| Design | `game-plan`, `game-balance-lab`, `game-playtest-analysis` |
| Development | `game-implement`, `game-debug` |
| Player experience | `game-ux-audit`, `music-composer` |
| Quality | `game-qa-cleanup`, `game-full-verification` |
| Release | `game-github-package` |
| Agent tooling | `game-context-continuity`, `game-skill-auditor`, `game-skill-creator`, `game-skill-installer` |

## Quick Start

Clone the repository, then install every skill:

```powershell
.\install-skills.ps1
```

The installer writes to `$CODEX_HOME\skills` when `CODEX_HOME` is set and
otherwise uses `~\.codex\skills`. Existing skill folders are backed up before
replacement.

Validate the complete package at any time:

```powershell
.\verify-package.ps1
```

## Adapt It To A Game

1. Copy `templates/GAME_PROJECT_PROFILE.template.md` into the game repository.
2. Rename the copy to `GAME_PROJECT_PROFILE.md`.
3. Fill in authoritative files, statuses, technical invariants, tests,
   distribution paths, and project-specific extensions.
4. Keep generic workflows in the skill core. Put game-specific terminology,
   mechanics, commands, and paths in the profile or focused references.

This structure makes it easy to create a focused skill suite for one game
without contaminating the reusable source skills.

## Design Principles

- Read implementation and durable project truth before acting.
- Preserve explicit approval and status boundaries.
- Prefer legal player actions and reproducible evidence.
- Treat passing automation as evidence, not proof of player experience.
- Keep implementation, verification, and cleanup responsibilities distinct.
- Report unrun and blocked checks honestly.
- Preserve existing work and make the smallest durable change.

## Validation

The release package is checked for:

- valid skill structure and matching metadata;
- project-neutral language and portable paths;
- strict static-audit findings;
- continuity and auditor adversarial self-tests;
- manifest completeness and SHA-256 byte integrity;
- backup-preserving installation;
- deterministic archive inventory; and
- extraction and clean installation from the archive.

The GitHub workflow runs the package verifier, official skill validator,
strict auditor, and both bundled self-test suites on Windows.

## Repository Layout

```text
skills/                    Installable skill folders
templates/                 Project-specialization profile
install-skills.ps1         Backup-preserving suite installer
verify-package.ps1         Standalone package verifier
MANIFEST.sha256            Complete file-integrity inventory
```

## License

Licensed under Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
Bundled upstream components retain their included license notices.
