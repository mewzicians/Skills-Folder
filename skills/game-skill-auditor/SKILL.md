---
name: game-skill-auditor
description: Audit, validate, forward-test, and repair agent skills for game development. Use when the user asks for a skill audit, trigger or portability gaps, project-coupling leaks, capability gaps, behavioral repair, or a readiness verdict; not for ordinary skill creation or editing.
---

# Game Skill Auditor

For a project-specific game skill, reconstruct its mission from the target
game's repository guidance and project profile. For a reusable game skill,
require it to operate without hidden assumptions about engine, genre,
architecture, mechanics, filenames, platforms, or release topology.

Evaluate a skill as a behavioral contract, not merely a Markdown file. Combine
deterministic package checks with evidence from realistic use. Distinguish a
skill defect from a missing project resource, unavailable tool, higher-level
instruction, model limitation, or unclear user expectation.

## Select The Audit Mode

Choose a quick check, full audit, repair, or regression; read
[references/audit-modes.md](references/audit-modes.md) for each mode and the
full-audit completion gate. Default to a full audit when the user asks to find
gaps or judge readiness. Do not edit the target during an
audit-only request.

## Load The Evidence

1. Read repository or workspace guidance that governs the target.
2. Read the target `SKILL.md` completely.
3. Read `agents/openai.yaml` and every resource the skill directly requires.
4. Inspect scripts before running them. Prefer bundled scripts over recreated
   checks.
5. Recover the user's intended behavior from their request, examples,
   corrections, approved outputs, and current project constraints.
6. Read [references/audit-rubric.md](references/audit-rubric.md) for every full,
   repair, or regression audit.
7. Read
   [references/independence-protocol.md](references/independence-protocol.md)
   before self-audits, readiness claims, behavioral repairs, or any audit whose
   result must be independently trustworthy.
8. Read
   [references/capability-enhancement-protocol.md](references/capability-enhancement-protocol.md)
   before recommending or adding tools, scripts, research workflows,
   delegated-agent roles, or other new capabilities.

Do not assume the current skill accurately describes its own intended job.
User intent and approved examples are evidence; higher-level system,
developer, safety, and project instructions remain binding constraints.

## Reconstruct The Behavioral Contract

Before freezing requirements, write a one-sentence **Skill Mission** naming the
intended user, concrete outcome, operating context, and most important
non-goal. Recover it from user requests, examples, corrections, governing
guidance, and approved behavior rather than trusting the target's description.

If the mission, use purposes, success criteria, recurring pain points, or hard
boundaries remain materially unclear, ask up to three targeted questions
before recommending repairs or capabilities, and do not ask when available
evidence already answers them.

Express the intended skill in seven clauses:

1. **Trigger:** requests that should and should not activate it.
2. **Read:** context and resources it must load before acting.
3. **Decide:** judgments it must make rather than mirror from the user.
4. **Do:** actions, artifacts, or recommendations it must produce.
5. **Do not:** boundaries, protected behavior, and forbidden shortcuts.
6. **Evidence:** tests or observations required before claiming success.
7. **Stop:** the condition that makes the task genuinely complete.

Create at least one substantive requirement for each clause. Tag every
requirement with its clause and provenance category: `User`, `Higher-level`,
`Project`, `Target`, `Observed`, or `Inferred`. At least one requirement must
come from user or governing evidence rather than the target describing itself.
Mark inferred clauses separately from explicit requirements.

Give requirements stable IDs. Maintain bidirectional traceability: every
requirement lists its tests and mutations, and every test or mutation lists
the requirements it evaluates.

## Separate Evaluation Roles

For self-audits and high-confidence readiness claims, separate contract, test
design, execution, judgment, and adversarial review into distinct clean
contexts when permitted. If separation cannot run, cap the verdict below
`Independently Cross-Checked`.

## Run Deterministic Checks

From the auditor's folder, run the bundled structural validator, which needs
only the Python standard library, then the strict static audit:

```text
python -B scripts/validate_skill.py <path-to-skill>
python -B scripts/audit_skill.py <path-to-skill> --strict
```

Treat their findings as evidence, not a substitute for semantic review. Read
[references/deterministic-checks.md](references/deterministic-checks.md) for
flags, the self-test, and the evidence assessor, and
[references/evidence-binding.md](references/evidence-binding.md) before
recording evidence.

`Not Validated` exits nonzero by default. Report the `readiness` field;
`automated_readiness_cap` is a constant ceiling, not an award.

