# Deterministic Checks

Read this before running the bundled checks, the assessor self-test, or the
evidence assessor. Run every command from the auditor's folder.

## Structural Validator And Static Audit

Run the bundled structural validator, which needs only the Python standard
library, then the bundled audit:

```text
python -B scripts/validate_skill.py <path-to-skill>
python -B scripts/audit_skill.py <path-to-skill> --strict
```

Use `--json` for machine-readable results and `--strict` when warnings should
fail a release gate.

The bundled audit checks structure, frontmatter, folder naming, trigger
language, placeholders, length, Markdown references, Python syntax, resource
layout, portability risks, and `agents/openai.yaml`. Treat its findings as
evidence, not as a substitute for semantic review.

## Assessor Self-Test

After changing the assessor or its evidence contract, run its bundled
regression suite:

```text
python -B scripts/self_test.py
```

By default it replays the bundled validator, so it needs no host installation.
Add `--host-validator` to replay Codex's installed validator instead, which
needs PyYAML. The suite must report exact expected readiness for every
positive and negative probe, not merely the absence of over-awards.

## Evidence Assessor

Use `scripts/assess_evidence.py` with an evidence manifest after behavioral
testing:

```text
python -B scripts/assess_evidence.py evidence.json --require-level "Structurally Valid"
```

Start from
[evidence-manifest.example.json](evidence-manifest.example.json)
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
to manual adjudication, never as automatic readiness awards. Report the
`readiness` field; `automated_readiness_cap` is a constant ceiling, not an
award.

Record what each check consumed and produced as
[evidence-binding.md](evidence-binding.md) requires.
