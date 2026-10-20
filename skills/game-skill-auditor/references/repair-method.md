# Repair Method

Read this before proposing repair text for a target skill or editing one.
Edit only when the user requests or approves repair.

## Classify First

Before editing, classify every capability change using
[capability-enhancement-protocol.md](capability-enhancement-protocol.md).
Apply only mission-preserving enablement covered by the user's repair request.
Return directional evolution as a recommendation and wait for approval.

## Steps

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
9. Rerun the bundled or Codex's validator, the bundled static audit, and
   relevant forward-tests.
10. Run mutation and holdout tests proportional to the claim being made.
11. Record the evidence in a manifest and run
    `scripts/assess_evidence.py`.
12. For repair mode, record finding IDs, distinct before/after package
    snapshots, repair provenance, and verification-test IDs. The after
    snapshot must equal the current target digest; verification must include
    both structural validators and a regression whose evidence is no earlier
    than the repair provenance.
13. Compare the final package and behavior with the frozen original contract.

## Installed Copies

When installed and source copies both exist, synchronize them and verify their
hashes.
