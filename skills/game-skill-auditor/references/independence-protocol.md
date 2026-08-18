# Independent Skill Evaluation Protocol

Use this protocol when an audit must be more trustworthy than a single
agent's self-consistent opinion. It reduces shared assumptions through
separation, blinding, adversarial tests, and calibrated claims. It cannot
prove that every assumption has been removed.

## Contents

1. Freeze the contract
2. Separate the roles
3. Control information leakage
4. Build test layers
5. Resolve disagreement
6. Record evidence
7. Award readiness

## Freeze The Contract

Before reading proposed repairs or executing tests, create a versioned
behavioral contract from:

- explicit user requests and corrections;
- governing system, developer, safety, and project instructions;
- approved examples and known regressions;
- observable behavior from the current skill; and
- clearly labeled inferences.

Give every requirement an identifier, one of the seven contract clauses, and
an acceptance criterion. Record its provenance category as `User`,
`Higher-level`, `Project`, `Target`, `Observed`, or `Inferred`. Cover all seven
clauses and include at least one requirement from user or governing evidence,
so the target cannot define the entire contract it will be judged against.
Record `contract_frozen_at` and freeze this contract for the evaluation round.
Changes discovered later become a new contract version rather than silently
changing the test.

Map every requirement to the tests and mutations that evaluate it. Map every
test and mutation back to its authorizing requirements. Missing, conflicting,
or one-way traceability blocks behavioral readiness.

## Separate The Roles

Use separate clean contexts where available:

| Role | May see | Must not see |
|---|---|---|
| Contract | user intent, governing instructions, approved examples | proposed repair |
| Test design | frozen contract, permitted environment | target implementation, expected target output |
| Execution | target skill, raw test prompt, required artifacts | expected result, prior diagnosis, author rationale |
| Judgment | frozen contract, raw prompt, raw output, execution evidence | proposed repair rationale, hidden holdout answers before scoring |
| Adversarial review | contract, evidence manifest, scored results | private chain-of-thought or unsupported summaries |

One context may perform multiple roles when tools or agents are unavailable,
but this is not independent evaluation. Record the collapse and lower the
readiness claim. For `Independently Cross-Checked`, contract, test-design,
judgment, and adversarial-review contexts must not invoke or follow the target
skill. They evaluate the target from the frozen external contract.

Use two judgment contexts for `Independently Cross-Checked`. Give them
materially different prompts, such as:

- observable-contract judge: score only explicit acceptance criteria;
- adversarial user advocate: seek persuasive outputs that still violate the
  user's requested behavior.

Prefer different model families when available. Distinct contexts using the
same model provide context independence, not model independence. Record both.

When these roles are implemented with delegated agents in this user's
environment, begin each assignment by addressing the agent as `Chud` and refer
to delegated agents as chuds in reports. Preserve unique actor and context IDs;
the shared role label does not establish or weaken independence by itself.

## Control Information Leakage

Record these facts before scoring:

- whether the test designer saw the target;
- whether executors saw expected outcomes;
- whether judges saw author rationale or intended repairs;
- whether holdouts were revealed before the repair froze; and
- whether prior findings were present in any supposedly clean context.

Any leaked expected answer invalidates that test as blind evidence. It may
still serve as a regression rehearsal.

Role separation requires distinct actor identifiers, context identifiers, and
prompt artifacts with distinct verified content hashes. Each role must provide
a structured attestation JSON bound to its role, actor, context, prompt hash,
target digest, governance status, and creation time. External roles also
provide structured output JSON bound to the same actor, context, and target.
A target cannot become external through a manifest flag or renamed role.
The two judgment roles must declare the distinct lenses `contract-criteria`
and `adversarial-user`, and both lenses must judge every behavioral case. Each
judgment must repeat the executor and judge context IDs and prompt hashes so
renamed actors cannot detach results from the roles that produced them.

Automated scoring supports at most `Structurally Valid`. Hash-bound records may
establish that a higher-level evidence package is internally complete, but
they cannot authenticate that auto-dispatch ran, the target produced the raw
output, a judgment is semantically competent, or an actor is who the manifest
claims. The main agent must observe and manually adjudicate those interactions
before reporting Levels 2-5. A separate external-review JSON must still match
the exact audited package, name the recorded external roles, and identify a
review steward distinct from the target and every evaluated role before Level
4 evidence can be considered complete.

