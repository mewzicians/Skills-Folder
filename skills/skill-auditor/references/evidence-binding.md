# Evidence Binding

Read this before recording structural, behavioral, role, or package evidence
that the assessor or a reviewer will rely on.

## Structural Evidence

For structural evidence, record a structured invocation with the Python
executable, hashed validator script, argument list, exit code, target package
digest, and actual hashed output. The `official-validator` record must name a
trusted validator: the bundled `scripts/validate_skill.py` beside the assessor,
whose bytes and schema module match the assessor's pinned hashes, or Codex's
installed system validator under `CODEX_HOME`, falling back to `~/.codex`. The
assessor parses that validator's success text and live-replays it, then
live-replays the auditor's bundled static checker and parses its JSON summary.
The bundled checker must be the script beside the assessor. The bundled audit
arguments must contain the exact `--strict` flag; a free-form command string
or target-supplied lookalike is not proof of execution.

## Behavioral Evidence

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

## Roles And Artifacts

Preserve hashes for prompts, role attestations, command outputs, and scored
artifacts. External roles must have distinct actors, contexts, and prompt
artifacts by both path and content hash. Role attestations and external-role
outputs must be structured JSON bound to the role, actor, context, target
digest, prompt, and declared review lens where applicable. Every behavioral
case must receive both `contract-criteria` and `adversarial-user` judgments.
Treat labels without resolvable, cross-bound evidence as claims, not proof.
For Level 4, the contract role must be the producing actor recorded on every
frozen requirement.

## Package Digests And Snapshots

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
