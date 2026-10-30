# Verification record

Run date: 30 October 2026. All operational actions were simulated.

## Full DataCo v3 offline replay

Source SHA-256: `fa6d022ed437155e1a2f0378710602848703c8a7f203f7ff5d77805bf8480aa6`.

| Measure | Count |
|---|---:|
| CSV order-item rows | 180,519 |
| Distinct orders processed | 65,752 |
| Missing order-ID rows | 0 |
| Simulated monitoring | 8,155 |
| Human review | 30,748 |
| No action | 26,849 |
| Agent failures | 0 (no model calls in offline mode) |

Configuration: policy v1.0, maximum auto-monitor delay 1 day, maximum auto-monitor value 500 dataset monetary units, minimum evidence completeness 1.0, minimum proposal confidence 0.90. All distinct orders were processed. The seed changes display order, not the full-population routing counts.

These are **policy-routing counts**. The offline proposal mirrors the policy deterministically. Agreement is true by construction. No accuracy, cost saving, reduction in workload, prediction skill, confidence calibration, or business-value conclusion follows from these counts.

## Automated verification

**20 tests passed** in the project environment (Python 3.12, OpenAI Agents SDK 0.24.0):

- 16 core tests: policy limits, incomplete and contradictory evidence, status handling, confidence boundaries, invalid proposals and numeric values, agent errors, item aggregation, duplicate/missing identifiers, privacy exclusions, and HTML escaping.
- 4 optional SDK tests: real SDK tool execution and structured output with a scripted model, required tool-call enforcement, unsafe recommendation rejection, and failure propagation.

Without the optional dependencies, the four SDK tests are skipped and the 16 core tests still run with Python's standard library.

The generated full-dataset report was also checked in a browser: 120 balanced example rows displayed, the Monitor filter returned 40 examples, an unmatched search returned zero rows, and a 390-pixel viewport had no page overflow. The full audit was checked for exactly one decision and queue event per distinct order and an exact match to the retained-field allowlist.

## What remains untested

The optional integration has not been exercised against a live OpenAI model because no API key is configured. The scripted model verifies SDK plumbing, not AI reasoning. A live smoke test on five synthetic cases is the next step.

An operational evaluation needs decision-time data snapshots, expert-labelled acceptable actions, independently held-out cases, a deterministic baseline, and measures of unsafe auto-actions, escalation quality, coverage, latency and cost. The source data does not provide ground-truth triage actions or verified material criticality.
