"""Run the actual SDK loop with a scripted model; no API credentials or network."""
import json
import unittest
from unittest.mock import patch

from triage import Order, Policy, decide
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
            return ModelResponse(output=output, usage=Usage(), response_id=f"test_{self.turn}")

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
