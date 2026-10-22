# Forward Testing

Read this before running behavioral cases against a target skill.

## Case Set

Use clean-context agents when permitted and useful. Forward-test the target as
a real user would invoke it, not as an agent told what defect to find.

Include:

1. a canonical task;
2. an edge or ambiguity task;
3. a negative-control task outside the intended scope;
4. a regression task when approved behavior already exists; and
5. at least three metamorphic tasks covering rephrased or reordered input,
   irrelevant context, and a controlled conflict.

Pass raw artifacts and the target skill, not the expected answer or prior
diagnosis. Compare outputs against the behavioral contract. A test passes only
when the observable result satisfies the requirement; a persuasive
explanation is not evidence by itself.

## Freeze And Chronology

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

## Cost And Side Effects

If forward-testing could modify live systems, consume meaningful money, take a
long time, or require new permissions, request approval first.

Record each case as [evidence-binding.md](evidence-binding.md) requires.
