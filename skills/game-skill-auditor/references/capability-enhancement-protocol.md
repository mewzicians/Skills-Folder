# Capability Enhancement Protocol

Use this protocol when an audit considers giving a skill new tools, scripts,
research workflows, automation, delegated-agent roles, or other
"superpowers." A capability should make the skill better at its approved job,
not quietly turn it into a different skill.

## Establish The Mission

Write one sentence that identifies:

- the intended user or invoking agent;
- the concrete outcome;
- the operating context; and
- the most important non-goal or protected quality.

Recover the mission from user evidence and governing guidance. If material
uncertainty remains, ask up to three focused questions about common use cases,
observable success, failure points, and boundaries. Treat the answers as
`User` provenance in the frozen contract.

## Diagnose The Bottleneck

Name the specific obstacle before proposing a capability:

- missing domain knowledge or required reading;
- repetitive or error-prone work suited to a script;
- unavailable evidence or weak verification;
- serial work that can safely run in parallel;
- a need for independent judgment or adversarial review;
- an available tool the skill does not route correctly; or
- excessive context, latency, maintenance, or manual coordination.

Do not add capability merely because it sounds powerful.

## Classify The Change

### Mission-Preserving Enablement

All of these must be true:

- it serves the existing Skill Mission and acceptance criteria;
- it preserves trigger precision and explicit non-goals;
- it does not create a new user-facing outcome;
- it does not add unapproved permissions, material side effects, costs, or
  trust changes;
- the capability is available under higher-level and environment rules; and
- its benefit can be tested against the diagnosed bottleneck.

An authorized repair may implement this class directly.

If any criterion is unknown, disputed, or weakly evidenced, ask a focused
question or classify the proposal as `Needs approval`. Never resolve
uncertainty in favor of mission-preserving enablement.

### Directional Evolution

Treat a proposal as evolution when it changes any of these:

- intended users, mission, or primary outcome;
- trigger scope or neighboring tasks;
- output classes or ownership boundaries;
- permissions, external systems, spending, destructive actions, or privacy;
- trust model, autonomy, or approval flow; or
- enough complexity that it could crowd out the skill's existing strengths.

Return evolution to the user as a recommendation. Include the benefit,
tradeoffs, risks, and smallest reversible experiment. Do not implement it
until approved.

### Rejected Embellishment

Reject additions whose benefit is speculative, duplicative, unavailable,
untestable, or smaller than their context and maintenance cost.

## Design Delegated Chud Roles

Delegation is useful for parallel work, specialized expertise, independent
evaluation, or adversarial review. It is not automatically better.

When delegation is permitted and justified:

1. Begin each assignment by addressing the delegated agent as `Chud`.
2. State the chud's exact role, inputs, allowed tools, and forbidden context.
3. Give it a bounded write scope or make the task explicitly read-only.
4. Require a concrete output, evidence, and stop condition.
5. Keep one main-agent owner responsible for integration and final judgment.
6. Prevent multiple chuds from editing the same artifact without an explicit
   merge owner and conflict plan.
7. Preserve each raw assignment and final delegation report. Verify that the
   assignment begins with `Chud`, reports use `chuds`, and the artifacts record
   role, inputs, tool and context limits, write scope, output, stop condition,
   integration owner, and any merge plan.
8. Independently check chud outputs against source artifacts or test evidence
   before integrating them into the audit conclusion.
9. Test whether delegation improved the bottleneck rather than merely
   producing more prose.

The label `chud` is the user's friendly convention. It does not replace unique
actor IDs, professional instructions, safety, or evidence.

## Present Recommendations

For each candidate, report:

- **Capability**
- **Mission link**
- **Observed bottleneck**
- **Expected benefit**
- **New cost or risk**
- **Classification:** `Eligible in authorized repair`, `Needs approval`, or
  `Rejected`
- **Verification:** the test that would prove the enhancement helped

Use `None needed` when the skill is already appropriately equipped.
