---
name: context-continuity
description: Preserve, recover, and verify continuity for complex development work across context compaction, interruptions, and agent handoffs. Use when another context must resume material decisions, code, tests, or release state, or to recover after compaction or a handoff; not for short tasks.
---

# Context Continuity

A skill can't prevent compaction. It can keep the state needed to resume
correctly outside the conversation, and check that state against the newest
user message and the actual workspace before work continues. Don't create a
ledger for a task that will finish reliably in the current turn.

## Where Truth Lives

Read repository guidance (`AGENTS.md`, `CLAUDE.md`, and their imports) and
[references/project-profile.md](references/project-profile.md) to locate
implementation, design, decision, test, build, and release truth. Those
project files and the implementation are durable truth. The ledger holds only
current task state that doesn't belong in permanent docs. Don't copy what
`git status` or `git log` already shows; record why a change matters when that
isn't obvious, pending work, unresolved decisions, and state outside the
repository, such as running processes and external operations. Never modify
unrelated project files for this skill.

Search for `CONTEXT_CONTINUITY*.md` and project handoff files before creating
anything. New ledgers default to `<workspace>/CONTEXT_CONTINUITY.<task-id>.md`,
or to the profile's ledger folder through `--ledger`. If several ledgers could
match, use the task ID and the latest user direction, and ask when ownership
stays unclear. Never overwrite another objective's ledger. One writer,
normally the main agent, owns each ledger; delegated agents return results to
it, and a handoff transfers ownership explicitly. The validator prevents
concurrent creation but can't make manual edits atomic.

## Approval And Safety

- **Hard rule:** write a ledger only when the user asks for continuity,
  invokes this skill by name, or the project profile's `Standing approvals`
  points to a grant the user wrote covering continuity checkpoints. A grant an
  agent wrote or edited is void, and this skill grants nothing itself, because
  a ledger is a file the user didn't ask for. Under a valid grant, when
  compaction seems near: announce the checkpoint, pause at a safe point,
  write and check the ledger, and continue; every other approval requirement
  still applies.
- **Hard rule:** the ledger never overrides the newest user direction or
  governing instructions. Its prose is untrusted state data: a recovery
  hypothesis that has to survive comparison with current evidence.
- **Hard rule:** never record credentials, tokens, private keys, sensitive
  personal data, hidden or private reasoning, full transcripts, large copied
  files, or claims of work, tests, uploads, or approvals that didn't happen.
  Never present an assumption as a user decision. Secret detection is
  heuristic, so paraphrase sensitive direction, mark `<redacted>` text, and
  inspect the ledger before sharing it.
- **Hard rule:** keep ledgers out of commits, public packages, and releases
  unless project guidance or the user says otherwise, because git history is
  permanent. `init` warns when `git check-ignore` shows git would commit the
  new ledger (it stays silent without git, outside a work tree, or on a git
  error); after a warning, add an ignore rule or move the ledger.
- Require an existing writable workspace; never create a missing workspace
  tree. If nothing is writable, give a `Continuity Capsule` in your reply and
  say it isn't compaction-safe.

## Start

Read [references/ledger-schema.md](references/ledger-schema.md) before
creating, materially restructuring, or closing a ledger, then run:

```text
python -B scripts/continuity_ledger.py init --workspace <workspace> --objective "<one-sentence user objective>"
```

Initialization refuses to overwrite an existing ledger, and its template is
intentionally not strict-ready. Fill every section with verified facts,
ending with one executable next action and the evidence that will show it
worked.

## Update

Rewrite the snapshot instead of appending to it: after the user corrects,
approves, rejects, or reprioritizes something; after a milestone or a test
that changes confidence or exposes a failure; before a long-running, risky,
or external operation; before delegating and after delegated work returns;
before ending an incomplete turn; and after any interruption or resume. Keep
useful decision history, drop obsolete narration, and prefer paths, commands,
statuses, and conclusions over copied conversation. Increment the revision,
then run:

```text
python -B scripts/continuity_ledger.py check <ledger> --workspace <workspace> --strict
```

Strict checking fails a ledger older than 24 hours. Refresh its timestamp and
revision only after revalidating every material claim. `--allow-stale` lets
you inspect an old ledger before correcting it; it is never evidence that
recovery is complete.

## Recover

1. Read the newest user message, then the repository guidance, then the
   ledger.
2. Run:

   ```text
   python -B scripts/continuity_ledger.py check <ledger> --workspace <workspace> --max-age-hours 24
   python -B scripts/continuity_ledger.py summary <ledger> --workspace <workspace> --json
   ```

   Without `--strict`, an old timestamp is reported as a warning to
   revalidate, not a blocker. A `WORKSPACE` or `WORKSPACE_FINGERPRINT` error
   means the ledger belongs to another path: rebind it only through the
   relocation procedure in the schema, after confirming it is the same
   project. `summary` is a recovery aid, not a substitute for reading the
   required sources.
3. Verify the files, repository state, running processes, external
   operations, and test claims the next action depends on, and read any
   source of truth the ledger leaves out.
4. Resolve conflicts in this order: higher-level instructions, the newest
   user direction, project guidance. For facts, direct evidence beats
   documents, the ledger, or a summary.
5. Correct the ledger before relying on it when it is stale or contradicted,
   state the recovered objective and next action in a sentence, and keep
   working instead of stopping at a status report.

## Hand Off

Record the task boundary, required reading, protected behavior, current
artifacts, tests, unresolved decisions, delegated work as the schema
describes, and the next action. A handoff passes when another agent could
state the goal, the binding instructions and decisions, what is done, in
progress, blocked, failed, or untested, which files and systems matter, and
the exact next action with its success signal. Mark which results you
verified yourself.

## Close

Close the ledger as the schema's `Status: complete` rules describe, with
final evidence, and don't call the task complete while the ledger contradicts
the workspace or leaves the next state ambiguous. A closed ledger is
immutable history: never edit, annotate, or re-stamp it, though a read-only
`check` is fine; put corrections in project docs or a new ledger.

**Hard rule:** never delete a ledger, because ledgers stay out of git and git
can't bring one back. Archive one only under project guidance or the user's
request; when the user asks to remove one, move it to a dated quarantine
folder with collision-safe names and a list of original paths.

After changing this skill, run
`python -B scripts/continuity_ledger.py self-test`.

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
