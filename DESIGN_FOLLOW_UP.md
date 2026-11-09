# Design issues to revisit after the interview

Recorded 9 November 2026. This is a follow-up plan, not implemented behaviour or validated business policy.

## Current state to preserve

- Historical DataCo replay and the separate fictional shipment investigator both exist.
- Live triage was reviewed on ten distinct synthetic orders. Live investigation was reviewed on five fictional scenarios under policy investigation-1.0.
- Those five investigation outcomes matched developer-defined expectations. No AI advantage over the scripted investigator has been established.
- Policy investigation-1.1 removes age alone as a reason to reject collection evidence. It has 39 passing automated tests, a scripted walkthrough and reviewed live results for all three challenge cases: old scan MONITOR, other two ESCALATE. Earlier policy 1.0 reports retain their original outcomes.
- All queue actions are simulated. There is no real tracking integration, notification service, scheduler or operational case-management system.

## 1. Separate collection confirmation from the operational decision

**Problem:** A collection scan establishes a past event. It does not establish that delivery is on track or monitoring is sufficient. Current code combines these conclusions.

**Proposed design:** First record collection_status (confirmed, unconfirmed or disputed) and supporting evidence. Separately decide an allowed next action using deadline, latest progress, urgency, source quality and any relevant material criticality. Define missing-evidence behaviour with practitioners rather than inventing production rules.

**Acceptance examples:** A collected shipment progressing toward its deadline can be eligible for monitoring. A collected shipment that threatens a critical deadline may need review. Both retain collection_status=confirmed. Missing operational information does not erase the collection event.

## 2. Handle delayed reporting

**Problem:** The code still requires the collection event to occur after the initial no-collection observation. That rejects some legitimate records that arrive late.

**Example:** Collection occurs at 08:30; the order snapshot still says no collection at 09:00; the scan becomes available at 09:15; a decision is made at 10:00. The scan may resolve an outdated display even though the event predates it.

**Proposed design:** Distinguish event time, record availability time and what the initial observation actually asserts. Absence of a recorded scan is not a verified claim of physical non-collection. Never expose evidence unavailable at decision time.

**Acceptance examples:** The above scan can establish collection at 10:00. It must not be visible to a decision at 09:10. An explicit contradictory record needs a defined reconciliation policy.

## 3. Distinguish normal progress from contradiction

**Problem:** The latest retrieved carrier event must currently be COLLECTED. A later sorting-facility event can cause rejection even though it supports normal progress.

**Proposed design:** Define supported shipment event types and their relationships. Preserve valid collection history while distinguishing subsequent progress, corrections, reversals and unresolved contradictions. Unknown events should not silently establish permission.

**Acceptance examples:** COLLECTED followed by ARRIVED_AT_SORTING_FACILITY retains collection confirmation. A scan explicitly corrected as belonging to another shipment requires reassessment. Conflicting authoritative records require review unless a defined reconciliation rule resolves them.

## 4. Validate source authority and evidence quality

**Problem:** The demo treats carrier records as authoritative once structural checks pass. Real sources can produce duplicates, incorrect associations, corrections or delayed updates.

**Proposed work:** With logistics practitioners, identify source ownership, event identifiers, revision/correction semantics, identity matching, timestamp reliability and what constitutes sufficient proof. Assess what evidence is appropriate for each action's consequences.

**Acceptance examples:** Duplicate ingestion does not count as independent confirmation. Corrected evidence can supersede an earlier record with a retained audit trail. Free-text instructions in records cannot grant permissions. Missing or uncertain source identity prevents unsupported automatic actions.

## 5. Establish whether AI adds value

**Problem:** The existing scripted investigator reaches the same final categories on the demonstration fixtures. Comparing investigation with immediate escalation changes information access and does not isolate AI benefit.

**Proposed evaluation:** Give scripted and AI investigators equal source access and comparable tool budgets. Define acceptable actions before running tests, with practitioner input. Use independent cases, including varied notes and uncertain investigation paths, without choosing cases solely to favour AI. Keep deterministic validation for facts that code can check reliably.

**Measure:** Unacceptable automatic actions, missed and unnecessary escalations, evidence-supported explanations, tool usage, elapsed time and API usage. Investigate confidence calibration before treating self-reported confidence as a probability. Report negative results and use simpler rules when they suffice.

## Suggested order of work

1. Agree the two decision questions and write example timelines before changing code.
2. Define evidence semantics for delayed reports, progress and corrections.
3. Implement and test those rules together; version the policy and keep earlier reports unchanged.
4. Re-run scripted and live comparisons and document which policy each result tested.
5. Add real integrations or continuing case workflows only after the decision and evidence requirements are clear.

No timetable, external integration or production readiness is implied by this plan.
