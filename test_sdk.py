"""Run the actual SDK loop with a scripted model; no API credentials or network."""
import json
import unittest
from unittest.mock import patch

from triage import Order, Policy, decide, summarize_ai_usage
from sdk_agent import make_proposer

try:
    from agents import Model, ModelResponse
    from agents.usage import Usage
    from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


if SDK_AVAILABLE:
    class ScriptedModel(Model):
        def __init__(self, action="MONITOR", call_tools=True, fail=False):
            self.turn = 0
            self.action = action
            self.call_tools = call_tools
            self.fail = fail
            self.inputs = []

        async def get_response(self, *args, **kwargs):
            self.inputs.append(kwargs.get("input", args[1] if len(args) > 1 else None))
            if self.fail:
                raise TimeoutError("Scripted failure")
            self.turn += 1
            if self.turn == 1 and self.call_tools:
                output = [ResponseFunctionToolCall(type="function_call", id="call_" + name,
                          call_id=name, name=name, arguments="{}")
                          for name in ["inspect_order", "inspect_policy"]]
            else:
                text = json.dumps({"action": self.action, "confidence": .95,
                                   "rationale": "Scripted SDK integration test; not model intelligence."})
                output = [ResponseOutputMessage(id="message_1", role="assistant", type="message", status="completed",
                          content=[ResponseOutputText(type="output_text", text=text, annotations=[])])]
            return ModelResponse(output=output, usage=Usage(requests=1, input_tokens=100, output_tokens=20, total_tokens=120), response_id=f"test_{self.turn}")

        async def stream_response(self, *args, **kwargs):
            raise NotImplementedError("Streaming not used in this prototype")
            yield  # Async-generator interface required by the abstract model.


@unittest.skipUnless(SDK_AVAILABLE, "Install requirements-ai.txt for optional SDK integration tests")
class SDKTests(unittest.TestCase):
    def setUp(self):
        self.order = Order("SYNTHETIC", 5, 4, 200, "Late delivery", "COMPLETE", "Standard Class", 1)
        self.policy = Policy()

    def test_sdk_executes_both_tools_and_structured_output(self):
        model = ScriptedModel()
        with patch.dict("os.environ", {}, clear=True):
            proposal = make_proposer(model=model)(self.order, self.policy)
        self.assertEqual(model.turn, 2)
        self.assertEqual(proposal.action, "MONITOR")
        self.assertEqual(decide(self.order, proposal, self.policy, "openai")["final_action"], "MONITOR")
        tool_results = json.dumps(model.inputs[-1])
        self.assertIn("SYNTHETIC", tool_results)
        self.assertIn("max_auto_value", tool_results)

    def test_usage_accumulates_tools_and_final_turn_and_resets_on_failure(self):
        model = ScriptedModel()
        proposer = make_proposer(model=model)
        proposer(self.order, self.policy)
        metadata = proposer.last_metadata
        self.assertEqual(metadata["configured_model"], "ScriptedModel")
        self.assertEqual(metadata["usage"]["requests"], 2)
        self.assertEqual(metadata["usage"]["input_tokens"], 200)
        self.assertEqual(metadata["usage"]["output_tokens"], 40)
        self.assertEqual(metadata["usage"]["total_tokens"], 240)
        model.fail = True
        with self.assertRaises(TimeoutError):
            proposer(self.order, self.policy)
        self.assertIsNone(proposer.last_metadata["usage"])
        summary = summarize_ai_usage([{"ai": metadata}, {"ai": metadata},
                                      {"ai": proposer.last_metadata}])
        self.assertEqual(summary["reported_totals"]["total_tokens"], 480)
        self.assertEqual(summary["orders_with_usage"], 2)
        self.assertEqual(summary["orders_without_usage"], 1)
        self.assertIsNone(summarize_ai_usage([{"ai": proposer.last_metadata}])["reported_totals"])
        json.dumps(summary, allow_nan=False)

    def test_usage_preserved_when_required_tool_check_rejects_output(self):
        proposer = make_proposer(model=ScriptedModel(call_tools=False))
        with self.assertRaises(RuntimeError):
            proposer(self.order, self.policy)
        self.assertEqual(proposer.last_metadata["usage"]["total_tokens"], 120)

    def test_sdk_missing_evidence_tools_is_rejected(self):
        with self.assertRaises(RuntimeError):
            make_proposer(model=ScriptedModel(call_tools=False))(self.order, self.policy)

    def test_sdk_unsafe_recommendation_cannot_bypass_policy(self):
        from dataclasses import replace
        order = replace(self.order, value=1000)
        proposal = make_proposer(model=ScriptedModel())(order, self.policy)
        self.assertEqual(decide(order, proposal, self.policy, "openai")["final_action"], "ESCALATE")

    def test_sdk_failure_propagates_to_host_for_escalation(self):
        with self.assertRaises(TimeoutError):
            make_proposer(model=ScriptedModel(fail=True))(self.order, self.policy)


if __name__ == "__main__":
    unittest.main()
