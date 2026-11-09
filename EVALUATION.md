# Verification record

Offline verification: 30 October 2026. Live smoke tests: 7 November 2026. All operational actions were simulated.

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

## Live AI smoke tests — 7 November 2026

The user ran the existing OpenAI mode with `OPENAI_MODEL=gpt-5-mini`. The saved summaries and decision records were inspected locally. The model name comes from the terminal setup in the session: the audit format used for those runs did not save the configured model name or resolved model version. New runs now record the configured name, but not a resolved version.

| Run ID | Orders processed | Monitor | Human review | No action | Recorded agent failures |
|---|---:|---:|---:|---:|---:|
| `20261107T181349Z-42802bab` | 5 | 0 | 3 | 2 | 0 |
| `20261107T213402Z-63e7d391` | 10 | 1 | 7 | 2 | 0 |

Both runs used policy v1.0 and the bundled synthetic CSV, with source SHA-256 `41ad320928d3c3529352471bd89e5c8b963712b9961d3e1bfbcfa6f981d9d3ce`. These are 15 order evaluations across 10 distinct fictional orders, not 15 independent cases. The five-order sample is included in the ten-order run.

Every saved proposal action matched its final action in these runs. The ten-order totals also match the synthetic fixture's expected policy routing. DEMO-001 received a MONITOR proposal with self-reported confidence 0.92, which the policy gate accepted. No policy override occurred in these runs; rejection of unsafe proposals is covered separately by automated tests.

The SDK adapter requires both evidence tools to execute before returning a proposal. All 15 records contain successful proposals without recorded agent errors. Detailed tool-call traces, model-version metadata, token usage and cost were not saved. Raw run files remain local under `runs/` and are excluded from Git; this document records the reviewed results without publishing credentials or local logs.

These smoke tests demonstrate that the live model connection, structured recommendations and policy gate worked on these examples. They do not establish calibrated confidence, broad reliability, operational effectiveness or performance on the full DataCo dataset. Live model calls do not change the meaning of `simulation_only`: queue actions are still local simulations, with no real notifications, shipment changes or scheduled rechecks.

## What remains untested

An operational evaluation needs decision-time data snapshots, expert-labelled acceptable actions, independently held-out cases, a deterministic baseline, and measures of unsafe auto-actions, escalation quality, coverage, latency and cost. The source data does not provide ground-truth triage actions or verified material criticality.

## Usage logging verification

After adding model and usage metadata, all 22 automated tests passed locally. Two added scripted-SDK tests verify multi-turn token accumulation, summary totals, unavailable usage after failure without reuse of a preceding order's counts, and usage retention when the required-tool check rejects an answer. No paid model calls were made to validate this change. Earlier live smoke-test records remain unchanged.

## Separate investigation demo — 8 November 2026

Added two fictional decision-time shipment scenarios and a separate optional live investigator. The scripted run produces CASE-RESOLVED → MONITOR after carrier inspection, and CASE-UNCONFIRMED → ESCALATE after carrier and warehouse inspection. All 35 automated tests passed (22 existing plus 13 investigation tests), including actual SDK execution with scripted models. No paid calls were made for this addition. See INVESTIGATION.md for policy definitions and comparison limits; no new live-model or business-effectiveness results are claimed.

## Live investigation review and challenge extension — 8 November 2026

Reviewed local run `investigation-20261108T222931Z-379fb62f` with configured model `gpt-5-mini`:

| Case | Tools, in execution order | Proposal / final action | Model requests | Total tokens |
|---|---|---|---:|---:|
| CASE-RESOLVED | Carrier | MONITOR / MONITOR | 2 | 2,279 |
| CASE-UNCONFIRMED | Carrier, warehouse | ESCALATE / ESCALATE | 3 | 3,488 |

Neither case recorded an agent error. The proposals cited retrieved evidence, and the final actions matched the developer-defined expected outcomes. These are two fictional cases and do not establish superiority to the scripted investigator or operational effectiveness.

Subsequently added three runnable challenges: stale scan, wrong shipment and unavailable carrier. Scripted runs escalate all three, with one intentional source timeout and zero agent errors. All 39 automated tests pass, including deliberate unsafe recommendations through the actual SDK with scripted models. The subsequent live challenge run is recorded below. No paid calls were made while implementing it. Original live run records remain unchanged.

## Live challenge review — 8 November 2026

Reviewed local run `investigation-20261108T224752Z-82e592dc` with configured model `gpt-5-mini`.

| Case | AI proposal | Final action | Requests | Total tokens |
|---|---|---|---:|---:|
| CASE-STALE-SCAN | ESCALATE | ESCALATE | 2 | 2,346 |
| CASE-WRONG-SHIPMENT | ESCALATE | ESCALATE | 3 | 2,780 |
| CASE-CARRIER-UNAVAILABLE | ESCALATE | ESCALATE | 3 | 2,754 |

All three proposals cited retrieved evidence and matched the configured expected outcomes. Each invoked both carrier and warehouse tools. There were zero recorded agent failures and one deliberate carrier-source timeout. No unsafe proposal was overridden in this live run: the model itself proposed escalation in each case. Tool traces record execution order, not necessarily separate model turns (both tools can be requested together). These small developer-defined tests establish behaviour on the fixtures, not policy validity or business effectiveness. Raw run records remain local and ignored by Git.
