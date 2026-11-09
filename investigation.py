"""Synthetic shipment investigation; separate from the DataCo historical replay."""
import argparse
import html
import json
import math
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POLICY = {
    'version': 'investigation-1.0',
    'max_value': 500,
    'max_estimated_delay_days': 1,
    'max_evidence_age_minutes': 60,
    'rules': [
        'Only a carrier COLLECTED event can establish carrier collection.',
        'The event must match the shipment, be observed and available by decision time, '
        'be no more than 60 minutes old, and occur after the initial no-collection observation.',
        'Warehouse PREPARED or DISPATCHED alone cannot prove carrier collection.',
        'The latest retrieved carrier event must be COLLECTED; contradictory latest events require review.',
        'MONITOR requires value at most 500, estimated delay from 0 to 1 day, '
        'order status DISPATCHED, and a citation to qualifying retrieved carrier evidence.',
        'Escalate missing, stale, conflicting or unavailable evidence. Do not invent a cause.',
        'All tools and queue actions are simulated. MONITOR does not schedule another check.',
    ],
}


def scenarios():
    """Invented decision-time snapshots, not additions to the DataCo dataset."""
    base = {
        'shipment_id': 'SHIP-001', 'decision_at': '2026-11-08T10:00:00+00:00',
        'value': 200, 'estimated_delay_days': 0.5, 'order_status': 'DISPATCHED',
        'initial_carrier_status': 'NO_COLLECTION_RECORDED',
        'initial_observed_at': '2026-11-08T09:00:00+00:00',
        'carrier': [], 'warehouse': [],
    }
    resolved = deepcopy(base)
    resolved.update(case_id='CASE-RESOLVED', expected_action='MONITOR')
    resolved['carrier'] = [dict(evidence_id='C-001', shipment_id='SHIP-001', source='carrier',
        status='COLLECTED', observed_at='2026-11-08T09:40:00+00:00',
        available_at='2026-11-08T09:42:00+00:00', note='Collection scan recorded.')]
    unresolved = deepcopy(base)
    unresolved.update(case_id='CASE-UNCONFIRMED', expected_action='ESCALATE')
    unresolved['carrier'] = [dict(evidence_id='C-002', shipment_id='SHIP-001', source='carrier',
        status='NO_COLLECTION_RECORDED', observed_at='2026-11-08T09:40:00+00:00',
        available_at='2026-11-08T09:42:00+00:00', note='No collection scan is available.')]
    unresolved['warehouse'] = [dict(evidence_id='W-001', shipment_id='SHIP-001', source='warehouse',
        status='PREPARED', observed_at='2026-11-08T09:30:00+00:00',
        available_at='2026-11-08T09:31:00+00:00', note='Prepared for collection; pickup not confirmed.')]
    return [resolved, unresolved]


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return result


class EvidenceDesk:
    """Tools expose only retrieved evidence and record their results, not model reasoning."""
    def __init__(self, case):
        self.case = case
        self.trace = []
        self.evidence = []
        self.failed = False

    def read(self, source):
        try:
            rows = deepcopy(self.case[source])
            if not isinstance(rows, list):
                raise ValueError('Invalid source response')
            rows = [r for r in rows if timestamp(r['available_at']) <= timestamp(self.case['decision_at'])]
            # Source identity comes from the adapter, not a free-text record field.
            for r in rows:
                r['source'] = source
            self.evidence.extend(r for r in rows if r not in self.evidence)
            result = {'source': source, 'evidence': rows}
        except Exception as exc:
            self.failed = True
            result = {'source': source, 'error_type': type(exc).__name__, 'evidence': []}
        self.trace.append({'step': len(self.trace) + 1, 'tool': 'inspect_' + source, 'result': result})
        return result


