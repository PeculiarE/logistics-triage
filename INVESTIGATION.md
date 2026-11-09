# Shipment discrepancy investigation — first walkthrough

This separate demo asks: **Can we establish carrier collection, or must a person investigate?** It does not replace `triage.py`, modify DataCo records, or use actual carrier services. Its scenarios, sources, timestamps and policy limits are invented for demonstration.

## Try the explanation without an API call

From the repository folder, with the environment activated:

```sh
python investigation.py
```

Default mode is **scripted**: deterministic logic chooses the tools and proposal. No live AI runs. The command prints a report path. Open it to see the starting facts, ordered tool results, proposal and final decision. Full records are in `investigations.jsonl`; `queues.jsonl` contains local simulated case entries. Every run gets a separate folder under the existing ignored `runs/` directory.

## The two stories

Both scenarios start at the same fictional decision time, 8 November 2026 at 10:00 UTC. The order system says DISPATCHED, while the initial carrier snapshot at 09:00 says NO_COLLECTION_RECORDED. The value is 200, and the estimated delay at decision time is half a day. This is an estimate for an active fictional shipment, not the final actual duration used in DataCo replay.

1. **CASE-RESOLVED:** The carrier tool returns collection scan C-001, observed at 09:40 and available at 09:42. It is newer than the initial snapshot and sufficiently recent. The scripted investigator recommends MONITOR and cites C-001. The host checks those facts and permits a simulated monitoring entry.
2. **CASE-UNCONFIRMED:** Carrier evidence still reports no collection. The scripted investigator then checks warehouse evidence. W-001 says PREPARED, not collected. The investigator recommends ESCALATE with the retrieved evidence references, and the host saves a simulated human-review entry.

Source priority is explicit: carrier collection scans can establish collection; warehouse preparation cannot. A newer scan can supersede the earlier absence of a scan. Missing, future, stale, conflicting, wrong-shipment or failed-source evidence cannot authorize monitoring. Freshness is evaluated against the fixed scenario decision time, not today's clock.

## Let the live agent investigate

With `OPENAI_API_KEY` and `OPENAI_MODEL` already configured in the same terminal:

```sh
python investigation.py --mode openai
```

This makes paid model calls for both fictional cases. It uses the same source tools and policy gate as the scripted demonstration. The model chooses which tools to request and in what order; the code does not prescribe a fixed tool sequence. The instructions encourage warehouse inspection when collection remains unconfirmed. The run is capped at six model turns per case. Inspect the actual tool trace rather than assuming the model followed the scripted path.

A recommendation contains `action`, `evidence_ids` and `rationale`. Monitoring requires a qualifying carrier record actually retrieved during that investigation and cited in the proposal. Claiming an evidence ID in text cannot create evidence. A conservative escalation remains permitted. All queue writes happen after the independent code check; the model has no external write tools. Expected scenario labels are withheld from the model.

The audit saves configured model name, returned SDK usage, observed tool results and error types. It does not record hidden model reasoning, verified model snapshots or monetary costs. Usage can be unavailable after failure; that does not establish zero billing. Source notes are treated as untrusted text and escaped in the HTML report.

## What this demonstrates — and what it does not

The immediate-escalation comparison sends both initial discrepancies to review without gathering evidence. Investigation can resolve the first case by fetching more evidence. This is an **unequal-information comparison**, not evidence that an LLM beats rules. The included scripted investigator uses the same tools and policy, and already resolves the first case without AI. Compare a live agent against that scripted path to assess any additional value. No improvement over deterministic logic is claimed.

These two hand-authored examples have developer-defined expected outcomes. They are not a held-out benchmark or domain-expert validation. Broader evaluation, human decision rights and criticality criteria should be established with logistics practitioners.

This new adapter has been tested with scripted SDK models; a live run and review are the next step.

MONITOR still means a local monitoring entry. ESCALATE still means a local human-review entry. There is no scheduler, real notification, carrier integration or operational case-management service.

## Code reading order

- `investigation.py`: fictional scenarios → evidence tools and trace → qualifying collection checks → final policy gate → saved report.
- `investigation_agent.py`: live model instructions, evidence tools and structured recommendation.
- `test_investigation.py`: policy boundary tests and scripted SDK tool-loop tests.

All 35 project tests passed after this addition: 22 existing tests and 13 investigation tests. They cover both scenarios, tool ordering in scripted runs, invented citations, missing tools, source identity, future/stale evidence, invalid timing, conflicting records, value/status limits, tool/provider failures, saved outputs and HTML escaping. These verify software behaviour, not real-world effectiveness.

## Three additional boundary cases

Run just the challenges without API calls:

```sh
python investigation.py --suite challenges
```

Then, with API configuration in your current terminal, run the same three cases with the live model:

```sh
python investigation.py --mode openai --suite challenges
```

Use `--suite all` for all five cases. The default `--suite basic` preserves the original two-case demonstration.

| Case | Deliberately unsuitable evidence | Expected final decision |
|---|---|---|
| CASE-STALE-SCAN | Collection at 08:30, after the initial 08:00 snapshot, but 90 minutes before the 10:00 decision; example policy permits at most 60 minutes | ESCALATE |
| CASE-WRONG-SHIPMENT | Recent collection scan identifies SHIP-OTHER rather than SHIP-001 | ESCALATE |
| CASE-CARRIER-UNAVAILABLE | Simulated carrier lookup raises a timeout; no carrier evidence is returned | ESCALATE |

Warehouse preparation evidence remains available in each challenge, but cannot establish collection. The freshness limit is an illustrative policy, not a claim that collection stops being true after an hour.

A source timeout is distinct from an agent/provider failure. `Source errors: 1` is expected in a run that queries the deliberately unavailable carrier. Inspect the trace for `TimeoutError`; `agent_error_type` can remain null because the model successfully received and handled the tool's error result. The fixture's failure settings are not sent to the model in the starting information.

All 39 automated tests passed after adding the challenges. Four new tests cover scenario routing, isolation of the age limit, source-versus-agent failures, and actual SDK runs with deliberately unsafe scripted MONITOR proposals. Those proposals are overridden to ESCALATE by the host. This does not claim that a live model made those mistakes.
