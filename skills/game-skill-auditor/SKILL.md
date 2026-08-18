---
name: game-skill-auditor
description: Audit, validate, forward-test, repair, and improve Codex skills used for game design, implementation, debugging, balance, UX, playtesting, release, audio, or production. Use to find trigger gaps, project-coupling leaks, missing game-development evidence, conflicts, portability failures, or mission drift in a game skill. Do not use for ordinary game-skill creation or editing unless the user requests an audit, validation, capability-gap analysis, behavioral repair, or readiness judgment.
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

## Full-Audit Completion Gate

Treat any request to judge intended behavior, exactness, gaps, conflicts, or
readiness as a full audit unless the user explicitly asks for a quick check.
This includes semantic-only audits where execution is unavailable.

Before sending the final response, verify that it contains findings, the
skill's exact mission and non-goals, the reconstructed behavioral contract, a
requirement matrix, test status, repairs, capability recommendations, an
independence statement, and a calibrated readiness verdict. The presentation
may combine or reorder sections when that improves clarity, but it may not
omit the matrix, evidence provenance, unrun tests, independence limits, or
final readiness judgment.

## Select The Audit Mode

- **Quick check:** run structural validation and report obvious gaps.
- **Full audit:** reconstruct intent, inspect every required resource, test
  triggering and instructions, and produce an evidence matrix.
- **Repair:** perform the full audit, edit the skill and its metadata, then
  rerun structural and behavioral tests.
- **Regression:** preserve an approved behavior while checking a proposed
  update against prior successes and edge cases.

Default to a full audit when the user asks to find gaps or determine whether a
skill will produce exactly what they want. Do not edit the target during an
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
before recommending repairs or capabilities. Questions may ask who uses the
skill, what situations matter most, what observable success looks like, what
must never change, and where the current skill falls short. Do not ask when
available evidence already answers them.

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

Do not let one reasoning context silently author the contract, design all
tests, execute them, and award the final verdict when independent evaluation
is available.

For self-audits and high-confidence readiness claims, separate:

1. **Contract:** reconstruct requirements from user and governing evidence.
2. **Test design:** create cases from the frozen contract without reading the
   target implementation.
3. **Execution:** run the target on raw cases without expected answers.
4. **Judgment:** compare outputs with the contract without seeing author
   rationale or intended repairs.
5. **Adversarial review:** seek false confidence, leakage, and missed failure
   modes.

Use distinct clean contexts for these roles when subagents are permitted.
Prefer model diversity when available, but record prompt diversity and model
diversity separately. Merely labeling sections in one context does not create
independence. If role separation cannot run, continue the audit but cap the
verdict below `Independently Cross-Checked`. Level 4 also requires contract,
test-design, judgment, and adversarial evaluators that are not following or
governed by the target skill; more instances of the target auditing itself are
still self-evaluation.

When assigning a delegated agent in this environment, begin the assignment by
addressing it as `Chud` and refer to delegated agents as chuds in reports.
Keep actor IDs, role boundaries, prompts, artifacts, and judgments precise;
the friendly label does not replace evidence or independence controls.

## Run Deterministic Checks

Run the official skill validator when it is available. Then run:

```powershell
python scripts/audit_skill.py <path-to-skill>
```

Use `--json` for machine-readable results and `--strict` when warnings should
fail a release gate.

The bundled audit checks structure, frontmatter, folder naming, trigger
language, placeholders, length, Markdown references, Python syntax, resource
layout, portability risks, and `agents/openai.yaml`. Treat its findings as
evidence, not as a substitute for semantic review.

After changing the assessor or its evidence contract, run its bundled
regression suite:

```powershell
python scripts/self_test.py
```

The suite must report exact expected readiness for every positive and negative
probe, not merely the absence of over-awards.

