# Skill Audit Rubric

Use this rubric for full, repair, and regression audits. Score each applicable
row as `Pass`, `Partial`, `Fail`, or `Unknown` and attach evidence.

## Contract And Intent

| Area | Questions |
|---|---|
| Purpose | Is the promised outcome concrete enough to verify? |
| User intent | Does the skill reflect the user's actual examples and corrections rather than generic best practices alone? |
| Scope | Are included tasks, neighboring tasks, and explicit non-goals clear? |
| Completion | Does the skill define when work is genuinely done rather than merely analyzed? |
| Clause coverage | Does the frozen contract contain substantive Trigger, Read, Decide, Do, Do not, Evidence, and Stop requirements? |
| Contract independence | Does at least one requirement come from user or governing evidence rather than the target itself? |

## Trigger Surface

| Area | Questions |
|---|---|
| Name | Is it memorable, hyphen-case, and aligned with the job? |
| Description | Does it state both what the skill does and when to use it? |
| Recall | Do direct, paraphrased, and indirect intended requests trigger it? |
| Precision | Do neighboring out-of-scope requests avoid triggering it? |
| Activation evidence | Were trigger cases run through auto-dispatch with expected and observed selection recorded? |
| UI metadata | Does `agents/openai.yaml` accurately represent the current skill? |

## Context And Progressive Disclosure

| Area | Questions |
|---|---|
| Required reading | Are mandatory sources named and ordered? |
| Source of truth | Does the skill distinguish implementation, planning, approval, and historical evidence? |
| Reference routing | Does `SKILL.md` say when each bundled reference is required? |
| Missing context | Can the agent discover required files without guessing? |
| Context cost | Is core guidance concise while detailed material remains optional? |

## Workflow And Judgment

| Area | Questions |
|---|---|
| Ordering | Are prerequisites completed before dependent actions? |
| Decision ownership | Does the agent evaluate proposals instead of automatically endorsing them? |
| Degrees of freedom | Are fragile steps constrained and creative steps left flexible? |
| Root cause | Does the workflow repair the earliest broken layer? |
| Alternatives | Does it compare materially different options when uncertainty remains? |
| Stop condition | Does it continue through implementation and verification when requested? |

## Capability Enhancements

| Area | Questions |
|---|---|
| Mission precision | Does the audit state the exact user, outcome, context, and non-goal before proposing new capability? |
| Purpose questions | When intent is materially unclear, does the auditor ask focused questions about use cases, success, boundaries, and pain points instead of guessing? |
| Bottleneck evidence | Is each proposed capability tied to an observed failure, friction point, or missing evidence path? |
| Mission fit | Does the capability strengthen the approved mission without diluting the skill's existing identity? |
| Tool reality | Are proposed tools, scripts, research, and delegated roles actually available and permitted? |
| Evolution boundary | Are new outcomes, broader triggers, permissions, side effects, costs, or trust changes returned for user approval before implementation? |
| Delegation design | If chuds are proposed, are their roles, inputs, tool and context limits, write scopes, outputs, integration owner, stop conditions, evidence artifacts, and any merge plan explicit? |
| Delegation verification | Do preserved assignments and reports prove the `Chud` naming convention and role boundaries, and does the main agent independently verify chud output before integration? |
| Capability evidence | Is the enhancement tested against the original contract, a regression, and the bottleneck it is meant to remove? |
| Complexity cost | Is the expected benefit worth added context, maintenance, latency, coordination, and failure modes? |

## Resources, Tools, And Environment

| Area | Questions |
|---|---|
| Availability | Are required tools and dependencies actually available? |
| Permissions | Are escalation, destructive actions, networking, and user approvals handled? |
| Scripts | Are deterministic repeated tasks implemented and tested as scripts when useful? |
| Paths | Are paths portable or explicitly project-bound? |
| Fallbacks | Does the skill say what to do when a source, tool, or environment is unavailable? |

## State, Safety, And Boundaries

| Area | Questions |
|---|---|
| Status | Are draft, approved, implemented, rejected, and unknown states kept distinct? |
| Preservation | Does the skill protect unrelated user changes and approved artifacts? |
| Higher-level rules | Can the workflow operate without violating system, developer, safety, legal, or project instructions? |
| Side effects | Does audit-only work avoid edits? Are live or costly tests gated? |
| Preservation evidence | Do audit-only runs prove unchanged target snapshots rather than merely claim no edits? |
| Package snapshots | Are preservation and repair artifacts full package directories whose digests match the claimed target state? |
| Failure honesty | Must the agent report blocked, untested, or uncertain requirements? |

## Output And Evidence

