# Mutation And Holdout Tests

Read this before self-audits, repairs to critical skills, and strong
readiness claims.

## Mutation Categories

Deliberately test whether the auditor detects planted defects. Include at
least one mutation in each category:

- trigger recall or precision;
- required reading or source-of-truth routing;
- side-effect, approval, or preservation boundary;
- evidence, completion, or honesty gate; and
- metadata, resource, or portability integrity.

## Detection Gate

The adversarial gate requires every Critical and High mutation to be detected
and at least 80 percent detection across the five required mutation
categories. A category counts as detected only when every completed mutation
in that category is detected, so duplicate easy cases cannot inflate the
score. A mutation is detected only when the finding identifies the broken
requirement and a durable repair, not merely when the output sounds
suspicious.

## Mutation Evidence

Every completed mutation, including a miss, must preserve a full mutated skill
package with the same skill identity, a digest different from the target, raw
audit output, and a structured mutation judgment bound to both package
digests. Record the intended defect, expected failure, and exact changed paths;
the scorer verifies those paths against the actual package diff. Mutation
categories must use distinct packages, outputs, and judgment artifacts, and a
multi-file mutation must preserve enough unchanged package lineage to prove it
derives from the target. A boolean and prose alone are not mutation evidence.

## Holdouts

Keep holdout cases outside the target package and hide their expected outcomes
from the author, executor, and repair context until the repair is frozen.
Historical user corrections make strong holdouts. A bundled example corpus is
public regression evidence, never a hidden holdout.
