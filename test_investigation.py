import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from investigation import EvidenceDesk, enforce, investigate, qualifying_collection, scenarios, write_outputs
from test_sdk import SDK_AVAILABLE

if SDK_AVAILABLE:
    from test_sdk import ScriptedModel
    from agents import ModelResponse
    from agents.usage import Usage
    from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

    class InvestigationModel(ScriptedModel):
        """Scripted tool requests exercise the actual SDK; not model intelligence."""
        def __init__(self, resolved=True, skip=False, fail=False):
            super().__init__(fail=fail)
            self.resolved, self.skip = resolved, skip

        async def get_response(self, *args, **kwargs):
            self.inputs.append(kwargs.get('input', args[1] if len(args) > 1 else None))
            if self.fail:
                raise TimeoutError('Simulated provider failure')
            self.turn += 1
            tool = None
            if not self.skip:
                if self.turn == 1:
                    tool = 'inspect_carrier'
                elif self.turn == 2 and not self.resolved:
                    tool = 'inspect_warehouse'
            if tool:
                output = [ResponseFunctionToolCall(type='function_call', id='call_' + tool,
                          call_id=tool, name=tool, arguments='{}')]
            else:
                proposal = {'action': 'MONITOR' if self.resolved else 'ESCALATE',
                            'evidence_ids': ['C-001'] if self.resolved else ['C-002', 'W-001'],
                            'rationale': 'Scripted SDK test.'}
                output = [ResponseOutputMessage(id='answer', role='assistant', type='message', status='completed',
                          content=[ResponseOutputText(type='output_text', text=json.dumps(proposal), annotations=[])])]
            return ModelResponse(output=output, usage=Usage(requests=1, input_tokens=100,
                                 output_tokens=20, total_tokens=120), response_id='test_' + str(self.turn))


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.case = scenarios()[0]
        self.proposal = {'action': 'MONITOR', 'evidence_ids': ['C-001'], 'rationale': 'Test'}

    def test_two_paths_and_tool_order(self):
        resolved, unresolved = [investigate(c) for c in scenarios()]
        self.assertEqual(resolved['final_action'], 'MONITOR')
        self.assertEqual([t['tool'] for t in resolved['tool_trace']], ['inspect_carrier'])
        self.assertEqual(unresolved['final_action'], 'ESCALATE')
        self.assertEqual([t['tool'] for t in unresolved['tool_trace']], ['inspect_carrier', 'inspect_warehouse'])
        self.assertFalse(resolved['queue_entry']['scheduled_recheck'])

    def test_no_tool_or_fabricated_citation_cannot_monitor(self):
        desk = EvidenceDesk(self.case)
        self.assertEqual(enforce(self.case, self.proposal, desk)['final_action'], 'ESCALATE')
        desk.read('carrier')
        for ids in [['made-up'], [], 'C-001', [42]]:
            proposal = dict(self.proposal, evidence_ids=ids)
            self.assertEqual(enforce(self.case, proposal, desk)['final_action'], 'ESCALATE')

    def test_warehouse_cannot_impersonate_carrier(self):
        case = scenarios()[1]
        case['warehouse'][0].update(source='carrier', status='COLLECTED', evidence_id='C-001')
        desk = EvidenceDesk(case)
        desk.read('warehouse')
        self.assertEqual(enforce(case, self.proposal, desk)['final_action'], 'ESCALATE')

    def test_future_information_not_exposed(self):
        self.case['carrier'][0]['available_at'] = '2026-11-08T10:01:00+00:00'
        desk = EvidenceDesk(self.case)
        self.assertEqual(desk.read('carrier')['evidence'], [])
        self.assertEqual(enforce(self.case, self.proposal, desk)['final_action'], 'ESCALATE')

    def test_stale_wrong_shipment_and_invalid_timing_rejected(self):
        changes = [dict(observed_at='2026-11-08T08:30:00+00:00'),
                   dict(shipment_id='OTHER'), dict(observed_at='2026-11-08T10:05:00+00:00'),
                   dict(observed_at='not-a-date')]
        for update in changes:
            case = deepcopy(self.case)
            case['carrier'][0].update(update)
            desk = EvidenceDesk(case)
            desk.read('carrier')
            self.assertEqual(enforce(case, self.proposal, desk)['final_action'], 'ESCALATE')

    def test_later_conflicting_event_and_duplicate_ids_rejected(self):
        for duplicate in (False, True):
            case = deepcopy(self.case)
            other = dict(case['carrier'][0], evidence_id='C-001' if duplicate else 'C-OTHER',
                         status='NO_COLLECTION_RECORDED', observed_at='2026-11-08T09:45:00+00:00',
                         available_at='2026-11-08T09:46:00+00:00')
            case['carrier'].append(other)
            desk = EvidenceDesk(case)
            desk.read('carrier')
            self.assertEqual(enforce(case, self.proposal, desk)['final_action'], 'ESCALATE')

    def test_operating_limits_and_missing_data(self):
        for update in [dict(value=501), dict(estimated_delay_days=2), dict(value=None),
                       dict(value=float('nan')), dict(order_status='CANCELED')]:
            case = dict(self.case, **update)
            desk = EvidenceDesk(case)
            desk.read('carrier')
            self.assertEqual(enforce(case, self.proposal, desk)['final_action'], 'ESCALATE')

    def test_failure_prevents_monitoring_even_with_good_evidence(self):
        case = dict(self.case, warehouse=None)
        desk = EvidenceDesk(case)
        desk.read('carrier')
        desk.read('warehouse')
        self.assertTrue(desk.failed)
        self.assertEqual(enforce(case, self.proposal, desk)['final_action'], 'ESCALATE')

    def test_conservative_escalation_and_invalid_action(self):
        desk = EvidenceDesk(self.case)
        desk.read('carrier')
        for action in ['ESCALATE', 'REFUND']:
            self.assertEqual(enforce(self.case, dict(self.proposal, action=action), desk)['final_action'], 'ESCALATE')

    def test_saved_audit_queues_and_html_escaping(self):
        case = deepcopy(self.case)
        case['carrier'][0]['note'] = '<script>alert(1)</script>'
        record = investigate(case)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            write_outputs(out, [record])
            saved = json.loads((out / 'investigations.jsonl').read_text())
            self.assertEqual(saved['tool_trace'][0]['result']['evidence'][0]['evidence_id'], 'C-001')
            self.assertEqual(json.loads((out / 'queues.jsonl').read_text())['queue'], 'simulated_monitoring')
            report = (out / 'report.html').read_text()
            self.assertNotIn('<script>alert(1)</script>', report)
            self.assertIn('&lt;script&gt;', report)