| Area | Questions |
|---|---|
| Output shape | Is the response organized for the user's decision rather than the skill author's convenience? |
| Required report | Are findings, the contract, requirement matrix, test status, repairs, and readiness verdict all present? |
| Evidence | Are claims tied to files, commands, tests, observations, or artifacts? |
| Evidence integrity | Does provenance identify source, actor, artifact, creation time, and custodian? |
| Manifest integrity | Are placeholders, non-object records, duplicate role identities, and duplicate disagreement IDs rejected before readiness? |
| Structural binding | Do validator records preserve a structured executable, hashed script, exact arguments, strict mode, exit code, target digest, and hashed output? |
| Validator replay | Does the assessor live-replay both the installed official validator and its own strict checker? |
| Output binding | Are validator outputs parsed, and are behavioral results bound to raw outputs, prompts, requirements, actors, and the exact target? |
| Judgment substance | Does each judgment state its lens, rationale, and an observable result for every linked criterion? |
| Context binding | Are result actors bound to their role context IDs and prompt hashes? |
| Artifact diversity | Do behavioral cases preserve distinct prompt and output artifacts rather than reuse generic evidence? |
| Verification | Does the test depth match the risk and blast radius? |
| User experience | Does the skill produce the tone, detail, and collaboration style the user expects? |
| Exactness | Can each requested behavior be mapped to an observable acceptance criterion? |
| Provenance | Is every material claim tied to its source and evaluation role? |

## Evaluation Independence

| Area | Questions |
|---|---|
| Contract freeze | Was a versioned contract frozen before test execution and repair scoring? |
| Chronology | Do roles, tests, review, holdout, and acceptance follow the frozen contract in causal order? |
| Payload chronology | Do payload timestamps follow the freeze and precede or equal their provenance wrappers? |
| Role separation | Were contract, test design, execution, and judgment separated when independence was claimed? |
| Blinding | Were expected answers, author rationale, prior findings, and holdouts withheld from roles that must not see them? |
| Actor integrity | Are external actors, contexts, prompts, and attestations distinct and hash-verifiable? |
| Reviewer diversity | Were two judgment contexts used, with prompt and model diversity recorded separately? |
| Contract actor | Is every requirement provenance record produced by the independent contract role when Level 4 is claimed? |
| Judgment lenses | Did both contract-criteria and adversarial-user judges score every behavioral case? |
| Metamorphic coverage | Did rephrasing or reordering, irrelevant context, and a controlled conflict preserve the intended behavior? |
| External review artifact | Is Level 4 tied to a separately supplied review JSON for the exact target digest? |
| Mutation sensitivity | Did the audit detect planted trigger, context, boundary, evidence, and metadata defects? |
| Mutation artifacts | Does every completed mutation preserve a full same-identity mutated package, raw output, and a target-bound structured judgment? |
| Mutation uniqueness | Are packages, raw outputs, and judgments distinct across required categories, with lineage to the target? |
| Mutation score integrity | Is detection scored across required categories without duplicate-case inflation? |
| Completed mutations | Does scoring count only completed mutation categories and reject unrun Critical or High cases? |
| Holdout integrity | Was the holdout external to the target, frozen after public review, and revealed only after that holdout freeze? |
| User acceptance | Was acceptance supplied separately by the user rather than asserted only inside the manifest? |
| Acceptance binding | Do holdout and acceptance JSON artifacts name the exact target digest, actor, verdict, and relevant timestamps? |
| Disagreement | Were conflicting judgments traced to evidence rather than averaged into a pass? |
| Calibration | Does automated readiness stop at Level 1, with Levels 2-5 reported only after manual adjudication of actual interactions? |

## Maintainability

| Area | Questions |
|---|---|
| Duplication | Is each rule owned in one clear place? |
| Conflicts | Are contradictory instructions reconciled instead of layered? |
| Extensibility | Can new cases fit the model without accumulating exceptions? |
| Portability | Can another agent install and understand the package? |
| Regression safety | Are successful prior behaviors represented in tests or explicit constraints? |
| Repair validity | Has any concrete proposed patch been checked for new structural, trigger, metadata, reference, or portability defects? |
| Repair chronology | Do both validators and a target-bound regression postdate repair provenance? |

## Forward-Test Set

Create the smallest set that exercises distinct failure modes:

1. **Canonical:** at least three clear intended requests.
2. **Paraphrase:** at least two differently worded requests with the same
   intent.
3. **Edge:** at least one incomplete, ambiguous, or conflicting boundary case.
4. **Negative control:** at least two nearby tasks the skill should decline or
   leave to another skill.
5. **Regression:** at least one task that previously succeeded and must remain
   stable.

Do not disclose the expected answer to the test agent. Evaluate observable
behavior against the contract after the run. Preserve every prompt as a
distinct hashed artifact.

For independent evaluation, design the cases from the frozen contract before
the test designer sees the target. Use two separate judgment contexts. Read
[independence-protocol.md](independence-protocol.md) for leakage boundaries,
mutation coverage, holdouts, and readiness gates.

## Repair Test

Before accepting a repair, ask:

- Did it fix the root cause rather than the visible symptom?
- Did trigger recall improve without unacceptable false positives?
- Did the canonical and regression cases remain successful?
- Did instructions become clearer rather than merely longer?
- Did every capability remain tied to the exact Skill Mission and a verified
  bottleneck?
- Was directional evolution withheld for user approval instead of silently
  entering the repair?
- Did the package remain valid, portable, and internally consistent?
- Is any remaining gap a defect, an open preference, or an environmental
  limitation?
- Did the repair pass the mutation gate without test-answer leakage?
- Does the final readiness label reflect independent evidence rather than
  self-consistency?
