# Readiness Levels

Read this before awarding or reporting a readiness level.

## Levels

Use the highest level whose evidence gate actually passed:

1. **Structurally Valid:** required deterministic package checks pass.
2. **Behaviorally Tested:** the three direct, two paraphrased, two negative,
   one boundary, one regression, and three metamorphic prompts pass against the
   frozen contract with auto-dispatch activation evidence. For an
   explicit-only skill, whose metadata disables implicit invocation, test
   instead that implicit prompts do not activate it and that invocation by
   name does, and record that policy. Never treat its missing auto-dispatch as
   a recall defect, or repair it by re-enabling implicit invocation.
3. **Adversarially Tested:** the mutation gate passes.
4. **Independently Cross-Checked:** access-isolated evaluators outside the
   target skill, blind execution, two judging contexts, and the disagreement
   protocol pass.
5. **User Validated:** an external holdout passes after its post-review freeze
   and the user accepts the behavior.

## Manual Adjudication

A skill auditing itself may earn only automated Level 1. The assessor never
awards Levels 2-5, and `--require-level` for any of those levels must fail by
design. A main agent may manually award Level 2 only after observing the actual
auto-dispatch and target outputs (for an explicit-only skill, the actual
implicit non-activation and named invocations), and Level 3 only after
reviewing actual mutation audits rather than manifest assertions. It may award
Level 4 only after observing evaluator separation outside the target skill
and resolving disagreements, and Level 5 only after an actual post-review
holdout plus explicit acceptance from the user in the live interaction. Report
the automated level, the evidence-package completeness, and any separately
adjudicated manual level with the exact limiting gate. The assessor's
activation check expects positive cases to auto-dispatch, so it reports an
explicit-only skill's behavioral evidence as incomplete; say so, and
adjudicate its Level 2 manually.

## Limits

These gates provide tamper-evident artifact binding and process separation;
they do not cryptographically prove a human or service identity. State that
remaining limit instead of presenting the readiness label as identity
authentication.