Do not store hidden holdouts inside the target skill. Keep them in a separate
workspace location controlled by the user or test steward. Reveal them only
after the repair candidate and public tests are frozen.

## Build Test Layers

Use evidence with different failure modes:

1. **Structural:** official validator, bundled checker, references, syntax,
   metadata, and package layout.
2. **Behavioral:** canonical, paraphrase, edge, negative-control, and
   regression prompts. Preserve at least three direct canonical prompts, two
   paraphrases, two negative controls, one boundary/edge case, and one
   regression prompt as distinct hashed artifacts. Run these through
   auto-dispatch and record expected activation, observed activation, and the
   selected skill; explicit invocation is not trigger evidence.
3. **Metamorphic:** rephrase, reorder, add irrelevant context, remove optional
   context, and introduce a controlled conflict. Required behavior should
   remain invariant unless the changed information is material. Preserve at
   least three distinct metamorphic cases for readiness.
4. **Mutation:** plant defects and verify that the audit catches the broken
   requirement and recommends a durable repair.
5. **Holdout:** use unseen historical failures or user corrections after the
   repair is frozen.

For the mutation gate, include at least five mutations covering:

- trigger recall or precision;
- required reading or source routing;
- side effects, approvals, or preservation;
- evidence, honesty, or completion;
- metadata, resources, or portability.

Detect every Critical and High mutation and at least 80 percent overall.
Compute the 80 percent threshold across the five required categories, with a
category counted as detected only when every completed mutation in it is
detected. Do not let repeated easy cases inflate the score. Classify a miss by
its earliest cause: contract, test design, execution, judgment, or missing
evidence.

## Resolve Disagreement

Do not average conflicting judgments into a pass.

1. Compare the exact requirement and cited evidence.
2. Decide whether the contract is ambiguous, evidence is insufficient, or one
   reviewer made a demonstrable scoring error.
3. Correct demonstrable errors with evidence.
4. Ask the user when the conflict is a material preference.
5. Mark unresolved material disagreement as `Unknown`.

An unresolved Critical or High disagreement blocks `Independently
Cross-Checked`.

## Record Evidence

Start from
[evidence-manifest.example.json](evidence-manifest.example.json). Record:

- contract version and requirement identifiers;
- a contract clause, observable acceptance criterion, and provenance category
  for every requirement;
- role actors, context identifiers, prompts, and model families when known;
- tests, execution status, results, and artifact references;
- mutation severity and detection;
- blinding and leakage facts;
- reviewer disagreements and resolutions;
- external holdout timing and result; and
- explicit user acceptance.

Set the manifest mode to `audit` or `repair`. Repair mode must additionally
record the repaired finding IDs, distinct before/after full-package
directories and hashes, repair provenance, and the passing tests that verify
the repair. The after package must equal the current target digest, and the
verification set must include both structural validators and a regression
whose provenance is timestamped no earlier than the repair. Audit mode must
record distinct full-package before/after preservation directories whose
verified hashes both equal the current target digest.

Bind every behavioral test and mutation record to the exact target package
digest. Selected files, free-form snapshot text, and verification evidence
that predates the repair do not prove package preservation or repair.

Every evidence provenance record must identify its source, producing actor,
artifact, SHA-256 hash, creation time, and custodian. The scorer must resolve
and hash the artifact rather than trust the string. Independent roles must
include a distinct hashed prompt reference, matching role attestation, and
whether they were governed by the target skill.

Structural test records must include a structured Python invocation, a hashed
validator script, zero exit code, and the digest of the target package tested.
The bundled audit must record `strict: true` and an exact `--strict` argument.
The provenance artifact must contain the actual validator output: the assessor
parses and live-replays the installed official validator, then live-replays the
auditor's own bundled checker, requiring a zero-error, zero-warning JSON
summary. Do not treat a free-form command string, target-supplied checker,
echoed validator name, or unrelated hashed file as execution evidence.

