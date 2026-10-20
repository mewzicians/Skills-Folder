# Specialize The Suite For One Game

The skills in `skills/` are a reusable core. To fit them to one game, add a
project profile first, and a specialized skill only where the profile is not
enough. Neither step changes this repository.

## 1. Add A Project Profile

Copy `templates/GAME_PROJECT_PROFILE.template.md` into the game repository as
`GAME_PROJECT_PROFILE.md` and fill in its fields. Every generic skill except
`game-skill-auditor`, which audits skills rather than a game, reads it through
its `references/project-profile.md`.

The profile holds pointers: repository-relative paths, status labels,
commands, and yes-or-no answers. Rules stay in the files it points to, and the
repository's own instruction files, such as `AGENTS.md` and `CLAUDE.md`, win
over it. A blank field means the generic default.

## 2. Specialize A Skill Only When It Pays

When a game needs procedure that no generic skill carries, such as an engine's
build steps, a balance metric, or a release gate, write a specialized skill
with your agent host's own skill-creator. This suite no longer ships one.

- Start from the generic skill and keep its trigger, evidence, status, and
  completion contract intact.
- Add only the game's paths, terminology, invariants, tests, and release
  gates. Keep reusable craft in the generic skill.
- Give it a distinct name, and a description that says when to use it instead
  of the generic skill.
- Check it before use:

  ```text
  python -B tools/validate_skill.py --level spec path/to/skill
  python -B skills/game-skill-auditor/scripts/audit_skill.py path/to/skill --strict
  ```

## 3. Keep Volatile Status Out Of Skills

A skill is loaded into many future sessions, so anything that changes between
sessions goes stale inside it. Never copy current project status into a
specialized skill: candidate or build hashes, test results, open questions,
approval states, dates, or release readiness. Point to the document that holds
that status, such as a handoff or decision ledger, and let the skill read it
when it runs.

## History

Versions 1.0.x shipped `game-skill-creator` and `game-skill-installer`, adapted
from OpenAI Codex system skills. Version 1.1 removed both, in favor of each
host's own skill-creator and this guide. The `v1.0.0` tag still contains them.