def qualifying_collection(case, evidence):
    """Authority stays in code; only retrieved, time-correct carrier facts qualify."""
    try:
        now = timestamp(case['decision_at'])
        start = timestamp(case['initial_observed_at'])
        if start > now or case['order_status'] != 'DISPATCHED':
            return None
        for key, maximum in [('value', POLICY['max_value']),
                             ('estimated_delay_days', POLICY['max_estimated_delay_days'])]:
            value = case[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
                return None
        carrier = [r for r in evidence if r['source'] == 'carrier']
        if not carrier or any(r['shipment_id'] != case['shipment_id'] for r in carrier):
            return None
        ids = [r['evidence_id'] for r in evidence]
        if len(ids) != len(set(ids)):
            return None
        for r in carrier:
            if not timestamp(r['observed_at']) <= timestamp(r['available_at']) <= now:
                return None
        latest_at = max(timestamp(r['observed_at']) for r in carrier)
        latest = [r for r in carrier if timestamp(r['observed_at']) == latest_at]
        if any(r['status'] != 'COLLECTED' for r in latest):
            return None
        if latest_at <= start or not 0 <= (now - latest_at).total_seconds() <= 60 * POLICY['max_evidence_age_minutes']:
            return None
        return latest[0]['evidence_id']
    except (KeyError, TypeError, ValueError):
        return None


def enforce(case, proposal, desk, error=None):
    citation = qualifying_collection(case, desk.evidence)
    action, reason = 'ESCALATE', 'Collection is not confirmed by qualifying retrieved carrier evidence.'
    if error or desk.failed:
        reason = 'Investigation encountered an error; human review required.'
    elif not isinstance(proposal, dict) or proposal.get('action') not in {'MONITOR', 'ESCALATE'}:
        reason = 'Invalid proposal; human review required.'
    elif (not isinstance(proposal.get('evidence_ids'), list)
          or any(not isinstance(i, str) for i in proposal['evidence_ids'])
          or not set(proposal['evidence_ids']).issubset({r['evidence_id'] for r in desk.evidence})):
        reason = 'Proposal cites unavailable or invalid evidence; human review required.'
    elif proposal['action'] == 'ESCALATE':
        reason = 'Investigator requested human review; collection has not been accepted for monitoring.'
    elif citation and citation in proposal['evidence_ids']:
        action, reason = 'MONITOR', 'Recent carrier collection evidence resolves the initial discrepancy; limits are met.'
    elif citation:
        reason = 'Proposal did not cite the required collection evidence.'
    return {'final_action': action, 'reason': reason}


def scripted_proposal(case, desk):
    """Transparent deterministic comparison, not AI. Adapt tool order to the evidence."""
    desk.read('carrier')
    citation = qualifying_collection(case, desk.evidence)
    if citation:
        return {'action': 'MONITOR', 'evidence_ids': [citation],
                'rationale': 'Scripted: recent collection scan meets the monitoring policy.'}
    desk.read('warehouse')
    return {'action': 'ESCALATE', 'evidence_ids': [r['evidence_id'] for r in desk.evidence],
            'rationale': 'Scripted: available evidence does not establish permitted monitoring.'}


def investigate(case, mode='scripted', model=None):
    desk = EvidenceDesk(case)
    proposal, error = None, None
    metadata = {'configured_model': None, 'usage': None}
    try:
        if mode == 'openai':
            from investigation_agent import propose
            proposal = propose(case, desk, metadata, model=model)
        else:
            proposal = scripted_proposal(case, desk)
    except Exception as exc:
        error = type(exc).__name__
    decision = enforce(case, proposal, desk, error)
    return {
        'case_id': case['case_id'], 'mode': mode, 'synthetic': True, 'simulation_only': True,
        'initial_evidence': {k: v for k, v in case.items() if k not in {'carrier', 'warehouse', 'expected_action'}},
        'policy': deepcopy(POLICY), 'tool_trace': desk.trace, 'proposal': proposal,
        'ai': metadata, 'agent_error_type': error, **decision,
        'expected_action': case['expected_action'],
        'matches_developer_expectation': decision['final_action'] == case['expected_action'],
        'immediate_escalation_baseline': 'ESCALATE',
        'queue_entry': {'case_id': case['case_id'], 'shipment_id': case['shipment_id'],
                        'queue': 'simulated_monitoring' if decision['final_action'] == 'MONITOR' else 'human_review',
                        'simulated': True, 'scheduled_recheck': False},
    }


def write_outputs(output, records):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'investigations.jsonl').write_text(''.join(json.dumps(r, allow_nan=False) + '\n' for r in records))
    (output / 'queues.jsonl').write_text(''.join(json.dumps(r['queue_entry']) + '\n' for r in records))
    cards = []
    for r in records:
        steps = ''.join('<li><b>' + html.escape(t['tool']) + '</b><pre>' +
                        html.escape(json.dumps(t['result'], indent=2)) + '</pre></li>' for t in r['tool_trace'])
        cards.append('<section><h2>' + html.escape(r['case_id']) + ' → ' + r['final_action'] + '</h2><p>' +
                     html.escape(r['reason']) + '</p><h3>Starting information</h3><pre>' +
                     html.escape(json.dumps(r['initial_evidence'], indent=2)) + '</pre><h3>Tools used, in order</h3><ol>' +
                     steps + '</ol><h3>Proposal</h3><pre>' + html.escape(json.dumps(r['proposal'], indent=2)) +
                     '</pre><details><summary>Full audit record</summary><pre>' +
                     html.escape(json.dumps(r, indent=2)) + '</pre></details></section>')
    mode = records[0]['mode'] if records else 'empty'
    (output / 'report.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Shipment investigation</title>
<style>body{font:17px/1.6 system-ui;background:#f3f5f4;color:#19332e;max-width:960px;margin:auto;padding:24px}
section{background:white;border:1px solid #cbd6d1;border-radius:12px;padding:24px;margin:24px 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f1;padding:12px;font-size:14px}h1,h2{line-height:1.3}</style>
<h1>Shipment investigation</h1><p>Mode: <b>''' + mode + '''</b>. Fictional sources and simulated queue actions.
Scripted mode uses fixed logic, not a live AI. There are no real notifications or scheduled rechecks.</p>
<p>The initial mismatch triggers investigation. A recent carrier collection scan may resolve it;
warehouse preparation alone cannot. Expected outcomes are developer-defined examples, not business validation.</p>''' + ''.join(cards) + '</html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['scripted', 'openai'], default='scripted')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs')
    args = parser.parse_args()
    if args.mode == 'openai':
        from investigation_agent import check_configuration
        check_configuration()
    records = [investigate(case, args.mode) for case in scenarios()]
    output = args.output / ('investigation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    write_outputs(output, records)
    for r in records:
        print(r['case_id'], '→', r['final_action'], '| tools:', ', '.join(t['tool'] for t in r['tool_trace']))
    print('Mode:', args.mode, '| All scenarios and actions are simulated.')
    print('Open report:', output / 'report.html')


if __name__ == '__main__':
    main()