Each behavioral record must preserve the raw output plus a structured judgment
JSON bound to the test, requirements, target, prompt, output, executor, and a
distinct judge. Record the review lens, substantive rationale, one observable
criterion result per linked requirement, and the matching auto-dispatch
activation record. Require distinct prompt and output paths and hashes across
behavioral cases. Each completed mutation must preserve a full mutated
package with the same skill identity, raw audit output, and a structured
judgment bound to both package digests. Mutation records marked detected must
also include a substantive finding and durable repair tied through their
requirement IDs, plus the intended defect, expected failure, and exact changed
paths verified against the package diff. Completed categories must use
distinct mutated packages, outputs, and judgment artifacts. Multi-file targets
require enough unchanged file lineage to reject a minimal decoy package.

Treat manifest integrity as an entry gate, not a later independence concern.
Reject unresolved placeholder identities or claims, non-object records,
duplicate role identities, duplicate disagreement IDs, inaccessible targets,
and malformed supplied role evidence before awarding any readiness level.
Omitting optional higher-level evidence may cap readiness; supplying malformed
evidence must not be silently ignored.

Hashes prove which bytes were reviewed; they do not prove that a report is
truthful or semantically competent. That judgment belongs to the external
reviewers. Keep the bundled manifest as a deliberately non-passing template,
never as sample proof of readiness.

Payload timestamps, not only their provenance wrappers, must follow the frozen
contract and may not postdate the wrapper that records them. For Level 4, every
requirement provenance actor must match the independent contract role.

After changing the assessor or evidence schema, run `python
scripts/self_test.py`. Every probe must match its exact expected readiness;
under-awards are regressions too.

Run:

```powershell
python scripts/assess_evidence.py evidence.json
```

Use `--require-level` to make Level 1 a deterministic release gate. Requests
for Levels 2-5 fail by design because local artifacts do not authenticate
execution, semantic judgment, or actors. Inspect
`evidence_package_completeness` and the evidence-completeness fields before
manual adjudication. To validate the internal completeness of Level 4
evidence, provide an external review:

```powershell
python scripts/assess_evidence.py evidence.json `
  --external-review-file path/to/external-review.json
```

The review JSON must contain `verdict: "pass"`, the exact `target_sha256`,
the external `reviewer_actor_ids`, a distinct `review_actor_id`, and a valid
`created_at` timestamp. Its hashed provenance must resolve to the same
separately supplied file and name the same review actor.

To validate the completeness of Level 5 evidence, also provide an external
user-supplied artifact:

```powershell
python scripts/assess_evidence.py evidence.json `
  --external-review-file path/to/external-review.json `
  --user-acceptance-file path/to/user-acceptance.json
```

The acceptance file must be outside the target package and match the hashed
acceptance provenance. It must be JSON containing `kind: "user-acceptance"`,
`verdict: "accept"`, the exact `target_sha256`, `accepted_level:
"User Validated"`, the provenance actor ID, a valid creation time, and a
substantive acceptance statement.

The holdout provenance artifact must likewise be JSON containing `kind:
"holdout-result"`, `verdict: "pass"`, the exact target digest, the holdout
actor ID, and `holdout_frozen_at` and `revealed_at` timestamps matching the
manifest.

Chronology is causal: requirements exist by `contract_frozen_at`; roles and
public tests follow the freeze; external review follows public evidence; the
holdout freezes and reveals after external review; and acceptance follows the
holdout reveal. Future-dated or out-of-order evidence does not count.

These bindings make evidence tamper-evident and expose inconsistent
declarations. They are not cryptographic identity authentication; report that
remaining limitation honestly.

## Award Readiness

Award only the highest fully supported level. The assessor awards only Level
1; the main agent awards Levels 2-5 after observing the actual interactions:

| Level | Required evidence |
|---|---|
| `Structurally Valid` | the official validator and bundled strict audit complete and pass with provenance |
| `Behaviorally Tested` | manual verdict after observing structural plus three direct, two paraphrased, two negative, one boundary, one regression, and three metamorphic prompts run with actual activation evidence |
| `Adversarially Tested` | manual verdict after Level 2 plus observing completed mutation audits in all five categories, all Critical/High mutations detected, and at least 80 percent overall detected |
| `Independently Cross-Checked` | manual verdict after adversarial evidence, actual evaluators outside the target skill, blind execution, two judgment contexts, and no unresolved material disagreement |
| `User Validated` | manual verdict after Level 4, an actual external post-freeze holdout, and explicit live user acceptance |

Report model diversity separately. It strengthens confidence but does not
replace contract, execution, or evidence independence.