Use `scripts/assess_evidence.py` with an evidence manifest after behavioral
testing. Start from
[references/evidence-manifest.example.json](references/evidence-manifest.example.json)
and use `--require-level` when enforcing a release gate. The bundled manifest
is a non-passing template and must never serve as readiness evidence. Level 5
additionally requires `--user-acceptance-file` with a separate user-supplied
artifact; a manifest assertion alone cannot prove user acceptance.

`Not Validated` exits nonzero by default. Use `--report-only` only when a
caller intentionally wants a successful process exit for an invalid or
incomplete manifest.

The assessor deliberately caps automated readiness at Level 1. It may verify
that higher-level evidence packages are internally complete, but local files
cannot authenticate target execution, semantic judgment, evaluator identity,
agent context, or user acceptance. Use `evidence_package_completeness`,
`behavioral_evidence_complete`, `adversarial_evidence_complete`,
`independence_evidence_ready`, and `user_validation_evidence_ready` as inputs
to manual adjudication, never as automatic readiness awards.

For structural evidence, record a structured invocation with the Python
executable, hashed validator script, argument list, exit code, target package
digest, and actual hashed output. The assessor parses the official validator's
success text, live-replays that installed validator, then live-replays the
auditor's bundled static checker and parses its JSON summary. The official
validator must be the installed system validator under `CODEX_HOME`, falling
back to `~/.codex`, and the bundled checker must be the script beside the
assessor. The bundled audit arguments must contain the exact `--strict` flag;
a free-form command string or target-supplied lookalike is not proof of
execution.

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
`$skill-name` invocation. Record expected activation, observed activation, and
the selected skill for every case. Preserve each prompt as a distinct hashed
artifact in the evidence manifest. The behavioral gate also requires a
regression case.

## Audit Instructions And Resources

Use the rubric to evaluate:

- source-of-truth routing and required reading;
- ordering, prerequisites, and completion conditions;
- appropriate degrees of freedom;
- decision ownership and resistance to user mirroring;
- approval, status, persistence, or update rules;
- tool availability, permissions, and fallback behavior;
- progressive disclosure and reference routing;
- output shape and evidence requirements;
- safety, scope, and interaction with higher-level instructions;
- portability, maintainability, and context cost; and
- whether examples clarify behavior without overfitting it.

Locate the earliest broken layer. A weak output may originate in metadata,
missing context, ambiguous instructions, unavailable resources, poor test
design, or the underlying task rather than in the final response format.

## Evaluate Capability Enhancements

Treat a requested "superpower" as a capability enhancement, not as permission
to invent unavailable tools or bypass higher-level instructions, approvals,
safety, or environment limits. Follow
[references/capability-enhancement-protocol.md](references/capability-enhancement-protocol.md).

Tie every capability to the frozen Skill Mission and an observed bottleneck.
Consider available tools, deterministic scripts, focused research, references,
assets, automation, or delegated chud roles when they make the approved job
more reliable, exact, efficient, or independently testable.

Classify each proposal:

- **Mission-preserving enablement:** strengthens the approved outcome without
  broadening triggers, users, outputs, permissions, side effects, or trust
  boundaries. It may be added during an authorized repair and must be tested.
- **Directional evolution:** changes the mission, adds a new outcome, broadens
  activation, introduces material cost or side effects, changes permissions or
  the trust model, or risks crowding out the skill's existing strengths.
  Present it to the user with benefits, costs, and a smallest experiment; do
  not implement it without approval.
- **Rejected embellishment:** adds complexity without evidence that it improves
  the mission. Explain briefly and leave the skill lean.

If any classification criterion is unknown, disputed, or weakly evidenced,
ask a focused question or classify the proposal as `Needs approval`. Never
resolve uncertainty in favor of silent enablement.

When delegated chuds would help, specify why delegation is better than one
agent, each chud's role and write scope, required inputs and outputs, the main
agent's integration responsibility, the evidence that must be preserved, and
the observable test. Independently verify chud outputs against source
artifacts or test evidence before integrating them. Do not add vague "use
more agents" instructions.

## Forward-Test Behavior

