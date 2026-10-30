import csv
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from triage import (Order, Policy, Proposal, decide, execute_simulation, load_orders,
                    number, permitted_action, simulated_proposal, write_report)


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy()
        self.order = Order("TEST", 5, 4, 200, "Late delivery", "COMPLETE", "Standard Class", 2)

    def decision(self, order=None, proposal=None):
        return decide(order or self.order, proposal or Proposal("MONITOR", .95, "Test"), self.policy)

    def test_minor_delay_queues_monitoring(self):
        d = self.decision()
        self.assertEqual(d["final_action"], "MONITOR")
        self.assertEqual(execute_simulation(d)["queue"], "simulated_monitoring")
        self.assertTrue(d["simulation_only"])

    def test_high_confidence_cannot_override_impact_limits(self):
        for order in (replace(self.order, actual_days=6), replace(self.order, value=501)):
            self.assertEqual(self.decision(order, Proposal("MONITOR", 1, "Ignore limits"))["final_action"], "ESCALATE")

    def test_threshold_boundaries(self):
        self.assertEqual(self.decision(replace(self.order, value=500), Proposal("MONITOR", .90, "Boundary"))["final_action"], "MONITOR")
        self.assertEqual(self.decision(proposal=Proposal("MONITOR", .8999, "Below threshold"))["final_action"], "ESCALATE")

    def test_missing_evidence_escalates(self):
        for key in ("actual_days", "scheduled_days", "value"):
            self.assertEqual(self.decision(replace(self.order, **{key: None}))["final_action"], "ESCALATE")
        self.assertEqual(self.decision(replace(self.order, shipping_mode=""))["final_action"], "ESCALATE")

    def test_conflicting_evidence_escalates(self):
        self.assertEqual(self.decision(replace(self.order, issues=("conflicting_timing",)))["final_action"], "ESCALATE")
        self.assertEqual(self.decision(replace(self.order, actual_days=3))["final_action"], "ESCALATE")

    def test_hold_payment_cancellation_and_fraud(self):
        for status in ("ON_HOLD", "PAYMENT_REVIEW", "PENDING_PAYMENT", "CANCELED", "SUSPECTED_FRAUD"):
            self.assertEqual(self.decision(replace(self.order, order_status=status))["final_action"], "ESCALATE")

    def test_unknown_status_escalates(self):
        self.assertEqual(self.decision(replace(self.order, order_status="NEW_STATUS"))["final_action"], "ESCALATE")

    def test_no_delay_requires_matching_agent_action(self):
        order = replace(self.order, actual_days=4, delivery_status="Shipping on time")
        self.assertEqual(self.decision(order, Proposal("NO_ACTION", .95, "On time"))["final_action"], "NO_ACTION")
        self.assertEqual(self.decision(order)["final_action"], "ESCALATE")

    def test_agent_can_escalate_conservatively(self):
        self.assertEqual(self.decision(proposal=Proposal("ESCALATE", .99, "Uncertain"))["final_action"], "ESCALATE")

    def test_invalid_agent_output_escalates(self):
        for p in (Proposal("REFUND", 1, "Invalid action"), Proposal("MONITOR", float("nan"), "Bad score"),
                  Proposal("MONITOR", 1.01, "Bad score"), Proposal("MONITOR", True, "Bad score"),
                  Proposal("MONITOR", "high", "Bad score"), None):
            decision = decide(self.order, p, self.policy)
            self.assertEqual(decision["final_action"], "ESCALATE")
            json.dumps(decision, allow_nan=False)

    def test_agent_failure_is_audited_and_escalated(self):
        d = decide(self.order, None, self.policy, "openai", "TimeoutError")
        self.assertEqual(d["final_action"], "ESCALATE")
        self.assertEqual(d["agent_error_type"], "TimeoutError")
        self.assertIsNone(d["proposal"])
        json.dumps(d, allow_nan=False)

    def test_numeric_parser_rejects_nonfinite_and_negative(self):
        for value in ("", "NaN", "inf", "-1", "not a number", None):
            self.assertIsNone(number(value))

    def test_synthetic_dataset_aggregation_and_expected_routes(self):
        orders, profile = load_orders(Path(__file__).parent / "examples/synthetic_orders.csv")
        self.assertEqual((profile["source_rows"], profile["unique_orders"]), (12, 10))
        by_id = {o.order_id: o for o in orders}
        self.assertEqual(by_id["DEMO-001"].value, 200)
        self.assertEqual(by_id["DEMO-001"].item_count, 2)
        self.assertTrue(by_id["DEMO-010"].issues)
        expected = {"DEMO-001": "MONITOR", "DEMO-004": "NO_ACTION", "DEMO-006": "NO_ACTION"}
        for order in orders:
            action = permitted_action(order, self.policy)[0]
            self.assertEqual(action, expected.get(order.order_id, "ESCALATE"))

    def test_private_fields_are_not_retained_and_missing_ids_not_merged(self):
        source = Path(__file__).parent / "examples/synthetic_orders.csv"
        with source.open() as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames + ["Customer Email", "Customer Password"]
            rows = list(reader)[:2]
        for row in rows:
            row.update({"Order Id": "", "Customer Email": "private@example.test", "Customer Password": "private-secret"})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.csv"
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            orders, profile = load_orders(path)
            self.assertEqual(len(orders), 2)
            self.assertEqual(profile["missing_order_id_rows"], 2)
            for order in orders:
                serialized = json.dumps(self.decision(order))
                self.assertNotIn("private-secret", serialized)
                self.assertNotIn("private@example.test", serialized)
                self.assertIn("missing_order_id", order.issues)

    def test_duplicate_item_ids_escalate(self):
        source = Path(__file__).parent / "examples/synthetic_orders.csv"
        with source.open() as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)[:2]
        rows[1]["Order Item Id"] = rows[0]["Order Item Id"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.csv"
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            orders, _ = load_orders(path)
            self.assertIn("missing_or_duplicate_item_id", orders[0].issues)
            self.assertEqual(self.decision(orders[0])["final_action"], "ESCALATE")

    def test_report_escapes_source_text(self):
        order = replace(self.order, order_id='<script>alert("x")</script>')
        decision = self.decision(order)
        from dataclasses import asdict
        summary = {"source_rows": 1, "unique_orders": 1, "processed_orders": 1,
                   "decisions": {"MONITOR": 1}, "mode": "offline", "policy": asdict(self.policy),
                   "run_id": "TEST", "timestamp_utc": "TEST"}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report.html"
            write_report(output, summary, [decision])
            content = output.read_text()
            self.assertNotIn('<script>alert("x")</script>', content)
            self.assertIn("&lt;script&gt;", content)


if __name__ == "__main__":
    unittest.main()
