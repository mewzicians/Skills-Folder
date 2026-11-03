# Audit Modes

Read this when choosing an audit mode or checking a full audit's final
response.

## Select The Mode

- **Quick check:** run structural validation and report obvious gaps.
- **Practical audit:** run structural validation and the strict static audit,
  state the Skill Mission and a brief seven-clause contract, read every
  required resource, run the triggering prompt set when auto-dispatch is
  available, and forward-test one or two realistic tasks. Report findings, a
  short requirement matrix, and each gate that didn't run. Its readiness
  verdict is at most `Structurally Valid` unless the evidence for a higher
  level, as `readiness-levels.md` defines it, was actually gathered; it is
  not `Behaviorally Tested` on fewer cases than that gate requires.
- **Full audit:** reconstruct intent, inspect every required resource, test
  triggering and instructions, and produce an evidence matrix.
- **Repair:** perform the full audit, edit the skill and its metadata, then
  rerun structural and behavioral tests.
- **Regression:** preserve an approved behavior while checking a proposed
  update against prior successes and edge cases.

Default to a practical audit when the user asks to find gaps. Use a full audit
when they ask whether a skill will produce exactly what they want, ask for a
readiness verdict, or the audit is a self-audit or must be independently
trustworthy. Only repair mode edits the target;
an audit-only request leaves it unchanged.

## Full-Audit Completion Gate

Treat any request to judge exactness or readiness as a full audit unless the
user explicitly asks for a quick or practical check.
This includes semantic-only audits where execution is unavailable.

Before sending the final response, verify that it contains findings, the
skill's exact mission and non-goals, the reconstructed behavioral contract, a
requirement matrix, test status, repairs, capability recommendations, an
independence statement, and a calibrated readiness verdict. The presentation
may combine or reorder sections when that improves clarity, but it may not
omit the matrix, evidence provenance, unrun tests, independence limits, or
final readiness judgment.