Use clean-context agents when permitted and useful. Forward-test the target as
a real user would invoke it, not as an agent told what defect to find.

Include:

1. a canonical task;
2. an edge or ambiguity task;
3. a negative-control task outside the intended scope; and
4. a regression task when approved behavior already exists; and
5. at least three metamorphic tasks covering rephrased or reordered input,
   irrelevant context, and a controlled conflict.

Pass raw artifacts and the target skill, not the expected answer or prior
diagnosis. Compare outputs against the behavioral contract. A test passes only
when the observable result satisfies the requirement; a persuasive
explanation is not evidence by itself.

For each behavioral case, preserve the prompt, raw target output, and a
structured judgment JSON. Bind the judgment to the test ID, requirement IDs,
target digest, prompt digest, output digest, executor actor, and a distinct
judge actor. Bind both actors to their recorded context IDs and prompt hashes.
The judgment must also state its review lens, give a substantive rationale,
score every linked requirement, and cite an observable result for each
criterion. Bind the same auto-dispatch activation record into both judgments.
Behavioral cases must use distinct prompt and output artifacts. A manifest
`result: pass` without these matching artifacts does not satisfy the
behavioral gate.

Freeze the contract and test set before executing the target. Record which
role saw the target, expected results, author rationale, and prior findings.
Record `contract_frozen_at`; behavioral tests, mutations, roles, reviews,
holdouts, and acceptance must follow it in causal order.
Payload creation times must also follow the contract freeze and may not predate
their contents while being laundered through a newer provenance wrapper.
For an independently cross-checked verdict, use at least two judging contexts
with different review prompts. Do not resolve disagreement by majority vote:
trace it to ambiguous requirements, insufficient evidence, or reviewer error.
Keep unresolved material disagreement as `Unknown`.

Preserve hashes for prompts, role attestations, command outputs, and scored
artifacts. External roles must have distinct actors, contexts, and prompt
artifacts by both path and content hash. Role attestations and external-role
outputs must be structured JSON bound to the role, actor, context, target
digest, prompt, and declared review lens where applicable. Every behavioral
case must receive both `contract-criteria` and `adversarial-user` judgments.
Treat labels without resolvable, cross-bound evidence as claims, not proof.
For Level 4, the contract role must be the producing actor recorded on every
frozen requirement.

Bind every behavioral test and mutation record to the exact target package
digest. Audit preservation and repair before/after evidence must be full skill
package directories, not selected files.

Reject unresolved placeholders and malformed supplied evidence records before
awarding any readiness level. Duplicate role identities, duplicate
disagreement IDs, placeholder contract or repair fields, and non-object
records may not be silently ignored or treated as lower-tier evidence.

In audit-only mode, preserve distinct before/after target snapshots and verify
that their hashes match. In repair mode, verify the recorded before and after
artifacts themselves rather than accepting hash strings alone.

If forward-testing could modify live systems, consume meaningful money, take a
long time, or require new permissions, request approval first.

## Run Mutation And Holdout Tests

For self-audits, repairs to critical skills, and strong readiness claims,
deliberately test whether the auditor detects planted defects. Include at
least one mutation in each category:

- trigger recall or precision;
- required reading or source-of-truth routing;
- side-effect, approval, or preservation boundary;
- evidence, completion, or honesty gate; and
- metadata, resource, or portability integrity.

The adversarial gate requires every Critical and High mutation to be detected
and at least 80 percent detection across the five required mutation
categories. A category counts as detected only when every completed mutation
in that category is detected, so duplicate easy cases cannot inflate the
score. A mutation is detected only when the finding identifies the broken
requirement and a durable repair, not merely when the output sounds
suspicious.

Every completed mutation, including a miss, must preserve a full mutated skill
package with the same skill identity, a digest different from the target, raw
audit output, and a structured mutation judgment bound to both package
digests. Record the intended defect, expected failure, and exact changed paths;
the scorer verifies those paths against the actual package diff. Mutation
categories must use distinct packages, outputs, and judgment artifacts, and a
multi-file mutation must preserve enough unchanged package lineage to prove it
derives from the target. A boolean and prose alone are not mutation evidence.