## Audit Triggering

Because the description is the primary trigger surface, test it independently
from the body.

Create a prompt set containing:

- at least three clear requests that should trigger;
- two paraphrased or indirect requests that should trigger;
- two neighboring requests that should not trigger; and
- one ambiguous boundary request.

Check for both false negatives and false positives. Ensure the description says
what the skill does and when to use it without trying to encode the entire
workflow. Run trigger cases through auto-dispatch rather than explicit
invocation by name. Record expected activation, observed activation, and
the selected skill for every case. Preserve each prompt as a distinct hashed
artifact in the evidence manifest. The behavioral gate also requires a
regression case.

For an explicit-only skill, whose metadata disables implicit invocation, test
that implicit prompts do not activate it and that invocation by name does,
and record that policy. Its missing auto-dispatch is not a recall defect;
never repair it by re-enabling implicit invocation.

## Audit Instructions And Resources

Score every applicable rubric row, from source-of-truth routing and decision
ownership to safety, portability, and context cost, and check that examples
clarify behavior without overfitting it.

Locate the earliest broken layer. A weak output may originate in metadata,
missing context, ambiguous instructions, unavailable resources, poor test
design, or the underlying task rather than in the final response format.

## Evaluate Capability Enhancements

Treat a requested "superpower" as a capability enhancement, never as license
to invent tools or bypass higher-level instructions, approvals, safety, or
environment limits. Tie each capability to the frozen Skill Mission and an
observed bottleneck, and classify it with the capability enhancement protocol;
when a criterion is unknown, mark it `Needs approval`.

## Forward-Test Behavior

Forward-test the target as a real user would invoke it, not as an agent told
what defect to find. Follow
[references/forward-testing.md](references/forward-testing.md) for the cases,
the contract freeze, and approval before live or costly tests. A test passes
only when the observable result satisfies the requirement.

## Run Mutation And Holdout Tests

For self-audits, repairs to critical skills, and strong readiness claims,
plant at least one defect in each required category and keep holdouts outside
the target, as
[references/mutation-and-holdout.md](references/mutation-and-holdout.md)
describes.

## Classify Findings

- **Critical:** the skill is unsafe, unusable, impossible to trigger, or
  structurally invalid.
- **High:** a core promised behavior is missing or unreliable.
- **Medium:** an important edge case, ambiguity, or maintainability risk.
- **Low:** clarity, efficiency, portability, or polish improvement.

For each finding give its severity and requirement, evidence with file or
test references, provenance and the role that produced it, the user-visible
consequence, the earliest root cause, and the smallest durable repair.

Do not inflate a preference into a defect. Label unresolved subjective choices
as open decisions.

## Repair Without Overfitting

Edit only when the user requests or approves repair. Classify every capability
change first, apply only mission-preserving enablement the repair request
covers, and return directional evolution as a recommendation. Follow
[references/repair-method.md](references/repair-method.md) for the repair
steps and their evidence.

## Calibrate Readiness

Use the highest level whose evidence gate actually passed:
`Structurally Valid`, `Behaviorally Tested`, `Adversarially Tested`,
`Independently Cross-Checked`, or `User Validated`. A skill auditing itself
may earn only automated Level 1, and the assessor never awards Levels 2-5.
Read [references/readiness-levels.md](references/readiness-levels.md) before
awarding or reporting any level.

## Report

For a full, repair, or regression audit:

- lead with findings ordered by severity when defects exist;
- summarize the seven-clause behavioral contract;
- provide a requirement matrix with `Requirement`, `Status`, `Evidence`, and
  `Gap or Repair`;
- use only `Pass`, `Partial`, `Fail`, or `Unknown` for requirement status;
- use `Completed`, `Not Run`, or `Blocked` for whether a test executed;
- provide the smallest validated repair or clearly label it `Unvalidated`;
- identify role separation, blinding, mutation score, holdout status,
  disagreement status, and evidence provenance;
- state residual risks and untested cases;
- report capability recommendations as `Eligible in authorized repair`,
  `Needs approval`, `Rejected`, or `None needed`, with their mission link and
  evidence; and
- give a clear calibrated readiness level and limiting gate.

Do not call an inspection `Pass` when the target skill failed its requirements.
A full audit is incomplete when the matrix, evidence, unrun tests, or readiness
judgment is missing.

If no defects are found, say so directly and identify remaining test coverage
or environmental uncertainty.
