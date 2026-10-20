# Audit Modes

Read this when choosing an audit mode or checking a full audit's final
response.

## Select The Mode

- **Quick check:** run structural validation and report obvious gaps.
- **Full audit:** reconstruct intent, inspect every required resource, test
  triggering and instructions, and produce an evidence matrix.
- **Repair:** perform the full audit, edit the skill and its metadata, then
  rerun structural and behavioral tests.
- **Regression:** preserve an approved behavior while checking a proposed
  update against prior successes and edge cases.

Default to a full audit when the user asks to find gaps or determine whether a
skill will produce exactly what they want. Only repair mode edits the target;
an audit-only request leaves it unchanged.

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