Keep holdout cases outside the target package and hide their expected outcomes
from the author, executor, and repair context until the repair is frozen.
Historical user corrections make strong holdouts. A bundled example corpus is
public regression evidence, never a hidden holdout.

## Classify Findings

- **Critical:** the skill is unsafe, unusable, impossible to trigger, or
  structurally invalid.
- **High:** a core promised behavior is missing or unreliable.
- **Medium:** an important edge case, ambiguity, or maintainability risk.
- **Low:** clarity, efficiency, portability, or polish improvement.

For each finding provide:

- severity and requirement;
- evidence with file or test references;
- provenance and the role that produced the evidence;
- user-visible consequence;
- earliest root cause; and
- the smallest durable repair.

Do not inflate a preference into a defect. Label unresolved subjective choices
as open decisions.

## Repair Without Overfitting

Edit only when the user requests or approves repair.

Before editing, classify every capability change using the enhancement
protocol. Apply only mission-preserving enablement covered by the user's repair
request. Return directional evolution as a recommendation and wait for
approval.

1. Preserve the intended scope and successful behaviors.
2. Fix the earliest broken layer.
3. Prefer a minimal durable diff. Replace an entire skill only when its current
   structure prevents a reliable targeted repair.
4. Prefer concise instructions and reusable resources over repeated prose.
5. Do not add one-off rules that merely force a single test answer.
6. Update `agents/openai.yaml` when the skill's trigger or interface changes.
   An audit-only recommendation that expands scope or triggering must include
   the corresponding metadata repair; do not leave the interface knowingly
   stale.
7. Keep references one level from `SKILL.md` when practical.
8. Validate concrete repair text before presenting it, even during an
   audit-only request. If execution is unavailable, label the proposed patch
   `Unvalidated` and check it manually against frontmatter, trigger, metadata,
   reference, and portability requirements.
9. Rerun the official validator, bundled static audit, and relevant
   forward-tests.
10. Run mutation and holdout tests proportional to the claim being made.
11. Record the evidence in a manifest and run
    `scripts/assess_evidence.py`.
12. For repair mode, record finding IDs, distinct before/after package
    snapshots, repair provenance, and verification-test IDs. The after
    snapshot must equal the current target digest; verification must include
    both structural validators and a regression whose evidence is no earlier
    than the repair provenance.
13. Compare the final package and behavior with the frozen original contract.

When installed and source copies both exist, synchronize them and verify their
hashes.

## Calibrate Readiness

Use the highest level whose evidence gate actually passed:

1. **Structurally Valid:** required deterministic package checks pass.
2. **Behaviorally Tested:** the three direct, two paraphrased, two negative,
   one boundary, one regression, and three metamorphic prompts pass against the
   frozen contract with auto-dispatch activation evidence.
3. **Adversarially Tested:** the mutation gate passes.
4. **Independently Cross-Checked:** access-isolated evaluators outside the
   target skill, blind execution, two judging contexts, and the disagreement
   protocol pass.
5. **User Validated:** an external holdout passes after its post-review freeze
   and the user accepts the behavior.

A skill auditing itself may earn only automated Level 1. The assessor never
awards Levels 2-5, and `--require-level` for any of those levels must fail by
design. A main agent may manually award Level 2 only after observing the actual
auto-dispatch and target outputs, and Level 3 only after reviewing actual
mutation audits rather than manifest assertions. It may award Level 4 only
after observing evaluator separation outside the target skill and resolving
disagreements, and Level 5 only after an actual post-review holdout plus
explicit acceptance from the user in the live interaction. Report the
automated level, the evidence-package completeness, and any separately
adjudicated manual level with the exact limiting gate.

These gates provide tamper-evident artifact binding and process separation;
they do not cryptographically prove a human or service identity. State that
remaining limit instead of presenting the readiness label as identity
authentication.

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
