---
name: game-balance-lab
description: Analyze game balance with rules-faithful simulation, legal policy audits, telemetry, ablations, uncertainty, and human evidence. Use for difficulty, win rates, economies, progression curves, builds, content power, encounters, rewards, or whether a mechanic is too strong or weak.
---

# Game Balance Lab

Read repository guidance, [references/project-profile.md](references/project-profile.md), current implementation, decision status, and relevant playtest evidence. Record the exact candidate version and label proposed values as experiments.

## Validate The Instrument

Before trusting telemetry, prove automated policies obey legal information, actions, costs, limits, exclusions, timing, randomness, and resolution order, and can actually use every compared strategy. Treat policy-rule mismatch as a blocker.

## Experiment

Define the question, hypothesis, population, metrics, decision threshold, baseline, and controlled ablations. Prefer paired fixed seeds. Report sample size and uncertainty. Keep human evidence separate from scripted-policy evidence.

Measure the whole curve: success/failure by stage, resources, pacing, recovery, economy, exposure, availability, selection, conversion, survivorship, overkill, remaining power, action burden, and outliers. Find the first decisive deficit or excess, not only the final result.

Guard against rare exposure, policy blindness, survivorship bias, conditional samples, and averaging away exciting high-rolls. Protect distinct option identities and viable tradeoffs.

Report evidence, policy legality, confidence, structural problems, watchpoints, competing explanations, and smallest next experiments. Recommendations remain draft until explicitly approved; do not edit values during analysis.