@unittest.skipUnless(SDK_AVAILABLE, 'Optional SDK not installed')
class InvestigationSDKTests(unittest.TestCase):
    def test_real_sdk_tool_loop_branches_and_hides_expected_answers(self):
        for case, resolved in zip(scenarios(), [True, False]):
            model = InvestigationModel(resolved=resolved)
            record = investigate(case, mode='openai', model=model)
            self.assertEqual(record['final_action'], case['expected_action'])
            self.assertIsNone(record['agent_error_type'])
            self.assertEqual(model.turn, 2 if resolved else 3)
            self.assertEqual(record['ai']['usage']['total_tokens'], 120 * model.turn)
            self.assertNotIn('expected_action', json.dumps(model.inputs))
            self.assertIn('C-001' if resolved else 'W-001', json.dumps(model.inputs[-1]))

    def test_skipped_tools_cannot_authorize_monitoring(self):
        record = investigate(scenarios()[0], mode='openai', model=InvestigationModel(skip=True))
        self.assertEqual(record['final_action'], 'ESCALATE')
        self.assertEqual(record['tool_trace'], [])

    def test_provider_failure_logged_without_error_message(self):
        record = investigate(scenarios()[0], mode='openai', model=InvestigationModel(fail=True))
        self.assertEqual(record['final_action'], 'ESCALATE')
        self.assertEqual(record['agent_error_type'], 'TimeoutError')
        self.assertIsNone(record['ai']['usage'])
        self.assertNotIn('Simulated provider failure', json.dumps(record))


if __name__ == '__main__':
    unittest.main()
